
import hashlib
import uuid
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models, transaction

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
    es_prueba = models.BooleanField(
        default=False,
        help_text="Marca explícita para separar datos sintéticos de prueba.",
    )
    consolidado_en = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="fichas_consolidadas",
        help_text="Ficha canónica que conserva este registro consolidado.",
    )

    origen_importacion = models.CharField(
        max_length=100,
        blank=True,
        help_text="Fuente externa de la importación, si corresponde.",
    )
    identificador_origen = models.CharField(
        max_length=200,
        blank=True,
        help_text="Identificador estable entregado por la fuente.",
    )

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Candidato"
        verbose_name_plural = "Candidatos"
        ordering = ["nombre"]
        constraints = [
            models.UniqueConstraint(
                fields=("organizacion", "origen_importacion", "identificador_origen"),
                condition=models.Q(
                    origen_importacion__gt="",
                    identificador_origen__gt="",
                ),
                name="candidato_origen_unico_por_organizacion",
            ),
        ]

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


class CandidatoProcedencia(models.Model):
    candidato = models.ForeignKey(
        Candidato,
        on_delete=models.PROTECT,
        related_name="procedencias",
    )
    organizacion = models.ForeignKey(Organizacion, on_delete=models.PROTECT)
    origen_importacion = models.CharField(max_length=100)
    identificador_origen = models.CharField(max_length=200)
    sha256 = models.CharField(max_length=64, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("organizacion", "origen_importacion", "identificador_origen"),
                name="procedencia_unica_por_organizacion_origen_id",
            ),
        ]


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

    class EstadoExtraccion(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        EXTRAIDO = "extraido", "Texto extraído"
        SIN_TEXTO = "sin_texto", "Sin texto"
        ERROR = "error", "Error de lectura"
        NO_APLICA = "no_aplica", "No aplica"

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

    texto_extraido = models.TextField(
        blank=True,
        editable=False,
    )

    estado_extraccion = models.CharField(
        "Estado de extracción de texto",
        max_length=20,
        choices=EstadoExtraccion.choices,
        default=EstadoExtraccion.PENDIENTE,
        editable=False,
    )

    sha256 = models.CharField(
        max_length=64,
        blank=True,
        editable=False,
        db_index=True,
    )

    origen_importacion = models.CharField(max_length=100, blank=True)
    identificador_origen = models.CharField(max_length=200, blank=True)

    pendiente_clasificacion = models.BooleanField(default=False, db_index=True)

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Documento del candidato"
        verbose_name_plural = "Documentos de candidatos"
        ordering = ["-creado_en"]
        constraints = [
            models.UniqueConstraint(
                fields=("candidato", "origen_importacion", "identificador_origen"),
                condition=models.Q(origen_importacion__gt="", identificador_origen__gt=""),
                name="documento_origen_unico_por_candidato",
            ),
        ]

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

        anterior = None

        if self.pk:
            anterior = type(self).objects.filter(
                pk=self.pk
            ).values("archivo", "tipo").first()

        archivo_cambio = (
            anterior is None
            or anterior["archivo"] != self.archivo.name
            or not self.archivo._committed
        )

        tipo_cambio = (
            anterior is not None
            and anterior["tipo"] != self.tipo
        )

        update_fields = kwargs.get("update_fields")

        if update_fields is not None:
            campos = set(update_fields)
            archivo_cambio = (
                archivo_cambio and "archivo" in campos
            )
            tipo_cambio = (
                tipo_cambio and "tipo" in campos
            )

        if archivo_cambio or tipo_cambio:
            # Persistir el estado inicial sin texto anterior antes de leer el archivo.
            self.texto_extraido = ""
            self.estado_extraccion = self.EstadoExtraccion.PENDIENTE
            if update_fields is not None:
                kwargs["update_fields"] = set(update_fields) | {
                    "texto_extraido", "estado_extraccion",
                }

        resultado = super().save(*args, **kwargs)

        if archivo_cambio or tipo_cambio:
            self._actualizar_sha256()
            self.extraer_texto()

        return resultado

    def _actualizar_sha256(self):
        """Calcula la huella del archivo ya persistido, sin leerlo en logs."""
        digest = ""
        if self.archivo:
            try:
                hasher = hashlib.sha256()
                with self.archivo.open("rb") as archivo:
                    for chunk in iter(lambda: archivo.read(1024 * 1024), b""):
                        hasher.update(chunk)
                digest = hasher.hexdigest()
            except OSError:
                digest = ""
        self.sha256 = digest
        type(self).objects.filter(pk=self.pk).update(sha256=digest)

    def extraer_texto(self):
        """Actualiza únicamente el texto y su estado, sin guardar el archivo."""
        from .extraccion_cv import extraer_texto_cv, ErrorExtraccionCV

        self.texto_extraido = ""
        self.estado_extraccion = self.EstadoExtraccion.PENDIENTE
        type(self).objects.filter(pk=self.pk).update(
            texto_extraido="", estado_extraccion=self.estado_extraccion
        )
        texto = ""
        estado = self.EstadoExtraccion.NO_APLICA
        if self.tipo == self.Tipo.CURRICULUM and self.archivo:
            try:
                with self.archivo.open("rb") as archivo:
                    texto = extraer_texto_cv(
                        archivo, self.archivo.name
                    )
                estado = (
                    self.EstadoExtraccion.EXTRAIDO
                    if texto.strip()
                    else self.EstadoExtraccion.SIN_TEXTO
                )
            except (ErrorExtraccionCV, OSError):
                texto = ""
                estado = self.EstadoExtraccion.ERROR

        self.texto_extraido = texto
        self.estado_extraccion = estado
        type(self).objects.filter(pk=self.pk).update(
            texto_extraido=texto, estado_extraccion=estado
        )
        return estado

    def __str__(self):
        return f"{self.candidato.nombre} - {self.nombre}"


class DocumentoProcedencia(models.Model):
    documento = models.ForeignKey(
        DocumentoCandidato,
        on_delete=models.CASCADE,
        related_name="procedencias",
    )
    procedencia = models.ForeignKey(
        CandidatoProcedencia,
        on_delete=models.PROTECT,
        related_name="documentos",
    )
    identificador_origen = models.CharField(max_length=200)

    def clean(self):
        if self.documento_id and self.procedencia_id:
            documento = self.documento
            procedencia = self.procedencia
            if documento.candidato_id != procedencia.candidato_id:
                raise ValidationError(
                    "El documento y la procedencia deben pertenecer al mismo candidato."
                )
            if documento.candidato.organizacion_id != procedencia.organizacion_id:
                raise ValidationError(
                    "El documento y la procedencia deben pertenecer a la misma organización."
                )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("procedencia", "identificador_origen"),
                name="procedencia_identificador_documento_unico",
            ),
        ]


