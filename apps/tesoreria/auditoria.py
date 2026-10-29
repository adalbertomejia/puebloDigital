"""Record evidence in the same transaction as the financial operation."""

from .models import Abono, ConceptoTesoreria, RegistroFinanciero


def registrar_movimiento(usuario, objeto, accion, *, detalle=None, origen="PANEL"):
    concepto = objeto if isinstance(objeto, ConceptoTesoreria) else (
        objeto.obligacion.concepto if isinstance(objeto, Abono) else objeto.concepto
    )
    return RegistroFinanciero.objects.create(
        usuario=usuario, usuario_nombre=usuario.get_username(), comite=concepto.comite,
        accion=accion, tipo_objeto=objeto._meta.model_name, objeto_id=objeto.pk,
        concepto_id_registrado=concepto.pk, concepto_nombre=concepto.concepto,
        monto=getattr(objeto, "monto", getattr(objeto, "monto_asignado", None)),
        referencia=getattr(objeto, "referencia", ""),
        detalle={"periodo_agua": concepto.periodo_agua.isoformat() if concepto.periodo_agua else None, "naturaleza": concepto.naturaleza, "monto_base": str(concepto.monto_individual),
                 "alcance": concepto.alcance, **(detalle or {})}, origen=origen,
    )
