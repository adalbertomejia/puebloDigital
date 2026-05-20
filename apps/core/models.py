from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone

class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Creado')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Actualizado')

    class Meta:
        abstract = True

class Ciudadano(TimeStampedModel):
    nombre = models.CharField(max_length=100)
    apellido_paterno = models.CharField(max_length=100)
    apellido_materno = models.CharField(max_length=100, blank=True)
    edad = models.PositiveSmallIntegerField()
    fecha_nacimiento = models.DateField(null=True, blank=True)
    telefono = models.CharField(max_length=20, blank=True)
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

    def clean(self):
        super().clean()
        if self.fecha_nacimiento:
            today = timezone.localdate()
            if self.fecha_nacimiento > today:
                raise ValidationError({"fecha_nacimiento": "La fecha de nacimiento no puede ser futura."})

            self.edad = today.year - self.fecha_nacimiento.year - (
                (today.month, today.day) < (self.fecha_nacimiento.month, self.fecha_nacimiento.day)
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
