from django.db import migrations
from django.utils import timezone


def sync_age(apps, schema_editor):
    Ciudadano = apps.get_model('core', 'Ciudadano')
    today = timezone.localdate()
    for ciudadano in Ciudadano.objects.exclude(fecha_nacimiento__isnull=True):
        nacimiento = ciudadano.fecha_nacimiento
        ciudadano.edad = today.year - nacimiento.year - ((today.month, today.day) < (nacimiento.month, nacimiento.day))
        ciudadano.save(update_fields=['edad'])


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_replace_curp_with_edad'),
    ]

    operations = [
        migrations.RunPython(sync_age, migrations.RunPython.noop),
    ]
