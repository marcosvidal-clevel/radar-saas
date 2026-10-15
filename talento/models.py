
from django.core.exceptions import ValidationError
from django.db import models

from core.models import Organizacion


class Candidato(models.Model):

    class Estado(models.TextChoices):
        DISPONIBLE = "disponible", "Disponible"
        EN_PROCESO = "en_proceso", "En proceso"
        CONTRATADO = "contratado", "Contratado"
        NO_DISPONIBLE = "no_disponible", "No disponible"

    class Fuente(models.TextChoices):
        WEB = "web", "Página web"
        LINKEDIN = "linkedin", "LinkedIn"
        EMAIL = "email", "Correo electrónico"
        REFERIDO = "referido", "Referido"
        BUSQUEDA = "busqueda", "Búsqueda directa"
        OTRO = "otro", "Otro"

    organizacion = models.ForeignKey(
        Organizacion,
        on_delete=models.PROTECT,
        related_name="candidatos",
    )

    nombre = models.CharField(max_length=200)
    email = models.EmailField(blank=True)
    telefono = models.CharField(max_length=50, blank=True)
    linkedin = models.URLField(blank=True)

    profesion = models.CharField(max_length=200, blank=True)
    especialidad = models.CharField(max_length=200, blank=True)

    region = models.CharField(max_length=100, blank=True)
    ciudad = models.CharField(max_length=100, blank=True)

    anos_experiencia = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
    )

    pretension_renta = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Pretensión de renta mensual en pesos chilenos.",
    )

    experiencia = models.TextField(blank=True)
    competencias = models.TextField(blank=True)

    fuente = models.CharField(
        max_length=20,
        choices=Fuente.choices,
        default=Fuente.OTRO,
    )

    estado = models.CharField(
        max_length=20,
        choices=Estado.choices,
        default=Estado.DISPONIBLE,
    )

    notas = models.TextField(blank=True)
    activo = models.BooleanField(default=True)

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Candidato"
        verbose_name_plural = "Candidatos"
        ordering = ["nombre"]

    def clean(self):
        super().clean()

        if not self.nombre.strip():
            raise ValidationError({
                "nombre": "El nombre del candidato es obligatorio."
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.nombre
