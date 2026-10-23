from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    initial = True
    dependencies = [("core", "0008_alter_oportunidad_origen")]
    operations = [migrations.CreateModel(name="ConexionGoogle", fields=[
        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
        ("cuenta_email", models.EmailField(max_length=254)),
        ("token_cifrado", models.TextField()),
        ("scopes", models.JSONField(default=list)),
        ("activa", models.BooleanField(default=True)),
        ("creada_en", models.DateTimeField(auto_now_add=True)),
        ("actualizada_en", models.DateTimeField(auto_now=True)),
        ("organizacion", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="conexiones_google", to="core.organizacion")),
    ], options={"verbose_name":"Conexión Google", "verbose_name_plural":"Conexiones Google", "constraints":[models.UniqueConstraint(fields=("organizacion", "cuenta_email"), name="conexion_google_org_cuenta_unica")]})]
