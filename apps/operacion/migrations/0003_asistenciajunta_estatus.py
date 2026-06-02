from django.db import migrations, models


def sincronizar_estatus_existente(apps, schema_editor):
    AsistenciaJunta = apps.get_model('operacion', 'AsistenciaJunta')
    AsistenciaJunta.objects.filter(asistio=True).update(estatus='ASISTIO')
    AsistenciaJunta.objects.filter(asistio=False).update(estatus='FALTO')


class Migration(migrations.Migration):

    dependencies = [
        ('operacion', '0002_registrofaena_pendiente_default'),
    ]

    operations = [
        migrations.AddField(
            model_name='asistenciajunta',
            name='estatus',
            field=models.CharField(
                choices=[
                    ('PENDIENTE', 'Pendiente'),
                    ('ASISTIO', 'Asistió'),
                    ('FALTO', 'Faltó'),
                    ('JUSTIFICADO', 'Justificado'),
                ],
                default='PENDIENTE',
                max_length=20,
            ),
        ),
        migrations.RunPython(sincronizar_estatus_existente, migrations.RunPython.noop),
    ]
