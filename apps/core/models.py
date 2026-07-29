from django.db import models

class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Creado')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Actualizado')

    class Meta:
        abstract = True


class Manzana(TimeStampedModel):
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True)
    activa = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Manzana"
        verbose_name_plural = "Manzanas"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class Ciudadano(TimeStampedModel):
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
        Manzana,
        on_delete=models.PROTECT,
        related_name="ciudadanos",
        null=True,
        blank=True,
    )
    # Puede convertirse en una entidad independiente si se requieren varias
    # labores, fechas, estados o evidencias por ciudadano.
    labor_social = models.TextField(blank=True, verbose_name="Labor social")
    motivo_alta = models.TextField(blank=True, verbose_name="Motivo de alta")
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
        ]

    @property
    def nombre_completo(self):
        return f"{self.nombre} {self.apellido_paterno} {self.apellido_materno}".strip()

    def __str__(self):
        return f"{self.nombre_completo} ({self.edad} años)"
