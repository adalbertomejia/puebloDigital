"""Read-only, scoped collection metrics. Money stays Decimal; unknown != zero."""
from decimal import Decimal
from django.db.models import Count, DecimalField, Exists, F, OuterRef, Subquery, Sum, Value, Q
from django.db.models.functions import Coalesce
from .models import Abono, ConceptoTesoreria, ObligacionCiudadano
from .balance_autorizacion import limitar_balance

CERO = Decimal("0.00")
DINERO = DecimalField(max_digits=14, decimal_places=2)


def dinero(qs, campo):
    dato = qs.aggregate(conocido=Sum(campo), desconocidos=Count("pk", filter=Q(**{campo+"__isnull": True})))
    return {"conocido": dato["conocido"] or CERO, "desconocidos": dato["desconocidos"], "valor": None if dato["desconocidos"] else dato["conocido"] or CERO}


def conceptos_autorizados(user):
    return limitar_balance(ConceptoTesoreria.objects.select_related("comite", "manzana", "faena", "junta"), user)


def obligaciones_autorizadas(user):
    return limitar_balance(ObligacionCiudadano.objects.all(), user, "concepto__comite_id")


def abonos_autorizados(user):
    return limitar_balance(Abono.objects.all(), user, "obligacion__concepto__comite_id")


def filtrar_dimension(qs, data, prefijo=""):
    campos = {"origen": "origen", "naturaleza": "naturaleza", "comite": "comite_id", "manzana": "manzana_id"}
    for clave, campo in campos.items():
        if data.get(clave):
            valor = getattr(data[clave], "pk", data[clave])
            qs = qs.filter(**{prefijo+campo: valor})
    if data.get("q"):
        qs = qs.filter(Q(**{prefijo+"concepto__icontains": data["q"]}) | Q(**{prefijo+"descripcion__icontains": data["q"]}))
    return qs


def cartera(qs):
    abonos = Abono.objects.filter(obligacion_id=OuterRef("pk")).order_by().values("obligacion_id").annotate(total=Sum("monto")).values("total")
    return qs.annotate(abonado_conocido=Coalesce(Subquery(abonos, output_field=DINERO), Value(CERO, output_field=DINERO)), abonos_desconocidos=Exists(Abono.objects.filter(obligacion_id=OuterRef("pk"), monto__isnull=True)))


def resumen_cartera(qs):
    # One row per obligation, no monetary sum across a multiplying join.
    vigente = cartera(qs.exclude(estado="CANCELADO"))
    asignado = dinero(vigente, "monto_asignado")
    saldo, aplicado, desconocidos = CERO, CERO, 0
    for o in vigente.iterator(chunk_size=500):
        if o.monto_asignado is None or o.abonos_desconocidos:
            desconocidos += 1
            continue
        saldo += max(o.monto_asignado-o.abonado_conocido, CERO)
        aplicado += min(o.monto_asignado, o.abonado_conocido)
    counts = vigente.aggregate(total=Count("pk"), pagadas=Count("pk", filter=Q(estado="PAGADO")), pendientes=Count("pk", filter=Q(estado="PENDIENTE")))
    abonado = dinero(Abono.objects.filter(obligacion_id__in=qs.exclude(estado="CANCELADO").values("pk")), "monto")
    return {**counts, "abonado": abonado, "asignado": asignado, "saldo": None if desconocidos else saldo, "saldo_conocido": saldo, "desconocidos": desconocidos,
            "cumplimiento_monetario": None if desconocidos or not asignado["valor"] else aplicado/asignado["valor"]*100,
            "cumplimiento_cantidad": counts["pagadas"]/Decimal(counts["total"])*100 if counts["total"] else None,
            "canceladas": dinero(qs.filter(estado="CANCELADO"), "monto_asignado"), "cantidad_canceladas": qs.filter(estado="CANCELADO").count()}


def agrupacion(qs, campo):
    return list(qs.order_by().values(campo).annotate(conocido=Coalesce(Sum("monto"), Value(CERO, output_field=DINERO)), desconocidos=Count("pk", filter=Q(monto__isnull=True)), cantidad=Count("pk")).order_by("-conocido", campo))


def datos_balance(user, data):
    conceptos = filtrar_dimension(conceptos_autorizados(user), data)
    cohorte = conceptos.filter(fecha__gte=data["desde"], fecha__lte=data["hasta"])
    obligaciones = obligaciones_autorizadas(user).filter(concepto_id__in=cohorte.values("pk"))
    abonos = abonos_autorizados(user).filter(obligacion__concepto_id__in=conceptos.values("pk"), fecha__gte=data["desde"], fecha__lte=data["hasta"])
    if data.get("estado"):
        obligaciones = obligaciones.filter(estado=data["estado"])
        abonos = abonos.filter(obligacion__estado=data["estado"])
    resumen = resumen_cartera(obligaciones)
    origenes = agrupacion(abonos, "obligacion__concepto__origen")
    for fila in origenes:
        fila["etiqueta"] = ConceptoTesoreria.Origenes(fila["obligacion__concepto__origen"]).label if fila["obligacion__concepto__origen"] in ConceptoTesoreria.Origenes.values else "Origen por revisar"
    por_comite = agrupacion(abonos, "obligacion__concepto__comite__nombre")
    por_territorio = agrupacion(abonos, "obligacion__concepto__manzana__nombre")
    from django.db.models.functions import TruncMonth
    mensual = agrupacion(abonos.annotate(mes_balance=TruncMonth("fecha")), "mes_balance")
    mensual.sort(key=lambda r:r["mes_balance"])
    return {"recaudacion": dinero(abonos, "monto"), "cartera": resumen, "origenes": origenes, "por_comite": por_comite, "por_territorio": por_territorio, "mensual": mensual,
            "cobros_canceladas": dinero(abonos.filter(obligacion__estado="CANCELADO"), "monto"), "cantidad_cobros_canceladas": abonos.filter(obligacion__estado="CANCELADO").count(), "cobros_sin_fondo": abonos.filter(movimiento_recurso__isnull=True).count(),
            "conceptos": cohorte, "abonos": abonos, "obligaciones": obligaciones,
            "grafica": {"origenes": [{"nombre": r["etiqueta"], "monto": str(r["conocido"])} for r in origenes], "meses": [{"nombre":r["mes_balance"].strftime("%m/%Y"), "monto":str(r["conocido"])} for r in mensual]}}


def filas_conceptos(user, data):
    qs = filtrar_dimension(conceptos_autorizados(user), data).filter(fecha__gte=data["desde"], fecha__lte=data["hasta"])
    return qs.order_by("-fecha", "-pk")
