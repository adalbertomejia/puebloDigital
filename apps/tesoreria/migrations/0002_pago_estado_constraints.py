from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tesoreria', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='pago',
            name='estado',
            field=models.CharField(choices=[('PENDIENTE', 'Pendiente'), ('PAGADO', 'Pagado'), ('CANCELADO', 'Cancelado')], default='PENDIENTE', max_length=20),
        ),
        migrations.AddConstraint(
            model_name='pago',
            constraint=models.UniqueConstraint(fields=('toma', 'anio_periodo', 'tipo'), name='uniq_pago_toma_anio_tipo'),
        ),
        migrations.AddConstraint(
            model_name='pago',
            constraint=models.UniqueConstraint(fields=('registro_faena', 'tipo'), name='uniq_pago_registro_faena_tipo'),
        ),
    ]
