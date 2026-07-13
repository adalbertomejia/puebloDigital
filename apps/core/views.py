from itertools import chain

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpResponse
from django import forms
from django.db import transaction
from django.db.models import Count, Max, Q, Sum
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
    }
    return render(request, "dashboard/padron_ciudadanos.html", context)


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


def _pdf_escape(value):
    return str(value).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _build_simple_pdf(lines):
    pages = []
    max_lines = 42
    for start in range(0, len(lines), max_lines):
        chunk = lines[start:start + max_lines]
        y = 780
        content = ["BT", "/F1 11 Tf"]
        for line in chunk:
            content.append(f"1 0 0 1 50 {y} Tm ({_pdf_escape(line)}) Tj")
            y -= 17
        content.append("ET")
        pages.append("\n".join(content).encode("latin-1", "replace"))

    objects = [b"<< /Type /Catalog /Pages 2 0 R >>"]
    kids = []
    content_object_ids = []
    next_id = 3
    for _page in pages:
        kids.append(f"{next_id} 0 R".encode())
        content_object_ids.append(next_id + 1)
        next_id += 2
    objects.append(b"<< /Type /Pages /Kids [" + b" ".join(kids) + b"] /Count " + str(len(pages)).encode() + b" >>")
    for page_content, content_id in zip(pages, content_object_ids):
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 {next_id} 0 R >> >> /Contents {content_id} 0 R >>".encode())
        objects.append(b"<< /Length " + str(len(page_content)).encode() + b" >>\nstream\n" + page_content + b"\nendstream")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for idx, obj in enumerate(objects, 1):
        offsets.append(len(pdf))
        pdf.extend(f"{idx} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = len(pdf)
    pdf.extend(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode())
    pdf.extend(f"trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode())
    return bytes(pdf)


@login_required
def descargar_padron_activo_pdf(request):
    ciudadanos = _ciudadanos_operativos_queryset().filter(activo=True).order_by("apellido_paterno", "apellido_materno", "nombre")
    generado = timezone.localtime().strftime("%d/%m/%Y %H:%M")
    lines = [
        "Pueblo Digital",
        "Centro de Gestión Comunitaria",
        "Padrón de Ciudadanos Activos",
        f"Fecha de generación: {generado}",
        "",
        "Nombre | Teléfono | Toma de agua | Estado",
        "-" * 95,
    ]
    for ciudadano in ciudadanos:
        toma = getattr(ciudadano, "toma", None)
        lines.append(
            f"{ciudadano.nombre_completo} | {ciudadano.telefono or 'Sin teléfono'} | "
            f"{toma.numero_toma if toma else 'Sin toma'} | Activo"
        )

    response = HttpResponse(_build_simple_pdf(lines), content_type="application/pdf")
    response["Content-Disposition"] = 'attachment; filename="padron-ciudadanos-activos.pdf"'
    return response


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


def _event_can_capture_attendance(event, total_participantes=None):
    """Return whether an event should expose the attendance capture action."""
    total = total_participantes
    if total is None:
        registros = getattr(event, "registros", getattr(event, "asistencias", None))
        total = registros.count() if registros is not None else 0

    if event.estado == event.Estados.CANCELADA:
        return False
    return event.estado == event.Estados.PROGRAMADA or total > 0


def _decorate_attendance_events(events, description_attr, admin_url_name, capture_url_name, detail_url_name):
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
        event.can_capture = _event_can_capture_attendance(event, total)
        event.estado_edit_url = reverse("editar_estado_evento", args=[event.__class__.__name__.lower(), event.pk])
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
        "editar_faena_operativa",
        "captura_asistencia_faena",
        "control_asistencias_faena_detalle",
    )
    juntas = _decorate_attendance_events(
        _attendance_queryset(Junta, "asistencias", AsistenciaJunta.Estatus.PENDIENTE).order_by("fecha", "created_at")[:50],
        "tema",
        "editar_junta_operativa",
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
        "can_capture": _event_can_capture_attendance(event, total),
        "participantes": registros.select_related("ciudadano").order_by("estatus", "ciudadano__apellido_paterno", "ciudadano__apellido_materno", "ciudadano__nombre")[:200],
    }


@login_required
def control_asistencias_faena_detalle(request, faena_id):
    faena = get_object_or_404(Faena.objects.select_related("comite"), pk=faena_id)
    context = _event_detail_context(faena, faena.registros.all(), "Faena", faena.descripcion)
    context["admin_change_url"] = reverse("editar_faena_operativa", args=[faena.pk])
    context["capture_url"] = reverse("captura_asistencia_faena", args=[faena.pk])
    context["estado_edit_url"] = reverse("editar_estado_evento", args=["faena", faena.pk])
    return render(request, "dashboard/control_asistencias_detalle.html", context)


@login_required
def control_asistencias_junta_detalle(request, junta_id):
    junta = get_object_or_404(Junta.objects.select_related("comite"), pk=junta_id)
    context = _event_detail_context(junta, junta.asistencias.all(), "Junta", junta.tema)
    context["admin_change_url"] = reverse("editar_junta_operativa", args=[junta.pk])
    context["capture_url"] = reverse("captura_asistencia_junta", args=[junta.pk])
    context["estado_edit_url"] = reverse("editar_estado_evento", args=["junta", junta.pk])
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
            "admin_change_url": "editar_faena_operativa",
            "capture_url": "captura_asistencia_faena",
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


def _captura_asistencia(request, event_kind, event_id):
    config = _capture_config(event_kind)
    event = get_object_or_404(config["event_model"].objects.select_related("comite"), pk=event_id)
    if not _event_can_capture_attendance(event):
        messages.error(request, "Solo se puede capturar asistencia en eventos programados o con registros generados.")
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
            "estado_edit_url": reverse("editar_estado_evento", args=[event_kind, event.pk]),
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
