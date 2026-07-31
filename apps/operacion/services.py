from django.db import transaction

from apps.core.models import Ciudadano

from .models import Faena, RegistroFaena


def obtener_ciudadanos_objetivo_faena(faena):
    """Return the active citizens covered by a faena, in stable name order."""
    ciudadanos = Ciudadano.objects.filter(activo=True)
    if faena.alcance == Faena.Alcances.MANZANA:
        ciudadanos = ciudadanos.filter(manzana_id=faena.manzana_id)
    return ciudadanos.order_by("apellido_paterno", "apellido_materno", "nombre", "pk")


@transaction.atomic
def generar_participantes_faena(faena):
    """Create only missing target records and preserve every existing record."""
    objetivo_ids = list(obtener_ciudadanos_objetivo_faena(faena).values_list("pk", flat=True))
    existentes = set(
        RegistroFaena.objects.filter(faena=faena).values_list("ciudadano_id", flat=True)
    )
    nuevos = [
        RegistroFaena(faena=faena, ciudadano_id=ciudadano_id)
        for ciudadano_id in objetivo_ids
        if ciudadano_id not in existentes
    ]
    RegistroFaena.objects.bulk_create(nuevos, batch_size=500, ignore_conflicts=True)
    return len(nuevos), len(set(objetivo_ids) & existentes), len(objetivo_ids)
