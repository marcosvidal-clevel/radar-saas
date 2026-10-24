from django.db import models


class RecepcionComercial(models.Model):
    organizacion = models.ForeignKey("core.Organizacion", on_delete=models.PROTECT)
    sitio = models.SlugField()
    buzon = models.EmailField()
    mensaje_id = models.CharField(max_length=200)
    es_prueba = models.BooleanField(default=True)
    contenido = models.JSONField()
    contenido_hash = models.CharField(max_length=64)
    similitud_hash = models.CharField(max_length=64, db_index=True)
    observaciones = models.JSONField(default=list)
    oportunidad = models.OneToOneField(
        "core.Oportunidad", null=True, blank=True, on_delete=models.PROTECT,
    )
    recibida_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(
            fields=["organizacion", "buzon", "mensaje_id", "es_prueba"],
            name="recepcion_comercial_mensaje_modo_unico",
        )]
