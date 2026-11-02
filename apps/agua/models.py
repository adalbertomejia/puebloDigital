from django.db import models
from apps.core.models import TimeStampedModel, Ciudadano

class Toma(TimeStampedModel):
    class Estados(models.TextChoices):
        ACTIVA = 'ACTIVA', 'Activa'
        SUSPENDIDA = 'SUSPENDIDA', 'Suspendida'
        CANCELADA = 'CANCELADA', 'Cancelada'

    ciudadano = models.OneToOneField(Ciudadano, on_delete=models.CASCADE, related_name='toma')
    numero_toma = models.CharField(max_length=30, unique=True)
    ubicacion = models.TextField(blank=True)
    costo_anual = models.DecimalField(max_digits=10, decimal_places=2, default=800)
    estado = models.CharField(max_length=20, choices=Estados.choices, default=Estados.ACTIVA)
    observaciones = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Toma'
        verbose_name_plural = 'Tomas'
        ordering = ['numero_toma']

    def __str__(self):
        return f"Toma {self.numero_toma} - {self.ciudadano.nombre_completo}"
