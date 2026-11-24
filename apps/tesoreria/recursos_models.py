"""Resource custody and review; separate from citizen receivables."""
import uuid
from decimal import Decimal
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from apps.core.models import TimeStampedModel


class InmutableQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError("Este historial no admite modificaciones directas.")

    def delete(self):
        raise ValidationError("Este historial no se elimina; conserva la evidencia registrada.")


class FondoRecurso(TimeStampedModel):
    objects = InmutableQuerySet.as_manager()
    class Categorias(models.TextChoices):
        OPERACION = "OPERACION", "Operación comunitaria"
        MANTENIMIENTO = "MANTENIMIENTO", "Mantenimiento"
        RESERVA = "RESERVA", "Reserva"
        OTRO = "OTRO", "Otro recurso"

    clave_apertura = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    nombre = models.CharField(max_length=120)
    categoria = models.CharField(max_length=20, choices=Categorias.choices)
    comite = models.ForeignKey("comites.Comite", on_delete=models.PROTECT)
    manzana = models.ForeignKey("core.Manzana", null=True, blank=True, on_delete=models.PROTECT)
    fecha_apertura = models.DateField()
    inicial_efectivo = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0"))])
    inicial_transferencia = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0"))])
    evidencia_apertura = models.CharField(max_length=250)
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["nombre", "pk"]
        permissions = [("consultar_balance", "Consultar balance comunitario agregado"),
                       ("gestionar_recursos", "Gestionar recursos de Delegación desde Secretaría")]
        constraints = [
            models.CheckConstraint(condition=models.Q(inicial_efectivo__gte=0, inicial_transferencia__gte=0), name="fondo_apertura_no_negativa"),
        ]
        indexes = [models.Index(fields=["comite", "manzana", "activo"], name="fondo_ambito_idx")]

    def save(self, *args, **kwargs):
        if self.pk:
            previo = type(self).objects.get(pk=self.pk)
            campos = ("clave_apertura", "nombre", "categoria", "comite_id", "manzana_id", "fecha_apertura", "inicial_efectivo", "inicial_transferencia", "evidencia_apertura", "creado_por_id")
            if any(getattr(previo, c) != getattr(self, c) for c in campos):
                raise ValidationError("La apertura y el ámbito del fondo son históricos. Registra otro fondo para una apertura distinta.")
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("La apertura de un recurso no se elimina; conserva su evidencia.")

    def __str__(self):
        return f"{self.nombre} · {self.comite}"


class MovimientoRecurso(TimeStampedModel):
    class Tipos(models.TextChoices):
        COBRO = "COBRO", "Abono recibido"
        SALIDA = "SALIDA", "Salida documentada"

    class Medios(models.TextChoices):
        EFECTIVO = "EFECTIVO", "Efectivo"
        TRANSFERENCIA = "TRANSFERENCIA", "Transferencia"

    class CategoriasSalida(models.TextChoices):
        MANTENIMIENTO = "MANTENIMIENTO", "Mantenimiento"
        PAPELERIA = "PAPELERIA", "Papel, tinta y material de oficina"
        REMUNERACION = "REMUNERACION", "Remuneraciones y apoyos"
        SERVICIOS = "SERVICIOS", "Servicios"
        OTRO = "OTRO", "Otro gasto documentado"

    objects = InmutableQuerySet.as_manager()
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    fondo = models.ForeignKey(FondoRecurso, on_delete=models.PROTECT, related_name="movimientos")
    abono = models.OneToOneField("tesoreria.Abono", on_delete=models.PROTECT, null=True, blank=True, related_name="movimiento_recurso")
    tipo = models.CharField(max_length=10, choices=Tipos.choices)
    medio = models.CharField(max_length=20, choices=Medios.choices)
    monto = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    fecha = models.DateField()
    descripcion = models.CharField(max_length=250)
    categoria_salida = models.CharField(max_length=20, choices=CategoriasSalida.choices, blank=True)
    beneficiario = models.CharField(max_length=150, blank=True)
    evidencia = models.CharField(max_length=250)
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    clave_operacion = models.UUIDField(unique=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        constraints = [
            models.CheckConstraint(condition=models.Q(monto__gt=0), name="recurso_monto_positivo"),
            models.CheckConstraint(condition=(models.Q(tipo="COBRO", abono__isnull=False, categoria_salida="") | models.Q(tipo="SALIDA", abono__isnull=True) & ~models.Q(categoria_salida="")), name="recurso_fuente_tipo_valida"),
        ]
        indexes = [models.Index(fields=["fondo", "created_at"], name="recurso_fondo_fecha_idx")]

    @property
    def folio(self):
        return f"PD-{'S' if self.tipo == 'SALIDA' else 'R'}-{str(self.pk).upper()}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Los movimientos registrados no se editan.")
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Los movimientos registrados no se eliminan.")


