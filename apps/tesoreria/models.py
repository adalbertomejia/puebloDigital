from django.db import models
from apps.core.models import TimeStampedModel, Ciudadano
from apps.comites.models import Comite
from apps.agua.models import Toma
from apps.operacion.models import RegistroFaena

class Pago(TimeStampedModel):
    class Tipos(models.TextChoices):
        CUOTA_ANUAL = 'CUOTA_ANUAL', 'Cuota anual'
        DEUDA_FAENA = 'DEUDA_FAENA', 'Deuda de faena'
        SERVICIO = 'SERVICIO', 'Servicio'
        CUOTA_COMITE = 'CUOTA_COMITE', 'Cuota de comité'
        OTRO = 'OTRO', 'Otro'

    ciudadano = models.ForeignKey(Ciudadano, on_delete=models.CASCADE, related_name='pagos')
    comite = models.ForeignKey(Comite, on_delete=models.CASCADE, related_name='pagos')
    tipo = models.CharField(max_length=20, choices=Tipos.choices, default=Tipos.CUOTA_COMITE)
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    fecha = models.DateField()
    concepto = models.CharField(max_length=200)
    anio_periodo = models.PositiveIntegerField(null=True, blank=True)
    registro_faena = models.ForeignKey(RegistroFaena, on_delete=models.SET_NULL, null=True, blank=True, related_name='pagos')
    toma = models.ForeignKey(Toma, on_delete=models.SET_NULL, null=True, blank=True, related_name='pagos')
    comprobante = models.CharField(max_length=100, blank=True)
    notas = models.TextField(blank=True)

    class Meta:
        verbose_name = '💰 Pago'
        verbose_name_plural = '💰 Pagos'
        ordering = ['-fecha', '-created_at']

    def __str__(self):
        return f"{self.ciudadano.nombre_completo} - {self.get_tipo_display()} - ${self.monto}"

class Cooperacion(TimeStampedModel):
    class Tipos(models.TextChoices):
        ORDINARIA = 'ORDINARIA', 'Ordinaria'
        EXTRAORDINARIA = 'EXTRAORDINARIA', 'Extraordinaria'
        DONACION = 'DONACION', 'Donación'
        APOYO_EVENTO = 'APOYO_EVENTO', 'Apoyo a evento'

    ciudadano = models.ForeignKey(Ciudadano, on_delete=models.CASCADE, related_name='cooperaciones')
    comite = models.ForeignKey(Comite, on_delete=models.CASCADE, related_name='cooperaciones')
    tipo = models.CharField(max_length=20, choices=Tipos.choices, default=Tipos.ORDINARIA)
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    fecha = models.DateField()
    concepto = models.CharField(max_length=200)
    anio_periodo = models.PositiveIntegerField(null=True, blank=True)
    comprobante = models.CharField(max_length=100, blank=True)
    notas = models.TextField(blank=True)

    class Meta:
        verbose_name = '💰 Cooperación'
        verbose_name_plural = '💰 Cooperaciones'
        ordering = ['-fecha', '-created_at']

    def __str__(self):
        return f"{self.ciudadano.nombre_completo} - {self.get_tipo_display()} - ${self.monto}"
