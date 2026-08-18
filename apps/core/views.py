import csv
import calendar
from datetime import date
from decimal import Decimal
from itertools import chain
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.core.exceptions import ValidationError
from django.http import HttpResponse, JsonResponse
from django import forms
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.db.models import Count, DecimalField, Max, Prefetch, Q, Sum, Subquery, Value
from django.db.models.functions import Coalesce, ExtractYear
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.text import slugify
from django.utils.http import url_has_allowed_host_and_scheme
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.agua.models import Toma
from apps.operacion.models import AsistenciaJunta, Faena, Junta, RegistroFaena
from apps.operacion.services import (
    aplicar_filtros_eventos,
    generar_participantes_faena,
    generar_participantes_junta,
)
from apps.tesoreria.models import Cooperacion, Pago
from apps.tesoreria.services import generar_obligaciones_faltantes
from apps.tesoreria.queries import (
    abonos_filtrados,
    aplicar_filtros_obligaciones,
    anotar_conceptos,
    anotar_obligaciones,
    conceptos_filtrados,
    buscar_movimientos_aportaciones,
)
from apps.tesoreria.forms import BuscarAportacionesForm

from .forms import CiudadanoOperativoForm, DashboardFormMixin, FaenaOperativaForm, JuntaOperativaForm
from .models import Ciudadano, Manzana


