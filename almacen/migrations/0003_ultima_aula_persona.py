from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("almacen", "0002_crear_grupo_profesores"),
    ]
    operations = [
        migrations.AddField(
            model_name="persona",
            name="last_aula",
            field=models.ForeignKey(
                to="almacen.aula",
                on_delete=django.db.models.deletion.SET_NULL,
                null=True,
                blank=True,
                related_name="preferida_por",
            ),
        ),
    ]
