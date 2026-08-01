from decimal import Decimal

from django.db.models import (
    Case, Count, DecimalField, ExpressionWrapper, F, IntegerField, Max,
    OuterRef, Q, Subquery, Sum, Value, When,
)
from django.db.models.functions import Coalesce, Greatest

from apps.core.models import Ciudadano
from apps.core.query_helpers import filtro_edad_efectiva

from .models import Abono, ConceptoTesoreria, ObligacionCiudadano


DINERO = DecimalField(max_digits=14, decimal_places=2)
CERO = Value(Decimal("0.00"), output_field=DINERO)


def anotar_conceptos(queryset=None):
    """Añade todas las métricas de tarjeta sin multiplicar montos por cada abono."""
    queryset = queryset or ConceptoTesoreria.objects.all()
    obligaciones = ObligacionCiudadano.objects.filter(concepto=OuterRef("pk"))
    abonos = Abono.objects.filter(
        obligacion__concepto=OuterRef("pk"),
        obligacion__estado__in=[ObligacionCiudadano.Estados.PENDIENTE, ObligacionCiudadano.Estados.PAGADO],
    )

    def cuenta(estado=None):
        base = obligaciones.filter(estado=estado) if estado else obligaciones
        return Coalesce(Subquery(base.values("concepto").annotate(n=Count("pk")).values("n")[:1]), Value(0))

    asignado = obligaciones.exclude(estado=ObligacionCiudadano.Estados.CANCELADO).values("concepto").annotate(
        total=Sum("monto_asignado")
    ).values("total")[:1]
    abonado = abonos.values("obligacion__concepto").annotate(total=Sum("monto")).values("total")[:1]
    queryset = queryset.select_related("comite", "manzana").annotate(
        cantidad_obligaciones=cuenta(),
        cantidad_pagada=cuenta(ObligacionCiudadano.Estados.PAGADO),
        cantidad_pendiente=cuenta(ObligacionCiudadano.Estados.PENDIENTE),
        cantidad_cancelada=cuenta(ObligacionCiudadano.Estados.CANCELADO),
        total_asignado=Coalesce(Subquery(asignado, output_field=DINERO), CERO),
        total_abonado=Coalesce(Subquery(abonado, output_field=DINERO), CERO),
    ).annotate(
        saldo_pendiente=Greatest(ExpressionWrapper(F("total_asignado") - F("total_abonado"), output_field=DINERO), CERO),
        estado_general=Case(
            When(cantidad_obligaciones=0, then=Value("SIN_GENERAR")),
            When(cantidad_pendiente__gt=0, then=Value("CON_PENDIENTES")),
            default=Value("COMPLETADO"),
        ),
    )
    return queryset


def aplicar_filtros_conceptos(queryset, params):
    q = params.get("q", "").strip()
    if q:
        queryset = queryset.filter(Q(concepto__icontains=q) | Q(descripcion__icontains=q) | Q(comite__nombre__icontains=q))
    for campo, opciones in (
        ("naturaleza", dict(ConceptoTesoreria.Naturalezas.choices)),
        ("alcance", dict(ConceptoTesoreria.Alcances.choices)),
    ):
        if params.get(campo) in opciones:
            queryset = queryset.filter(**{campo: params[campo]})
    if params.get("manzana", "todas").isdigit():
        queryset = queryset.filter(manzana_id=int(params["manzana"]))
    if params.get("mes", "todos").isdigit():
        queryset = queryset.filter(fecha__month=int(params["mes"]))
    if params.get("anio", "todos").isdigit():
        queryset = queryset.filter(fecha__year=int(params["anio"]))
    if params.get("comite", "todos").isdigit():
        queryset = queryset.filter(comite_id=int(params["comite"]))
    if params.get("estado") in {"SIN_GENERAR", "CON_PENDIENTES", "COMPLETADO"}:
        queryset = queryset.filter(estado_general=params["estado"])
    return queryset.order_by("-fecha", "-created_at")


def conceptos_filtrados(params):
    return aplicar_filtros_conceptos(anotar_conceptos(), params)


