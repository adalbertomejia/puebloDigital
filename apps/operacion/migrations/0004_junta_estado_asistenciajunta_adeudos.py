from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('operacion', '0003_asistenciajunta_estatus'),
    ]

    operations = [
        migrations.AddField(
            model_name='junta',
            name='estado',
            field=models.CharField(
                choices=[
                    ('PROGRAMADA', 'Programada'),
                    ('REALIZADA', 'Realizada'),
                    ('CANCELADA', 'Cancelada'),
                ],
                default='PROGRAMADA',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='asistenciajunta',
            name='genera_adeudo',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='asistenciajunta',
            name='monto_adeudo',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
    ]
