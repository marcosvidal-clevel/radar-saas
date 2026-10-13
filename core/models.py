from django.db import models


class Organizacion(models.Model):
    nombre = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    activa = models.BooleanField(default=True)
    creada_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Organización"
        verbose_name_plural = "Organizaciones"

    def __str__(self):
        return self.nombre