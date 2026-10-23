"""Añade RUT y dirección opcionales sin modificar datos existentes."""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("talento", "0001_initial"),
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
