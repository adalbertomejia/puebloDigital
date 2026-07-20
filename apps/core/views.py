import csv
from itertools import chain
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpResponse, JsonResponse
from django import forms
from django.db import transaction
from django.db.models import Count, Max, Q, Sum
from django.db.models.functions import ExtractYear
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.urls import reverse

from apps.agua.models import Toma
from apps.operacion.models import AsistenciaJunta, Faena, Junta, RegistroFaena
from apps.tesoreria.models import Cooperacion, Pago

from .forms import CiudadanoOperativoForm, DashboardFormMixin, FaenaOperativaForm, JuntaOperativaForm
from .models import Ciudadano


class EstadoEventoForm(DashboardFormMixin, forms.Form):
    estado = forms.ChoiceField(label="Nuevo estado")

    def __init__(self, *args, choices=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["estado"].choices = choices
        self._apply_dashboard_widgets()


def _ciudadanos_operativos_queryset():
    return Ciudadano.objects.select_related("toma").annotate(
        ultimo_pago_fecha=Max("pagos__fecha"),
        adeudos_faena=Count("registros_faena", filter=Q(registros_faena__genera_adeudo=True), distinct=True),
    )


def _filtrar_ciudadanos_operativos(queryset, params):
    q = params.get("q", "").strip()
    estado = params.get("estado", "todos")
    toma = params.get("toma", "todos")
    adeudo = params.get("adeudo", "todos")

    if q:
        search_filter = (
            Q(nombre__icontains=q)
            | Q(apellido_paterno__icontains=q)
            | Q(apellido_materno__icontains=q)
            | Q(telefono__icontains=q)
            | Q(toma__numero_toma__icontains=q)
        )
        if q.isdigit():
            search_filter |= Q(id=int(q))
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

    ordering = params.get("orden", "nombre")
    orderings = {
        "nombre": ["apellido_paterno", "apellido_materno", "nombre"],
        "estado": ["-activo", "apellido_paterno", "apellido_materno", "nombre"],
        "adeudos_faena": ["-adeudos_faena", "apellido_paterno", "apellido_materno", "nombre"],
        "registro": ["-created_at", "apellido_paterno", "apellido_materno", "nombre"],
    }
    return queryset.order_by(*orderings.get(ordering, orderings["nombre"]))


@login_required
def padron_ciudadanos(request):
    ciudadanos_qs = _filtrar_ciudadanos_operativos(_ciudadanos_operativos_queryset(), request.GET)
    paginator = Paginator(ciudadanos_qs, 20)
    ciudadanos_page = paginator.get_page(request.GET.get("page"))

    context = {
        "ciudadanos": ciudadanos_page,
        "filtros": {
            "q": request.GET.get("q", "").strip(),
            "estado": request.GET.get("estado", "todos"),
            "toma": request.GET.get("toma", "todos"),
            "adeudo": request.GET.get("adeudo", "todos"),
            "orden": request.GET.get("orden", "nombre"),
        },
        "metricas": {
            "total": Ciudadano.objects.count(),
            "activos": Ciudadano.objects.filter(activo=True).count(),
            "inactivos": Ciudadano.objects.filter(activo=False).count(),
            "sin_toma": Ciudadano.objects.filter(toma__isnull=True).count(),
            "con_adeudo": RegistroFaena.objects.filter(genera_adeudo=True).values("ciudadano").distinct().count(),
        },
        "crear_ciudadano_url": reverse("crear_ciudadano_operativo"),
        "exportar_ciudadanos_url": reverse("exportar_ciudadanos_csv"),
        "exportar_ciudadanos_querystring": urlencode(
            {key: value for key, value in request.GET.items() if key != "page" and value}
        ),
    }
    return render(request, "dashboard/padron_ciudadanos.html", context)


@login_required
def exportar_ciudadanos_csv(request):
    ciudadanos = _filtrar_ciudadanos_operativos(_ciudadanos_operativos_queryset(), request.GET)
    filename = f"ciudadanos_{timezone.localdate().isoformat()}.csv"
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
        "Teléfono",
        "Edad",
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
            ciudadano.telefono or "",
            ciudadano.edad,
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
        Ciudadano.objects.select_related("toma")
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
            | Q(telefono__icontains=q)
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
        Junta.objects.select_related("comite")
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
    return render(request, "dashboard/operativo.html", context)


def _evento_operativo_form_view(
    request,
    form_class,
    event_label,
    description,
    detail_url_name,
    *,
    instance=None,
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
    )


@login_required
def editar_junta_operativa(request, junta_id):
    junta = get_object_or_404(Junta.objects.select_related("comite"), pk=junta_id)
    return _evento_operativo_form_view(
        request,
        JuntaOperativaForm,
        "Junta",
        "Actualiza la información operativa de la junta sin salir del flujo de Control de Asistencias.",
        "control_asistencias_junta_detalle",
        instance=junta,
    )


@login_required
def generar_registros_faena(request, faena_id):
    if request.method != "POST":
        return redirect("dashboard_operativo")

    faena = get_object_or_404(Faena, pk=faena_id)
    if faena.estado != Faena.Estados.PROGRAMADA:
        messages.error(request, "Solo se pueden generar registros para faenas programadas.")
        return redirect("dashboard_operativo")
    if faena.registros.exists():
        messages.info(request, "Esta faena ya tiene registros generados; continúa la captura desde Control de Asistencias.")
        return redirect("dashboard_operativo")
    ciudadanos_ids = list(Ciudadano.objects.filter(activo=True).values_list("id", flat=True))
    existentes_ids = set(RegistroFaena.objects.filter(faena=faena, ciudadano_id__in=ciudadanos_ids).values_list("ciudadano_id", flat=True))

    nuevos = [
        RegistroFaena(faena=faena, ciudadano_id=cid, estatus=RegistroFaena.Estatus.PENDIENTE)
        for cid in ciudadanos_ids
        if cid not in existentes_ids
    ]

    if nuevos:
        RegistroFaena.objects.bulk_create(nuevos, batch_size=500)

    messages.success(request, f"Se generaron {len(nuevos)} registros pendientes para la faena '{faena.descripcion}'.")
    return redirect("dashboard_operativo")


@login_required
def generar_registros_junta(request, junta_id):
    if request.method != "POST":
        return redirect("dashboard_operativo")

    junta = get_object_or_404(Junta, pk=junta_id)
    if junta.estado != Junta.Estados.PROGRAMADA:
        messages.error(request, "Solo se pueden generar registros para juntas programadas.")
        return redirect("dashboard_operativo")
    if junta.asistencias.exists():
        messages.info(request, "Esta junta ya tiene registros generados; continúa la captura desde Control de Asistencias.")
        return redirect("dashboard_operativo")
    ciudadanos_ids = list(Ciudadano.objects.filter(activo=True).values_list("id", flat=True))
    existentes_ids = set(
        AsistenciaJunta.objects.filter(junta=junta, ciudadano_id__in=ciudadanos_ids).values_list(
            "ciudadano_id", flat=True
        )
    )

    nuevos = [
        AsistenciaJunta(junta=junta, ciudadano_id=cid, estatus=AsistenciaJunta.Estatus.PENDIENTE, asistio=False)
        for cid in ciudadanos_ids
        if cid not in existentes_ids
    ]

    if nuevos:
        AsistenciaJunta.objects.bulk_create(nuevos, batch_size=500)

    messages.success(request, f"Se generaron {len(nuevos)} registros pendientes para la junta '{junta.tema}'.")
    return redirect("dashboard_operativo")


def _attendance_queryset(model, relation_name, pending_status):
    """Annotate event querysets with operational attendance metrics."""
    return model.objects.select_related("comite").annotate(
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
    q = params.get("q", "").strip()
    mes = params.get("mes", "todos")
    anio = params.get("anio", "todos")

    if q:
        search_filter = (
            Q(**{f"{description_field}__icontains": q})
            | Q(comite__nombre__icontains=q)
            | Q(estado__icontains=q)
        )
        if tipo_actividad.lower().startswith(q.lower()) or q.lower() in tipo_actividad.lower():
            search_filter |= Q(pk__isnull=False)
        queryset = queryset.filter(search_filter)

    if mes != "todos" and mes.isdigit():
        queryset = queryset.filter(fecha__month=int(mes))

    if anio != "todos" and anio.isdigit():
        queryset = queryset.filter(fecha__year=int(anio))

    return queryset.order_by("-fecha", "-created_at")


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
            },
            "meses": MESES,
            "anios": _attendance_years(),
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
    writer.writerow([
        "Numero",
        "Nombre completo",
        "Estado",
        "Fecha",
        "Tipo de evento",
        "Descripcion",
        "Genera adeudo",
        "Monto adeudo",
        "Observaciones",
    ])

    registros = registros.select_related("ciudadano").order_by(
        "ciudadano__apellido_paterno",
        "ciudadano__apellido_materno",
        "ciudadano__nombre",
        "pk",
    )
    for numero, registro in enumerate(registros, start=1):
        writer.writerow([
            numero,
            registro.ciudadano.nombre_completo,
            registro.estatus,
            event.fecha.isoformat(),
            event_type,
            description,
            "Sí" if registro.genera_adeudo else "No",
            registro.monto_adeudo,
            registro.observaciones,
        ])

    return response


@login_required
def control_asistencias_faena_detalle(request, faena_id):
    faena = get_object_or_404(Faena.objects.select_related("comite"), pk=faena_id)
    context = _event_detail_context(faena, faena.registros.all(), "Faena", faena.descripcion)
    context["admin_change_url"] = reverse("editar_faena_operativa", args=[faena.pk])
    context["capture_url"] = reverse("captura_asistencia_faena", args=[faena.pk])
    context["sequential_capture_url"] = reverse("captura_asistencia_secuencial_faena", args=[faena.pk])
    context["estado_edit_url"] = reverse("editar_estado_evento", args=["faena", faena.pk])
    context["export_csv_url"] = reverse("exportar_participantes_faena_csv", args=[faena.pk])
    return render(request, "dashboard/control_asistencias_detalle.html", context)


@login_required
def control_asistencias_junta_detalle(request, junta_id):
    junta = get_object_or_404(Junta.objects.select_related("comite"), pk=junta_id)
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
    junta = get_object_or_404(Junta.objects.select_related("comite"), pk=junta_id)
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
    event = get_object_or_404(config["event_model"].objects.select_related("comite"), pk=event_id)
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
    event = get_object_or_404(config["event_model"].objects.select_related("comite"), pk=event_id)
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
    ciudadano = get_object_or_404(Ciudadano.objects.select_related("toma"), pk=pk)

    pagos = ciudadano.pagos.select_related("comite").order_by("-fecha", "-created_at")[:10]
    cooperaciones = ciudadano.cooperaciones.select_related("comite").order_by("-fecha", "-created_at")[:10]
    registros_faena = ciudadano.registros_faena.select_related("faena", "faena__comite").order_by("-faena__fecha")[:10]

    resumen = {
        "adeudos_faena": ciudadano.registros_faena.filter(genera_adeudo=True).count(),
        "ultimo_pago": ciudadano.pagos.order_by("-fecha").first(),
        "ultima_faena": ciudadano.registros_faena.select_related("faena").order_by("-faena__fecha").first(),
    }

    return render(
        request,
        "dashboard/perfil_ciudadano.html",
        {
            "ciudadano": ciudadano,
            "pagos": pagos,
            "cooperaciones": cooperaciones,
            "registros_faena": registros_faena,
            "resumen": resumen,
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


def _tesoreria_conceptos_queryset(params):
    qs = ConceptoTesoreria.objects.select_related("comite").annotate(
        cantidad_obligaciones=Count("obligaciones", distinct=True),
        cantidad_pagada=Count("obligaciones", filter=Q(obligaciones__estado=ObligacionCiudadano.Estados.PAGADO), distinct=True),
        cantidad_pendiente=Count("obligaciones", filter=Q(obligaciones__estado=ObligacionCiudadano.Estados.PENDIENTE), distinct=True),
        total_generado=Sum("obligaciones__monto_asignado"),
        total_abonado=Sum("obligaciones__abonos__monto"),
    )
    q = params.get("q", "").strip()
    if q:
        qs = qs.filter(Q(concepto__icontains=q) | Q(descripcion__icontains=q) | Q(comite__nombre__icontains=q))
    if params.get("naturaleza", "todos") in dict(ConceptoTesoreria.Naturalezas.choices):
        qs = qs.filter(naturaleza=params["naturaleza"])
    if params.get("mes", "todos").isdigit():
        qs = qs.filter(fecha__month=int(params["mes"]))
    if params.get("anio", "todos").isdigit():
        qs = qs.filter(fecha__year=int(params["anio"]))
    if params.get("comite", "todos").isdigit():
        qs = qs.filter(comite_id=int(params["comite"]))
    estado = params.get("estado", "todos")
    if estado == "SIN_GENERAR":
        qs = qs.filter(cantidad_obligaciones=0)
    elif estado == "CON_PENDIENTES":
        qs = qs.filter(cantidad_pendiente__gt=0)
    elif estado == "COMPLETADO":
        qs = qs.filter(cantidad_obligaciones__gt=0, cantidad_pendiente=0)
    return qs.order_by("-fecha", "-created_at")


def _decorate_tesoreria_concepts(concepts):
    for c in concepts:
        c.total_generado = c.total_generado or 0
        c.total_abonado = c.total_abonado or 0
        c.saldo_pendiente = c.total_generado - c.total_abonado
        if c.cantidad_obligaciones == 0:
            c.estado_general = "SIN_GENERAR"
            c.estado_general_label = "Sin generar"
        elif c.cantidad_pendiente:
            c.estado_general = "CON_PENDIENTES"
            c.estado_general_label = "Con pendientes"
        else:
            c.estado_general = "COMPLETADO"
            c.estado_general_label = "Completado"
    return concepts


@login_required
def tesoreria_operativa(request):
    conceptos_qs = _tesoreria_conceptos_queryset(request.GET)

    conceptos_con_obligaciones = ConceptoTesoreria.objects.annotate(
        total_obligaciones=Count("obligaciones", distinct=True),
        pendientes=Count(
            "obligaciones",
            filter=Q(obligaciones__estado=ObligacionCiudadano.Estados.PENDIENTE),
            distinct=True,
        ),
    )
    conceptos_en_cobro = conceptos_con_obligaciones.filter(total_obligaciones__gt=0, pendientes__gt=0).count()
    conceptos_completados = conceptos_con_obligaciones.filter(total_obligaciones__gt=0, pendientes=0).count()
    hoy = timezone.localdate()
    recaudado_mes = Abono.objects.filter(fecha__year=hoy.year, fecha__month=hoy.month).aggregate(total=Sum("monto"))["total"] or 0
    ciudadanos_conceptos_pendientes = (
        ObligacionCiudadano.objects.filter(estado=ObligacionCiudadano.Estados.PENDIENTE)
        .values("ciudadano_id")
        .distinct()
        .count()
    )

    paginator = Paginator(conceptos_qs, 12)
    conceptos_page = paginator.get_page(request.GET.get("page"))
    conceptos_page.previous_querystring = _page_querystring(request, "page", conceptos_page.previous_page_number()) if conceptos_page.has_previous() else ""
    conceptos_page.next_querystring = _page_querystring(request, "page", conceptos_page.next_page_number()) if conceptos_page.has_next() else ""
    return render(request, "dashboard/tesoreria.html", {
        "conceptos": _decorate_tesoreria_concepts(conceptos_page.object_list),
        "page_obj": conceptos_page,
        "metricas": {
            "conceptos_en_cobro": conceptos_en_cobro,
            "conceptos_completados": conceptos_completados,
            "recaudado_mes": recaudado_mes,
            "ciudadanos_conceptos_pendientes": ciudadanos_conceptos_pendientes,
        },
        "filtros": {"q": request.GET.get("q", "").strip(), "naturaleza": request.GET.get("naturaleza", "todos"), "mes": request.GET.get("mes", "todos"), "anio": request.GET.get("anio", "todos"), "estado": request.GET.get("estado", "todos"), "comite": request.GET.get("comite", "todos")},
        "meses": MESES,
        "anios": sorted(set(ConceptoTesoreria.objects.annotate(year=ExtractYear("fecha")).values_list("year", flat=True)), reverse=True),
        "comites": Comite.objects.filter(activo=True),
        "can_modify": _can_modify_tesoreria(request.user),
    })


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
    return render(request, "dashboard/tesoreria_form.html", {"form": form, "concepto": concepto, "cancel_url": reverse("tesoreria_operativa")})


@login_required
def generar_obligaciones_tesoreria(request, pk):
    if request.method != "POST":
        return redirect("tesoreria_operativa")
    if not _can_modify_tesoreria(request.user):
        messages.error(request, "No tienes permisos para generar obligaciones.")
        return redirect("tesoreria_operativa")
    concepto = get_object_or_404(ConceptoTesoreria, pk=pk)
    with transaction.atomic():
        ids = list(Ciudadano.objects.filter(activo=True).values_list("id", flat=True))
        existentes = set(ObligacionCiudadano.objects.filter(concepto=concepto, ciudadano_id__in=ids).values_list("ciudadano_id", flat=True))
        nuevos = [ObligacionCiudadano(concepto=concepto, ciudadano_id=i, monto_asignado=concepto.monto_individual) for i in ids if i not in existentes]
        if nuevos:
            ObligacionCiudadano.objects.bulk_create(nuevos, batch_size=500)
        concepto.registros_generados = True
        concepto.save(update_fields=["registros_generados", "updated_at"])
    messages.success(request, f"Se crearon {len(nuevos)} obligaciones. {len(existentes)} obligaciones ya existían y fueron omitidas.")
    return redirect("tesoreria_operativa")


@login_required
def tesoreria_concepto_detalle(request, pk):
    concepto = get_object_or_404(ConceptoTesoreria.objects.select_related("comite"), pk=pk)
    obligaciones = ObligacionCiudadano.objects.filter(concepto=concepto).select_related("ciudadano").annotate(total_abonado_anno=Sum("abonos__monto"), ultimo_abono=Max("abonos__fecha"))
    q = request.GET.get("q", "").strip()
    if q:
        obligaciones = obligaciones.filter(Q(ciudadano__nombre__icontains=q) | Q(ciudadano__apellido_paterno__icontains=q) | Q(ciudadano__apellido_materno__icontains=q))
    estado = request.GET.get("estado", "todos")
    if estado in dict(ObligacionCiudadano.Estados.choices):
        obligaciones = obligaciones.filter(estado=estado)
    paginator = Paginator(obligaciones, 20)
    page = paginator.get_page(request.GET.get("page"))
    page.previous_querystring = _page_querystring(request, "page", page.previous_page_number()) if page.has_previous() else ""
    page.next_querystring = _page_querystring(request, "page", page.next_page_number()) if page.has_next() else ""
    decorated = []
    for o in page.object_list:
        o.total_abonado_calc = o.total_abonado_anno or 0
        o.saldo_pendiente_calc = o.monto_asignado - o.total_abonado_calc
        decorated.append(o)
    metricas = obligaciones.aggregate(total_generado=Sum("monto_asignado"), total_abonado=Sum("abonos__monto"), pendientes=Count("id", filter=Q(estado=ObligacionCiudadano.Estados.PENDIENTE)), pagadas=Count("id", filter=Q(estado=ObligacionCiudadano.Estados.PAGADO)))
    concepto_decorado = _decorate_tesoreria_concepts([ConceptoTesoreria.objects.filter(pk=pk).annotate(cantidad_obligaciones=Count("obligaciones", distinct=True), cantidad_pagada=Count("obligaciones", filter=Q(obligaciones__estado=ObligacionCiudadano.Estados.PAGADO), distinct=True), cantidad_pendiente=Count("obligaciones", filter=Q(obligaciones__estado=ObligacionCiudadano.Estados.PENDIENTE), distinct=True), total_generado=Sum("obligaciones__monto_asignado"), total_abonado=Sum("obligaciones__abonos__monto")).get()])[0]
    return render(request, "dashboard/tesoreria_detalle.html", {"concepto": concepto_decorado, "obligaciones": decorated, "page_obj": page, "filtros": {"q": q, "estado": estado}, "metricas": {"total_generado": metricas["total_generado"] or 0, "total_abonado": metricas["total_abonado"] or 0, "saldo_pendiente": (metricas["total_generado"] or 0) - (metricas["total_abonado"] or 0), "pendientes": metricas["pendientes"] or 0, "pagadas": metricas["pagadas"] or 0}, "can_modify": _can_modify_tesoreria(request.user)})


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
                return redirect("tesoreria_concepto_detalle", obligacion.concepto_id)
            except Exception as exc:
                form.add_error(None, exc)
    else:
        form = AbonoForm(obligacion=obligacion)
    return render(request, "dashboard/tesoreria_abono_form.html", {"form": form, "obligacion": obligacion, "abonos": obligacion.abonos.all()})
