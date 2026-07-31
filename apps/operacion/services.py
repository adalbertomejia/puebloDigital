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
    """Apply the search, date and territorial filters shared by faenas and juntas."""
    q = params.get("q", "").strip()
    if q:
        filtro = Q(**{f"{description_field}__icontains": q}) | Q(comite__nombre__icontains=q) | Q(estado__icontains=q)
        if q.lower() in tipo_actividad.lower() or tipo_actividad.lower().startswith(q.lower()):
            filtro |= Q(pk__isnull=False)
        queryset = queryset.filter(filtro)
    mes, anio = params.get("mes", "todos"), params.get("anio", "todos")
    alcance, manzana = params.get("alcance", "todos"), params.get("manzana", "todas")
    if mes != "todos" and mes.isdigit():
        queryset = queryset.filter(fecha__month=int(mes))
    if anio != "todos" and anio.isdigit():
        queryset = queryset.filter(fecha__year=int(anio))
    if alcance in Faena.Alcances.values:
        queryset = queryset.filter(alcance=alcance)
    if manzana != "todas" and manzana.isdigit():
        queryset = queryset.filter(manzana_id=int(manzana))
    return queryset.order_by("-fecha", "-created_at")
