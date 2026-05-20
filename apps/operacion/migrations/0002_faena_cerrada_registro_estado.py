from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('operacion', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='faena',
            name='estado',
            field=models.CharField(choices=[('PROGRAMADA', 'Programada'), ('REALIZADA', 'Realizada'), ('CERRADA', 'Cerrada'), ('CANCELADA', 'Cancelada')], default='PROGRAMADA', max_length=20),
        ),
        migrations.RenameField(
            model_name='registrofaena',
            old_name='estatus',
            new_name='estado',
        ),
        migrations.AlterField(
            model_name='registrofaena',
            name='estado',
            field=models.CharField(choices=[('PENDIENTE', 'Pendiente'), ('ASISTIO', 'Asistió'), ('FALTO', 'Faltó'), ('JUSTIFICADO', 'Justificado')], default='PENDIENTE', max_length=20),
        ),
        migrations.AlterUniqueTogether(
            name='registrofaena',
            unique_together=set(),
        ),
        migrations.AddConstraint(
            model_name='registrofaena',
            constraint=models.UniqueConstraint(fields=('faena', 'ciudadano'), name='uniq_faena_ciudadano_registro'),
        ),
    ]
