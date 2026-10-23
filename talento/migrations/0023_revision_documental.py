from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("talento", "0022_adjunto_importado"),
    ]

    operations = [
        migrations.AddField(
            model_name="candidato",
            name="revision_documental",
            field=models.CharField(
                choices=[
                    ("pendiente", "Pendiente de revisión"),
                    ("aprobado", "Aprobado"),
                    ("rechazado", "Rechazado"),
                ],
                db_index=True,
                default="pendiente",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="candidato",
            name="observaciones_revision",
            field=models.TextField(blank=True),
        ),
    ]
