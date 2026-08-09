from datetime import date

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, RegexValidator
from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Creado')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Actualizado')

    class Meta:
        abstract = True


class Manzana(TimeStampedModel):
    nombre = models.CharField(max_length=100, unique=True, verbose_name="Nombre")
    clave = models.CharField(
        max_length=30,
        unique=True,
        null=True,
        blank=True,
        verbose_name="Clave",
        validators=[
            RegexValidator(
                regex=r"^[A-Za-z0-9-]+$",
                message="La clave solo puede contener letras, números o guiones.",
            )
        ],
    )
    descripcion = models.TextField(blank=True, verbose_name="Descripción")
    activa = models.BooleanField(default=True, verbose_name="Activa")
    responsable = models.ForeignKey(
        "Ciudadano",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="manzanas_a_cargo",
        verbose_name="Responsable",
        help_text=(
            "El responsable debería pertenecer normalmente a la manzana que representa."
        ),
    )

    class Meta:
        verbose_name = "Manzana"
        verbose_name_plural = "Manzanas"
        ordering = ["nombre"]

    def __str__(self):
        if self.clave:
            return f"{self.nombre} ({self.clave})"
        return self.nombre


class Ciudadano(TimeStampedModel):
    class Sexos(models.TextChoices):
        HOMBRE = "HOMBRE", "Hombre"
        MUJER = "MUJER", "Mujer"
        NO_ESPECIFICADO = "NO_ESPECIFICADO", "No especificado"

    class MotivosAlta(models.TextChoices):
        ESTUDIOS = "ESTUDIOS", "Conclusión o interrupción de estudios"
        MAYORIA_EDAD = "MAYORIA_EDAD", "Mayoría de edad"
        INTEGRACION_COMUNIDAD = (
            "INTEGRACION_COMUNIDAD",
            "Integración voluntaria a la comunidad",
        )

    nombre = models.CharField(max_length=100)
    apellido_paterno = models.CharField(max_length=100)
    apellido_materno = models.CharField(max_length=100, blank=True)
    edad = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MaxValueValidator(130)],
        verbose_name="Edad registrada",
    )
    fecha_nacimiento = models.DateField(
        null=True, blank=True, verbose_name="Fecha de nacimiento"
    )
    sexo = models.CharField(
        max_length=20,
        choices=Sexos.choices,
        default=Sexos.NO_ESPECIFICADO,
        verbose_name="Sexo",
    )
    numero_contrato = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name="No. de contrato",
    )
    manzana = models.ForeignKey(
        "Manzana",
        on_delete=models.PROTECT,
        related_name="ciudadanos",
        null=True,
        blank=True,
        verbose_name="Manzana",
    )
    # Puede convertirse en una entidad independiente si se requieren varias
    # labores, fechas, estados o evidencias por ciudadano.
    labor_social = models.TextField(blank=True, verbose_name="Labor social")
    motivo_alta = models.CharField(
        max_length=22,
        choices=MotivosAlta.choices,
        blank=True,
        verbose_name="Motivo de alta",
    )
    direccion = models.TextField(blank=True)
    activo = models.BooleanField(default=True)
    observaciones = models.TextField(blank=True)

    class Meta:
        verbose_name = '🧑 Ciudadano'
        verbose_name_plural = '🧑 Ciudadanos'
        ordering = ['apellido_paterno', 'apellido_materno', 'nombre']
        indexes = [
            models.Index(fields=['edad']),
            models.Index(fields=['apellido_paterno', 'apellido_materno', 'nombre']),
            models.Index(fields=["manzana", "activo"], name="ciud_manz_act_idx"),
        ]

    @property
    def nombre_completo(self):
        return f"{self.nombre} {self.apellido_paterno} {self.apellido_materno}".strip()

    @property
    def edad_actual(self):
        """Edad efectiva: la fecha exacta tiene prioridad sobre el dato heredado."""
        if self.fecha_nacimiento:
            hoy = date.today()
            return hoy.year - self.fecha_nacimiento.year - (
                (hoy.month, hoy.day)
                < (self.fecha_nacimiento.month, self.fecha_nacimiento.day)
            )
        return self.edad

    def clean(self):
        super().clean()
        if self.fecha_nacimiento and self.fecha_nacimiento > date.today():
            raise ValidationError(
                {"fecha_nacimiento": "La fecha de nacimiento no puede estar en el futuro."}
            )

    def __str__(self):
        edad = self.edad_actual
        return f"{self.nombre_completo} ({edad} años)" if edad is not None else self.nombre_completo
