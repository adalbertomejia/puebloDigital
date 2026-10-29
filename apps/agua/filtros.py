import django_filters
from django.db.models import Q
from .models import Toma


class TomasFilter(django_filters.FilterSet):
    q = django_filters.CharFilter(method="buscar", max_length=200)
    estado = django_filters.CharFilter(method="por_estado", max_length=30)
    asociacion = django_filters.CharFilter(method="por_asociacion", max_length=30)

    class Meta:
        model = Toma
        fields = []

    def buscar(self, qs, nombre, valor):
        for token in valor.split():
            qs = qs.filter(Q(numero_toma__icontains=token) | Q(ciudadano__numero_contrato__icontains=token) | Q(ciudadano__nombre__icontains=token) | Q(ciudadano__apellido_paterno__icontains=token) | Q(ciudadano__apellido_materno__icontains=token))
        return qs

    def por_estado(self, qs, nombre, valor):
        estado = {"activas": "ACTIVA", "suspendidas": "SUSPENDIDA", "canceladas": "CANCELADA"}.get(valor)
        return qs.filter(estado=estado) if estado else qs

    def por_asociacion(self, qs, nombre, valor):
        if valor in ("con_ciudadano", "sin_ciudadano"):
            return qs.filter(ciudadano__isnull=valor == "sin_ciudadano")
        vacio = Q(ciudadano__numero_contrato__isnull=True) | Q(ciudadano__numero_contrato="")
        if valor == "sin_contrato": return qs.filter(vacio)
        if valor == "con_contrato": return qs.exclude(vacio)
        return qs
