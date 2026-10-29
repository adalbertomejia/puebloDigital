import django_filters
from django.db.models import Q


class EventosFilter(django_filters.FilterSet):
    q = django_filters.CharFilter(method="buscar", max_length=200)
    alcance = django_filters.CharFilter(method="seleccion", max_length=30)
    manzana = django_filters.CharFilter(method="seleccion", max_length=16)
    mes = django_filters.CharFilter(method="seleccion", max_length=16)
    anio = django_filters.CharFilter(method="seleccion", max_length=16)

    def __init__(self, *args, description_field, tipo_actividad, **kwargs):
        self.description_field = description_field
        self.tipo_actividad = tipo_actividad
        super().__init__(*args, **kwargs)

    def buscar(self, qs, nombre, valor):
        filtro = Q(**{f"{self.description_field}__icontains": valor}) | Q(comite__nombre__icontains=valor) | Q(estado__icontains=valor)
        if valor.lower() in self.tipo_actividad.lower() or self.tipo_actividad.lower().startswith(valor.lower()):
            filtro |= Q(pk__isnull=False)
        return qs.filter(filtro)

    def seleccion(self, qs, nombre, valor):
        if nombre == "alcance" and valor in ("GENERAL", "MANZANA"): return qs.filter(alcance=valor)
        campos = {"manzana": "manzana_id", "mes": "fecha__month", "anio": "fecha__year"}
        if nombre in campos and valor.isdigit():
            numero = int(valor)
            if nombre == "mes" and not 1 <= numero <= 12: return qs.none()
            if nombre == "anio" and not 1 <= numero <= 9999: return qs.none()
            return qs.filter(**{campos[nombre]: numero})
        return qs
