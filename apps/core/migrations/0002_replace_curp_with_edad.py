from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name='ciudadano',
            name='core_ciudad_curp_ebfa01_idx',
        ),
        migrations.RemoveField(
            model_name='ciudadano',
            name='curp',
        ),
        migrations.AddField(
            model_name='ciudadano',
            name='edad',
            field=models.PositiveSmallIntegerField(default=18),
            preserve_default=False,
        ),
        migrations.AddIndex(
            model_name='ciudadano',
            index=models.Index(fields=['edad'], name='core_ciudad_edad_362f20_idx'),
        ),
    ]
