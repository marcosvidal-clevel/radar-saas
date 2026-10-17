from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("talento", "0015_documentocandidato_procedencia")]

    operations = [
        migrations.AddField(
            model_name="documentocandidato",
            name="pendiente_clasificacion",
            field=models.BooleanField(default=False, db_index=True),
        ),
    ]
