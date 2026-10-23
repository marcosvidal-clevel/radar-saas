from django.db import models

class ConexionGoogle(models.Model):
    organizacion = models.ForeignKey("core.Organizacion", on_delete=models.CASCADE, related_name="conexiones_google")
    cuenta_email = models.EmailField()
    token_cifrado = models.TextField()
    scopes = models.JSONField(default=list)
    activa = models.BooleanField(default=True)
    creada_en = models.DateTimeField(auto_now_add=True)
    actualizada_en = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("organizacion", "cuenta_email"), name="conexion_google_org_cuenta_unica")]
        verbose_name = "Conexión Google"
        verbose_name_plural = "Conexiones Google"
