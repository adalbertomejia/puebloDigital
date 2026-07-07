from itertools import chain

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Max, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.urls import reverse

from apps.agua.models import Toma
from apps.operacion.models import AsistenciaJunta, Faena, Junta, RegistroFaena
from apps.tesoreria.models import Cooperacion, Pago

from .forms import FaenaOperativaForm, JuntaOperativaForm
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
        .filter(fecha__gte=timezone.localdate())
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
        "faenas_programadas": Faena.objects.filter(estado=Faena.Estados.PROGRAMADA).order_by("fecha")[:10],
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


def _crear_evento_operativo(request, form_class, event_label, description, detail_url_name):
    if request.method == "POST":
        form = form_class(request.POST)
        if form.is_valid():
            event = form.save()
            messages.success(request, f"Se creó correctamente la {event_label.lower()}.")
            return redirect(detail_url_name, event.pk)
        messages.error(request, "Revisa los campos marcados antes de guardar.")
    else:
        form = form_class()

    return render(
        request,
        "dashboard/evento_form.html",
        {
            "form": form,
            "event_label": event_label,
            "title": f"Crear nueva {event_label.lower()}",
            "description": description,
            "submit_label": f"Guardar {event_label.lower()}",
            "cancel_url": reverse("dashboard_operativo"),
        },
    )


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
def generar_registros_faena(request, faena_id):
    if request.method != "POST":
        return redirect("dashboard_operativo")

    faena = get_object_or_404(Faena, pk=faena_id)
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
    )


def _decorate_attendance_events(events, description_attr, admin_url_name, capture_url_name, detail_url_name):
    today = timezone.localdate()
    decorated = []
    for event in events:
        total = event.total_participantes or 0
        registradas = event.asistencias_registradas or 0
        pendientes = event.pendientes or 0
        if total == 0:
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
        event.operational_priority = priority
        event.admin_change_url = reverse(admin_url_name, args=[event.pk])
        event.capture_url = reverse(capture_url_name, args=[event.pk])
        event.detail_url = reverse(detail_url_name, args=[event.pk])
        decorated.append(event)

    return sorted(decorated, key=lambda item: (item.operational_priority, item.fecha))


def _attendance_summary(faenas, juntas):
    return {
        "faenas_activas": sum(1 for event in faenas if event.estado_operacional != "COMPLETADA"),
        "juntas_activas": sum(1 for event in juntas if event.estado_operacional != "COMPLETADA"),
        "eventos_pendientes": sum(1 for event in [*faenas, *juntas] if event.pendientes > 0),
        "asistencias_pendientes": sum(event.pendientes for event in [*faenas, *juntas]),
    }


@login_required
def control_asistencias(request):
    faenas = _decorate_attendance_events(
        _attendance_queryset(Faena, "registros", RegistroFaena.Estatus.PENDIENTE).order_by("fecha", "created_at")[:50],
        "descripcion",
        "admin:operacion_faena_change",
        "captura_asistencia_faena",
        "control_asistencias_faena_detalle",
    )
    juntas = _decorate_attendance_events(
        _attendance_queryset(Junta, "asistencias", AsistenciaJunta.Estatus.PENDIENTE).order_by("fecha", "created_at")[:50],
        "tema",
        "admin:operacion_junta_change",
        "captura_asistencia_junta",
        "control_asistencias_junta_detalle",
    )

    return render(
        request,
        "dashboard/control_asistencias.html",
        {
            "resumen": _attendance_summary(faenas, juntas),
            "faenas": faenas,
            "juntas": juntas,
            "tipo_activo": request.GET.get("tipo", ""),
        },
    )


def _event_detail_context(event, registros, event_type, description):
    total = registros.count()
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
        },
        "estado_operacional": "PROGRAMADA" if total == 0 else ("REGISTROS_GENERADOS" if pendientes else "COMPLETADA"),
        "participantes": registros.select_related("ciudadano").order_by("estatus", "ciudadano__apellido_paterno", "ciudadano__apellido_materno", "ciudadano__nombre")[:200],
    }


@login_required
def control_asistencias_faena_detalle(request, faena_id):
    faena = get_object_or_404(Faena.objects.select_related("comite"), pk=faena_id)
    context = _event_detail_context(faena, faena.registros.all(), "Faena", faena.descripcion)
    context["admin_change_url"] = reverse("admin:operacion_faena_change", args=[faena.pk])
    context["capture_url"] = reverse("captura_asistencia_faena", args=[faena.pk])
    return render(request, "dashboard/control_asistencias_detalle.html", context)


@login_required
def control_asistencias_junta_detalle(request, junta_id):
    junta = get_object_or_404(Junta.objects.select_related("comite"), pk=junta_id)
    context = _event_detail_context(junta, junta.asistencias.all(), "Junta", junta.tema)
    context["admin_change_url"] = reverse("admin:operacion_junta_change", args=[junta.pk])
    context["capture_url"] = reverse("captura_asistencia_junta", args=[junta.pk])
    return render(request, "dashboard/control_asistencias_detalle.html", context)


def _capture_config(event_kind):
    configs = {
        "faena": {
            "event_model": Faena,
            "relation": "registros",
            "event_type": "Faena",
            "description_attr": "descripcion",
            "status_choices": RegistroFaena.Estatus.choices,
            "detail_url": "control_asistencias_faena_detalle",
            "admin_change_url": "admin:operacion_faena_change",
            "capture_url": "captura_asistencia_faena",
        },
        "junta": {
            "event_model": Junta,
            "relation": "asistencias",
            "event_type": "Junta",
            "description_attr": "tema",
            "status_choices": AsistenciaJunta.Estatus.choices,
            "detail_url": "control_asistencias_junta_detalle",
            "admin_change_url": "admin:operacion_junta_change",
            "capture_url": "captura_asistencia_junta",
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

        if isinstance(registro, RegistroFaena):
            genera_adeudo = request.POST.get(f"{prefix}_genera_adeudo") == "on"
            monto_raw = request.POST.get(f"{prefix}_monto_adeudo") or "0"
            if registro.genera_adeudo != genera_adeudo:
                registro.genera_adeudo = genera_adeudo
                changed = True
            if str(registro.monto_adeudo) != monto_raw:
                registro.monto_adeudo = monto_raw
                changed = True
        elif isinstance(registro, AsistenciaJunta):
            asistio = estatus == AsistenciaJunta.Estatus.ASISTIO
            if registro.asistio != asistio:
                registro.asistio = asistio
                changed = True

        if changed:
            registro.save()
            updated += 1
    return updated


def _captura_asistencia(request, event_kind, event_id):
    config = _capture_config(event_kind)
    event = get_object_or_404(config["event_model"].objects.select_related("comite"), pk=event_id)
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
        }
    )
    return render(request, "dashboard/captura_asistencia.html", context)


@login_required
def captura_asistencia_faena(request, faena_id):
    return _captura_asistencia(request, "faena", faena_id)


@login_required
def captura_asistencia_junta(request, junta_id):
    return _captura_asistencia(request, "junta", junta_id)


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
            "faenas_programadas": Faena.objects.filter(estado=Faena.Estados.PROGRAMADA).order_by("fecha")[:10],
            "quick_links": {
                "pago_add": f"{reverse('admin:tesoreria_pago_add')}?ciudadano={ciudadano.pk}",
                "cooperacion_add": f"{reverse('admin:tesoreria_cooperacion_add')}?ciudadano={ciudadano.pk}",
            },
        },
    )
