"""Campos opcionales de identificación para candidatos importados."""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("talento", "0020_recepcion_pendiente_contexto"),
    ]

    operations = [
        migrations.AddField(
            model_name="candidato",
            name="rut",
            field=models.CharField(blank=True, db_index=True, max_length=16),
        ),
        migrations.AddField(
            model_name="candidato",
            name="direccion",
            field=models.CharField(blank=True, max_length=250),
        ),
    ]
