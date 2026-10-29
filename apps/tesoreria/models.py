from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.db.models import Sum
from django.utils import timezone

from apps.core.models import TimeStampedModel, Ciudadano
from apps.comites.models import Comite
from apps.agua.models import Toma
from apps.operacion.models import RegistroFaena
from apps.operacion.alcance import validar_alcance_y_manzana

from .validaciones import validar_cambios_con_obligaciones


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
    periodo_agua = models.DateField(null=True, blank=True, verbose_name="Periodo mensual de agua")
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="conceptotesoreria_creados", verbose_name="Registrado por", editable=False,
    )
    class Naturalezas(models.TextChoices):
        PAGO = "PAGO", "Pago"
        COOPERACION = "COOPERACION", "Cooperación"

    class Alcances(models.TextChoices):
        GENERAL = "GENERAL", "Toda la comunidad"
        MANZANA = "MANZANA", "Por manzana"

    class Origenes(models.TextChoices):
        TESORERIA = "TESORERIA", "Tesorería"
        FAENA = "FAENA", "Faena"
        JUNTA = "JUNTA", "Junta"
        AGUA = "AGUA", "Agua"

    naturaleza = models.CharField(max_length=20, choices=Naturalezas.choices)
    alcance = models.CharField(max_length=15, choices=Alcances.choices, default=Alcances.GENERAL, verbose_name="Alcance")
    manzana = models.ForeignKey(
        "core.Manzana", on_delete=models.PROTECT, null=True, blank=True,
        related_name="conceptos_tesoreria", verbose_name="Manzana",
    )
    origen = models.CharField(max_length=20, choices=Origenes.choices, default=Origenes.TESORERIA)
    comite = models.ForeignKey(Comite, on_delete=models.PROTECT, related_name="conceptos_tesoreria")
    concepto = models.CharField(max_length=200)
    descripcion = models.TextField(blank=True)
    monto_individual = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    fecha = models.DateField(default=timezone.localdate)
    anio_periodo = models.PositiveIntegerField(null=True, blank=True)
    registros_generados = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Concepto de tesorería"
        verbose_name_plural = "Conceptos de tesorería"
        ordering = ["-fecha", "-created_at"]
        constraints = [models.UniqueConstraint(fields=["comite", "periodo_agua"], condition=models.Q(origen="AGUA", periodo_agua__isnull=False), name="agua_comite_periodo_unico", violation_error_message="Ya existe una cuota de agua para ese mes.")]
        indexes = [models.Index(fields=["naturaleza", "alcance", "manzana", "fecha"], name="tes_nat_alc_mz_fecha_idx")]

    def clean(self):
        super().clean()
        if self.origen == self.Origenes.AGUA and (self.periodo_agua or self._state.adding):
            from apps.agua.autorizacion import comite_agua
            if not self.periodo_agua or self.periodo_agua.day != 1:
                raise ValidationError({"periodo_agua": "Selecciona el mes de la cuota de agua."})
            if self.comite_id != comite_agua().pk or self.alcance != self.Alcances.GENERAL or self.naturaleza != self.Naturalezas.PAGO:
                raise ValidationError("La cuota mensual de agua debe ser un pago general del comité de Agua.")
        elif self.periodo_agua:
            raise ValidationError({"periodo_agua": "El periodo de agua solo aplica a cuotas de agua."})
        errors = validar_alcance_y_manzana(
            alcance=self.alcance, manzana_id=self.manzana_id,
            alcance_general=self.Alcances.GENERAL, alcance_manzana=self.Alcances.MANZANA,
            nombre_entidad="concepto",
        )
        errors.update(validar_cambios_con_obligaciones(self))
        if errors:
            raise ValidationError(errors)
        if not self.concepto or not self.concepto.strip():
            raise ValidationError({"concepto": "El concepto no puede estar vacío."})
        if self.monto_individual is not None and self.monto_individual <= 0:
            raise ValidationError({"monto_individual": "El monto individual debe ser mayor que cero."})
        if not self.comite_id:
            raise ValidationError({"comite": "Debe seleccionar un comité."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def alcance_legible(self):
        if self.alcance == self.Alcances.MANZANA and self.manzana_id:
            return str(self.manzana)
        return self.Alcances.GENERAL.label

    def __str__(self):
        return f"{self.get_naturaleza_display()} · {self.concepto}"


class ObligacionCiudadano(TimeStampedModel):
    toma = models.ForeignKey(Toma, on_delete=models.PROTECT, null=True, blank=True, related_name="obligaciones", verbose_name="Toma de agua")
    numero_toma_registrado = models.CharField(max_length=30, blank=True, editable=False)
    numero_contrato_registrado = models.CharField(max_length=50, blank=True, editable=False)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="obligacionciudadano_creados", verbose_name="Registrado por", editable=False,
    )
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

    def clean(self):
        super().clean()
        original = type(self).objects.filter(pk=self.pk).values("toma_id", "ciudadano_id", "concepto_id").first() if self.pk else None
        if original and all(original[campo] == getattr(self, campo) for campo in original):
            return
        if self.concepto_id and self.concepto.origen == "AGUA" and self.concepto.periodo_agua:
            if not self.toma_id or self.toma.ciudadano_id != self.ciudadano_id:
                raise ValidationError({"toma": "Selecciona la toma correspondiente al ciudadano de esta obligación."})

    def save(self, *args, **kwargs):
        if self._state.adding and self.toma_id:
            self.numero_toma_registrado = self.toma.numero_toma
            self.numero_contrato_registrado = self.toma.ciudadano.numero_contrato or ""
        return super().save(*args, **kwargs)

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

    def acreditar(self, monto, fecha=None, notas="", *, usuario=None, referencia=""):
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
            abono = Abono.objects.create(obligacion=obligacion, monto=monto, fecha=fecha or timezone.localdate(), notas=notas, creado_por=usuario, referencia=referencia)
            obligacion.actualizar_estado_por_abonos(save=True)
            if usuario is not None:
                from .auditoria import registrar_movimiento
                registrar_movimiento(usuario, abono, RegistroFinanciero.Acciones.ABONAR)
            self.refresh_from_db()
            return abono

    def __str__(self):
        return f"{self.ciudadano.nombre_completo} · {self.concepto.concepto}"


class Abono(TimeStampedModel):
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="abono_creados", verbose_name="Registrado por", editable=False,
    )
    obligacion = models.ForeignKey(ObligacionCiudadano, on_delete=models.CASCADE, related_name="abonos")
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    fecha = models.DateField(default=timezone.localdate)
    referencia = models.CharField(max_length=100, blank=True, verbose_name="Referencia del comprobante")
    notas = models.TextField(blank=True)

    class Meta:
        verbose_name = "Abono"
        verbose_name_plural = "Abonos"
        ordering = ["-fecha", "-created_at"]

    @property
    def folio_recibo(self):
        return f"PD-A-{self.pk:08d}" if self.pk is not None else ""

    def clean(self):
        if self.monto is not None and self.monto <= 0:
            raise ValidationError({"monto": "El monto del abono debe ser mayor que cero."})
        if not self.obligacion_id or self.monto is None:
            return

        obligacion = self.obligacion
        if obligacion.estado == ObligacionCiudadano.Estados.CANCELADO:
            raise ValidationError("No se pueden registrar abonos sobre una obligación cancelada.")
        if obligacion.estado == ObligacionCiudadano.Estados.PAGADO and not self.pk:
            raise ValidationError("No se pueden registrar abonos sobre una obligación pagada.")

        abonos_existentes = obligacion.abonos.all()
        if self.pk:
            abonos_existentes = abonos_existentes.exclude(pk=self.pk)
        total_existente = abonos_existentes.aggregate(total=Sum("monto"))["total"] or Decimal("0.00")
        saldo_disponible = max(obligacion.monto_asignado - total_existente, Decimal("0.00"))
        if self.monto > saldo_disponible:
            raise ValidationError(f"El abono no puede superar el saldo pendiente de ${saldo_disponible:.2f}.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.obligacion} · ${self.monto}"


class RegistroFinanciero(models.Model):
    """Append-only operational evidence; IDs survive deletion of business rows."""

    class Acciones(models.TextChoices):
        CREAR = "CREAR", "Creación"
        EDITAR = "EDITAR", "Edición"
        GENERAR = "GENERAR", "Generación de obligaciones"
        ABONAR = "ABONAR", "Registro de abono"
        ELIMINAR = "ELIMINAR", "Eliminación"

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="registros_financieros")
    usuario_nombre = models.CharField(max_length=150, verbose_name="Usuario al registrar")
    comite = models.ForeignKey(Comite, on_delete=models.PROTECT, related_name="registros_financieros")
    fecha_registro = models.DateTimeField(auto_now_add=True)
    accion = models.CharField(max_length=15, choices=Acciones.choices)
    tipo_objeto = models.CharField(max_length=30)
    objeto_id = models.PositiveBigIntegerField()
    concepto_id_registrado = models.PositiveBigIntegerField()
    concepto_nombre = models.CharField(max_length=200)
    monto = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    referencia = models.CharField(max_length=100, blank=True)
    detalle = models.JSONField(default=dict, blank=True)
    origen = models.CharField(max_length=10, choices=[("PANEL", "Panel"), ("ADMIN", "Administración")], default="PANEL")

    class Meta:
        verbose_name = "Registro de actividad financiera"
        verbose_name_plural = "Actividad financiera"
        ordering = ["-fecha_registro", "-pk"]
        indexes = [
            models.Index(fields=["comite", "-fecha_registro"], name="fin_comite_fecha_idx"),
            models.Index(fields=["concepto_id_registrado", "-fecha_registro"], name="fin_concepto_fecha_idx"),
        ]

    def __str__(self):
        return f"{self.get_accion_display()} — {self.concepto_nombre} — {self.usuario_nombre}"
