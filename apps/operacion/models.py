from django.db import models
from apps.core.models import TimeStampedModel, Ciudadano
from apps.comites.models import Comite
from .alcance import validar_territorio_evento

class Junta(TimeStampedModel):
    class Alcances(models.TextChoices):
        GENERAL = "GENERAL", "Toda la comunidad"
        MANZANA = "MANZANA", "Por manzana"

    class Estados(models.TextChoices):
        PROGRAMADA = 'PROGRAMADA', 'Programada'
        REALIZADA = 'REALIZADA', 'Realizada'
        CANCELADA = 'CANCELADA', 'Cancelada'

    class Tipos(models.TextChoices):
        ORDINARIA = 'ORDINARIA', 'Ordinaria'
        EXTRAORDINARIA = 'EXTRAORDINARIA', 'Extraordinaria'
        INFORMATIVA = 'INFORMATIVA', 'Informativa'

    comite = models.ForeignKey(Comite, on_delete=models.CASCADE, related_name='juntas')
    fecha = models.DateField()
    alcance = models.CharField(max_length=15, choices=Alcances.choices, default=Alcances.GENERAL, verbose_name="Alcance")
    manzana = models.ForeignKey(
        "core.Manzana", on_delete=models.PROTECT, null=True, blank=True,
        related_name="juntas", verbose_name="Manzana",
    )
    tipo = models.CharField(max_length=20, choices=Tipos.choices, default=Tipos.ORDINARIA)
    lugar = models.CharField(max_length=150, blank=True)
    tema = models.CharField(max_length=200)
    estado = models.CharField(max_length=20, choices=Estados.choices, default=Estados.PROGRAMADA)
    notas = models.TextField(blank=True)

    class Meta:
        verbose_name = '\U0001F465 Junta'
        verbose_name_plural = '\U0001F465 Juntas'
        ordering = ['-fecha']
        indexes = [
            models.Index(fields=["alcance", "manzana", "fecha"], name="junta_alc_manz_fecha_idx"),
        ]

    def clean(self):
        super().clean()
        validar_territorio_evento(
            instancia=self, registros=AsistenciaJunta.objects.filter(junta_id=self.pk), nombre_entidad="junta"
        )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.comite} - {self.fecha} - {self.tema}"

class AsistenciaJunta(TimeStampedModel):
    class Estatus(models.TextChoices):
        PENDIENTE = 'PENDIENTE', 'Pendiente'
        ASISTIO = 'ASISTIO', 'Asistió'
        FALTO = 'FALTO', 'Faltó'
        JUSTIFICADO = 'JUSTIFICADO', 'Justificado'

    junta = models.ForeignKey(Junta, on_delete=models.CASCADE, related_name='asistencias')
    ciudadano = models.ForeignKey(Ciudadano, on_delete=models.CASCADE, related_name='asistencias_junta')
    estatus = models.CharField(max_length=20, choices=Estatus.choices, default=Estatus.PENDIENTE)
    genera_adeudo = models.BooleanField(default=False)
    monto_adeudo = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    asistio = models.BooleanField(default=True)
    observaciones = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Asistencia a junta'
        verbose_name_plural = 'Asistencias a juntas'
        unique_together = ('junta', 'ciudadano')

    def __str__(self):
        return f"{self.ciudadano.nombre_completo} - {self.junta} ({self.estatus})"

class Faena(TimeStampedModel):
    class Alcances(models.TextChoices):
        GENERAL = "GENERAL", "Toda la comunidad"
        MANZANA = "MANZANA", "Por manzana"

    class Estados(models.TextChoices):
        PROGRAMADA = 'PROGRAMADA', 'Programada'
        REALIZADA = 'REALIZADA', 'Realizada'
        CANCELADA = 'CANCELADA', 'Cancelada'

    comite = models.ForeignKey(Comite, on_delete=models.CASCADE, related_name='faenas')
    fecha = models.DateField()
    alcance = models.CharField(
        max_length=15,
        choices=Alcances.choices,
        default=Alcances.GENERAL,
        verbose_name="Alcance",
    )
    manzana = models.ForeignKey(
        "core.Manzana",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="faenas",
        verbose_name="Manzana",
    )
    descripcion = models.CharField(max_length=200)
    estado = models.CharField(max_length=20, choices=Estados.choices, default=Estados.PROGRAMADA)
    notas = models.TextField(blank=True)

    class Meta:
        verbose_name = '🛠️ Faena'
        verbose_name_plural = '🛠️ Faenas'
        ordering = ['-fecha']
        indexes = [
            models.Index(fields=["alcance", "manzana", "fecha"], name="faena_alc_manz_fecha_idx"),
        ]

    def clean(self):
        super().clean()
        validar_territorio_evento(
            instancia=self, registros=RegistroFaena.objects.filter(faena_id=self.pk), nombre_entidad="faena"
        )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.comite} - {self.fecha} - {self.descripcion}"

class RegistroFaena(TimeStampedModel):
    class Estatus(models.TextChoices):
        PENDIENTE = 'PENDIENTE', 'Pendiente'
        ASISTIO = 'ASISTIO', 'Asistió'
        FALTO = 'FALTO', 'Faltó'
        JUSTIFICADO = 'JUSTIFICADO', 'Justificado'

    faena = models.ForeignKey(Faena, on_delete=models.CASCADE, related_name='registros')
    ciudadano = models.ForeignKey(Ciudadano, on_delete=models.CASCADE, related_name='registros_faena')
    estatus = models.CharField(max_length=20, choices=Estatus.choices, default=Estatus.PENDIENTE)
    genera_adeudo = models.BooleanField(default=False)
    monto_adeudo = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    observaciones = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Registro de faena'
        verbose_name_plural = 'Registros de faena'
        unique_together = ('faena', 'ciudadano')

    def __str__(self):
        return f"{self.ciudadano.nombre_completo} - {self.faena} ({self.estatus})"

class Actividad(TimeStampedModel):
    comite = models.ForeignKey(Comite, on_delete=models.CASCADE, related_name='actividades')
    titulo = models.CharField(max_length=200)
    descripcion = models.TextField(blank=True)
    fecha = models.DateField()

    class Meta:
        verbose_name = '📌 Actividad'
        verbose_name_plural = '📌 Actividades'
        ordering = ['-fecha']

    def __str__(self):
        return f"{self.comite} - {self.titulo}"

class ActividadArchivo(TimeStampedModel):
    actividad = models.ForeignKey(Actividad, on_delete=models.CASCADE, related_name='archivos')
    nombre = models.CharField(max_length=150)
    archivo = models.FileField(upload_to='actividades/')
    descripcion = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Archivo de actividad'
        verbose_name_plural = 'Archivos de actividades'

    def __str__(self):
        return self.nombre
