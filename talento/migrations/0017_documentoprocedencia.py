from django.db import migrations, models
import django.db.models.deletion


def enlazar_procedencias_existentes(apps, schema_editor):
    Documento = apps.get_model("talento", "DocumentoCandidato")
    Procedencia = apps.get_model("talento", "CandidatoProcedencia")
    Vinculo = apps.get_model("talento", "DocumentoProcedencia")
    for documento in Documento.objects.exclude(
        origen_importacion="", identificador_origen=""
    ).iterator():
        procedencias = Procedencia.objects.filter(
            candidato_id=documento.candidato_id,
            organizacion_id=documento.candidato.organizacion_id,
            origen_importacion=documento.origen_importacion,
        )
        if procedencias.count() == 1:
            procedencia = procedencias.get()
            Vinculo.objects.get_or_create(
                documento_id=documento.pk,
                procedencia_id=procedencia.pk,
                identificador_origen=documento.identificador_origen,
            )


class Migration(migrations.Migration):
    dependencies = [("talento", "0016_documentocandidato_pendiente_clasificacion")]

    operations = [
        migrations.CreateModel(
            name="DocumentoProcedencia",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "documento",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="procedencias",
                        to="talento.documentocandidato",
                    ),
                ),
                (
                    "procedencia",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="documentos",
                        to="talento.candidatoprocedencia",
                    ),
                ),
                ("identificador_origen", models.CharField(max_length=200)),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(
                        fields=("procedencia", "identificador_origen"),
                        name="procedencia_identificador_documento_unico",
                    ),
                ],
            },
        ),
        migrations.RunPython(enlazar_procedencias_existentes, migrations.RunPython.noop),
    ]
