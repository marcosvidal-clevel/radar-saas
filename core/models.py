from django.conf import settings
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


class Membresia(models.Model):
    class Rol(models.TextChoices):
        ADMINISTRADOR = "admin", "Administrador"
        SUPERVISOR = "supervisor", "Supervisor"
        COLABORADOR = "colaborador", "Colaborador"

    organizacion = models.ForeignKey(
        Organizacion,
        on_delete=models.CASCADE,
        related_name="membresias",
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="membresias",
    )
    rol = models.CharField(
        max_length=20,
        choices=Rol.choices,
        default=Rol.COLABORADOR,
    )
    activa = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Membresía"
        verbose_name_plural = "Membresías"
        constraints = [
            models.UniqueConstraint(
                fields=["organizacion", "usuario"],
                name="membresia_unica_por_organizacion",
            )
        ]

    def __str__(self):
        return f"{self.usuario} - {self.organizacion}"


class Sector(models.Model):
    organizacion = models.ForeignKey(
        Organizacion,
        on_delete=models.CASCADE,
        related_name="sectores",
    )
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Sector"
        verbose_name_plural = "Sectores"
        ordering = ["nombre"]
        constraints = [
            models.UniqueConstraint(
                fields=["organizacion", "nombre"],
                name="sector_unico_por_organizacion",
            )
        ]

    def __str__(self):
        return f"{self.nombre} - {self.organizacion}"