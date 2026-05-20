from itertools import chain

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Max, Q, Sum
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.urls import reverse

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
                "registro_faena_add": f"{reverse('admin:operacion_registrofaena_add')}?ciudadano={ciudadano.pk}",
            },
        },
    )
