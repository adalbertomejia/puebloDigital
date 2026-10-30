import uuid
from pathlib import Path
from django.conf import settings
from django.db import models
from django.utils import timezone
from apps.core.models import TimeStampedModel
from .archivos import almacen_privado


def folio_nuevo():
    return 'DHD-S-' + uuid.uuid4().hex.upper()


def ruta_adjunto(instance, filename):
    return f'{instance.solicitud_id}/{uuid.uuid4().hex}{Path(filename).suffix.lower()}'


class TipoSolicitud(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ['nombre']
        verbose_name_plural = 'Tipos de solicitud'

    def __str__(self):
        return self.nombre


class Solicitud(TimeStampedModel):
    class Estados(models.TextChoices):
        RECIBIDA = 'RECIBIDA', 'Recibida'
        ATENCION = 'ATENCION', 'En atención'
        INFORMACION = 'INFORMACION', 'Pendiente de información'
        RESUELTA = 'RESUELTA', 'Resuelta'
        CANCELADA = 'CANCELADA', 'Cancelada'

    folio = models.CharField(max_length=38, unique=True, default=folio_nuevo, editable=False)
    token_envio = models.UUIDField(unique=True, editable=False)
    ciudadano = models.ForeignKey('core.Ciudadano', on_delete=models.PROTECT, related_name='solicitudes')
    tipo = models.ForeignKey(TipoSolicitud, on_delete=models.PROTECT)
    descripcion = models.TextField(max_length=2000)
    comite = models.ForeignKey('comites.Comite', on_delete=models.PROTECT)
    responsable = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='solicitudes_asignadas')
    estado = models.CharField(max_length=15, choices=Estados.choices, default=Estados.RECIBIDA)
    fecha_compromiso = models.DateField(null=True, blank=True, db_index=True)
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='solicitudes_registradas')
    motivo_cierre = models.TextField(blank=True)
    fecha_cierre = models.DateTimeField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ['-created_at', '-pk']
        indexes = [models.Index(fields=['comite', 'estado'], name='sol_comite_estado_idx'), models.Index(fields=['responsable', 'estado'], name='sol_resp_estado_idx')]

    @property
    def cerrada(self):
        return self.estado in (self.Estados.RESUELTA, self.Estados.CANCELADA)

    @property
    def vencida(self):
        return bool(not self.cerrada and self.fecha_compromiso and self.fecha_compromiso < timezone.localdate())

    def __str__(self):
        return self.folio


class Seguimiento(models.Model):
    solicitud = models.ForeignKey(Solicitud, on_delete=models.PROTECT, related_name='historial')
    autor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    fecha = models.DateTimeField(auto_now_add=True)
    observaciones = models.TextField(blank=True)
    cambios = models.JSONField(default=dict)

    class Meta:
        ordering = ['fecha', 'pk']


class Adjunto(models.Model):
    solicitud = models.ForeignKey(Solicitud, on_delete=models.PROTECT, related_name='adjuntos')
    autor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    fecha = models.DateTimeField(auto_now_add=True)
    nombre = models.CharField(max_length=200)
    archivo = models.FileField(storage=almacen_privado, upload_to=ruta_adjunto)
