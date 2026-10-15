
import uuid
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
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


def ruta_documento_candidato(instance, filename):
    extension = Path(filename).suffix.lower()
    nombre_seguro = f"{uuid.uuid4().hex}{extension}"

    return (
        f"curriculums/"
        f"organizacion_{instance.candidato.organizacion_id}/"
        f"candidato_{instance.candidato_id}/"
        f"{nombre_seguro}"
    )


class DocumentoCandidato(models.Model):

    class Tipo(models.TextChoices):
        CURRICULUM = "curriculum", "Currículum"
        TITULO = "titulo", "Título académico"
        CAPACITACION = "capacitacion", "Capacitación"
        CERTIFICACION = "certificacion", "Certificación"
        RECOMENDACION = "recomendacion", "Carta de recomendación"
        EXPERIENCIA = "experiencia", "Certificado de experiencia"
        EVALUACION = "evaluacion", "Evaluación"
        OTRO = "otro", "Otro documento"

    candidato = models.ForeignKey(
        Candidato,
        on_delete=models.CASCADE,
        related_name="documentos",
    )

    tipo = models.CharField(
        max_length=30,
        choices=Tipo.choices,
        default=Tipo.OTRO,
    )

    nombre = models.CharField(max_length=200)

    archivo = models.FileField(
        upload_to=ruta_documento_candidato,
        validators=[
            FileExtensionValidator(
                allowed_extensions=["pdf", "doc", "docx"]
            )
        ],
    )

    es_cv_principal = models.BooleanField(default=False)
    vigente = models.BooleanField(default=True)

    observaciones = models.TextField(blank=True)

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Documento del candidato"
        verbose_name_plural = "Documentos de candidatos"
        ordering = ["-creado_en"]

    def clean(self):
        super().clean()

        if self.es_cv_principal and self.tipo != self.Tipo.CURRICULUM:
            raise ValidationError({
                "es_cv_principal": (
                    "Solo un currículum puede marcarse como CV principal."
                )
            })

        if self.archivo and hasattr(self.archivo, "size"):
            if self.archivo.size > 10 * 1024 * 1024:
                raise ValidationError({
                    "archivo": "El archivo no puede superar los 10 MB."
                })

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.candidato.nombre} - {self.nombre}"
