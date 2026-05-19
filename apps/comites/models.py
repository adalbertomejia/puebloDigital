from django.conf import settings
from django.db import models
from apps.core.models import TimeStampedModel, Ciudadano

class Comite(TimeStampedModel):
    class Tipos(models.TextChoices):
        AGUA = 'AGUA', 'Agua'
        FERIA = 'FERIA', 'Feria'
        IGLESIA = 'IGLESIA', 'Iglesia'
        DELEGACION = 'DELEGACION', 'Delegación'

    nombre = models.CharField(max_length=100, unique=True)
    tipo = models.CharField(max_length=20, choices=Tipos.choices, default=Tipos.DELEGACION)
    activo = models.BooleanField(default=True)
    descripcion = models.TextField(blank=True)

    class Meta:
        verbose_name = '🏛️ Comité'
        verbose_name_plural = '🏛️ Comités'
        ordering = ['nombre']

    def __str__(self):
        return self.nombre

class UsuarioApp(TimeStampedModel):
    class Roles(models.TextChoices):
        DELEGADO = 'DELEGADO', 'Delegado'
        PRESIDENTE = 'PRESIDENTE', 'Presidente'
        TESORERO = 'TESORERO', 'Tesorero'
        SECRETARIO = 'SECRETARIO', 'Secretario'
        CAPTURISTA = 'CAPTURISTA', 'Capturista'
        LECTURA = 'LECTURA', 'Solo lectura'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='perfiles_app')
    ciudadano = models.ForeignKey(Ciudadano, on_delete=models.SET_NULL, null=True, blank=True, related_name='accesos')
    comite = models.ForeignKey(Comite, on_delete=models.CASCADE, related_name='usuarios')
    rol = models.CharField(max_length=20, choices=Roles.choices)
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Perfil de acceso'
        verbose_name_plural = 'Perfiles de acceso'
        unique_together = ('user', 'comite', 'rol')
        ordering = ['comite__nombre', 'rol']

    def __str__(self):
        return f"{self.user} - {self.comite} ({self.get_rol_display()})"
