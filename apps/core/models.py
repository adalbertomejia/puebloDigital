from django.core.validators import RegexValidator
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
    edad = models.PositiveSmallIntegerField()
    fecha_nacimiento = models.DateField(null=True, blank=True)
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

    def __str__(self):
        return f"{self.nombre_completo} ({self.edad} años)"
