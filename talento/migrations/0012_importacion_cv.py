from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [
        ("talento", "0011_entrevista_recomendacion_entrevista_resultado"),
    ]

    operations = [
        migrations.AddField(
            model_name="candidato",
            name="identificador_origen",
            field=models.CharField(blank=True, help_text="Identificador estable entregado por la fuente.", max_length=200),
        ),
        migrations.AddField(
            model_name="candidato",
            name="origen_importacion",
            field=models.CharField(blank=True, help_text="Fuente externa de la importación, si corresponde.", max_length=100),
        ),
        migrations.AddField(
            model_name="documentocandidato",
            name="sha256",
            field=models.CharField(blank=True, db_index=True, editable=False, max_length=64),
        ),
        migrations.AddConstraint(
            model_name="candidato",
            constraint=models.UniqueConstraint(
                condition=Q(identificador_origen__gt="", origen_importacion__gt=""),
                fields=("organizacion", "origen_importacion", "identificador_origen"),
                name="candidato_origen_unico_por_organizacion",
            ),
        ),
    ]
