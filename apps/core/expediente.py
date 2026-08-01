"""Consultas del expediente ciudadano transversal.

Este módulo mantiene la lectura histórica fuera de la vista y evita que los
templates calculen saldos o recorran relaciones sin precargar.
"""
from decimal import Decimal
from django.core.paginator import Paginator
from django.db.models import Count, DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce

from apps.operacion.models import AsistenciaJunta, RegistroFaena
from apps.tesoreria.models import Abono, ObligacionCiudadano
from apps.tesoreria.queries import anotar_obligaciones


DINERO = DecimalField(max_digits=14, decimal_places=2)
CERO = Value(Decimal("0.00"), output_field=DINERO)


def obtener_resumen_ciudadano(ciudadano):
    """Métricas agregadas; su cantidad de consultas no depende de las filas."""
    obligaciones = ObligacionCiudadano.objects.filter(ciudadano=ciudadano)
    finanzas = obligaciones.aggregate(
        conceptos=Count("concepto_id", distinct=True),
        pendientes=Count("pk", filter=Q(estado=ObligacionCiudadano.Estados.PENDIENTE)),
        pagadas=Count("pk", filter=Q(estado=ObligacionCiudadano.Estados.PAGADO)),
        asignado=Coalesce(
            Sum("monto_asignado", filter=~Q(estado=ObligacionCiudadano.Estados.CANCELADO)), CERO
        ),
    )
    total_abonado = Abono.objects.filter(obligacion__ciudadano=ciudadano).aggregate(
        total=Coalesce(Sum("monto"), CERO)
    )["total"]
    estados_faena = RegistroFaena.objects.filter(ciudadano=ciudadano).aggregate(
        faenas=Count("pk"),
        asistencias=Count("pk", filter=Q(estatus=RegistroFaena.Estatus.ASISTIO)),
        faltas=Count("pk", filter=Q(estatus=RegistroFaena.Estatus.FALTO)),
        justificaciones=Count("pk", filter=Q(estatus=RegistroFaena.Estatus.JUSTIFICADO)),
    )
    estados_junta = AsistenciaJunta.objects.filter(ciudadano=ciudadano).aggregate(
        juntas=Count("pk"),
        asistencias=Count("pk", filter=Q(estatus=AsistenciaJunta.Estatus.ASISTIO)),
        faltas=Count("pk", filter=Q(estatus=AsistenciaJunta.Estatus.FALTO)),
        justificaciones=Count("pk", filter=Q(estatus=AsistenciaJunta.Estatus.JUSTIFICADO)),
    )
    return {
        **finanzas,
        "total_abonado": total_abonado,
        "saldo_pendiente": max(finanzas["asignado"] - total_abonado, Decimal("0.00")),
        "faenas": estados_faena["faenas"],
        "juntas": estados_junta["juntas"],
        "asistencias": estados_faena["asistencias"] + estados_junta["asistencias"],
        "faltas": estados_faena["faltas"] + estados_junta["faltas"],
        "justificaciones": estados_faena["justificaciones"] + estados_junta["justificaciones"],
    }


def obtener_obligaciones_ciudadano(ciudadano):
    return anotar_obligaciones(
        ObligacionCiudadano.objects.filter(ciudadano=ciudadano).select_related(
            "concepto", "concepto__comite", "concepto__manzana"
        )
    ).order_by("-concepto__fecha", "-concepto_id", "-pk")


def obtener_abonos_ciudadano(ciudadano):
    return Abono.objects.filter(obligacion__ciudadano=ciudadano).select_related(
        "obligacion", "obligacion__concepto", "obligacion__concepto__comite",
        "obligacion__concepto__manzana",
    ).order_by("-fecha", "-created_at", "-pk")


def obtener_asistencias_ciudadano(ciudadano):
    """Une ambos tipos conservando el territorio guardado en cada evento."""
    faenas = RegistroFaena.objects.filter(ciudadano=ciudadano).select_related("faena", "faena__manzana")
    juntas = AsistenciaJunta.objects.filter(ciudadano=ciudadano).select_related("junta", "junta__manzana")
    filas = [
        {
            "tipo": "Faena", "descripcion": r.faena.descripcion, "fecha": r.faena.fecha,
            "territorio": r.faena.manzana if r.faena.manzana_id else "Toda la comunidad",
            "estado": r.get_estatus_display(), "genera_adeudo": r.genera_adeudo,
            "monto_adeudo": r.monto_adeudo, "id": r.pk, "evento_id": r.faena_id,
            "url_name": "control_asistencias_faena_detalle",
        } for r in faenas
    ]
    filas.extend({
        "tipo": "Junta", "descripcion": r.junta.tema, "fecha": r.junta.fecha,
        "territorio": r.junta.manzana if r.junta.manzana_id else "Toda la comunidad",
        "estado": r.get_estatus_display(), "genera_adeudo": r.genera_adeudo,
        "monto_adeudo": r.monto_adeudo, "id": r.pk, "evento_id": r.junta_id,
        "url_name": "control_asistencias_junta_detalle",
    } for r in juntas)
    return sorted(filas, key=lambda x: (-x["fecha"].toordinal(), x["tipo"], -x["id"]))


def paginar(queryset, request, parametro, por_pagina=10):
    pagina = Paginator(queryset, por_pagina).get_page(request.GET.get(parametro))
    return pagina
