from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('operacion', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='registrofaena',
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
    ]
