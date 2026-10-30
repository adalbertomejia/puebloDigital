from datetime import timedelta
import django_filters
from django.db.models import Q
from django.utils import timezone
from .models import Solicitud

ABIERTAS = ('RECIBIDA', 'ATENCION', 'INFORMACION')


class BandejaFilter(django_filters.FilterSet):
    q = django_filters.CharFilter(method='buscar', max_length=200)
    estado = django_filters.ChoiceFilter(choices=Solicitud.Estados.choices)
    tipo = django_filters.NumberFilter(field_name='tipo_id', min_value=1, max_value=2**63-1, decimal_places=0)
    comite = django_filters.NumberFilter(field_name='comite_id', min_value=1, max_value=2**63-1, decimal_places=0)
    responsable = django_filters.NumberFilter(field_name='responsable_id', min_value=1, max_value=2**63-1, decimal_places=0)
    tarea = django_filters.ChoiceFilter(method='por_tarea', choices=[(k, k) for k in ('mis_pendientes', 'sin_asignar', 'vencidas', 'proximas')])

    class Meta:
        model = Solicitud
        fields = []

    def __init__(self, *args, usuario, **kwargs):
        self.usuario = usuario
        super().__init__(*args, **kwargs)

    def buscar(self, qs, nombre, valor):
        for termino in valor.split():
            qs = qs.filter(Q(folio__icontains=termino) | Q(ciudadano__nombre__icontains=termino) | Q(ciudadano__apellido_paterno__icontains=termino) | Q(ciudadano__apellido_materno__icontains=termino))
        return qs

    def por_tarea(self, qs, nombre, valor):
        qs = qs.filter(estado__in=ABIERTAS)
        hoy = timezone.localdate()
        if valor == 'mis_pendientes': return qs.filter(responsable=self.usuario)
        if valor == 'sin_asignar': return qs.filter(responsable__isnull=True)
        if valor == 'vencidas': return qs.filter(fecha_compromiso__lt=hoy)
        if valor == 'proximas': return qs.filter(fecha_compromiso__range=(hoy, hoy+timedelta(days=7)))
        return qs
