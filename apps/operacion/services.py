from typing import NamedTuple

from django.db import transaction
from django.db.models import Q

from apps.core.models import Ciudadano

from .models import AsistenciaJunta, Faena, RegistroFaena


class ResultadoGeneracion(NamedTuple):
    creados: int
    existentes: int
    total_objetivo: int


def obtener_ciudadanos_objetivo(evento):
    """Return active citizens in any event's territory, in stable name order."""
    ciudadanos = Ciudadano.objects.filter(activo=True)
    if evento.alcance == evento.Alcances.MANZANA:
        ciudadanos = ciudadanos.filter(manzana_id=evento.manzana_id)
    return ciudadanos.order_by("apellido_paterno", "apellido_materno", "nombre", "pk")


@transaction.atomic
def generar_registros_faltantes(*, evento, modelo_registro, campo_evento, defaults=None):
    """Bulk-create only missing target records for an event, preserving existing states."""
    objetivo_ids = list(obtener_ciudadanos_objetivo(evento).values_list("pk", flat=True))
    filtro_evento = {campo_evento: evento}
    existentes = set(modelo_registro.objects.filter(**filtro_evento).values_list("ciudadano_id", flat=True))
    defaults = defaults or {}
    nuevos = [
        modelo_registro(**filtro_evento, ciudadano_id=ciudadano_id, **defaults)
        for ciudadano_id in objetivo_ids
        if ciudadano_id not in existentes
    ]
    modelo_registro.objects.bulk_create(nuevos, batch_size=500, ignore_conflicts=True)
    return ResultadoGeneracion(len(nuevos), len(set(objetivo_ids) & existentes), len(objetivo_ids))


def generar_participantes_faena(faena):
    return generar_registros_faltantes(evento=faena, modelo_registro=RegistroFaena, campo_evento="faena")


def generar_participantes_junta(junta):
    return generar_registros_faltantes(
        evento=junta, modelo_registro=AsistenciaJunta, campo_evento="junta", defaults={"asistio": False}
    )


def aplicar_filtros_eventos(queryset, *, params, description_field, tipo_actividad):
    """Both event types share validated filters over their authorized scope."""
    from .filtros import EventosFilter
    filtro = EventosFilter(params, queryset=queryset, description_field=description_field, tipo_actividad=tipo_actividad)
    return (filtro.qs if filtro.is_valid() else queryset.none()).order_by("-fecha", "-created_at")
