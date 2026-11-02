"""Reusable filters: callers must supply an already authorized queryset."""
import django_filters
from django.db.models import Q
from .models import Ciudadano
from .query_helpers import filtro_busqueda_ciudadano, filtro_edad_efectiva


class PadronFilter(django_filters.FilterSet):
    q = django_filters.CharFilter(method="buscar", max_length=200)
    estado = django_filters.CharFilter(method="seleccion", max_length=30)
    toma = django_filters.CharFilter(method="seleccion", max_length=30)
    adeudo = django_filters.CharFilter(method="seleccion", max_length=30)
    manzana = django_filters.CharFilter(method="seleccion", max_length=30)
    motivo_alta = django_filters.CharFilter(method="seleccion", max_length=30)
    sexo = django_filters.CharFilter(method="seleccion", max_length=30)
    rango_edad = django_filters.CharFilter(method="seleccion", max_length=30)
    fecha_nacimiento = django_filters.CharFilter(method="seleccion", max_length=30)
    contrato = django_filters.CharFilter(method="seleccion", max_length=30)
    datos = django_filters.CharFilter(method="seleccion", max_length=30)
    orden = django_filters.CharFilter(method="ordenar", max_length=30)

    class Meta:
        model = Ciudadano
        fields = []

    def buscar(self, qs, nombre, valor):
        return qs.filter(filtro_busqueda_ciudadano(valor, extra_fields=("toma__numero_toma",)))

    def seleccion(self, qs, nombre, valor):
        if nombre == "estado" and valor in ("activos", "inactivos"):
            return qs.filter(activo=valor == "activos")
        if nombre == "toma" and valor in ("con_toma", "sin_toma"):
            return qs.filter(toma__isnull=valor == "sin_toma")
        if nombre == "adeudo" and valor in ("con_adeudo", "sin_adeudo"):
            return qs.filter(adeudos_faena__gt=0) if valor == "con_adeudo" else qs.filter(adeudos_faena=0)
        if nombre == "manzana":
            if valor == "sin_asignar": return qs.filter(manzana__isnull=True)
            if valor.isdigit(): return qs.filter(manzana_id=int(valor)) if len(valor) <= 18 else qs.none()
        if nombre == "motivo_alta":
            if valor == "sin_motivo": return qs.filter(Q(motivo_alta="") | Q(motivo_alta__isnull=True))
            if valor in dict(Ciudadano.MotivosAlta.choices): return qs.filter(motivo_alta=valor)
        if nombre == "sexo" and valor in dict(Ciudadano.Sexos.choices): return qs.filter(sexo=valor)
        if nombre == "rango_edad":
            filtro = filtro_edad_efectiva(valor)
            if filtro is not None: return qs.filter(filtro)
        if nombre == "fecha_nacimiento" and valor in ("con_fecha", "sin_fecha"):
            return qs.filter(fecha_nacimiento__isnull=valor == "sin_fecha")
        vacio = Q(numero_contrato__isnull=True) | Q(numero_contrato="")
        if nombre == "contrato" and valor == "sin_contrato": return qs.filter(vacio)
        if nombre == "contrato" and valor == "con_contrato": return qs.exclude(vacio)
        if nombre == "datos" and valor == "incompletos":
            return qs.filter(vacio | Q(manzana__isnull=True) | Q(fecha_nacimiento__isnull=True, edad__isnull=True))
        return qs

    def ordenar(self, qs, nombre, valor):
        ordenes = {"nombre": [], "estado": ["-activo"], "adeudos_faena": ["-adeudos_faena"], "registro": ["-created_at"]}
        return qs.order_by(*ordenes.get(valor, []), "apellido_paterno", "apellido_materno", "nombre", "pk")


def filtrar_padron(queryset, params):
    datos = params.copy()
    datos.setdefault("orden", "nombre")
    filtro = PadronFilter(datos, queryset=queryset)
    return filtro.qs if filtro.is_valid() else queryset.none()
