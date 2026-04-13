from django.core.exceptions import ValidationError
from django.db import models

class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Creado')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Actualizado')

    class Meta:
        abstract = True

class Ciudadano(TimeStampedModel):
    nombre = models.CharField(max_length=100)
    apellido_paterno = models.CharField(max_length=100)
    apellido_materno = models.CharField(max_length=100, blank=True)
    curp = models.CharField(max_length=18, unique=True)
    fecha_nacimiento = models.DateField(null=True, blank=True)
    telefono = models.CharField(max_length=20, blank=True)
    direccion = models.TextField(blank=True)
    activo = models.BooleanField(default=True)
    observaciones = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Ciudadano'
        verbose_name_plural = 'Ciudadanos'
        ordering = ['apellido_paterno', 'apellido_materno', 'nombre']
        indexes = [
            models.Index(fields=['curp']),
            models.Index(fields=['apellido_paterno', 'apellido_materno', 'nombre']),
        ]

    def clean(self):
        if self.curp:
            self.curp = self.curp.strip().upper()
            if len(self.curp) != 18:
                raise ValidationError({'curp': 'La CURP debe tener 18 caracteres.'})

    def save(self, *args, **kwargs):
        if self.curp:
            self.curp = self.curp.strip().upper()
        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def nombre_completo(self):
        return f"{self.nombre} {self.apellido_paterno} {self.apellido_materno}".strip()

    def __str__(self):
        return f"{self.nombre_completo} ({self.curp})"
