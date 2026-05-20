from itertools import chain

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db import transaction
from django.db.models import Count, Max, Q, Sum
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.agua.models import Toma
from apps.operacion.models import Faena, RegistroFaena
from apps.tesoreria.models import Cooperacion, Pago

from .models import Ciudadano


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

    ciudadanos = ciudadanos_qs[:12]

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
        "ciudadanos": ciudadanos,
        "actividad_reciente": actividad_reciente,
        "tarjeta_agua": tarjeta_agua,
        "tarjeta_faena": tarjeta_faena,
        "quick_links": {
            "pago_add": reverse("admin:tesoreria_pago_add"),
            "cooperacion_add": reverse("admin:tesoreria_cooperacion_add"),
            "registro_faena_add": reverse("admin:operacion_registrofaena_add"),
            "faena_changelist": reverse("admin:operacion_faena_changelist"),
            "ciudadano_changelist": reverse("admin:core_ciudadano_changelist"),
        },
    }
    return render(request, "dashboard/operativo.html", context)


@login_required
@permission_required("operacion.view_faena", raise_exception=True)
def faenas_operativas(request):
    estado = request.GET.get("estado", "")
    q = request.GET.get("q", "").strip()

    faenas = Faena.objects.select_related("comite").annotate(
        total_participantes=Count("registros"),
        pendientes=Count("registros", filter=Q(registros__estado=RegistroFaena.EstadosAsistencia.PENDIENTE)),
    )

    if estado:
        faenas = faenas.filter(estado=estado)

    if q:
        faenas = faenas.filter(Q(descripcion__icontains=q) | Q(comite__nombre__icontains=q))

    faenas = faenas.order_by("-fecha", "-created_at")

    return render(request, "dashboard/faenas_operativas.html", {
        "faenas": faenas,
        "estado": estado,
        "q": q,
        "estados": Faena.Estados,
    })


@login_required
@permission_required("operacion.view_faena", raise_exception=True)
def faena_operativa(request, pk):
    faena = get_object_or_404(Faena.objects.select_related("comite"), pk=pk)
    q = request.GET.get("q", "").strip()
    estado = request.GET.get("estado", "")

    registros = RegistroFaena.objects.select_related("ciudadano", "faena").filter(faena=faena)
    if q:
        registros = registros.filter(
            Q(ciudadano__nombre__icontains=q)
            | Q(ciudadano__apellido_paterno__icontains=q)
            | Q(ciudadano__apellido_materno__icontains=q)
        )
    if estado:
        registros = registros.filter(estado=estado)

    resumen = faena.registros.aggregate(
        total=Count("id"),
        pendientes=Count("id", filter=Q(estado=RegistroFaena.EstadosAsistencia.PENDIENTE)),
        asistieron=Count("id", filter=Q(estado=RegistroFaena.EstadosAsistencia.ASISTIO)),
        faltaron=Count("id", filter=Q(estado=RegistroFaena.EstadosAsistencia.FALTO)),
        justificados=Count("id", filter=Q(estado=RegistroFaena.EstadosAsistencia.JUSTIFICADO)),
    )
    can_edit = request.user.has_perm("operacion.change_registrofaena") and faena.estado != Faena.Estados.CERRADA
    return render(request, "dashboard/faena_operativa.html", {
        "faena": faena,
        "registros": registros.order_by("ciudadano__apellido_paterno", "ciudadano__apellido_materno", "ciudadano__nombre"),
        "resumen": resumen,
        "estado_actual": estado,
        "q": q,
        "estados": RegistroFaena.EstadosAsistencia,
        "can_edit": can_edit,
        "can_close": request.user.has_perm("operacion.change_faena") and faena.estado != Faena.Estados.CERRADA,
    })


@login_required
@permission_required("operacion.change_registrofaena", raise_exception=True)
@require_POST
def actualizar_estado_faena(request, pk):
    registro = get_object_or_404(RegistroFaena.objects.select_related("faena", "ciudadano"), pk=pk)
    if registro.faena.estado == Faena.Estados.CERRADA:
        return HttpResponseBadRequest("La faena está cerrada.")
    nuevo_estado = request.POST.get("estado")
    validos = {item[0] for item in RegistroFaena.EstadosAsistencia.choices}
    if nuevo_estado not in validos:
        return HttpResponseBadRequest("Estado inválido.")

    registro.estado = nuevo_estado
    registro.save(update_fields=["estado", "updated_at"])

    if request.headers.get("HX-Request"):
        return render(request, "dashboard/partials/registro_faena_row.html", {
            "registro": registro,
            "faena": registro.faena,
            "can_edit": True,
        })
    return redirect("faena_operativa", pk=registro.faena_id)


@login_required
@permission_required("operacion.change_registrofaena", raise_exception=True)
@require_POST
def accion_masiva_faena(request, pk):
    faena = get_object_or_404(Faena, pk=pk)
    if faena.estado == Faena.Estados.CERRADA:
        messages.error(request, "La faena está cerrada. No se pueden aplicar acciones masivas.")
        return redirect("faena_operativa", pk=pk)

    seleccionados = request.POST.getlist("registros")
    estado = request.POST.get("estado")
    if not seleccionados or estado not in {item[0] for item in RegistroFaena.EstadosAsistencia.choices}:
        messages.warning(request, "Selecciona registros y una acción válida.")
        return redirect("faena_operativa", pk=pk)

    with transaction.atomic():
        actualizados = RegistroFaena.objects.filter(faena=faena, id__in=seleccionados).update(estado=estado)
    messages.success(request, f"Se actualizaron {actualizados} participantes.")
    return redirect("faena_operativa", pk=pk)


@login_required
@permission_required("operacion.change_faena", raise_exception=True)
@require_POST
def cerrar_faena(request, pk):
    faena = get_object_or_404(Faena, pk=pk)
    if faena.estado != Faena.Estados.CERRADA:
        faena.estado = Faena.Estados.CERRADA
        faena.save(update_fields=["estado", "updated_at"])
        messages.success(request, "Faena cerrada correctamente. El historial quedó congelado.")
    return redirect("faena_operativa", pk=pk)


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
            "quick_links": {
                "pago_add": f"{reverse('admin:tesoreria_pago_add')}?ciudadano={ciudadano.pk}",
                "cooperacion_add": f"{reverse('admin:tesoreria_cooperacion_add')}?ciudadano={ciudadano.pk}",
                "registro_faena_add": f"{reverse('admin:operacion_registrofaena_add')}?ciudadano={ciudadano.pk}",
            },
        },
    )
