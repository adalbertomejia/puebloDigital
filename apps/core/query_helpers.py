import calendar

from django.db.models import Q
from django.utils import timezone


def filtro_busqueda_ciudadano(q, prefijo="", extra_fields=()):
    """Cada palabra de q debe coincidir en nombre, apellidos, contrato u otros campos."""
    tokens = (q or "").split()
    if not tokens:
        return None
    fields = (
        f"{prefijo}nombre",
        f"{prefijo}apellido_paterno",
        f"{prefijo}apellido_materno",
        f"{prefijo}numero_contrato",
        *extra_fields,
    )
    combined = Q()
    for token in tokens:
        token_q = Q()
        for field in fields:
            token_q |= Q(**{f"{field}__icontains": token})
        combined &= token_q
    return combined


def _anios_antes(fecha, anios):
    """Devuelve el corte de cumpleaños, incluyendo correctamente el 29 de febrero."""
    year = fecha.year - anios
    return fecha.replace(year=year, day=min(fecha.day, calendar.monthrange(year, fecha.month)[1]))


def filtro_edad_efectiva(rango, hoy=None, prefijo=""):
    """Filtro ORM que prioriza fecha de nacimiento y usa la edad manual como respaldo."""
    hoy = hoy or timezone.localdate()
    fecha = f"{prefijo}fecha_nacimiento"
    edad = f"{prefijo}edad"
    sin_fecha = Q(**{f"{fecha}__isnull": True})
    rangos = {
        "menores_18": (0, 17),
        "18_29": (18, 29),
        "30_49": (30, 49),
        "50_64": (50, 64),
        "65_mas": (65, None),
    }
    if rango == "sin_informacion":
        return sin_fecha & Q(**{f"{edad}__isnull": True})
    if rango == "sin_fecha":
        return sin_fecha
    if rango not in rangos:
        return None
    minimo, maximo = rangos[rango]
    fecha_q = Q(**{f"{fecha}__lte": _anios_antes(hoy, minimo)})
    manual_q = Q(**{f"{edad}__gte": minimo})
    if maximo is not None:
        fecha_q &= Q(**{f"{fecha}__gt": _anios_antes(hoy, maximo + 1)})
        manual_q &= Q(**{f"{edad}__lte": maximo})
    return fecha_q | (sin_fecha & manual_q)
