from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0007_alter_ciudadano_motivo_alta"),
    ]

    operations = [
        migrations.AlterField(
            model_name="ciudadano",
            name="motivo_alta",
            field=models.CharField(
                blank=True,
                choices=[
                    ("ESTUDIOS", "Conclusión o interrupción de estudios"),
                    ("MAYORIA_EDAD", "Mayoría de edad"),
                    ("INTEGRACION_COMUNIDAD", "Integración voluntaria a la comunidad"),
                ],
                max_length=22,
                verbose_name="Motivo de alta",
            ),
        ),
    ]
