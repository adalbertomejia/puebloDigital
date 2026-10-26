from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("comites", "0001_initial"),
        ("core", "0001_initial"),
        ("operacion", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="faena",
            name="comite",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="faenas",
                to="comites.comite",
            ),
        ),
        migrations.AddField(
            model_name="faena",
            name="motivo",
            field=models.CharField(blank=True, default="", max_length=250, verbose_name="Motivo"),
        ),
        migrations.AlterField(
            model_name="junta",
            name="comite",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="juntas",
                to="comites.comite",
            ),
        ),
        migrations.AddField(
            model_name="junta",
            name="motivo",
            field=models.CharField(blank=True, default="", max_length=250, verbose_name="Motivo"),
        ),
    ]
