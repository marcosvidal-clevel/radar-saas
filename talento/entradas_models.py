import uuid
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models
from .entradas_storage import AlmacenEntradasPrivado


def ruta_entrada(instance, filename):
    return f"entradas/organizacion_{instance.organizacion_id}/{uuid.uuid4().hex}{Path(filename).suffix.lower()}"


class EntradaPendiente(models.Model):
    class Confirmacion(models.TextChoices):
        NO_CONSTA = "no_consta", "No consta"
        NO_CONFIRMADO = "no_confirmado", "No confirmado"
        CONFIRMADO = "confirmado", "Confirmado"

    class Contacto(models.TextChoices):
        DISPONIBLE = "disponible", "Disponible como contacto personal"
        AUSENTE = "ausente", "Ausente"
        NO_CONFIRMADO = "no_confirmado", "No confirmado como contacto personal"

    class Seguimiento(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        CONTACTAR = "requiere_contactar", "Requiere contactar"
        SIN_MEDIO = "sin_medio_contacto", "Sin medio de contacto"
        RESUELTO = "resuelto", "Resuelto"

    organizacion = models.ForeignKey("core.Organizacion", on_delete=models.PROTECT)
    origen_importacion = models.CharField(max_length=100)
    identificador_origen = models.CharField(max_length=200)
    clave_documental = models.CharField(max_length=200)
    archivo = models.FileField(upload_to=ruta_entrada, storage=AlmacenEntradasPrivado(), validators=[
        FileExtensionValidator(allowed_extensions=["pdf", "doc", "docx"]),
    ])
    nombre_archivo_original = models.CharField(max_length=255, editable=False)
    sha256 = models.CharField(max_length=64, editable=False)
    nombre = models.CharField(max_length=200, blank=True)
    identidad_estado = models.CharField(max_length=20, choices=Confirmacion.choices, default=Confirmacion.NO_CONSTA)
    profesion = models.CharField(max_length=200, blank=True)
    profesion_estado = models.CharField(max_length=20, choices=Confirmacion.choices, default=Confirmacion.NO_CONSTA)
    region = models.CharField(max_length=100, blank=True)
    ciudad = models.CharField(max_length=100, blank=True)
    ubicacion_estado = models.CharField(max_length=20, choices=Confirmacion.choices, default=Confirmacion.NO_CONSTA)
    telefono = models.CharField(max_length=50, blank=True)
    telefono_estado = models.CharField(max_length=20, choices=Contacto.choices, default=Contacto.NO_CONFIRMADO)
    email = models.EmailField(blank=True)
    email_estado = models.CharField(max_length=20, choices=Contacto.choices, default=Contacto.NO_CONFIRMADO)
    correo_remitente = models.EmailField(blank=True, help_text="Procedencia del mensaje; nunca se copia al contacto personal.")
    tipo_documento = models.CharField(max_length=30, choices=[
        ("curriculum", "Currículum"), ("certificacion", "Certificación"),
        ("titulo", "Título"), ("otro", "Otro"),
        ("capacitacion", "Capacitación"), ("recomendacion", "Carta de recomendación"),
        ("experiencia", "Certificado de experiencia"),
    ], default="otro")
    clasificacion_confirmada = models.BooleanField(default=False)
    limitacion_lectura = models.TextField(blank=True)
    informacion_por_completar = models.TextField(blank=True)
    seguimiento = models.CharField(max_length=30, choices=Seguimiento.choices, default=Seguimiento.PENDIENTE)
    candidato = models.ForeignKey("talento.Candidato", null=True, blank=True, editable=False, on_delete=models.PROTECT)
    documento = models.ForeignKey("talento.DocumentoCandidato", null=True, blank=True, editable=False, on_delete=models.PROTECT)
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="entradas_creadas", editable=False)
    actualizado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="entradas_actualizadas", editable=False)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Entrada pendiente de candidato"
        verbose_name_plural = "Entradas pendientes de candidatos"
        constraints = [models.UniqueConstraint(
            fields=["organizacion", "origen_importacion", "identificador_origen", "clave_documental"],
            name="entrada_procedencia_documental_unica",
        )]

    def __str__(self):
        return self.identificador_origen

    def clean(self):
        super().clean()
        errors = {}
        for state, fields in (("identidad_estado", ["nombre"]), ("profesion_estado", ["profesion"]), ("ubicacion_estado", ["region", "ciudad"])):
            values = any(getattr(self, f).strip() for f in fields)
            if getattr(self, state) == self.Confirmacion.CONFIRMADO and not values:
                errors[state] = "Indique el dato que se confirma."
            if getattr(self, state) == self.Confirmacion.NO_CONSTA and values:
                errors[state] = "Use no confirmado o confirmado si conserva un valor."
        for field in ("email", "telefono"):
            state = getattr(self, field + "_estado")
            if state == self.Contacto.DISPONIBLE and not getattr(self, field).strip():
                errors[field] = "Indique el contacto personal disponible."
            if state == self.Contacto.AUSENTE and getattr(self, field):
                errors[field] = "Un contacto ausente no puede contener un valor."
        if self.email and self.email_estado == self.Contacto.DISPONIBLE:
            local, _, domain = self.email.lower().partition("@")
            portals = ("chiletrabajos.cl", "trabajando.com", "laborum.cl", "computrabajo.com", "linkedin.com", "indeed.com")
            if any(domain == p or domain.endswith("." + p) for p in portals) or local.split("+")[0] in {"noreply", "no-reply", "notificaciones", "postulaciones", "info", "contacto", "soporte", "support"}:
                errors["email"] = "El correo genérico de un portal no es contacto personal; consérvelo como remitente o no confirmado."
        if self.seguimiento == self.Seguimiento.SIN_MEDIO and (
            self.email_estado == self.Contacto.DISPONIBLE or self.telefono_estado == self.Contacto.DISPONIBLE
        ):
            errors["seguimiento"] = "Hay un contacto personal disponible; revise el estado de seguimiento."
        if self.archivo and self.archivo.size > 10 * 1024 * 1024:
            errors["archivo"] = "Máximo 10 MB."
        if self.tipo_documento == "evaluacion":
            errors["tipo_documento"] = "Las evaluaciones requieren su flujo restringido."
        if self.seguimiento == self.Seguimiento.RESUELTO:
            if not self.candidato_id or not self.documento_id:
                errors["seguimiento"] = "Resuelva mediante crear o vincular un candidato."
        elif self.candidato_id or self.documento_id:
            errors["seguimiento"] = "Una entrada vinculada debe estar resuelta."
        if self.candidato_id and self.candidato.organizacion_id != self.organizacion_id:
            errors["candidato"] = "Organización incompatible."
        if self.documento_id and self.documento.candidato_id != self.candidato_id:
            errors["documento"] = "Documento incompatible con el candidato."
        if errors:
            raise ValidationError(errors)


class RevisionEntrada(models.Model):
    entrada = models.ForeignKey(EntradaPendiente, on_delete=models.PROTECT, related_name="revisiones")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    fecha = models.DateTimeField(auto_now_add=True)
    fuente = models.TextField()
    accion = models.CharField(max_length=20)
    datos = models.JSONField()

    class Meta:
        ordering = ["fecha", "pk"]
