from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(
            name="Aula",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("nombre", models.CharField(max_length=120, unique=True)),
                ("codigo", models.CharField(max_length=50, unique=True)),
            ],
        ),
        migrations.CreateModel(
            name="Producto",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("nombre", models.CharField(max_length=255)),
                ("epc", models.CharField(max_length=96, unique=True, verbose_name="EPC (RFID)")),
                ("posicion", models.CharField(blank=True, max_length=120)),
                ("n_serie", models.CharField(blank=True, max_length=120)),
                ("foto", models.ImageField(blank=True, null=True, upload_to="productos/")),
                ("estanteria", models.CharField(blank=True, max_length=120)),
                ("cantidad", models.FloatField(default=1)),
                ("descripcion", models.TextField(blank=True)),
                ("fds", models.URLField(blank=True, verbose_name="Ficha de seguridad (FDS)")),
                ("holder_desde", models.DateTimeField(blank=True, null=True)),
                ("creado", models.DateTimeField(auto_now_add=True)),
                ("actualizado", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["nombre", "aula_id"]},
        ),
        migrations.CreateModel(
            name="Ubicacion",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "tipo",
                    models.CharField(
                        choices=[("SHELF", "En estantería"), ("CO", "En préstamo")], max_length=10
                    ),
                ),
                ("estanteria", models.CharField(blank=True, max_length=120)),
                ("posicion", models.CharField(blank=True, max_length=120)),
                ("fecha", models.DateTimeField()),
                (
                    "aula",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="store.aula"),
                ),
                (
                    "persona",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "producto",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ubicaciones",
                        to="store.producto",
                    ),
                ),
            ],
            options={"ordering": ["-fecha"]},
        ),
        migrations.AddField(
            model_name="producto",
            name="aula",
            field=migrations.fields.related.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="productos",
                to="store.aula",
            ),
        ),
        migrations.AddField(
            model_name="producto",
            name="holder",
            field=migrations.fields.related.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="prestamos",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
