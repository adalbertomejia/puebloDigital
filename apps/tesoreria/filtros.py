import django_filters
from django.db.models import Q
from .models import ConceptoTesoreria


class ConceptosFilter(django_filters.FilterSet):
    q = django_filters.CharFilter(method="buscar", max_length=200)
    naturaleza = django_filters.CharFilter(method="seleccion", max_length=30)
    alcance = django_filters.CharFilter(method="seleccion", max_length=30)
    manzana = django_filters.CharFilter(method="seleccion", max_length=16)
    mes = django_filters.CharFilter(method="seleccion", max_length=16)
    anio = django_filters.CharFilter(method="seleccion", max_length=16)
    comite = django_filters.CharFilter(method="seleccion", max_length=16)
    estado = django_filters.CharFilter(method="seleccion", max_length=30)

    class Meta:
        model = ConceptoTesoreria
        fields = []

    def buscar(self, qs, nombre, valor):
        return qs.filter(Q(concepto__icontains=valor) | Q(descripcion__icontains=valor) | Q(comite__nombre__icontains=valor))

    def seleccion(self, qs, nombre, valor):
        if nombre == "naturaleza" and valor in ConceptoTesoreria.Naturalezas.values: return qs.filter(naturaleza=valor)
        if nombre == "alcance" and valor in ConceptoTesoreria.Alcances.values: return qs.filter(alcance=valor)
        campos = {"manzana": "manzana_id", "comite": "comite_id", "mes": "fecha__month", "anio": "fecha__year"}
        if nombre in campos and valor.isdigit():
            numero = int(valor)
            if nombre == "mes" and not 1 <= numero <= 12: return qs.none()
            if nombre == "anio" and not 1 <= numero <= 9999: return qs.none()
            return qs.filter(**{campos[nombre]: numero})
        if nombre == "estado" and valor in ("SIN_GENERAR", "CON_PENDIENTES", "COMPLETADO"): return qs.filter(estado_general=valor)
        return qs