class EstadoEventoForm(DashboardFormMixin, forms.Form):
    estado = forms.ChoiceField(label="Nuevo estado")

    def __init__(self, *args, choices=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["estado"].choices = choices
        self._apply_dashboard_widgets()


def _ciudadanos_operativos_queryset():
    return Ciudadano.objects.select_related("toma", "manzana").annotate(
        ultimo_pago_fecha=Max("pagos__fecha"),
        adeudos_faena=Count("registros_faena", filter=Q(registros_faena__genera_adeudo=True), distinct=True),
    )


def _anios_antes(fecha, anios):
    """Return a birthday cutoff, including Feb 29 safely."""
    year = fecha.year - anios
    return fecha.replace(year=year, day=min(fecha.day, calendar.monthrange(year, fecha.month)[1]))


def _filtro_edad_efectiva(rango, hoy=None):
    """Build an ORM-only filter, preferring birth date over manual age."""
    hoy = hoy or timezone.localdate()
    sin_fecha = Q(fecha_nacimiento__isnull=True)
    rangos = {
        "menores_18": (0, 17),
        "18_29": (18, 29),
        "30_49": (30, 49),
        "50_64": (50, 64),
        "65_mas": (65, None),
    }
    if rango == "sin_informacion":
        return sin_fecha & Q(edad__isnull=True)
    if rango == "sin_fecha":
        return sin_fecha
    if rango not in rangos:
        return None

    minimo, maximo = rangos[rango]
    fecha_q = Q(fecha_nacimiento__lte=_anios_antes(hoy, minimo))
    manual_q = Q(edad__gte=minimo)
    if maximo is not None:
        # Someone older than maximo+1 has a birth date on or before this cutoff.
        fecha_q &= Q(fecha_nacimiento__gt=_anios_antes(hoy, maximo + 1))
        manual_q &= Q(edad__lte=maximo)
    return fecha_q | (sin_fecha & manual_q)


def _filtrar_ciudadanos_operativos(queryset, params):
    q = params.get("q", "").strip()
    estado = params.get("estado", "todos")
    toma = params.get("toma", "todos")
    adeudo = params.get("adeudo", "todos")
    manzana = params.get("manzana", "todas")
    motivo_alta = params.get("motivo_alta", "todos")
    sexo = params.get("sexo", "todos")
    rango_edad = params.get("rango_edad", "todas")
    fecha_nacimiento = params.get("fecha_nacimiento", "todas")

    if q:
        search_filter = (
            Q(nombre__icontains=q)
            | Q(apellido_paterno__icontains=q)
            | Q(apellido_materno__icontains=q)
            | Q(numero_contrato__icontains=q)
        )
        queryset = queryset.filter(search_filter)

    if estado == "activos":
        queryset = queryset.filter(activo=True)
    elif estado == "inactivos":
        queryset = queryset.filter(activo=False)

    if toma == "con_toma":
        queryset = queryset.filter(toma__isnull=False)
    elif toma == "sin_toma":
        queryset = queryset.filter(toma__isnull=True)

    if adeudo == "con_adeudo":
        queryset = queryset.filter(adeudos_faena__gt=0)
    elif adeudo == "sin_adeudo":
        queryset = queryset.filter(adeudos_faena=0)

    if manzana == "sin_asignar":
        queryset = queryset.filter(manzana__isnull=True)
    elif manzana.isdigit():
        queryset = queryset.filter(manzana_id=int(manzana))

    motivos_validos = {value for value, _label in Ciudadano.MotivosAlta.choices}
    if motivo_alta == "sin_motivo":
        queryset = queryset.filter(Q(motivo_alta="") | Q(motivo_alta__isnull=True))
    elif motivo_alta in motivos_validos:
        queryset = queryset.filter(motivo_alta=motivo_alta)

    sexos_validos = {value for value, _label in Ciudadano.Sexos.choices}
    if sexo in sexos_validos:
        queryset = queryset.filter(sexo=sexo)

    filtro_edad = _filtro_edad_efectiva(rango_edad)
    if filtro_edad is not None:
        queryset = queryset.filter(filtro_edad)

    if fecha_nacimiento == "con_fecha":
        queryset = queryset.filter(fecha_nacimiento__isnull=False)
    elif fecha_nacimiento == "sin_fecha":
        queryset = queryset.filter(fecha_nacimiento__isnull=True)

    ordering = params.get("orden", "nombre")
    orderings = {
        "nombre": ["apellido_paterno", "apellido_materno", "nombre", "pk"],
        "estado": ["-activo", "apellido_paterno", "apellido_materno", "nombre", "pk"],
        "adeudos_faena": ["-adeudos_faena", "apellido_paterno", "apellido_materno", "nombre", "pk"],
        "registro": ["-created_at", "apellido_paterno", "apellido_materno", "nombre", "pk"],
    }
    return queryset.order_by(*orderings.get(ordering, orderings["nombre"]))


@login_required
def padron_ciudadanos(request):
    ciudadanos_qs = _filtrar_ciudadanos_operativos(_ciudadanos_operativos_queryset(), request.GET)
    paginator = Paginator(ciudadanos_qs, 20)
    ciudadanos_page = paginator.get_page(request.GET.get("page"))
    pagination_params = request.GET.copy()
    pagination_params.pop("page", None)

    context = {
        "ciudadanos": ciudadanos_page,
        "filtros": {
            "q": request.GET.get("q", "").strip(),
            "estado": request.GET.get("estado", "todos"),
            "toma": request.GET.get("toma", "todos"),
            "adeudo": request.GET.get("adeudo", "todos"),
            "manzana": request.GET.get("manzana", "todas"),
            "motivo_alta": request.GET.get("motivo_alta", "todos"),
            "sexo": request.GET.get("sexo", "todos"),
            "rango_edad": request.GET.get("rango_edad", "todas"),
            "fecha_nacimiento": request.GET.get("fecha_nacimiento", "todas"),
            "orden": request.GET.get("orden", "nombre"),
        },
        "manzanas": Manzana.objects.filter(Q(activa=True) | Q(ciudadanos__isnull=False)).distinct(),
        "motivos_alta": Ciudadano.MotivosAlta.choices,
        "sexos": Ciudadano.Sexos.choices,
        "motivo_alta_permite_vacio": Ciudadano._meta.get_field("motivo_alta").blank,
        "pagination_querystring": pagination_params.urlencode(),
        "metricas": {
            "total": Ciudadano.objects.count(),
            "activos": Ciudadano.objects.filter(activo=True).count(),
            "inactivos": Ciudadano.objects.filter(activo=False).count(),
            "sin_toma": Ciudadano.objects.filter(toma__isnull=True).count(),
            "sin_manzana": Ciudadano.objects.filter(manzana__isnull=True).count(),
            "activos_sin_manzana": Ciudadano.objects.filter(activo=True, manzana__isnull=True).count(),
            "con_adeudo": RegistroFaena.objects.filter(genera_adeudo=True).values("ciudadano").distinct().count(),
        },
        "crear_ciudadano_url": reverse("crear_ciudadano_operativo"),
        "exportar_ciudadanos_url": reverse("exportar_ciudadanos_csv"),
        "exportar_ciudadanos_querystring": urlencode(
            {key: value for key, value in request.GET.items() if key != "page" and value}
        ),
    }
    if request.headers.get("HX-Request") == "true":
        return render(request, "dashboard/partials/padron_ciudadanos_resultados.html", context)
    return render(request, "dashboard/padron_ciudadanos.html", context)


@login_required
def exportar_ciudadanos_csv(request):
    ciudadanos = _filtrar_ciudadanos_operativos(_ciudadanos_operativos_queryset(), request.GET)
    manzana = request.GET.get("manzana", "todas")
    if manzana == "sin_asignar":
        filename_context = "_sin_manzana"
    elif manzana.isdigit():
        filename_context = f"_manzana_{manzana}"
    else:
        filename_context = ""
    filename = f"ciudadanos{filename_context}_{timezone.localdate().isoformat()}.csv"
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.write("\ufeff")

    writer = csv.writer(response)
    writer.writerow([
        "ID",
        "Nombre",
        "Apellido paterno",
        "Apellido materno",
        "Nombre completo",
        "No. de contrato",
        "Manzana",
        "Fecha de nacimiento",
        "Edad registrada",
        "Edad actual",
        "Sexo",
        "Motivo de alta",
        "Labor social",
        "Estado",
        "Fecha de registro",
    ])

    for ciudadano in ciudadanos:
        writer.writerow([
            ciudadano.pk,
            ciudadano.nombre,
            ciudadano.apellido_paterno,
            ciudadano.apellido_materno,
            ciudadano.nombre_completo,
            ciudadano.numero_contrato or "",
            ciudadano.manzana.nombre if ciudadano.manzana else "Sin asignar",
            ciudadano.fecha_nacimiento.isoformat() if ciudadano.fecha_nacimiento else "",
            ciudadano.edad if ciudadano.edad is not None else "",
            ciudadano.edad_actual if ciudadano.edad_actual is not None else "Sin información",
            ciudadano.get_sexo_display(),
            ciudadano.get_motivo_alta_display() or "Sin motivo registrado",
            ciudadano.labor_social,
            "Activo" if ciudadano.activo else "Inactivo",
            timezone.localtime(ciudadano.created_at).strftime("%Y-%m-%d %H:%M"),
        ])

    return response


@login_required
def crear_ciudadano_operativo(request):
    if request.method == "POST":
        form = CiudadanoOperativoForm(request.POST)
        if form.is_valid():
            ciudadano = form.save()
            messages.success(request, f"Se registró correctamente a {ciudadano.nombre_completo}.")
            return redirect("perfil_ciudadano", ciudadano.pk)
        messages.error(request, "Revisa los campos marcados antes de guardar al ciudadano.")
    else:
        form = CiudadanoOperativoForm()

    return render(
        request,
        "dashboard/ciudadano_form.html",
        {
            "form": form,
            "title": "Agregar ciudadano",
            "description": "Registra a una persona en el padrón para dar seguimiento a su expediente, faenas, juntas y servicios comunitarios.",
            "submit_label": "Guardar ciudadano",
            "cancel_url": reverse("padron_ciudadanos"),
        },
    )


@login_required
def editar_ciudadano_operativo(request, pk):
    ciudadano = get_object_or_404(Ciudadano, pk=pk)
    if request.method == "POST":
        form = CiudadanoOperativoForm(request.POST, instance=ciudadano)
        if form.is_valid():
            ciudadano = form.save()
            messages.success(request, f"Se actualizó correctamente a {ciudadano.nombre_completo}.")
            return redirect("perfil_ciudadano", ciudadano.pk)
        messages.error(request, "Revisa los campos marcados antes de guardar al ciudadano.")
    else:
        form = CiudadanoOperativoForm(instance=ciudadano)

    return render(request, "dashboard/ciudadano_form.html", {
        "form": form,
        "title": "Editar ciudadano",
        "description": "Actualiza la información y la manzana asignada al ciudadano.",
        "submit_label": "Guardar cambios",
        "cancel_url": reverse("perfil_ciudadano", args=[ciudadano.pk]),
    })


def _filtrar_tomas_operativas(queryset, params):
    q = params.get("q", "").strip()
    estado = params.get("estado", "todas")
    asociacion = params.get("asociacion", "todas")

    if q:
        queryset = queryset.filter(
            Q(numero_toma__icontains=q)
            | Q(ciudadano__nombre__icontains=q)
            | Q(ciudadano__apellido_paterno__icontains=q)
            | Q(ciudadano__apellido_materno__icontains=q)
        )

    if estado == "activas":
        queryset = queryset.filter(estado=Toma.Estados.ACTIVA)
    elif estado == "suspendidas":
        queryset = queryset.filter(estado=Toma.Estados.SUSPENDIDA)

    if asociacion == "con_ciudadano":
        queryset = queryset.filter(ciudadano__isnull=False)
    elif asociacion == "sin_ciudadano":
        queryset = queryset.filter(ciudadano__isnull=True)

    return queryset.order_by("estado", "numero_toma")


@login_required
def control_agua(request):
    tomas_base = Toma.objects.select_related("ciudadano")
    tomas_qs = _filtrar_tomas_operativas(tomas_base, request.GET)
    paginator = Paginator(tomas_qs, 20)
    tomas_page = paginator.get_page(request.GET.get("page"))

    total_tomas = Toma.objects.count()
    tomas_activas = Toma.objects.filter(estado=Toma.Estados.ACTIVA).count()
    tomas_suspendidas = Toma.objects.filter(estado=Toma.Estados.SUSPENDIDA).count()
    tomas_canceladas = Toma.objects.filter(estado=Toma.Estados.CANCELADA).count()
    tomas_sin_ciudadano = Toma.objects.filter(ciudadano__isnull=True).count()
    costo_anual_total = Toma.objects.aggregate(total=Sum("costo_anual"))["total"] or 0

    revision_qs = (
        Toma.objects.select_related("ciudadano")
        .filter(Q(ciudadano__isnull=True) | Q(estado__in=[Toma.Estados.SUSPENDIDA, Toma.Estados.CANCELADA]) | Q(ubicacion=""))
        .order_by("estado", "numero_toma")[:8]
    )

    context = {
        "tomas": tomas_page,
        "filtros": {
            "q": request.GET.get("q", "").strip(),
            "estado": request.GET.get("estado", "todas"),
            "asociacion": request.GET.get("asociacion", "todas"),
        },
        "metricas": {
            "total_tomas": total_tomas,
            "tomas_activas": tomas_activas,
            "tomas_suspendidas": tomas_suspendidas,
            "tomas_canceladas": tomas_canceladas,
            "tomas_sin_ciudadano": tomas_sin_ciudadano,
            "costo_anual_total": costo_anual_total,
        },
        "distribucion": {
            "activas": round((tomas_activas / total_tomas) * 100) if total_tomas else 0,
            "suspendidas": round((tomas_suspendidas / total_tomas) * 100) if total_tomas else 0,
            "sin_ciudadano": round((tomas_sin_ciudadano / total_tomas) * 100) if total_tomas else 0,
            "canceladas": round((tomas_canceladas / total_tomas) * 100) if total_tomas else 0,
        },
        "tomas_revision": revision_qs,
    }
    return render(request, "dashboard/control_agua.html", context)

@login_required
def home(request):
    return render(request, "home.html")


@login_required
def dashboard_operativo(request):
    q = request.GET.get("q", "").strip()

    ciudadanos_qs = (
        Ciudadano.objects.select_related("toma", "manzana")
        .annotate(
            total_pagos=Count("pagos", distinct=True),
            ultimo_pago_fecha=Max("pagos__fecha"),
            adeudos_faena=Count("registros_faena", filter=Q(registros_faena__genera_adeudo=True), distinct=True),
            ultima_faena_fecha=Max("registros_faena__faena__fecha"),
        )
        .order_by("apellido_paterno", "apellido_materno", "nombre")
    )

    if q:
        ciudadanos_qs = ciudadanos_qs.filter(
            Q(nombre__icontains=q)
            | Q(apellido_paterno__icontains=q)
            | Q(apellido_materno__icontains=q)
            | Q(numero_contrato__icontains=q)
            | Q(toma__numero_toma__icontains=q)
        )

    paginator = Paginator(ciudadanos_qs, 12)
    ciudadanos_page = paginator.get_page(request.GET.get("page"))

    metricas = {
        "total_ciudadanos": Ciudadano.objects.count(),
        "ciudadanos_activos": Ciudadano.objects.filter(activo=True).count(),
        "morosos_faena": RegistroFaena.objects.filter(genera_adeudo=True).values("ciudadano").distinct().count(),
        "tomas_suspendidas": Toma.objects.filter(estado=Toma.Estados.SUSPENDIDA).count(),
        "pagos_mes": Pago.objects.filter(fecha__month=timezone.localdate().month, fecha__year=timezone.localdate().year).count(),
    }

    pagos_recientes = list(Pago.objects.select_related("ciudadano", "comite").order_by("-fecha", "-created_at")[:5])
    cooperaciones_recientes = list(
        Cooperacion.objects.select_related("ciudadano", "comite").order_by("-fecha", "-created_at")[:5]
    )
    faenas_recientes = list(Faena.objects.select_related("comite").order_by("-fecha", "-created_at")[:5])
    juntas_programadas = (
        Junta.objects.select_related("comite", "manzana")
        .annotate(total_registros=Count("asistencias", distinct=True))
        .filter(estado=Junta.Estados.PROGRAMADA, total_registros=0)
        .order_by("fecha")[:10]
    )

    actividad_reciente = sorted(
        chain(
            [{"tipo": "Pago", "fecha": p.fecha, "label": f"{p.ciudadano.nombre_completo} • {p.get_tipo_display()} • ${p.monto}"} for p in pagos_recientes],
            [
                {
                    "tipo": "Cooperación",
                    "fecha": c.fecha,
                    "label": f"{c.ciudadano.nombre_completo} • {c.get_tipo_display()} • ${c.monto}",
                }
                for c in cooperaciones_recientes
            ],
            [{"tipo": "Faena", "fecha": f.fecha, "label": f"{f.comite.nombre} • {f.descripcion}"} for f in faenas_recientes],
        ),
        key=lambda x: x["fecha"],
        reverse=True,
    )[:10]

    tarjeta_agua = {
        "tomas_pendientes": Toma.objects.filter(estado__in=[Toma.Estados.SUSPENDIDA, Toma.Estados.CANCELADA]).count(),
        "morosos_agua": Pago.objects.filter(tipo=Pago.Tipos.SERVICIO).values("ciudadano").distinct().count(),
    }

    tarjeta_faena = {
        "proximas_faenas": Faena.objects.filter(estado=Faena.Estados.PROGRAMADA).order_by("fecha")[:5],
        "con_adeudo": RegistroFaena.objects.filter(genera_adeudo=True).values("ciudadano").distinct().count(),
        "monto_total_adeudos": RegistroFaena.objects.filter(genera_adeudo=True).aggregate(total=Sum("monto_adeudo"))["total"] or 0,
    }

    context = {
        "q": q,
        "metricas": metricas,
        "ciudadanos": ciudadanos_page,
        "actividad_reciente": actividad_reciente,
        "tarjeta_agua": tarjeta_agua,
        "tarjeta_faena": tarjeta_faena,
        "faenas_programadas": Faena.objects.annotate(total_registros=Count("registros", distinct=True)).filter(estado=Faena.Estados.PROGRAMADA, total_registros=0).order_by("fecha")[:10],
        "juntas_programadas": juntas_programadas,
        "quick_links": {
            "captura_faenas": f"{reverse('control_asistencias')}?tipo=faenas#faenas",
            "captura_juntas": f"{reverse('control_asistencias')}?tipo=juntas#juntas",
            "faena_add": reverse("crear_faena_operativa"),
            "junta_add": reverse("crear_junta_operativa"),
            "ciudadano_changelist": reverse("admin:core_ciudadano_changelist"),
        },
    }
    if request.headers.get("HX-Request") == "true":
        return render(request, "dashboard/partials/inicio_ciudadanos_resultados.html", context)
    return render(request, "dashboard/operativo.html", context)


def _can_delete_operacion_event(user, permission_codename):
    return user.is_superuser or user.has_perm(permission_codename)


def _money(value):
    return f"${value:.2f}"


def _evento_operativo_form_view(
    request,
    form_class,
    event_label,
    description,
    detail_url_name,
    *,
    instance=None,
    delete_url_name="",
    delete_permission="",
):
    is_edit = instance is not None
    if request.method == "POST":
        form = form_class(request.POST, instance=instance)
        if form.is_valid():
            event = form.save()
            action = "actualizó" if is_edit else "creó"
            messages.success(request, f"Se {action} correctamente la {event_label.lower()}.")
            return redirect(detail_url_name, event.pk)
        messages.error(request, "Revisa los campos marcados antes de guardar.")
    else:
        form = form_class(instance=instance)

    cancel_url = reverse(detail_url_name, args=[instance.pk]) if is_edit else reverse("dashboard_operativo")
    can_delete = bool(is_edit and delete_permission and _can_delete_operacion_event(request.user, delete_permission))
    delete_url = reverse(delete_url_name, args=[instance.pk]) if can_delete and delete_url_name else ""
    return render(
        request,
        "dashboard/evento_form.html",
        {
            "form": form,
            "event_label": event_label,
            "title": f"Editar {event_label.lower()}" if is_edit else f"Crear nueva {event_label.lower()}",
            "description": description,
            "submit_label": f"Guardar cambios" if is_edit else f"Guardar {event_label.lower()}",
            "cancel_url": cancel_url,
            "cancel_label": "Volver al detalle" if is_edit else "Volver al dashboard",
            "can_delete": can_delete,
            "delete_url": delete_url,
        },
    )


def _crear_evento_operativo(request, form_class, event_label, description, detail_url_name):
    return _evento_operativo_form_view(request, form_class, event_label, description, detail_url_name)


@login_required
def crear_faena_operativa(request):
    return _crear_evento_operativo(
        request,
        FaenaOperativaForm,
        "Faena",
        "Registra una faena comunitaria y continúa el seguimiento desde Control de Asistencias.",
        "control_asistencias_faena_detalle",
    )


@login_required
def crear_junta_operativa(request):
    return _crear_evento_operativo(
        request,
        JuntaOperativaForm,
        "Junta",
        "Programa una junta comunitaria con la información necesaria para su seguimiento operativo.",
        "control_asistencias_junta_detalle",
    )


@login_required
def editar_faena_operativa(request, faena_id):
    faena = get_object_or_404(Faena.objects.select_related("comite"), pk=faena_id)
    return _evento_operativo_form_view(
        request,
        FaenaOperativaForm,
        "Faena",
        "Actualiza la información operativa de la faena sin salir del flujo de Control de Asistencias.",
        "control_asistencias_faena_detalle",
        instance=faena,
        delete_url_name="eliminar_faena_operativa",
        delete_permission="operacion.delete_faena",
    )


@login_required
def editar_junta_operativa(request, junta_id):
    junta = get_object_or_404(Junta.objects.select_related("comite", "manzana"), pk=junta_id)
    return _evento_operativo_form_view(
        request,
        JuntaOperativaForm,
        "Junta",
        "Actualiza la información operativa de la junta sin salir del flujo de Control de Asistencias.",
        "control_asistencias_junta_detalle",
        instance=junta,
        delete_url_name="eliminar_junta_operativa",
        delete_permission="operacion.delete_junta",
    )


def _confirmar_eliminacion(request, *, obj, object_type, object_label, cancel_url, success_redirect_name, permission, error_message, success_message, warning_message, deletion_summary):
    if not (request.user.is_superuser or request.user.has_perm(permission)):
        messages.error(request, error_message)
        return redirect(cancel_url)
    if request.method == "POST":
        try:
            with transaction.atomic():
                obj.delete()
        except ProtectedError:
            messages.error(request, "No se pudo eliminar porque existen registros protegidos relacionados.")
            return redirect(cancel_url)
        messages.success(request, success_message)
        return redirect(success_redirect_name)
    return render(request, "dashboard/confirmar_eliminacion.html", {"object_type": object_type, "object_label": object_label, "warning_message": warning_message, "deletion_summary": deletion_summary, "cancel_url": cancel_url})


@login_required
def eliminar_faena_operativa(request, faena_id):
    faena = get_object_or_404(Faena.objects.select_related("comite"), pk=faena_id)
    registros = faena.registros.all()
    total_registros = registros.count()
    pendientes = registros.filter(estatus=RegistroFaena.Estatus.PENDIENTE).count()
    registrados = total_registros - pendientes
    registros_con_adeudo = registros.filter(genera_adeudo=True).count()
    monto_adeudos = registros.filter(genera_adeudo=True).aggregate(total=Sum("monto_adeudo"))["total"] or Decimal("0.00")
    return _confirmar_eliminacion(request, obj=faena, object_type="faena", object_label=faena.descripcion, cancel_url=reverse("control_asistencias_faena_detalle", args=[faena.pk]), success_redirect_name="control_asistencias", permission="operacion.delete_faena", error_message="No tienes permisos para eliminar faenas.", success_message="La faena fue eliminada correctamente.", warning_message="Esta acción eliminará permanentemente la faena y todos sus registros de asistencia relacionados. También se eliminará la información de adeudos asociada directamente a esos registros. Esta acción no se puede deshacer.", deletion_summary=[{"label": "Descripción", "value": faena.descripcion}, {"label": "Fecha", "value": faena.fecha}, {"label": "Comité", "value": faena.comite.nombre}, {"label": "Total de registros generados", "value": total_registros}, {"label": "Registros pendientes", "value": pendientes}, {"label": "Asistencias registradas", "value": registrados}, {"label": "Registros con adeudo", "value": registros_con_adeudo}, {"label": "Monto total de adeudos", "value": _money(monto_adeudos)}])


@login_required
def eliminar_junta_operativa(request, junta_id):
    junta = get_object_or_404(Junta.objects.select_related("comite", "manzana"), pk=junta_id)
    asistencias = junta.asistencias.all()
    total_asistencias = asistencias.count()
    pendientes = asistencias.filter(estatus=AsistenciaJunta.Estatus.PENDIENTE).count()
    capturadas = total_asistencias - pendientes
    registros_con_adeudo = asistencias.filter(genera_adeudo=True).count()
    monto_adeudos = asistencias.filter(genera_adeudo=True).aggregate(total=Sum("monto_adeudo"))["total"] or Decimal("0.00")
    return _confirmar_eliminacion(request, obj=junta, object_type="junta", object_label=junta.tema, cancel_url=reverse("control_asistencias_junta_detalle", args=[junta.pk]), success_redirect_name="control_asistencias", permission="operacion.delete_junta", error_message="No tienes permisos para eliminar juntas.", success_message="La junta fue eliminada correctamente.", warning_message="Esta acción eliminará permanentemente la junta y todos sus registros de asistencia relacionados. También se eliminará la información de adeudos asociada directamente a esos registros. Esta acción no se puede deshacer.", deletion_summary=[{"label": "Tema", "value": junta.tema}, {"label": "Fecha", "value": junta.fecha}, {"label": "Comité", "value": junta.comite.nombre}, {"label": "Total de asistencias generadas", "value": total_asistencias}, {"label": "Registros pendientes", "value": pendientes}, {"label": "Asistencias capturadas", "value": capturadas}, {"label": "Registros con adeudo", "value": registros_con_adeudo}, {"label": "Monto total de adeudos", "value": _money(monto_adeudos)}])


@login_required
def generar_registros_faena(request, faena_id):
    if request.method != "POST":
        return redirect("dashboard_operativo")

    faena = get_object_or_404(Faena.objects.select_related("manzana"), pk=faena_id)
    if faena.estado != Faena.Estados.PROGRAMADA:
        messages.error(request, "Solo se pueden generar registros para faenas programadas.")
        return redirect("dashboard_operativo")
    creados, existentes, objetivo = generar_participantes_faena(faena)
    if not objetivo:
        messages.info(request, "No existen ciudadanos activos para el alcance seleccionado.")
    elif existentes:
        messages.success(request, f"Se crearon {creados} participantes. {existentes} registros ya existían.")
    elif faena.alcance == Faena.Alcances.MANZANA:
        messages.success(request, f"Se crearon {creados} participantes de {faena.manzana}.")
    else:
        messages.success(request, f"Se crearon {creados} participantes para una faena de toda la comunidad.")
    return redirect("dashboard_operativo")


@login_required
def generar_registros_junta(request, junta_id):
    if request.method != "POST":
        return redirect("dashboard_operativo")

    junta = get_object_or_404(Junta.objects.select_related("manzana"), pk=junta_id)
    if junta.estado != Junta.Estados.PROGRAMADA:
        messages.error(request, "Solo se pueden generar registros para juntas programadas.")
        return redirect("dashboard_operativo")
    creados, existentes, objetivo = generar_participantes_junta(junta)
    if not objetivo:
        messages.info(request, "No existen ciudadanos activos para el alcance seleccionado.")
    elif existentes:
        messages.success(request, f"Se crearon {creados} participantes. {existentes} registros ya existían.")
    elif junta.alcance == Junta.Alcances.MANZANA:
        messages.success(request, f"Se crearon {creados} participantes de {junta.manzana}.")
    else:
        messages.success(request, f"Se crearon {creados} participantes para una junta de toda la comunidad.")
    return redirect("dashboard_operativo")


def _attendance_queryset(model, relation_name, pending_status):
    """Annotate event querysets with operational attendance metrics."""
    return model.objects.select_related("comite", "manzana").annotate(
        total_participantes=Count(relation_name, distinct=True),
        asistencias_registradas=Count(
            relation_name,
            filter=~Q(**{f"{relation_name}__estatus": pending_status}),
            distinct=True,
        ),
        pendientes=Count(
            relation_name,
            filter=Q(**{f"{relation_name}__estatus": pending_status}),
            distinct=True,
        ),
        cantidad_adeudos=Count(
            relation_name,
            filter=Q(**{f"{relation_name}__genera_adeudo": True}),
            distinct=True,
        ),
        monto_total_adeudos=Sum(
            f"{relation_name}__monto_adeudo",
            filter=Q(**{f"{relation_name}__genera_adeudo": True}),
        ),
    )


def _decorate_attendance_events(events, description_attr, admin_url_name, capture_url_name, detail_url_name, generate_url_name):
    today = timezone.localdate()
    decorated = []
    for event in events:
        total = event.total_participantes or 0
        registradas = event.asistencias_registradas or 0
        pendientes = event.pendientes or 0
        if getattr(event, "estado", None) == "CANCELADA":
            estado_operacional = "CANCELADA"
            priority = 5
        elif getattr(event, "estado", None) == "REALIZADA":
            estado_operacional = "REALIZADA"
            priority = 3
        elif total == 0:
            estado_operacional = "PROGRAMADA"
            priority = 1 if event.fecha >= today else 4
        elif pendientes:
            estado_operacional = "REGISTROS_GENERADOS"
            priority = 0
        elif event.fecha >= today:
            estado_operacional = "EN_CAPTURA"
            priority = 2
        else:
            estado_operacional = "COMPLETADA"
            priority = 3

        event.descripcion_operativa = getattr(event, description_attr)
        event.estado_operacional = estado_operacional
        event.porcentaje_asistencia = round((registradas / total) * 100) if total else 0
        event.cantidad_adeudos = event.cantidad_adeudos or 0
        event.monto_total_adeudos = event.monto_total_adeudos or 0
        event.can_capture = event.estado == event.Estados.PROGRAMADA and total > 0 and pendientes > 0
        event.estado_edit_url = reverse("editar_estado_evento", args=[event.__class__.__name__.lower(), event.pk])
        event.operational_priority = priority
        event.admin_change_url = reverse(admin_url_name, args=[event.pk])
        event.capture_url = reverse(capture_url_name, args=[event.pk])
        event.sequential_capture_url = reverse(f"captura_asistencia_secuencial_{event.__class__.__name__.lower()}", args=[event.pk])
        event.generate_url = reverse(generate_url_name, args=[event.pk])
        event.detail_url = reverse(detail_url_name, args=[event.pk])
        decorated.append(event)

    return decorated


def _attendance_summary(faenas, juntas):
    return {
        "faenas_activas": sum(1 for event in faenas if event.estado_operacional != "COMPLETADA"),
        "juntas_activas": sum(1 for event in juntas if event.estado_operacional != "COMPLETADA"),
        "eventos_pendientes": sum(1 for event in [*faenas, *juntas] if event.pendientes > 0),
        "asistencias_pendientes": sum(event.pendientes for event in [*faenas, *juntas]),
    }


MESES = [
    (1, "Enero"),
    (2, "Febrero"),
    (3, "Marzo"),
    (4, "Abril"),
    (5, "Mayo"),
    (6, "Junio"),
    (7, "Julio"),
    (8, "Agosto"),
    (9, "Septiembre"),
    (10, "Octubre"),
    (11, "Noviembre"),
    (12, "Diciembre"),
]


def _attendance_years():
    faena_years = Faena.objects.annotate(year=ExtractYear("fecha")).values_list("year", flat=True)
    junta_years = Junta.objects.annotate(year=ExtractYear("fecha")).values_list("year", flat=True)
    return sorted({year for year in chain(faena_years, junta_years) if year}, reverse=True)


def _filtrar_eventos_asistencia(queryset, params, description_field, tipo_actividad):
    return aplicar_filtros_eventos(
        queryset, params=params, description_field=description_field, tipo_actividad=tipo_actividad
    )


def _page_querystring(request, page_param, page_number):
    params = request.GET.copy()
    params[page_param] = page_number
    return urlencode(params, doseq=True)


def _paginate_events(request, queryset, page_param):
    page = Paginator(queryset, 12).get_page(request.GET.get(page_param))
    page.previous_querystring = (
        _page_querystring(request, page_param, page.previous_page_number()) if page.has_previous() else ""
    )
    page.next_querystring = (
        _page_querystring(request, page_param, page.next_page_number()) if page.has_next() else ""
    )
    return page


@login_required
def control_asistencias(request):
    faenas_qs = _filtrar_eventos_asistencia(
        _attendance_queryset(Faena, "registros", RegistroFaena.Estatus.PENDIENTE),
        request.GET,
        "descripcion",
        "faena",
    )
    alcance = request.GET.get("alcance", "todos")
    manzana = request.GET.get("manzana", "todas")
    juntas_qs = _filtrar_eventos_asistencia(
        _attendance_queryset(Junta, "asistencias", AsistenciaJunta.Estatus.PENDIENTE),
        request.GET,
        "tema",
        "junta",
    )
    faenas_page = _paginate_events(request, faenas_qs, "faenas_page")
    juntas_page = _paginate_events(request, juntas_qs, "juntas_page")
    faenas = _decorate_attendance_events(
        faenas_page.object_list,
        "descripcion",
        "editar_faena_operativa",
        "captura_asistencia_faena",
        "control_asistencias_faena_detalle",
        "generar_registros_faena",
    )
    juntas = _decorate_attendance_events(
        juntas_page.object_list,
        "tema",
        "editar_junta_operativa",
        "captura_asistencia_junta",
        "control_asistencias_junta_detalle",
        "generar_registros_junta",
    )

    return render(
        request,
        "dashboard/control_asistencias.html",
        {
            "resumen": _attendance_summary(faenas, juntas),
            "faenas": faenas,
            "juntas": juntas,
            "faenas_page": faenas_page,
            "juntas_page": juntas_page,
            "filtros": {
                "q": request.GET.get("q", "").strip(),
                "mes": request.GET.get("mes", "todos"),
                "anio": request.GET.get("anio", "todos"),
                "alcance": alcance,
                "manzana": manzana,
            },
            "meses": MESES,
            "anios": _attendance_years(),
            "alcances": Faena.Alcances.choices,
            "manzanas": Manzana.objects.order_by("nombre"),
            "tipo_activo": request.GET.get("tipo", ""),
        },
    )


def _event_detail_context(event, registros, event_type, description):
    total = registros.count()
    cantidad_adeudos = registros.filter(genera_adeudo=True).count()
    monto_total_adeudos = registros.filter(genera_adeudo=True).aggregate(total=Sum("monto_adeudo"))["total"] or 0
    registradas = registros.exclude(estatus="PENDIENTE").count()
    pendientes = registros.filter(estatus="PENDIENTE").count()
    porcentaje = round((registradas / total) * 100) if total else 0
    return {
        "event": event,
        "event_type": event_type,
        "description": description,
        "metricas": {
            "total_participantes": total,
            "asistencias_registradas": registradas,
            "pendientes": pendientes,
            "porcentaje_asistencia": porcentaje,
            "cantidad_adeudos": cantidad_adeudos,
            "monto_total_adeudos": monto_total_adeudos,
        },
        "estado_operacional": event.estado if event.estado != event.Estados.PROGRAMADA else ("PROGRAMADA" if total == 0 else ("REGISTROS_GENERADOS" if pendientes else "COMPLETADA")),
        "can_capture": event.estado == event.Estados.PROGRAMADA and total > 0 and pendientes > 0,
        "participantes": registros.select_related("ciudadano").order_by("estatus", "ciudadano__apellido_paterno", "ciudadano__apellido_materno", "ciudadano__nombre")[:200],
    }


def _csv_filename(event_type, event):
    return f"{event_type.lower()}_{event.pk}_participantes_{event.fecha.isoformat()}.csv"


def _exportar_participantes_csv(event, registros, event_type, description):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    filename = _csv_filename(event_type, event)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.write("\ufeff")

    writer = csv.writer(response)
    encabezados = [
        "Numero",
        "Nombre completo",
        "Estado",
        "Fecha",
        "Tipo de evento",
        "Descripcion",
    ]
    encabezados += ["Alcance", "Manzana"]
    encabezados += [
        "Genera adeudo",
        "Monto adeudo",
        "Observaciones",
    ]
    writer.writerow(encabezados)

    registros = registros.select_related("ciudadano").order_by(
        "ciudadano__apellido_paterno",
        "ciudadano__apellido_materno",
        "ciudadano__nombre",
        "pk",
    )
    for numero, registro in enumerate(registros, start=1):
        fila = [
            numero,
            registro.ciudadano.nombre_completo,
            registro.estatus,
            event.fecha.isoformat(),
            event_type,
            description,
        ]
        fila += [event.get_alcance_display(), str(event.manzana) if event.manzana_id else ""]
        fila += [
            "Sí" if registro.genera_adeudo else "No",
            registro.monto_adeudo,
            registro.observaciones,
        ]
        writer.writerow(fila)

    return response


@login_required
def control_asistencias_faena_detalle(request, faena_id):
    faena = get_object_or_404(Faena.objects.select_related("comite", "manzana"), pk=faena_id)
    context = _event_detail_context(faena, faena.registros.all(), "Faena", faena.descripcion)
    context["admin_change_url"] = reverse("editar_faena_operativa", args=[faena.pk])
    context["capture_url"] = reverse("captura_asistencia_faena", args=[faena.pk])
    context["sequential_capture_url"] = reverse("captura_asistencia_secuencial_faena", args=[faena.pk])
    context["estado_edit_url"] = reverse("editar_estado_evento", args=["faena", faena.pk])
    context["export_csv_url"] = reverse("exportar_participantes_faena_csv", args=[faena.pk])
    return render(request, "dashboard/control_asistencias_detalle.html", context)


@login_required
def control_asistencias_junta_detalle(request, junta_id):
    junta = get_object_or_404(Junta.objects.select_related("comite", "manzana"), pk=junta_id)
    context = _event_detail_context(junta, junta.asistencias.all(), "Junta", junta.tema)
    context["admin_change_url"] = reverse("editar_junta_operativa", args=[junta.pk])
    context["capture_url"] = reverse("captura_asistencia_junta", args=[junta.pk])
    context["sequential_capture_url"] = reverse("captura_asistencia_secuencial_junta", args=[junta.pk])
    context["estado_edit_url"] = reverse("editar_estado_evento", args=["junta", junta.pk])
    context["export_csv_url"] = reverse("exportar_participantes_junta_csv", args=[junta.pk])
    return render(request, "dashboard/control_asistencias_detalle.html", context)


@login_required
def exportar_participantes_faena_csv(request, faena_id):
    faena = get_object_or_404(Faena.objects.select_related("comite"), pk=faena_id)
    return _exportar_participantes_csv(faena, faena.registros.all(), "Faena", faena.descripcion)


@login_required
def exportar_participantes_junta_csv(request, junta_id):
    junta = get_object_or_404(Junta.objects.select_related("comite", "manzana"), pk=junta_id)
    return _exportar_participantes_csv(junta, junta.asistencias.all(), "Junta", junta.tema)


def _capture_config(event_kind):
    configs = {
        "faena": {
            "event_model": Faena,
            "relation": "registros",
            "event_type": "Faena",
            "description_attr": "descripcion",
            "status_choices": RegistroFaena.Estatus.choices,
            "detail_url": "control_asistencias_faena_detalle",
            "admin_change_url": "editar_faena_operativa",
            "capture_url": "captura_asistencia_faena",
            "sequential_capture_url": "captura_asistencia_secuencial_faena",
        },
        "junta": {
            "event_model": Junta,
            "relation": "asistencias",
            "event_type": "Junta",
            "description_attr": "tema",
            "status_choices": AsistenciaJunta.Estatus.choices,
            "detail_url": "control_asistencias_junta_detalle",
            "admin_change_url": "editar_junta_operativa",
            "capture_url": "captura_asistencia_junta",
            "sequential_capture_url": "captura_asistencia_secuencial_junta",
        },
    }
    return configs[event_kind]


def _update_attendance_records(request, registros, config):
    updated = 0
    valid_statuses = {value for value, _label in config["status_choices"]}
    for registro in registros:
        prefix = f"registro_{registro.pk}"
        estatus = request.POST.get(f"{prefix}_estatus")
        if estatus not in valid_statuses:
            continue

        changed = False
        if registro.estatus != estatus:
            registro.estatus = estatus
            changed = True

        observaciones = request.POST.get(f"{prefix}_observaciones", "").strip()
        if registro.observaciones != observaciones:
            registro.observaciones = observaciones
            changed = True

        if isinstance(registro, (RegistroFaena, AsistenciaJunta)):
            genera_adeudo = request.POST.get(f"{prefix}_genera_adeudo") == "on"
            monto_raw = request.POST.get(f"{prefix}_monto_adeudo") or "0"
            if registro.genera_adeudo != genera_adeudo:
                registro.genera_adeudo = genera_adeudo
                changed = True
            if str(registro.monto_adeudo) != monto_raw:
                registro.monto_adeudo = monto_raw
                changed = True
        if isinstance(registro, AsistenciaJunta):
            asistio = estatus == AsistenciaJunta.Estatus.ASISTIO
            if registro.asistio != asistio:
                registro.asistio = asistio
                changed = True

        if changed:
            registro.save()
            updated += 1
    return updated


def _capture_metrics(registros):
    total = registros.count()
    asistieron = registros.filter(estatus="ASISTIO").count()
    faltaron = registros.filter(estatus="FALTO").count()
    pendientes = registros.filter(estatus="PENDIENTE").count()
    registradas = total - pendientes
    cantidad_adeudos = registros.filter(genera_adeudo=True).count()
    monto_total_adeudos = registros.filter(genera_adeudo=True).aggregate(total=Sum("monto_adeudo"))["total"] or 0
    return {
        "total": total,
        "asistieron": asistieron,
        "faltaron": faltaron,
        "pendientes": pendientes,
        "registradas": registradas,
        "actual": registradas + 1 if pendientes else total,
        "porcentaje": round((registradas / total) * 100) if total else 0,
        "cantidad_adeudos": cantidad_adeudos,
        "monto_total_adeudos": str(monto_total_adeudos),
        "porcentaje_asistencia": round((asistieron / total) * 100) if total else 0,
    }


def _pending_records(event, relation):
    return getattr(event, relation).select_related("ciudadano").filter(estatus="PENDIENTE").order_by(
        "ciudadano__apellido_paterno", "ciudadano__apellido_materno", "ciudadano__nombre", "pk"
    )


def _serialize_record(registro):
    if not registro:
        return None
    return {"id": registro.pk, "nombre": registro.ciudadano.nombre_completo}


LAST_PENDING_PRESENTIAL_MESSAGE = (
    "Has llegado al último participante pendiente. "
    "Para evitar cerrar el pase de lista sin revisar los adeudos y la información final, "
    "este registro debe completarse desde Captura Normal."
)


def _normal_capture_url(event, config):
    return reverse(config["capture_url"], args=[event.pk])


def _capture_payload(event, config):
    registros = getattr(event, config["relation"]).all()
    metrics = _capture_metrics(registros)
    siguiente = None
    if metrics["pendientes"] > 1:
        siguiente = _pending_records(event, config["relation"]).first()
    return {
        "ok": True,
        "metrics": metrics,
        "next_record": _serialize_record(siguiente),
        "completed": metrics["pendientes"] == 0,
        "requires_normal_capture": metrics["pendientes"] == 1,
        "normal_capture_url": _normal_capture_url(event, config),
        "last_pending_message": LAST_PENDING_PRESENTIAL_MESSAGE if metrics["pendientes"] == 1 else "",
    }


def _json_capture_action(request, event, config):
    action = request.POST.get("action")
    record_id = request.POST.get("record_id")
    valid = {"asistio": "ASISTIO", "falto": "FALTO", "undo": "PENDIENTE"}
    if action not in valid or not record_id:
        return JsonResponse({"ok": False, "error": "Acción inválida."}, status=400)

    with transaction.atomic():
        registros_locked = getattr(event, config["relation"]).select_for_update()
        registro = get_object_or_404(registros_locked, pk=record_id)
        expected = request.POST.get("expected_status")
        if action in {"asistio", "falto"}:
            pendientes = registros_locked.filter(estatus="PENDIENTE").count()
            if pendientes <= 1 and registro.estatus == "PENDIENTE":
                return JsonResponse(
                    {
                        **_capture_payload(event, config),
                        "ok": False,
                        "error": LAST_PENDING_PRESENTIAL_MESSAGE,
                    },
                    status=409,
                )
        if action in {"asistio", "falto"} and registro.estatus != "PENDIENTE":
            return JsonResponse({"ok": False, "error": "Este registro ya fue actualizado.", **_capture_payload(event, config)}, status=409)
        if action == "undo" and expected and registro.estatus != expected:
            return JsonResponse({"ok": False, "error": "El registro cambió desde la última acción.", **_capture_payload(event, config)}, status=409)
        registro.estatus = valid[action]
        if isinstance(registro, AsistenciaJunta):
            registro.asistio = registro.estatus == AsistenciaJunta.Estatus.ASISTIO
        registro.save()
    payload = _capture_payload(event, config)
    payload.update({"updated_record": {"id": registro.pk, "estatus": registro.estatus}})
    return JsonResponse(payload)


def _captura_asistencia(request, event_kind, event_id):
    config = _capture_config(event_kind)
    event = get_object_or_404(
        config["event_model"].objects.select_related("comite", "manzana"), pk=event_id
    )
    if event.estado != event.Estados.PROGRAMADA:
        messages.error(request, "Solo se puede capturar asistencia en eventos programados.")
        return redirect(config["detail_url"], event.pk)
    registros_qs = getattr(event, config["relation"]).select_related("ciudadano").order_by(
        "estatus", "ciudadano__apellido_paterno", "ciudadano__apellido_materno", "ciudadano__nombre"
    )

    if request.method == "POST":
        with transaction.atomic():
            registros = list(registros_qs.select_for_update())
            updated = _update_attendance_records(request, registros, config)
        messages.success(request, f"Se guardaron {updated} cambios de asistencia para {config['event_type'].lower()}.")
        return redirect(config["capture_url"], event.pk)

    context = _event_detail_context(
        event,
        getattr(event, config["relation"]).all(),
        config["event_type"],
        getattr(event, config["description_attr"]),
    )
    context.update(
        {
            "participantes": registros_qs,
            "status_choices": config["status_choices"],
            "detail_url": reverse(config["detail_url"], args=[event.pk]),
            "admin_change_url": reverse(config["admin_change_url"], args=[event.pk]),
            "capture_url": reverse(config["capture_url"], args=[event.pk]),
            "sequential_capture_url": reverse(config["sequential_capture_url"], args=[event.pk]),
            "estado_edit_url": reverse("editar_estado_evento", args=[event_kind, event.pk]),
        }
    )
    return render(request, "dashboard/captura_asistencia.html", context)


def _captura_asistencia_secuencial(request, event_kind, event_id):
    config = _capture_config(event_kind)
    event = get_object_or_404(
        config["event_model"].objects.select_related("comite", "manzana"), pk=event_id
    )
    if event.estado != event.Estados.PROGRAMADA:
        if request.method == "POST":
            return JsonResponse({"ok": False, "error": "Solo se puede capturar asistencia en eventos programados."}, status=403)
        messages.error(request, "Solo se puede capturar asistencia en eventos programados.")
        return redirect(config["detail_url"], event.pk)

    if request.method == "POST":
        return _json_capture_action(request, event, config)

    context = _event_detail_context(
        event,
        getattr(event, config["relation"]).all(),
        config["event_type"],
        getattr(event, config["description_attr"]),
    )
    payload = _capture_payload(event, config)
    context.update(
        {
            "current_record": payload["next_record"],
            "capture_metrics": payload["metrics"],
            "requires_normal_capture": payload["requires_normal_capture"],
            "normal_capture_url": payload["normal_capture_url"],
            "last_pending_message": payload["last_pending_message"],
            "detail_url": reverse(config["detail_url"], args=[event.pk]),
            "admin_change_url": reverse(config["admin_change_url"], args=[event.pk]),
            "capture_url": reverse(config["sequential_capture_url"], args=[event.pk]),
            "bulk_capture_url": reverse(config["capture_url"], args=[event.pk]),
            "estado_edit_url": reverse("editar_estado_evento", args=[event_kind, event.pk]),
        }
    )
    return render(request, "dashboard/captura_asistencia_secuencial.html", context)


@login_required
def captura_asistencia_faena(request, faena_id):
    return _captura_asistencia(request, "faena", faena_id)


@login_required
def captura_asistencia_junta(request, junta_id):
    return _captura_asistencia(request, "junta", junta_id)


@login_required
def captura_asistencia_secuencial_faena(request, faena_id):
    return _captura_asistencia_secuencial(request, "faena", faena_id)


@login_required
def captura_asistencia_secuencial_junta(request, junta_id):
    return _captura_asistencia_secuencial(request, "junta", junta_id)


@login_required
def editar_estado_evento(request, event_kind, event_id):
    configs = {
        "faena": (Faena, "Faena", "descripcion", "control_asistencias_faena_detalle"),
        "junta": (Junta, "Junta", "tema", "control_asistencias_junta_detalle"),
    }
    if event_kind not in configs:
        return redirect("control_asistencias")

    model, event_type, description_attr, detail_url = configs[event_kind]
    event = get_object_or_404(model.objects.select_related("comite"), pk=event_id)
    form = EstadoEventoForm(
        request.POST or None,
        initial={"estado": event.estado},
        choices=model.Estados.choices,
    )
    if request.method == "POST" and form.is_valid():
        nuevo_estado = form.cleaned_data["estado"]
        total_registros = getattr(event, "registros", getattr(event, "asistencias", None)).count()
        if nuevo_estado == model.Estados.REALIZADA and total_registros == 0:
            messages.error(request, "No se puede marcar como realizada sin registros generados.")
        else:
            event.estado = nuevo_estado
            event.save(update_fields=["estado", "updated_at"])
            messages.success(request, f"Se actualizó el estado de {event_type.lower()}.")
            return redirect(detail_url, event.pk)

    return render(request, "dashboard/editar_estado_evento.html", {
        "form": form,
        "event": event,
        "event_type": event_type,
        "description": getattr(event, description_attr),
        "cancel_url": reverse(detail_url, args=[event.pk]),
    })


@login_required
def perfil_ciudadano(request, pk):
    from .expediente import (
        obtener_abonos_ciudadano, obtener_asistencias_ciudadano,
        obtener_obligaciones_ciudadano, obtener_resumen_ciudadano, paginar,
    )

    ciudadano = get_object_or_404(Ciudadano.objects.select_related("toma", "manzana", "manzana__responsable"), pk=pk)
    retorno_solicitado = request.GET.get("return_to", "")
    retorno_valido = bool(retorno_solicitado and url_has_allowed_host_and_scheme(
        retorno_solicitado, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ) and retorno_solicitado.startswith("/"))
    return_to = retorno_solicitado if retorno_valido else reverse("padron_ciudadanos")
    if return_to.startswith(reverse("resumen_aportaciones")):
        origen = "Resumen de aportaciones"
    elif return_to.startswith(reverse("tesoreria_operativa")):
        origen = "Tesorería"
    elif return_to.startswith(reverse("control_asistencias")):
        origen = "Control de Asistencias"
    else:
        origen = "Ciudadanos"

    obligaciones_page = paginar(obtener_obligaciones_ciudadano(ciudadano), request, "obligaciones_page")
    abonos_page = paginar(obtener_abonos_ciudadano(ciudadano), request, "abonos_page")
    asistencias_page = paginar(obtener_asistencias_ciudadano(ciudadano), request, "asistencias_page")
    for page, parametro in ((obligaciones_page, "obligaciones_page"), (abonos_page, "abonos_page"), (asistencias_page, "asistencias_page")):
        params = request.GET.copy()
        params["return_to"] = return_to
        page.previous_querystring = ""
        page.next_querystring = ""
        if page.has_previous():
            params[parametro] = page.previous_page_number(); page.previous_querystring = params.urlencode()
        if page.has_next():
            params[parametro] = page.next_page_number(); page.next_querystring = params.urlencode()

    return render(
        request,
        "dashboard/perfil_ciudadano.html",
        {
            "ciudadano": ciudadano,
            "resumen": obtener_resumen_ciudadano(ciudadano),
            "obligaciones_page": obligaciones_page,
            "abonos_page": abonos_page,
            "asistencias_page": asistencias_page,
            "return_to": return_to,
            "origen": origen,
            "admin_change_url": reverse("admin:core_ciudadano_change", args=[ciudadano.pk]),
            "faenas_programadas": Faena.objects.annotate(total_registros=Count("registros", distinct=True)).filter(estado=Faena.Estados.PROGRAMADA, total_registros=0).order_by("fecha")[:10],
            "quick_links": {
                "pago_add": f"{reverse('admin:tesoreria_pago_add')}?ciudadano={ciudadano.pk}",
                "cooperacion_add": f"{reverse('admin:tesoreria_cooperacion_add')}?ciudadano={ciudadano.pk}",
            },
        },
    )

from apps.comites.models import Comite
from apps.tesoreria.forms import AbonoForm, ConceptoTesoreriaForm
from apps.tesoreria.models import Abono, ConceptoTesoreria, ObligacionCiudadano


def _can_modify_tesoreria(user):
    return user.has_perm("tesoreria.add_conceptotesoreria") or user.has_perm("tesoreria.change_conceptotesoreria") or user.is_superuser


def _can_delete_tesoreria(user):
    return user.is_superuser or user.has_perm("tesoreria.delete_conceptotesoreria")


def _filtros_tesoreria(params):
    return {
        "q": params.get("q", "").strip(),
        "naturaleza": params.get("naturaleza", "todos"),
        "alcance": params.get("alcance", "todos"),
        "manzana": params.get("manzana", "todas"),
        "mes": params.get("mes", "todos"),
        "anio": params.get("anio", "todos"),
        "estado": params.get("estado", "todos"),
        "comite": params.get("comite", "todos"),
    }


def _etiqueta_estado_general(estado):
    return {"SIN_GENERAR": "Sin generar", "CON_PENDIENTES": "Con pendientes", "COMPLETADO": "Completado"}[estado]


def _metricas_conceptos(conceptos):
    concepto_ids = conceptos.order_by().values("pk")
    obligaciones = ObligacionCiudadano.objects.filter(concepto_id__in=Subquery(concepto_ids))
    datos = obligaciones.aggregate(
        total_asignado=Sum("monto_asignado", filter=~Q(estado=ObligacionCiudadano.Estados.CANCELADO)),
        pagadas=Count("pk", filter=Q(estado=ObligacionCiudadano.Estados.PAGADO)),
        pendientes=Count("pk", filter=Q(estado=ObligacionCiudadano.Estados.PENDIENTE)),
    )
    asignado = datos["total_asignado"] or Decimal("0.00")
    abonado = Abono.objects.filter(
        obligacion__concepto_id__in=Subquery(concepto_ids),
        obligacion__estado__in=[ObligacionCiudadano.Estados.PENDIENTE, ObligacionCiudadano.Estados.PAGADO],
    ).aggregate(total=Sum("monto"))["total"] or Decimal("0.00")
    aplicables = (datos["pagadas"] or 0) + (datos["pendientes"] or 0)
    return {
        "total_asignado": asignado,
        "total_abonado": abonado,
        "saldo_pendiente": max(asignado - abonado, Decimal("0.00")),
        "ciudadanos_pendientes": ObligacionCiudadano.objects.filter(
            concepto_id__in=Subquery(concepto_ids), estado=ObligacionCiudadano.Estados.PENDIENTE,
        ).values("ciudadano_id").distinct().count(),
        "porcentaje_cumplimiento": round(((datos["pagadas"] or 0) / aplicables) * 100, 1) if aplicables else 0,
    }


@login_required
def tesoreria_operativa(request):
    conceptos_qs = conceptos_filtrados(request.GET)
    metricas = _metricas_conceptos(conceptos_qs)
    pagos_page = Paginator(
        conceptos_qs.filter(naturaleza=ConceptoTesoreria.Naturalezas.PAGO), 3,
    ).get_page(request.GET.get("pagina_conceptos"))
    cooperaciones_page = Paginator(
        conceptos_qs.filter(naturaleza=ConceptoTesoreria.Naturalezas.COOPERACION), 3,
    ).get_page(request.GET.get("pagina_cooperaciones"))

    def preparar_pagina(page, parametro):
        page.previous_querystring = _page_querystring(request, parametro, page.previous_page_number()) if page.has_previous() else ""
        page.next_querystring = _page_querystring(request, parametro, page.next_page_number()) if page.has_next() else ""
        page.neighbors = []
        for number in range(max(1, page.number - 1), min(page.paginator.num_pages, page.number + 1) + 1):
            page.neighbors.append({
                "number": number,
                "querystring": _page_querystring(request, parametro, number),
                "current": number == page.number,
            })
        return page

    preparar_pagina(pagos_page, "pagina_conceptos")
    preparar_pagina(cooperaciones_page, "pagina_cooperaciones")
    export_params = request.GET.copy()
    for parametro in ("page", "pagina_conceptos", "pagina_cooperaciones"):
        export_params.pop(parametro, None)
    filtros = _filtros_tesoreria(request.GET)
    context = {
        "pagos_page": pagos_page, "cooperaciones_page": cooperaciones_page,
        "metricas": metricas, "filtros": filtros,
        "meses": MESES,
        "anios": ConceptoTesoreria.objects.dates("fecha", "year", order="DESC"),
        "comites": Comite.objects.filter(activo=True), "manzanas": Manzana.objects.order_by("nombre"),
        "can_modify": _can_modify_tesoreria(request.user),
        "hay_conceptos": ConceptoTesoreria.objects.exists(),
        "export_querystring": export_params.urlencode(),
        "manzana_activa": Manzana.objects.filter(pk=filtros["manzana"]).first() if filtros["manzana"].isdigit() else None,
    }
    template = "dashboard/partials/_conceptos_paginados.html" if request.headers.get("X-Requested-With") == "XMLHttpRequest" else "dashboard/tesoreria.html"
    return render(request, template, context)


@login_required
def exportar_tesoreria_csv(request):
    conceptos = conceptos_filtrados(request.GET)
    partes = ["tesoreria"]
    naturaleza = request.GET.get("naturaleza")
    if naturaleza in dict(ConceptoTesoreria.Naturalezas.choices):
        partes.append(dict(ConceptoTesoreria.Naturalezas.choices)[naturaleza].lower())
    if request.GET.get("manzana", "").isdigit():
        manzana = Manzana.objects.filter(pk=request.GET["manzana"]).first()
        if manzana: partes.append(str(manzana))
    nombre = slugify("_".join(partes))[:80] or "tesoreria"
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{nombre}_{timezone.localdate().isoformat()}.csv"'
    response.write("\ufeff")
    writer = csv.writer(response)
    writer.writerow(["ID", "Naturaleza", "Concepto", "Descripción", "Comité", "Alcance", "Manzana", "Fecha", "Año del periodo", "Monto base", "Obligaciones totales", "Pagadas", "Pendientes", "Canceladas", "Total asignado", "Total abonado", "Saldo pendiente", "Estado general"])
    for c in conceptos.iterator():
        writer.writerow([c.pk, c.get_naturaleza_display(), c.concepto, c.descripcion or "", c.comite.nombre,
            c.get_alcance_display(), str(c.manzana) if c.manzana_id else "Sin asignar", c.fecha.isoformat(),
            c.anio_periodo or c.fecha.year, c.monto_individual, c.cantidad_obligaciones, c.cantidad_pagada,
            c.cantidad_pendiente, c.cantidad_cancelada, c.total_asignado, c.total_abonado,
            c.saldo_pendiente, _etiqueta_estado_general(c.estado_general)])
    return response


def _pagina_aportaciones(request, queryset, parametro, cantidad):
    pagina = Paginator(queryset, cantidad).get_page(request.GET.get(parametro))
    pagina.previous_querystring = _page_querystring(request, parametro, pagina.previous_page_number()) if pagina.has_previous() else ""
    pagina.next_querystring = _page_querystring(request, parametro, pagina.next_page_number()) if pagina.has_next() else ""
    return pagina


def _filtros_aportaciones(params):
    return {
        "mes": params.get("mes", "todos"), "anio": params.get("anio", "todos"),
        "naturaleza": params.get("naturaleza", "todos"), "alcance": params.get("alcance", "todos"),
        "manzana": params.get("manzana", "todas"), "comite": params.get("comite", "todos"),
        "concepto": params.get("concepto", "").strip(), "ciudadano": params.get("ciudadano", "").strip(),
    }


def _opcion_entera(valor, *, permitidos, predeterminado):
    """Devuelve solamente límites conocidos para evitar cargas arbitrarias."""
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        return predeterminado
    return numero if numero in permitidos else predeterminado


def _opcion(valor, *, permitidos, predeterminado):
    return valor if valor in permitidos else predeterminado


def _campos_contexto_aportaciones(filtros, controles, *, excluir=()):
    """Campos GET validados que un formulario local puede reenviar con seguridad."""
    campos = {**filtros, **controles}
    return [
        {"name": nombre, "value": valor}
        for nombre, valor in campos.items()
        if nombre not in excluir and valor not in (None, "")
    ]


def _resumen_territorial(base, filtros, incluir_inactivas, orden):
    """Combina territorios seleccionados con agregados SQL, sin consultas por fila."""
    alcance = filtros["alcance"]
    manzana_seleccionada = filtros["manzana"]
    mostrar_manzanas = alcance != ConceptoTesoreria.Alcances.GENERAL
    mostrar_general = (
        alcance != ConceptoTesoreria.Alcances.MANZANA
        and not manzana_seleccionada.isdigit()
    )

    manzanas_qs = Manzana.objects.none()
    if mostrar_manzanas:
        manzanas_qs = Manzana.objects.all()
        if manzana_seleccionada.isdigit():
            manzanas_qs = manzanas_qs.filter(pk=int(manzana_seleccionada))
        elif not incluir_inactivas:
            manzanas_qs = manzanas_qs.filter(activa=True)
    manzanas = list(manzanas_qs.order_by("nombre", "pk"))

    agregados = base.filter(
        obligacion__concepto__alcance=ConceptoTesoreria.Alcances.MANZANA,
        obligacion__concepto__manzana_id__in=[manzana.pk for manzana in manzanas],
    ).values("obligacion__concepto__manzana_id").annotate(
        total_recibido=Sum("monto"), cantidad_abonos=Count("pk"),
        ciudadanos_distintos=Count("obligacion__ciudadano_id", distinct=True),
        ultimo_movimiento=Max("fecha"),
    )
    por_id = {fila["obligacion__concepto__manzana_id"]: fila for fila in agregados}
    filas = []
    for manzana in manzanas:
        agregado = por_id.get(manzana.pk, {})
        total = agregado.get("total_recibido") or Decimal("0.00")
        ciudadanos = agregado.get("ciudadanos_distintos") or 0
        filas.append({
            "key": ("manzana", manzana.pk), "manzana_id": manzana.pk,
            "nombre": manzana.nombre, "activa": manzana.activa,
            "total_recibido": total,
            "cantidad_abonos": agregado.get("cantidad_abonos") or 0,
            "ciudadanos_distintos": ciudadanos,
            "promedio_participante": total / ciudadanos if ciudadanos else Decimal("0.00"),
            "ultimo_movimiento": agregado.get("ultimo_movimiento"),
        })

    ordenes = {
        "monto": lambda fila: (-fila["total_recibido"], fila["nombre"].casefold(), fila["manzana_id"]),
        "ciudadanos": lambda fila: (-fila["ciudadanos_distintos"], -fila["total_recibido"], fila["nombre"].casefold(), fila["manzana_id"]),
        "movimientos": lambda fila: (-fila["cantidad_abonos"], -fila["total_recibido"], fila["nombre"].casefold(), fila["manzana_id"]),
        "nombre": lambda fila: (fila["nombre"].casefold(), fila["manzana_id"]),
    }
    filas.sort(key=ordenes[orden])

    general = None
    if mostrar_general:
        datos = base.filter(
            obligacion__concepto__alcance=ConceptoTesoreria.Alcances.GENERAL,
        ).aggregate(
            total_recibido=Sum("monto"), cantidad_abonos=Count("pk"),
            ciudadanos_distintos=Count("obligacion__ciudadano_id", distinct=True),
            ultimo_movimiento=Max("fecha"),
        )
        total = datos["total_recibido"] or Decimal("0.00")
        ciudadanos = datos["ciudadanos_distintos"] or 0
        general = {
            "key": ("general", None), "nombre": "Toda la comunidad", "activa": True,
            **datos, "total_recibido": total,
            "promedio_participante": total / ciudadanos if ciudadanos else Decimal("0.00"),
        }
    return filas, general


def _querystring_sin_pagina(params, **cambios):
    copia = params.copy()
    copia.pop("pagina", None)
    for clave, valor in cambios.items():
        copia[clave] = valor
    return copia.urlencode()


@login_required
def buscar_aportaciones(request):
    """Coordina la búsqueda SSR y su respuesta parcial progresiva."""
    manzanas = list(Manzana.objects.order_by("nombre"))
    comites = list(Comite.objects.filter(activo=True).order_by("nombre"))
    anios = {fecha.year for fecha in Abono.objects.dates("fecha", "year", order="DESC")}
    if request.GET.get("anio", "").isdigit():
        anios.add(int(request.GET["anio"]))
    datos = request.GET.copy()
    datos.setdefault("mes", "todos"); datos.setdefault("anio", "todos")
    datos.setdefault("naturaleza", "todos"); datos.setdefault("alcance", "todos")
    datos.setdefault("manzana", "todas"); datos.setdefault("comite", "todos")
    datos.setdefault("estado", "todos"); datos.setdefault("orden", "reciente")
    datos.setdefault("por_pagina", "25")
    form = BuscarAportacionesForm(
        datos, anios=sorted(anios, reverse=True), manzanas=manzanas,
        comites=comites, meses=MESES,
    )
    filtros = form.cleaned_data if form.is_valid() else {}
    movimientos = buscar_movimientos_aportaciones(filtros) if form.is_valid() else Abono.objects.none()
    total = movimientos.count()
    por_pagina = int(filtros.get("por_pagina") or 25) if form.is_valid() else 25
    pagina = Paginator(movimientos, por_pagina).get_page(request.GET.get("pagina"))
    params = request.GET.copy(); params.pop("pagina", None)
    etiquetas = []
    if filtros.get("anio") and filtros["anio"] != "todos": etiquetas.append(f"Año {filtros['anio']}")
    if filtros.get("mes") and filtros["mes"] != "todos": etiquetas.append(dict((str(v), n) for v, n in MESES).get(filtros["mes"], filtros["mes"]))
    if filtros.get("naturaleza") in dict(ConceptoTesoreria.Naturalezas.choices): etiquetas.append(dict(ConceptoTesoreria.Naturalezas.choices)[filtros["naturaleza"]])
    if filtros.get("manzana") and filtros["manzana"] != "todas": etiquetas.append(next((str(m) for m in manzanas if str(m.pk) == filtros["manzana"]), ""))
    if filtros.get("concepto"): etiquetas.append(f"Concepto: {filtros['concepto']}")
    if filtros.get("estado") in dict(ObligacionCiudadano.Estados.choices): etiquetas.append(dict(ObligacionCiudadano.Estados.choices)[filtros["estado"]])
    if filtros.get("fecha_inicial"): etiquetas.append(f"Desde {filtros['fecha_inicial'].strftime('%d/%m/%Y')}")
    if filtros.get("fecha_final"): etiquetas.append(f"Hasta {filtros['fecha_final'].strftime('%d/%m/%Y')}")
    if filtros.get("importe_minimo") is not None: etiquetas.append(f"Importe desde ${filtros['importe_minimo']:.2f}")
    if filtros.get("importe_maximo") is not None: etiquetas.append(f"Importe hasta ${filtros['importe_maximo']:.2f}")
    resumen_params = {
        k: request.GET[k] for k in ("mes", "anio", "naturaleza", "alcance", "manzana", "comite", "concepto")
        if request.GET.get(k) not in (None, "", "todos", "todas")
    }
    contexto = {
        "form": form, "pagina": pagina, "cantidad_resultados": total,
        "etiquetas_contexto": [e for e in etiquetas if e], "texto_busqueda": filtros.get("q", ""),
        "hay_parametros": any(k not in {"orden", "por_pagina"} for k in request.GET),
        "querystring": params.urlencode(),
        "previous_querystring": _querystring_sin_pagina(request.GET, pagina=pagina.previous_page_number()) if pagina.has_previous() else "",
        "next_querystring": _querystring_sin_pagina(request.GET, pagina=pagina.next_page_number()) if pagina.has_next() else "",
        "resumen_querystring": urlencode(resumen_params),
    }
    if request.headers.get("HX-Request") == "true" or request.GET.get("parcial") == "1":
        return render(request, "dashboard/partials/buscar_aportaciones_resultados.html", contexto)
    return render(request, "dashboard/buscar_aportaciones.html", contexto)


@login_required
def resumen_aportaciones(request):
    opciones_limite_ciudadanos = (5, 10, 20, 50, 100)
    opciones_limite_movimientos = (5, 10, 20, 25, 50, 100)
    opciones_orden_ciudadanos = (
        ("monto", "Mayor monto aportado"),
        ("movimientos", "Mayor cantidad de aportaciones"),
        ("reciente", "Aportación más reciente"),
    )
    opciones_orden_manzanas = (
        ("monto", "Mayor monto recibido"), ("ciudadanos", "Más ciudadanos"),
        ("movimientos", "Más movimientos"), ("nombre", "Nombre de manzana"),
    )
    ciudadanos_por_pagina = _opcion_entera(
        request.GET.get("ciudadanos_por_pagina", request.GET.get("limite_ciudadanos")),
        permitidos=opciones_limite_ciudadanos, predeterminado=10,
    )
    movimientos_por_pagina = _opcion_entera(
        request.GET.get("movimientos_por_pagina", request.GET.get("limite_movimientos")),
        permitidos=opciones_limite_movimientos, predeterminado=5,
    )
    orden_ciudadanos = _opcion(
        request.GET.get("orden_ciudadanos"),
        permitidos={valor for valor, _ in opciones_orden_ciudadanos}, predeterminado="monto",
    )
    orden_manzanas = _opcion(
        request.GET.get("orden_manzanas"),
        permitidos={valor for valor, _ in opciones_orden_manzanas}, predeterminado="monto",
    )
    incluir_inactivas = _opcion(
        request.GET.get("incluir_manzanas_inactivas"), permitidos={"0", "1"}, predeterminado="0",
    ) == "1"
    base = abonos_filtrados(request.GET)
    dinero = DecimalField(max_digits=14, decimal_places=2)
    cero = Value(Decimal("0.00"), output_field=dinero)
    metricas = base.aggregate(
        total_recibido=Coalesce(Sum("monto"), cero),
        pagos_recibidos=Coalesce(Sum("monto", filter=Q(obligacion__concepto__naturaleza=ConceptoTesoreria.Naturalezas.PAGO)), cero),
        cooperaciones_recibidas=Coalesce(Sum("monto", filter=Q(obligacion__concepto__naturaleza=ConceptoTesoreria.Naturalezas.COOPERACION)), cero),
        ciudadanos_con_aportaciones=Count("obligacion__ciudadano", distinct=True),
    )
    por_concepto = base.values(
        "obligacion__concepto_id", "obligacion__concepto__concepto", "obligacion__concepto__naturaleza",
        "obligacion__concepto__comite__nombre", "obligacion__concepto__alcance", "obligacion__concepto__manzana__nombre",
    ).annotate(
        total_recibido=Coalesce(Sum("monto"), cero), cantidad_abonos=Count("pk"),
        ciudadanos_distintos=Count("obligacion__ciudadano", distinct=True), ultimo_movimiento=Max("fecha"),
    ).order_by("-total_recibido", "obligacion__concepto__concepto")
    mayores_qs = base.values(
        "obligacion__ciudadano_id", "obligacion__ciudadano__nombre", "obligacion__ciudadano__apellido_paterno",
        "obligacion__ciudadano__apellido_materno", "obligacion__ciudadano__manzana__nombre",
    ).annotate(
        total_abonado=Coalesce(Sum("monto"), cero), cantidad_aportaciones=Count("pk"), ultima_aportacion=Max("fecha"),
    )
    ordenes_ciudadanos = {
        "monto": ("-total_abonado", "-cantidad_aportaciones", "obligacion__ciudadano__nombre", "obligacion__ciudadano_id"),
        "movimientos": ("-cantidad_aportaciones", "-total_abonado", "obligacion__ciudadano__nombre", "obligacion__ciudadano_id"),
        "reciente": ("-ultima_aportacion", "-total_abonado", "obligacion__ciudadano_id"),
    }
    mayores_qs = mayores_qs.order_by(*ordenes_ciudadanos[orden_ciudadanos])
    movimientos_qs = base.select_related(
        "obligacion__ciudadano", "obligacion__ciudadano__manzana", "obligacion__concepto",
        "obligacion__concepto__manzana", "obligacion__concepto__comite",
    ).order_by("-fecha", "-created_at", "-pk")
    ultimo_movimiento_id = movimientos_qs.values_list("pk", flat=True).first()
    ciudadanos_page = Paginator(mayores_qs, ciudadanos_por_pagina).get_page(
        request.GET.get("ciudadanos_pagina")
    )
    movimientos_page = Paginator(movimientos_qs, movimientos_por_pagina).get_page(
        request.GET.get("movimientos_pagina")
    )
    mayores = list(ciudadanos_page.object_list)
    movimientos = list(movimientos_page.object_list)
    filtros = _filtros_aportaciones(request.GET)
    controles = {
        "ciudadanos_por_pagina": ciudadanos_por_pagina,
        "orden_ciudadanos": orden_ciudadanos,
        "movimientos_por_pagina": movimientos_por_pagina,
        "orden_manzanas": orden_manzanas,
        "incluir_manzanas_inactivas": "1" if incluir_inactivas else "0",
        "resumen": _opcion(request.GET.get("resumen"), permitidos={"conceptos", "manzanas", "ciudadanos"}, predeterminado="conceptos"),
        "concepto_indice": max(1, _opcion_entera(request.GET.get("concepto_indice"), permitidos=range(1, max(por_concepto.count(), 1) + 1), predeterminado=1)),
    }
    por_manzana, fila_general = _resumen_territorial(base, filtros, incluir_inactivas, orden_manzanas)
    monto_ciudadanos_visible = sum((fila["total_abonado"] for fila in mayores), Decimal("0.00"))
    aportaciones_ciudadanos_visibles = sum(fila["cantidad_aportaciones"] for fila in mayores)
    monto_movimientos_visible = sum((abono.monto for abono in movimientos), Decimal("0.00"))
    export_params = request.GET.copy()
    for parametro in ("page", "conceptos_page", "ciudadanos_pagina", "movimientos_pagina", *controles, "limite_ciudadanos", "limite_movimientos"):
        export_params.pop(parametro, None)
    buscar_params = {
        k: v for k, v in filtros.items()
        if k in {"mes", "anio", "naturaleza", "alcance", "manzana", "comite", "concepto"}
        and v not in ("", "todos", "todas")
    }
    if filtros["ciudadano"]:
        buscar_params["q"] = filtros["ciudadano"]
    params_retorno = {**{k: v for k, v in filtros.items() if v not in ("", "todos", "todas")}, **controles}
    return_to = f"{reverse('resumen_aportaciones')}?{urlencode(params_retorno)}"
    etiquetas_contexto = []
    if filtros["anio"].isdigit(): etiquetas_contexto.append(f"Año {filtros['anio']}")
    if filtros["mes"].isdigit() and 1 <= int(filtros["mes"]) <= 12: etiquetas_contexto.append(MESES[int(filtros["mes"]) - 1][1])
    if filtros["naturaleza"] in dict(ConceptoTesoreria.Naturalezas.choices):
        etiquetas_contexto.append("Pagos" if filtros["naturaleza"] == "PAGO" else "Cooperaciones")
    if filtros["alcance"] in dict(ConceptoTesoreria.Alcances.choices): etiquetas_contexto.append(dict(ConceptoTesoreria.Alcances.choices)[filtros["alcance"]])
    manzana_contexto = Manzana.objects.filter(pk=filtros["manzana"]).first() if filtros["manzana"].isdigit() else None
    comite_contexto = Comite.objects.filter(pk=filtros["comite"]).first() if filtros["comite"].isdigit() else None
    if manzana_contexto: etiquetas_contexto.append(str(manzana_contexto))
    if comite_contexto: etiquetas_contexto.append(comite_contexto.nombre)
    if filtros["concepto"]: etiquetas_contexto.append(f"Concepto: {filtros['concepto']}")
    if filtros["ciudadano"]: etiquetas_contexto.append(f"Ciudadano: {filtros['ciudadano']}")
    # El resumen por concepto es una agregación compacta: no carga obligaciones ni
    # ciudadanos individuales y permite recorrer el conjunto sin consultas N+1.
    conceptos_resumen = list(por_concepto)
    # Una tarjeta representa al concepto, no solamente a los conceptos que ya
    # tienen abonos. Completar la agregación con los conceptos recién creados
    # permite mostrar desde el inicio su avance en cero y su objetivo financiero.
    # Cuando se busca a un ciudadano conservamos la semántica anterior: sólo se
    # muestran conceptos en los que esa persona registra una aportación.
    if not filtros["ciudadano"]:
        parametros_conceptos = request.GET.copy()
        parametros_conceptos["q"] = filtros["concepto"]
        conceptos_presentes = {
            fila["obligacion__concepto_id"] for fila in conceptos_resumen
        }
        conceptos_sin_aportaciones = conceptos_filtrados(parametros_conceptos).exclude(
            pk__in=conceptos_presentes
        ).values(
            "pk", "concepto", "naturaleza", "comite__nombre", "alcance", "manzana__nombre",
        )
        for concepto in conceptos_sin_aportaciones:
            conceptos_resumen.append({
                "obligacion__concepto_id": concepto["pk"],
                "obligacion__concepto__concepto": concepto["concepto"],
                "obligacion__concepto__naturaleza": concepto["naturaleza"],
                "obligacion__concepto__comite__nombre": concepto["comite__nombre"],
                "obligacion__concepto__alcance": concepto["alcance"],
                "obligacion__concepto__manzana__nombre": concepto["manzana__nombre"],
                "total_recibido": Decimal("0.00"),
                "cantidad_abonos": 0,
                "ciudadanos_distintos": 0,
                "ultimo_movimiento": None,
            })
    # El objetivo financiero procede de las mismas obligaciones que alimentan
    # las tarjetas de Tesorería. Se obtiene en una sola consulta agrupada para
    # que la visualización no introduzca accesos por concepto (N+1).
    objetivos = ObligacionCiudadano.objects.filter(
        concepto_id__in=[fila["obligacion__concepto_id"] for fila in conceptos_resumen],
    ).exclude(estado=ObligacionCiudadano.Estados.CANCELADO).values(
        "concepto_id"
    ).annotate(total=Sum("monto_asignado"))
    objetivos_por_concepto = {fila["concepto_id"]: fila["total"] for fila in objetivos}
    datos_grafica_conceptos = []
    for fila in conceptos_resumen:
        fila["tesoreria_url"] = reverse("tesoreria_concepto_detalle", args=[fila["obligacion__concepto_id"]])
        objetivo = objetivos_por_concepto.get(fila["obligacion__concepto_id"])
        restante = max(objetivo - fila["total_recibido"], Decimal("0.00")) if objetivo is not None else None
        datos_grafica_conceptos.append({
            "nombre": fila["obligacion__concepto__concepto"],
            "aportado": float(fila["total_recibido"]),
            "objetivo": float(objetivo) if objetivo is not None else None,
            "restante": float(restante) if restante is not None else None,
            "porcentaje": float((fila["total_recibido"] / objetivo * 100) if objetivo else 0),
            "superado": bool(objetivo is not None and fila["total_recibido"] > objetivo),
        })
    conceptos_page = _pagina_aportaciones(request, conceptos_resumen, "conceptos_page", 10)
    compatibles = {k: v for k, v in filtros.items() if k in {"naturaleza", "alcance", "manzana", "comite", "mes", "anio"} and v not in ("todos", "todas", "")}
    if fila_general: fila_general["tesoreria_url"] = f"{reverse('tesoreria_operativa')}?{urlencode({**compatibles, 'alcance': 'GENERAL'})}"
    for fila in por_manzana:
        fila["tesoreria_url"] = f"{reverse('tesoreria_operativa')}?{urlencode({**compatibles, 'alcance': 'MANZANA', 'manzana': fila['manzana_id']})}"
    datos_grafica_manzanas = []
    if fila_general:
        datos_grafica_manzanas.append({"nombre": fila_general["nombre"], "total": float(fila_general["total_recibido"])})
    datos_grafica_manzanas.extend(
        {"nombre": fila["nombre"], "total": float(fila["total_recibido"])} for fila in por_manzana
    )
    datos_grafica_ciudadanos = [{
        "nombre": " ".join(filter(None, (
            fila["obligacion__ciudadano__nombre"], fila["obligacion__ciudadano__apellido_paterno"],
            fila["obligacion__ciudadano__apellido_materno"],
        ))),
        "total": float(fila["total_abonado"]),
    } for fila in mayores]
    return render(request, "dashboard/resumen_aportaciones.html", {
        "metricas": metricas,
        "conceptos_resumen": conceptos_resumen,
        # Alias conservado para integraciones que consumían el contexto anterior.
        "conceptos_page": conceptos_page,
        "cantidad_conceptos": len(conceptos_resumen),
        "manzanas_resumen": por_manzana, "movimientos_recientes": movimientos,
        "fila_general": fila_general,
        "manzanas_mostradas": len(por_manzana),
        "manzanas_sin_movimientos": sum(not fila["cantidad_abonos"] for fila in por_manzana),
        "total_territorial_recibido": sum((fila["total_recibido"] for fila in por_manzana), Decimal("0.00")),
        "movimientos_page": movimientos_page,
        "ciudadanos_page": ciudadanos_page,
        "mayores_aportaciones": mayores, "filtros": filtros, "meses": MESES,
        "anios": Abono.objects.dates("fecha", "year", order="DESC"), "comites": Comite.objects.filter(activo=True),
        "manzanas": Manzana.objects.order_by("nombre"), "hay_abonos": Abono.objects.exists(),
        "hay_filtros": any(v not in ("", "todos", "todas") for v in filtros.values()),
        "export_querystring": export_params.urlencode(),
        "buscar_querystring": urlencode(buscar_params),
        "limite_ciudadanos_actual": ciudadanos_por_pagina,
        "ciudadanos_por_pagina": ciudadanos_por_pagina,
        "opciones_limite_ciudadanos": opciones_limite_ciudadanos,
        "orden_ciudadanos_actual": orden_ciudadanos,
        "opciones_orden_ciudadanos": opciones_orden_ciudadanos,
        "orden_ciudadanos_etiqueta": dict(opciones_orden_ciudadanos)[orden_ciudadanos],
        "limite_movimientos_actual": movimientos_por_pagina,
        "movimientos_por_pagina": movimientos_por_pagina,
        "opciones_limite_movimientos": opciones_limite_movimientos,
        "orden_manzanas_actual": orden_manzanas,
        "opciones_orden_manzanas": opciones_orden_manzanas,
        "incluir_manzanas_inactivas": incluir_inactivas,
        "monto_ciudadanos_visible": monto_ciudadanos_visible,
        "aportaciones_ciudadanos_visibles": aportaciones_ciudadanos_visibles,
        "monto_movimientos_visible": monto_movimientos_visible,
        "ultimo_movimiento_id": ultimo_movimiento_id,
        "resumen_actual": controles["resumen"],
        "concepto_indice_actual": controles["concepto_indice"],
        "campos_control_ciudadanos": _campos_contexto_aportaciones(
            filtros, controles, excluir=("ciudadanos_por_pagina", "orden_ciudadanos", "ciudadanos_pagina"),
        ),
        "campos_control_movimientos": _campos_contexto_aportaciones(
            filtros, controles, excluir=("movimientos_por_pagina", "movimientos_pagina"),
        ),
        "campos_control_manzanas": _campos_contexto_aportaciones(
            filtros, controles, excluir=("orden_manzanas", "incluir_manzanas_inactivas"),
        ),
        "etiquetas_contexto": etiquetas_contexto,
        "return_to": return_to,
        "datos_grafica": {
            "conceptos": datos_grafica_conceptos,
            "manzanas": datos_grafica_manzanas,
            "ciudadanos": datos_grafica_ciudadanos,
        },
    })


@login_required
def exportar_aportaciones_csv(request):
    abonos = abonos_filtrados(request.GET).select_related(
        "obligacion__ciudadano", "obligacion__ciudadano__manzana", "obligacion__concepto",
        "obligacion__concepto__manzana", "obligacion__concepto__comite",
    ).order_by("-fecha", "-created_at", "-pk")
    partes = ["aportaciones"]
    naturaleza = request.GET.get("naturaleza")
    if naturaleza in dict(ConceptoTesoreria.Naturalezas.choices):
        partes.append(dict(ConceptoTesoreria.Naturalezas.choices)[naturaleza])
    if request.GET.get("manzana", "").isdigit():
        manzana = Manzana.objects.filter(pk=request.GET["manzana"]).first()
        if manzana:
            partes.append(str(manzana))
    nombre = slugify("_".join(partes))[:90] or "aportaciones"
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{nombre}_{timezone.localdate().isoformat()}.csv"'
    response.write("\ufeff")
    writer = csv.writer(response)
    writer.writerow(["ID de abono", "Fecha", "Ciudadano", "Nombre", "Apellido paterno", "Apellido materno", "No. de contrato", "Manzana actual", "Naturaleza", "Concepto", "Comité", "Alcance", "Manzana del concepto", "Monto abonado", "Estado de la obligación"])
    for abono in abonos.iterator(chunk_size=1000):
        obligacion, concepto, ciudadano = abono.obligacion, abono.obligacion.concepto, abono.obligacion.ciudadano
        writer.writerow([
            abono.pk, abono.fecha.isoformat(), ciudadano.nombre_completo, ciudadano.nombre,
            ciudadano.apellido_paterno, ciudadano.apellido_materno or "Sin información",
            ciudadano.numero_contrato or "Sin asignar", str(ciudadano.manzana) if ciudadano.manzana_id else "Sin asignar",
            concepto.get_naturaleza_display(), concepto.concepto, concepto.comite.nombre,
            concepto.get_alcance_display(), str(concepto.manzana) if concepto.manzana_id else "Sin asignar",
            abono.monto, obligacion.get_estado_display(),
        ])
    return response


@login_required
def crear_concepto_tesoreria(request, pk=None):
    concepto = get_object_or_404(ConceptoTesoreria, pk=pk) if pk else None
    if not _can_modify_tesoreria(request.user):
        messages.error(request, "No tienes permisos para modificar tesorería.")
        return redirect("tesoreria_operativa")
    form = ConceptoTesoreriaForm(request.POST or None, instance=concepto)
    if request.method == "POST" and form.is_valid():
        obj = form.save()
        messages.success(request, "Se guardó correctamente el concepto de tesorería.")
        return redirect("tesoreria_concepto_detalle", obj.pk)
    can_delete = bool(concepto and _can_delete_tesoreria(request.user))
    delete_url = reverse("eliminar_concepto_tesoreria", args=[concepto.pk]) if can_delete else ""
    return render(request, "dashboard/tesoreria_form.html", {"form": form, "concepto": concepto, "cancel_url": reverse("tesoreria_operativa"), "can_delete": can_delete, "delete_url": delete_url})


@login_required
def eliminar_concepto_tesoreria(request, pk):
    concepto = get_object_or_404(ConceptoTesoreria.objects.select_related("comite", "manzana"), pk=pk)
    if not _can_delete_tesoreria(request.user):
        messages.error(request, "No tienes permisos para eliminar conceptos de tesorería.")
        return redirect("tesoreria_operativa")
    obligaciones = ObligacionCiudadano.objects.filter(concepto=concepto)
    cantidad_obligaciones = obligaciones.count()
    obligaciones_pendientes = obligaciones.filter(estado=ObligacionCiudadano.Estados.PENDIENTE).count()
    obligaciones_pagadas = obligaciones.filter(estado=ObligacionCiudadano.Estados.PAGADO).count()
    abonos = Abono.objects.filter(obligacion__concepto=concepto)
    cantidad_abonos = abonos.count()
    total_abonado = abonos.aggregate(total=Sum("monto"))["total"] or Decimal("0.00")
    if request.method == "POST":
        try:
            with transaction.atomic():
                concepto.delete()
        except ProtectedError:
            messages.error(request, "No se pudo eliminar porque existen registros protegidos relacionados.")
            return redirect("tesoreria_concepto_detalle", pk)
        messages.success(request, "El concepto de tesorería fue eliminado correctamente.")
        return redirect("tesoreria_operativa")
    return render(request, "dashboard/confirmar_eliminacion.html", {"object_type": "concepto de tesorería", "object_label": concepto.concepto, "warning_message": "Esta acción eliminará permanentemente el concepto, todas sus obligaciones ciudadanas y todos los abonos asociados. El historial eliminado no podrá recuperarse.", "cancel_url": reverse("tesoreria_concepto_detalle", args=[concepto.pk]), "deletion_summary": [{"label": "Concepto", "value": concepto.concepto}, {"label": "Naturaleza", "value": concepto.get_naturaleza_display()}, {"label": "Fecha", "value": concepto.fecha}, {"label": "Comité", "value": concepto.comite.nombre}, {"label": "Cantidad de obligaciones", "value": cantidad_obligaciones}, {"label": "Obligaciones pendientes", "value": obligaciones_pendientes}, {"label": "Obligaciones pagadas", "value": obligaciones_pagadas}, {"label": "Cantidad de abonos", "value": cantidad_abonos}, {"label": "Total abonado histórico", "value": _money(total_abonado)}]})


@login_required
@require_POST
def generar_obligaciones_tesoreria(request, pk):
    if not _can_modify_tesoreria(request.user):
        messages.error(request, "No tienes permisos para generar obligaciones.")
        return redirect("tesoreria_operativa")
    concepto = get_object_or_404(ConceptoTesoreria.objects.select_related("manzana"), pk=pk)
    try:
        resultado = generar_obligaciones_faltantes(concepto)
    except ValidationError as error:
        detalle = "; ".join(error.messages)
        messages.error(request, f"No se generaron obligaciones: {detalle}")
        return redirect("tesoreria_operativa")

    if resultado.total_objetivo == 0:
        messages.warning(request, "No existen ciudadanos activos para el alcance seleccionado.")
    elif resultado.creados == 0:
        messages.info(request, "Todas las obligaciones del alcance seleccionado ya estaban generadas.")
    elif resultado.existentes:
        messages.success(
            request,
            f"Se crearon {resultado.creados} obligaciones. {resultado.existentes} ya existían.",
        )
    else:
        territorio = (
            str(concepto.manzana)
            if concepto.alcance == concepto.Alcances.MANZANA
            else "toda la comunidad"
        )
        messages.success(request, f"Se crearon {resultado.creados} obligaciones para {territorio}.")
    return redirect("tesoreria_operativa")


def _filtros_obligaciones(params):
    return {campo: params.get(campo, defecto) for campo, defecto in (
        ("q", ""), ("estado", "todos"), ("manzana", "todas"), ("sexo", "todos"),
        ("rango_edad", "todas"), ("motivo_alta", "todos"), ("saldo", "todos"),
    )}


def _metricas_concepto(concepto):
    obligaciones = ObligacionCiudadano.objects.filter(concepto=concepto)
    resumen = obligaciones.aggregate(
        total=Count("pk"), pagadas=Count("pk", filter=Q(estado=ObligacionCiudadano.Estados.PAGADO)),
        pendientes=Count("pk", filter=Q(estado=ObligacionCiudadano.Estados.PENDIENTE)),
        canceladas=Count("pk", filter=Q(estado=ObligacionCiudadano.Estados.CANCELADO)),
        total_asignado=Sum("monto_asignado", filter=~Q(estado=ObligacionCiudadano.Estados.CANCELADO)),
    )
    resumen["total_asignado"] = resumen["total_asignado"] or Decimal("0.00")
    # Alias conservado para integraciones internas anteriores; la interfaz usa "asignado".
    resumen["total_generado"] = resumen["total_asignado"]
    resumen["total_abonado"] = Abono.objects.filter(
        obligacion__concepto=concepto,
        obligacion__estado__in=[ObligacionCiudadano.Estados.PENDIENTE, ObligacionCiudadano.Estados.PAGADO],
    ).aggregate(total=Sum("monto"))["total"] or Decimal("0.00")
    resumen["saldo_pendiente"] = max(resumen["total_asignado"] - resumen["total_abonado"], Decimal("0.00"))
    aplicables = resumen["pagadas"] + resumen["pendientes"]
    resumen["porcentaje_cumplimiento"] = round(resumen["pagadas"] / aplicables * 100, 1) if aplicables else 0
    resumen["estado_general"] = "SIN_GENERAR" if not resumen["total"] else ("CON_PENDIENTES" if resumen["pendientes"] else "COMPLETADO")
    resumen["estado_general_label"] = _etiqueta_estado_general(resumen["estado_general"])
    return resumen


@login_required
def tesoreria_concepto_detalle(request, pk):
    concepto = get_object_or_404(ConceptoTesoreria.objects.select_related("comite", "manzana"), pk=pk)
    metricas = _metricas_concepto(concepto)
    concepto.cantidad_obligaciones = metricas["total"]
    concepto.cantidad_pagada = metricas["pagadas"]
    concepto.cantidad_pendiente = metricas["pendientes"]
    concepto.cantidad_cancelada = metricas["canceladas"]
    obligaciones = anotar_obligaciones(ObligacionCiudadano.objects.filter(concepto=concepto))
    obligaciones = aplicar_filtros_obligaciones(obligaciones, request.GET).prefetch_related(
        Prefetch("abonos", queryset=Abono.objects.order_by("-fecha", "-created_at"))
    )
    page = Paginator(obligaciones, 25).get_page(request.GET.get("page"))
    page.previous_querystring = _page_querystring(request, "page", page.previous_page_number()) if page.has_previous() else ""
    page.next_querystring = _page_querystring(request, "page", page.next_page_number()) if page.has_next() else ""
    export_params = request.GET.copy(); export_params.pop("page", None)
    filtros = _filtros_obligaciones(request.GET)
    return render(request, "dashboard/tesoreria_detalle.html", {
        "concepto": concepto, "obligaciones": page.object_list, "page_obj": page, "filtros": filtros,
        "metricas": metricas, "manzanas": Manzana.objects.order_by("nombre"), "sexos": Ciudadano.Sexos.choices,
        "motivos_alta": Ciudadano.MotivosAlta.choices, "can_modify": _can_modify_tesoreria(request.user),
        "export_querystring": export_params.urlencode(), "current_querystring": export_params.urlencode(),
    })


@login_required
def exportar_obligaciones_tesoreria_csv(request, pk):
    concepto = get_object_or_404(ConceptoTesoreria.objects.select_related("manzana"), pk=pk)
    obligaciones = aplicar_filtros_obligaciones(
        anotar_obligaciones(ObligacionCiudadano.objects.filter(concepto=concepto)), request.GET
    )
    partes = ["obligaciones", concepto.get_naturaleza_display(), concepto.concepto]
    if concepto.manzana_id: partes.append(str(concepto.manzana))
    nombre = slugify("_".join(partes))[:100] or f"obligaciones-{concepto.pk}"
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{nombre}_{timezone.localdate().isoformat()}.csv"'
    response.write("\ufeff"); writer = csv.writer(response)
    writer.writerow(["Ciudadano", "Nombre", "Apellido paterno", "Apellido materno", "No. de contrato", "Manzana actual", "Sexo", "Fecha de nacimiento", "Edad actual", "Motivo de alta", "Monto asignado", "Total abonado", "Saldo pendiente", "Estado", "Último abono"])
    for o in obligaciones.iterator():
        c = o.ciudadano
        writer.writerow([c.nombre_completo, c.nombre, c.apellido_paterno, c.apellido_materno or "Sin información",
            c.numero_contrato or "Sin información", str(c.manzana) if c.manzana_id else "Sin asignar",
            c.get_sexo_display() or "No especificado", c.fecha_nacimiento.isoformat() if c.fecha_nacimiento else "Sin información",
            c.edad_actual if c.edad_actual is not None else "Sin información", c.get_motivo_alta_display() or "Sin información",
            o.monto_asignado, o.total_abonado_calc, o.saldo_pendiente_calc, o.get_estado_display(),
            o.ultimo_abono.isoformat() if o.ultimo_abono else "Sin información"])
    return response


@login_required
def acreditar_obligacion(request, pk):
    obligacion = get_object_or_404(ObligacionCiudadano.objects.select_related("ciudadano", "concepto"), pk=pk)
    if not _can_modify_tesoreria(request.user):
        messages.error(request, "No tienes permisos para acreditar pagos.")
        return redirect("tesoreria_concepto_detalle", obligacion.concepto_id)
    if request.method == "POST":
        form = AbonoForm(request.POST, obligacion=obligacion)
        if form.is_valid():
            try:
                obligacion.acreditar(form.cleaned_data["monto"], form.cleaned_data["fecha"], form.cleaned_data["notas"])
                messages.success(request, "Se registró correctamente el abono.")
                siguiente = request.POST.get("next", "")
                if siguiente.startswith(f"/tesoreria/conceptos/{obligacion.concepto_id}/"):
                    return redirect(siguiente)
                return redirect("tesoreria_concepto_detalle", obligacion.concepto_id)
            except Exception as exc:
                form.add_error(None, exc)
    else:
        form = AbonoForm(obligacion=obligacion)
    siguiente = request.GET.get("next", "")
    return render(request, "dashboard/tesoreria_abono_form.html", {"form": form, "obligacion": obligacion, "abonos": obligacion.abonos.all(), "next": siguiente})
