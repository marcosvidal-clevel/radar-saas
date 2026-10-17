from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("talento", "0014_candidato_consolidado_en_candidatoprocedencia")]

    operations = [
        migrations.AddField(
            model_name="documentocandidato", name="origen_importacion",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="documentocandidato", name="identificador_origen",
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddConstraint(
            model_name="documentocandidato",
            constraint=models.UniqueConstraint(
                fields=("candidato", "origen_importacion", "identificador_origen"),
                condition=models.Q(origen_importacion__gt="", identificador_origen__gt=""),
                name="documento_origen_unico_por_candidato",
            ),
        ),
    ]
