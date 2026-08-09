from django.core.exceptions import ValidationError
from django.db.models import Q


def validar_alcance_y_manzana(*, alcance, manzana_id, alcance_general, alcance_manzana, nombre_entidad):
    """Return field errors for the territorial rules shared by operation events."""
    if alcance == alcance_manzana and not manzana_id:
        return {"manzana": f"Selecciona una manzana para esta {nombre_entidad}."}
    if alcance == alcance_general and manzana_id:
        return {
            "manzana": f"Una {nombre_entidad} para toda la comunidad no debe tener una manzana."
        }
    return {}


def validar_cambio_territorial(*, instancia, registros, nombre_entidad):
    """Protect an event's historical territory after its participant list exists."""
    if not instancia.pk or not registros.exists():
        return {}
    original = type(instancia).objects.filter(pk=instancia.pk).values("alcance", "manzana_id").first()
    if not original:
        return {}
    errors = {}
    mensaje = (
        f"No puedes cambiar el alcance o la manzana porque esta {nombre_entidad} "
        "ya tiene participantes generados."
    )
    if original["alcance"] != instancia.alcance:
        errors["alcance"] = mensaje
    if original["manzana_id"] != instancia.manzana_id:
        errors["manzana"] = mensaje
    return errors


def validar_territorio_evento(*, instancia, registros, nombre_entidad):
    errors = validar_alcance_y_manzana(
        alcance=instancia.alcance,
        manzana_id=instancia.manzana_id,
        alcance_general=instancia.Alcances.GENERAL,
        alcance_manzana=instancia.Alcances.MANZANA,
        nombre_entidad=nombre_entidad,
    )
    errors.update(
        validar_cambio_territorial(
            instancia=instancia, registros=registros, nombre_entidad=nombre_entidad
        )
    )
    if errors:
        raise ValidationError(errors)


def manzanas_disponibles_para_instancia(instancia):
    """Offer active blocks plus the inactive block retained by an existing record."""
    from apps.core.models import Manzana

    disponibles = Q(activa=True)
    if instancia.pk and instancia.manzana_id:
        disponibles |= Q(pk=instancia.manzana_id)
    return Manzana.objects.filter(disponibles).order_by("nombre")
