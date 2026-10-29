from django.db import transaction
from django.core.exceptions import ValidationError
from apps.agua.models import Toma

from apps.operacion.services import ResultadoGeneracion, obtener_ciudadanos_objetivo

from .models import ConceptoTesoreria, ObligacionCiudadano, RegistroFinanciero
from .auditoria import registrar_movimiento


def construir_obligacion(concepto, ciudadano_id, *, usuario=None):
    """Build a new historical assignment; future financial rules belong here."""
    return ObligacionCiudadano(
        concepto=concepto,
        creado_por=usuario,
        ciudadano_id=ciudadano_id,
        monto_asignado=concepto.monto_individual,
        estado=ObligacionCiudadano.Estados.PENDIENTE,
    )


@transaction.atomic
def generar_obligaciones_faltantes(concepto, *, usuario=None):
    """Create only obligations missing from the concept's current territory."""
    # Serialize generation for this concept on databases with row locking so
    # the recorded author/count describe this request's new obligations.
    ConceptoTesoreria.objects.select_for_update().get(pk=concepto.pk)
    # The action is operational and may run long after the creation form was used.
    concepto.full_clean()
    tomas = {}
    if concepto.origen == ConceptoTesoreria.Origenes.AGUA:
        if not concepto.periodo_agua:
            raise ValidationError("Este concepto de agua no tiene periodo mensual; requiere revisión antes de generar obligaciones.")
        tomas = {t.ciudadano_id: t for t in Toma.objects.filter(estado=Toma.Estados.ACTIVA).select_related("ciudadano")}
        objetivo_ids = list(tomas)
    else:
        objetivo_ids = list(obtener_ciudadanos_objetivo(concepto).values_list("pk", flat=True))
    existentes_ids = set(
        concepto.obligaciones.filter(ciudadano_id__in=objetivo_ids).values_list("ciudadano_id", flat=True)
    )
    nuevas = [
        construir_obligacion(concepto, ciudadano_id, usuario=usuario)
        for ciudadano_id in objetivo_ids
        if ciudadano_id not in existentes_ids
    ]
    for obligacion in nuevas:
        if obligacion.ciudadano_id in tomas:
            toma = tomas[obligacion.ciudadano_id]
            obligacion.toma = toma
            obligacion.numero_toma_registrado = toma.numero_toma
            obligacion.numero_contrato_registrado = toma.ciudadano.numero_contrato or ""
    ObligacionCiudadano.objects.bulk_create(
        nuevas,
        batch_size=500,
        ignore_conflicts=True,
    )

    # Recount the target set so the result also remains truthful if a concurrent
    # request won a unique-constraint race during bulk_create.
    finales = concepto.obligaciones.filter(ciudadano_id__in=objetivo_ids).count()
    creados = max(finales - len(existentes_ids), 0)
    if creados and not concepto.registros_generados:
        ConceptoTesoreria.objects.filter(pk=concepto.pk).update(registros_generados=True)
        concepto.registros_generados = True
    if creados and usuario is not None:
        registrar_movimiento(usuario, concepto, RegistroFinanciero.Acciones.GENERAR,
                             detalle={"creados": creados, "total_objetivo": len(objetivo_ids)})
    return ResultadoGeneracion(
        creados=creados,
        existentes=len(objetivo_ids) - creados,
        total_objetivo=len(objetivo_ids),
    )