class Vacante(models.Model):

    class Estado(models.TextChoices):
        BORRADOR = "borrador", "Borrador"
        ABIERTA = "abierta", "Abierta"
        PAUSADA = "pausada", "Pausada"
        CERRADA = "cerrada", "Cerrada"
        CANCELADA = "cancelada", "Cancelada"

    organizacion = models.ForeignKey(
        "core.Organizacion",
        on_delete=models.PROTECT,
        related_name="vacantes",
    )

    empresa = models.ForeignKey(
        "core.EmpresaProspectada",
        on_delete=models.PROTECT,
        related_name="vacantes",
        null=True,
        blank=True,
    )

    oportunidad = models.ForeignKey(
        "core.Oportunidad",
        on_delete=models.PROTECT,
        related_name="vacantes",
        null=True,
        blank=True,
    )

    titulo = models.CharField(max_length=250)
    descripcion = models.TextField(blank=True)
    requisitos = models.TextField(blank=True)

    region = models.CharField(max_length=100, blank=True)
    ciudad = models.CharField(max_length=100, blank=True)

    estado = models.CharField(
        max_length=20,
        choices=Estado.choices,
        default=Estado.BORRADOR,
    )

    publicar_web = models.BooleanField(default=False)
    activa = models.BooleanField(default=True)

    creada_en = models.DateTimeField(auto_now_add=True)
    actualizada_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Vacante"
        verbose_name_plural = "Vacantes"
        ordering = ["-creada_en"]

    def clean(self):
        super().clean()
        errores = {}

        if self.empresa_id and self.organizacion_id:
            if self.empresa.organizacion_id != self.organizacion_id:
                errores["empresa"] = (
                    "La empresa debe pertenecer a la misma organización."
                )

        if self.oportunidad_id and self.organizacion_id:
            if self.oportunidad.organizacion_id != self.organizacion_id:
                errores["oportunidad"] = (
                    "La oportunidad debe pertenecer a la misma organización."
                )

        if self.empresa_id and self.oportunidad_id:
            if (
                self.oportunidad.empresa_id
                and self.oportunidad.empresa_id != self.empresa_id
            ):
                errores["oportunidad"] = (
                    "La oportunidad debe corresponder a la empresa indicada."
                )

        if errores:
            raise ValidationError(errores)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.titulo


