from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Sum
from django.utils import timezone

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


class ConceptoTesoreria(TimeStampedModel):
    class Naturalezas(models.TextChoices):
        PAGO = "PAGO", "Pago"
        COOPERACION = "COOPERACION", "Cooperación"

    class Origenes(models.TextChoices):
        TESORERIA = "TESORERIA", "Tesorería"
        FAENA = "FAENA", "Faena"
        JUNTA = "JUNTA", "Junta"
        AGUA = "AGUA", "Agua"

    naturaleza = models.CharField(max_length=20, choices=Naturalezas.choices)
    origen = models.CharField(max_length=20, choices=Origenes.choices, default=Origenes.TESORERIA)
    comite = models.ForeignKey(Comite, on_delete=models.PROTECT, related_name="conceptos_tesoreria")
    concepto = models.CharField(max_length=200)
    descripcion = models.TextField(blank=True)
    monto_individual = models.DecimalField(max_digits=10, decimal_places=2)
    fecha = models.DateField(default=timezone.localdate)
    anio_periodo = models.PositiveIntegerField(null=True, blank=True)
    registros_generados = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Concepto de tesorería"
        verbose_name_plural = "Conceptos de tesorería"
        ordering = ["-fecha", "-created_at"]

    def clean(self):
        if not self.concepto or not self.concepto.strip():
            raise ValidationError({"concepto": "El concepto no puede estar vacío."})
        if self.monto_individual is not None and self.monto_individual <= 0:
            raise ValidationError({"monto_individual": "El monto individual debe ser mayor que cero."})
        if not self.comite_id:
            raise ValidationError({"comite": "Debe seleccionar un comité."})

    def __str__(self):
        return f"{self.get_naturaleza_display()} · {self.concepto}"


class ObligacionCiudadano(TimeStampedModel):
    class Estados(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente"
        PAGADO = "PAGADO", "Pagado"
        CANCELADO = "CANCELADO", "Cancelado"

    concepto = models.ForeignKey(ConceptoTesoreria, on_delete=models.CASCADE, related_name="obligaciones")
    ciudadano = models.ForeignKey(Ciudadano, on_delete=models.PROTECT, related_name="obligaciones_tesoreria")
    monto_asignado = models.DecimalField(max_digits=10, decimal_places=2)
    estado = models.CharField(max_length=15, choices=Estados.choices, default=Estados.PENDIENTE)
    notas = models.TextField(blank=True)

    class Meta:
        verbose_name = "Obligación ciudadana"
        verbose_name_plural = "Obligaciones ciudadanas"
        ordering = ["ciudadano__apellido_paterno", "ciudadano__apellido_materno", "ciudadano__nombre"]
        constraints = [models.UniqueConstraint(fields=["concepto", "ciudadano"], name="unique_obligacion_por_concepto_ciudadano")]

    @property
    def total_abonado(self):
        return self.abonos.aggregate(total=Sum("monto"))["total"] or Decimal("0.00")

    @property
    def saldo_pendiente(self):
        saldo = self.monto_asignado - self.total_abonado
        return max(saldo, Decimal("0.00"))

    def actualizar_estado_por_abonos(self, save=True):
        if self.estado == self.Estados.CANCELADO:
            return self.estado
        self.estado = self.Estados.PAGADO if self.saldo_pendiente <= 0 else self.Estados.PENDIENTE
        if save:
            self.save(update_fields=["estado", "updated_at"])
        return self.estado

    def acreditar(self, monto, fecha=None, notas=""):
        monto = Decimal(str(monto))
        with transaction.atomic():
            obligacion = ObligacionCiudadano.objects.select_for_update().get(pk=self.pk)
            if obligacion.estado == self.Estados.CANCELADO:
                raise ValidationError("No se pueden registrar abonos sobre una obligación cancelada.")
            if obligacion.estado == self.Estados.PAGADO:
                raise ValidationError("No se pueden registrar abonos sobre una obligación pagada.")
            if monto <= 0:
                raise ValidationError("El monto del abono debe ser mayor que cero.")
            saldo = obligacion.saldo_pendiente
            if monto > saldo:
                raise ValidationError(f"El abono no puede superar el saldo pendiente de ${saldo:.2f}.")
            abono = Abono.objects.create(obligacion=obligacion, monto=monto, fecha=fecha or timezone.localdate(), notas=notas)
            obligacion.actualizar_estado_por_abonos(save=True)
            self.refresh_from_db()
            return abono

    def __str__(self):
        return f"{self.ciudadano.nombre_completo} · {self.concepto.concepto}"


class Abono(TimeStampedModel):
    obligacion = models.ForeignKey(ObligacionCiudadano, on_delete=models.CASCADE, related_name="abonos")
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    fecha = models.DateField(default=timezone.localdate)
    notas = models.TextField(blank=True)

    class Meta:
        verbose_name = "Abono"
        verbose_name_plural = "Abonos"
        ordering = ["-fecha", "-created_at"]

    def clean(self):
        if self.monto is not None and self.monto <= 0:
            raise ValidationError({"monto": "El monto del abono debe ser mayor que cero."})

    def __str__(self):
        return f"{self.obligacion} · ${self.monto}"