class CorteRecurso(TimeStampedModel):
    objects = InmutableQuerySet.as_manager()
    class Estados(models.TextChoices):
        EN_REVISION = "EN_REVISION", "En revisión"
        DEVUELTO = "DEVUELTO", "Devuelto para aclaración"
        CONFIRMADO = "CONFIRMADO", "Confirmado"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    fondo = models.ForeignKey(FondoRecurso, on_delete=models.PROTECT, related_name="cortes")
    desde = models.DateTimeField()
    hasta = models.DateTimeField()
    estado = models.CharField(max_length=15, choices=Estados.choices, default=Estados.EN_REVISION)
    preparado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="cortes_preparados")
    revisado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="cortes_revisados")
    revisado_en = models.DateTimeField(null=True, blank=True)
    contado = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0"))])
    esperado = models.DecimalField(max_digits=14, decimal_places=2)
    diferencia = models.DecimalField(max_digits=14, decimal_places=2)
    aclaracion = models.TextField(blank=True)
    evidencia_conteo = models.CharField(max_length=250)
    manifiesto = models.JSONField()
    huella = models.CharField(max_length=64)
    clave_operacion = models.UUIDField(unique=True)

    class Meta:
        ordering = ["-hasta", "-pk"]
        constraints = [
            models.UniqueConstraint(fields=["fondo"], condition=models.Q(estado="EN_REVISION"), name="corte_revision_unica_fondo"),
            models.CheckConstraint(condition=models.Q(desde__lte=models.F("hasta"), contado__gte=0), name="corte_intervalo_conteo_valido"),
            models.CheckConstraint(condition=~models.Q(preparado_por=models.F("revisado_por")), name="corte_segunda_persona"),
            models.CheckConstraint(condition=models.Q(diferencia=models.F("contado")-models.F("esperado")), name="corte_diferencia_exacta"),
            models.CheckConstraint(condition=~models.Q(estado="CONFIRMADO")|models.Q(diferencia=0), name="corte_confirmado_cuadrado"),
            models.CheckConstraint(condition=models.Q(estado="EN_REVISION", revisado_por__isnull=True, revisado_en__isnull=True)|models.Q(estado__in=["DEVUELTO","CONFIRMADO"], revisado_por__isnull=False, revisado_en__isnull=False), name="corte_revision_completa"),
        ]

    @property
    def folio(self):
        return f"PD-C-{str(self.pk).upper()}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            previo = type(self).objects.get(pk=self.pk)
            fijos = [f.attname for f in self._meta.concrete_fields if f.name not in ("estado", "revisado_por", "revisado_en", "updated_at")]
            if previo.estado != self.Estados.EN_REVISION or any(getattr(previo, c) != getattr(self, c) for c in fijos):
                raise ValidationError("El corte enviado conserva sus cifras y evidencia. La revisión no las modifica.")
            if self.estado not in (self.Estados.DEVUELTO, self.Estados.CONFIRMADO):
                raise ValidationError("Transición de revisión inválida.")
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Los cortes enviados no se eliminan.")


class EventoCorteRecurso(models.Model):
    objects = InmutableQuerySet.as_manager()
    corte = models.ForeignKey(CorteRecurso, on_delete=models.PROTECT, related_name="eventos")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    accion = models.CharField(max_length=20, choices=[("ENVIAR", "Envío a revisión"), ("DEVOLVER", "Solicitud de aclaración"), ("CONFIRMAR", "Confirmación")])
    fecha = models.DateTimeField(auto_now_add=True)
    motivo = models.TextField()

    class Meta:
        ordering = ["fecha", "pk"]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("La evidencia de revisión no se modifica.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("La evidencia de revisión no se elimina.")