class Postulacion(models.Model):

    class Estado(models.TextChoices):
        RECIBIDA = "recibida", "Recibida"
        PRESELECCIONADA = "preseleccionada", "Preseleccionada"
        ENTREVISTA = "entrevista", "Entrevista"
        EVALUACION = "evaluacion", "Evaluación"
        FINALISTA = "finalista", "Finalista"
        SELECCIONADA = "seleccionada", "Seleccionada"
        DESCARTADA = "descartada", "Descartada"
        RETIRADA = "retirada", "Retirada"

    class Fuente(models.TextChoices):
        WEB = "web", "Página web"
        LINKEDIN = "linkedin", "LinkedIn"
        EMAIL = "email", "Correo electrónico"
        WHATSAPP = "whatsapp", "WhatsApp"
        REFERIDO = "referido", "Referido"
        BUSQUEDA = "busqueda", "Búsqueda directa"
        MANUAL = "manual", "Ingreso manual"
        OTRO = "otro", "Otro"

    vacante = models.ForeignKey(
        "talento.Vacante",
        on_delete=models.PROTECT,
        related_name="postulaciones",
    )

    candidato = models.ForeignKey(
        "talento.Candidato",
        on_delete=models.PROTECT,
        related_name="postulaciones",
    )

    documento_cv = models.ForeignKey(
        "talento.DocumentoCandidato",
        on_delete=models.PROTECT,
        related_name="postulaciones",
        null=True,
        blank=True,
    )

    estado = models.CharField(
        max_length=20,
        choices=Estado.choices,
        default=Estado.RECIBIDA,
    )

    fuente = models.CharField(
        max_length=20,
        choices=Fuente.choices,
        default=Fuente.MANUAL,
    )

    observaciones = models.TextField(blank=True)

    creada_en = models.DateTimeField(auto_now_add=True)
    actualizada_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Postulación"
        verbose_name_plural = "Postulaciones"
        ordering = ["-creada_en"]
        constraints = [
            models.UniqueConstraint(
                fields=("vacante", "candidato"),
                name="postulacion_unica_por_vacante_candidato",
            ),
        ]

    def clean(self):
        super().clean()
        errores = {}

        if self.vacante_id and self.candidato_id:
            if (
                self.vacante.organizacion_id
                != self.candidato.organizacion_id
            ):
                errores["candidato"] = (
                    "El candidato y la vacante deben pertenecer "
                    "a la misma organización."
                )

        if self.documento_cv_id and self.candidato_id:
            if self.documento_cv.candidato_id != self.candidato_id:
                errores["documento_cv"] = (
                    "El documento debe pertenecer al candidato."
                )

            elif (
                self.documento_cv.tipo
                != DocumentoCandidato.Tipo.CURRICULUM
            ):
                errores["documento_cv"] = (
                    "El documento seleccionado debe ser un currículum."
                )

        if errores:
            raise ValidationError(errores)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.candidato.nombre} - {self.vacante.titulo}"


class HistorialEstadoPostulacion(models.Model):
    postulacion = models.ForeignKey(
        Postulacion,
        on_delete=models.CASCADE,
        related_name="historial_estados",
    )
    estado_anterior = models.CharField(max_length=20, choices=Postulacion.Estado.choices)
    estado_nuevo = models.CharField(max_length=20, choices=Postulacion.Estado.choices)
    usuario = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cambios_estado_postulacion",
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creado_en", "-pk"]


def guardar_postulacion_con_historial(postulacion, usuario=None):
    """Guarda una postulación y registra cambios de estado atómicamente."""
    anterior = None
    if postulacion.pk:
        anterior = type(postulacion).objects.only("estado").get(pk=postulacion.pk).estado
    with transaction.atomic():
        postulacion.save()
        if anterior is not None and anterior != postulacion.estado:
            HistorialEstadoPostulacion.objects.create(
                postulacion=postulacion,
                estado_anterior=anterior,
                estado_nuevo=postulacion.estado,
                usuario=usuario if getattr(usuario, "is_authenticated", False) else None,
            )
    return postulacion


class Entrevista(models.Model):
    class Modalidad(models.TextChoices):
        PRESENCIAL = "presencial", "Presencial"
        VIDEOLLAMADA = "videollamada", "Videollamada"
        TELEFONO = "telefono", "Teléfono"

    class Estado(models.TextChoices):
        PROGRAMADA = "programada", "Programada"
        REALIZADA = "realizada", "Realizada"
        CANCELADA = "cancelada", "Cancelada"

    class Recomendacion(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        CONTINUAR = "continuar", "Continuar"
        NO_CONTINUAR = "no_continuar", "No continuar"
        RESERVA = "reserva", "Mantener en reserva"

    postulacion = models.ForeignKey(Postulacion, on_delete=models.CASCADE, related_name="entrevistas")
    fecha_hora = models.DateTimeField()
    motivo = models.CharField(max_length=200, blank=True, null=True)
    entrevistador = models.CharField(max_length=200)
    modalidad = models.CharField(max_length=20, choices=Modalidad.choices)
    lugar_enlace = models.CharField(max_length=500, blank=True)
    observaciones = models.TextField(blank=True)
    estado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.PROGRAMADA)
    resultado = models.TextField(blank=True, null=True)
    recomendacion = models.CharField(max_length=20, choices=Recomendacion.choices, blank=True, null=True)
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="entrevistas_creadas")
    creada_en = models.DateTimeField(auto_now_add=True)
    actualizada_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["fecha_hora", "pk"]

    def clean(self):
        super().clean()
        if self.postulacion_id and self.postulacion.vacante.organizacion_id != self.postulacion.candidato.organizacion_id:
            raise ValidationError("La postulación debe pertenecer a una organización válida.")
