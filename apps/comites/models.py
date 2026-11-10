from django.conf import settings
from django.db import models, transaction
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from apps.core.models import TimeStampedModel, Ciudadano


class PerfilAcceso(TimeStampedModel):
    """Links one authenticated account to one person in the community roster."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="perfil_acceso",
        verbose_name="Cuenta de usuario",
    )
    ciudadano = models.OneToOneField(
        Ciudadano,
        on_delete=models.PROTECT,
        related_name="perfil_acceso",
        verbose_name="Ciudadano",
    )

    class Meta:
        verbose_name = "Vínculo de cuenta y ciudadano"
        verbose_name_plural = "Vínculos de cuenta y ciudadano"
        ordering = ["ciudadano__apellido_paterno", "ciudadano__apellido_materno", "ciudadano__nombre"]

    def clean(self):
        super().clean()
        original = type(self).objects.filter(pk=self.pk).values('user_id','ciudadano_id').first() if self.pk else None
        if original and (original['user_id'] != self.user_id or original['ciudadano_id'] != self.ciudadano_id) and UsuarioApp.objects.filter(user_id=original['user_id'], activo=True).exists():
            raise ValidationError('Desactiva el cargo vigente antes de cambiar el vínculo de identidad.')
        if self.user_id and self.ciudadano_id and UsuarioApp.objects.filter(user_id=self.user_id, activo=True).exclude(ciudadano_id=self.ciudadano_id).exists():
            raise ValidationError({'ciudadano':'Desactiva el cargo vigente antes de cambiar la identidad de la cuenta.'})

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if self.user_id:
                get_user_model().objects.select_for_update().get(pk=self.user_id)
            if self.ciudadano_id:
                Ciudadano.objects.select_for_update().get(pk=self.ciudadano_id)
            self.full_clean()
            return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.ciudadano.nombre_completo} — {self.user}"

class Comite(TimeStampedModel):
    class Tipos(models.TextChoices):
        AGUA = 'AGUA', 'Agua'
        PANTEON = 'PANTEON', 'Panteón'
        FERIA = 'FERIA', 'Feria'
        IGLESIA = 'IGLESIA', 'Iglesia'
        PEREGRINO = 'PEREGRINO', 'Peregrino'
        CLINICA = 'CLINICA', 'Clínica'
        PEREGRINACION = 'PEREGRINACION', 'Peregrinación'
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
    ciudadano = models.ForeignKey(Ciudadano, on_delete=models.PROTECT, null=True, blank=True, related_name='accesos')
    comite = models.ForeignKey(Comite, on_delete=models.CASCADE, related_name='usuarios')
    rol = models.CharField(max_length=20, choices=Roles.choices)
    activo = models.BooleanField(default=True)

    def clean(self):
        super().clean()
        if self.user_id:
            from .cargos import validar_cargo
            validar_cargo(self)

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if self.user_id:
                get_user_model().objects.select_for_update().get(pk=self.user_id)
                perfil = PerfilAcceso.objects.filter(user_id=self.user_id).first()
                if perfil:
                    Ciudadano.objects.select_for_update().get(pk=perfil.ciudadano_id)
            self.full_clean()
            if kwargs.get('update_fields') is not None:
                kwargs['update_fields'] = set(kwargs['update_fields']) | {'ciudadano'}
            return super().save(*args, **kwargs)

    class Meta:
        verbose_name = 'Cargo de comité'
        verbose_name_plural = 'Cargos de comité'
        unique_together = ('user', 'comite', 'rol')
        constraints = [
            models.UniqueConstraint(fields=['user'], condition=models.Q(activo=True), name='cargo_activo_unico_cuenta'),
            models.UniqueConstraint(fields=['ciudadano'], condition=models.Q(activo=True), name='cargo_activo_unico_ciudadano'),
            models.CheckConstraint(condition=models.Q(activo=False) | models.Q(ciudadano__isnull=False), name='cargo_activo_con_ciudadano'),
        ]
        ordering = ['comite__nombre', 'rol']

    def __str__(self):
        return f"{self.user} - {self.comite} ({self.get_rol_display()})"