def anotar_obligaciones(queryset):
    abonado = Abono.objects.filter(obligacion=OuterRef("pk")).values("obligacion").annotate(
        total=Sum("monto")
    ).values("total")[:1]
    ultimo = Abono.objects.filter(obligacion=OuterRef("pk")).values("obligacion").annotate(
        fecha=Max("fecha")
    ).values("fecha")[:1]
    return queryset.select_related("ciudadano", "ciudadano__manzana").annotate(
        total_abonado_calc=Coalesce(Subquery(abonado, output_field=DINERO), CERO),
        ultimo_abono=Subquery(ultimo),
    ).annotate(
        saldo_pendiente_calc=Greatest(ExpressionWrapper(F("monto_asignado") - F("total_abonado_calc"), output_field=DINERO), CERO)
    )


def aplicar_filtros_obligaciones(queryset, params):
    q = params.get("q", "").strip()
    if q:
        for termino in q.split():
            queryset = queryset.filter(
                Q(ciudadano__nombre__icontains=termino) | Q(ciudadano__apellido_paterno__icontains=termino)
                | Q(ciudadano__apellido_materno__icontains=termino) | Q(ciudadano__numero_contrato__icontains=termino)
            )
    if params.get("estado") in dict(ObligacionCiudadano.Estados.choices):
        queryset = queryset.filter(estado=params["estado"])
    if params.get("manzana", "todas").isdigit():
        queryset = queryset.filter(ciudadano__manzana_id=int(params["manzana"]))
    if params.get("sexo") in dict(Ciudadano.Sexos.choices):
        queryset = queryset.filter(ciudadano__sexo=params["sexo"])
    if params.get("motivo_alta") in dict(Ciudadano.MotivosAlta.choices):
        queryset = queryset.filter(ciudadano__motivo_alta=params["motivo_alta"])
    edad = filtro_edad_efectiva(params.get("rango_edad", "todas"), prefijo="ciudadano__")
    if edad is not None:
        queryset = queryset.filter(edad)
    if params.get("saldo") == "con_saldo":
        queryset = queryset.filter(saldo_pendiente_calc__gt=0)
    elif params.get("saldo") == "sin_saldo":
        queryset = queryset.filter(saldo_pendiente_calc=0)
    return queryset.order_by("ciudadano__apellido_paterno", "ciudadano__apellido_materno", "ciudadano__nombre", "pk")


def aplicar_filtros_aportaciones(queryset, params):
    """Aplica una única interpretación de los filtros a movimientos de Abono."""
    if params.get("mes", "todos").isdigit():
        queryset = queryset.filter(fecha__month=int(params["mes"]))
    if params.get("anio", "todos").isdigit():
        queryset = queryset.filter(fecha__year=int(params["anio"]))
    if params.get("naturaleza") in dict(ConceptoTesoreria.Naturalezas.choices):
        queryset = queryset.filter(obligacion__concepto__naturaleza=params["naturaleza"])
    if params.get("alcance") in dict(ConceptoTesoreria.Alcances.choices):
        queryset = queryset.filter(obligacion__concepto__alcance=params["alcance"])
    if params.get("manzana", "todas").isdigit():
        # El territorio es el conservado por el concepto, no el domicilio actual.
        queryset = queryset.filter(obligacion__concepto__manzana_id=int(params["manzana"]))
    if params.get("comite", "todos").isdigit():
        queryset = queryset.filter(obligacion__concepto__comite_id=int(params["comite"]))
    concepto = params.get("concepto", "").strip()
    if concepto:
        queryset = queryset.filter(obligacion__concepto__concepto__icontains=concepto)
    ciudadano = params.get("ciudadano", "").strip()
    for termino in ciudadano.split():
        queryset = queryset.filter(
            Q(obligacion__ciudadano__nombre__icontains=termino)
            | Q(obligacion__ciudadano__apellido_paterno__icontains=termino)
            | Q(obligacion__ciudadano__apellido_materno__icontains=termino)
            | Q(obligacion__ciudadano__numero_contrato__icontains=termino)
        )
    return queryset


def abonos_filtrados(params):
    """QuerySet base reutilizado por la vista, sus agregados y el CSV."""
    return aplicar_filtros_aportaciones(Abono.objects.all(), params)
