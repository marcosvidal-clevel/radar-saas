from django.db import migrations, models
import django.db.models.deletion
import talento.models


class Migration(migrations.Migration):
    dependencies = [("talento", "0021_candidato_rut_direccion")]

    operations = [
        migrations.CreateModel(
            name="AdjuntoImportado",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nombre", models.CharField(max_length=255)),
                ("archivo", models.FileField(upload_to=talento.models.ruta_adjunto_importado)),
                ("origen_importacion", models.CharField(max_length=100)),
                ("identificador_origen", models.CharField(max_length=200)),
                ("tipo", models.CharField(default="otro", max_length=30)),
                ("creado_en", models.DateTimeField(auto_now_add=True)),
                ("candidato", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="otros_adjuntos_importados", to="talento.candidato")),
            ],
        ),
        migrations.AddConstraint(
            model_name="adjuntoimportado",
            constraint=models.UniqueConstraint(fields=("candidato", "origen_importacion", "identificador_origen"), name="adjunto_importado_origen_unico"),
        ),
    ]
