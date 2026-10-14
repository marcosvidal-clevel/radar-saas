from django.conf import settings
from django.core.exceptions import ValidationError
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


class EmpresaProspectada(models.Model):
    organizacion = models.ForeignKey(
        Organizacion,
        on_delete=models.PROTECT,
        related_name="empresas_prospectadas",
    )
    sector = models.ForeignKey(
        Sector,
        on_delete=models.PROTECT,
        related_name="empresas_prospectadas",
    )
    nombre = models.CharField(max_length=200)
    sitio_web = models.URLField(blank=True)
    linkedin = models.URLField(blank=True)
    pais = models.CharField(max_length=100, default="Chile")
    ciudad = models.CharField(max_length=100, blank=True)
    descripcion = models.TextField(blank=True)
    notas = models.TextField(blank=True)
    activa = models.BooleanField(default=True)
    creada_en = models.DateTimeField(auto_now_add=True)
    actualizada_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Empresa prospectada"
        verbose_name_plural = "Empresas prospectadas"
        ordering = ["nombre"]
        constraints = [
            models.UniqueConstraint(
                fields=["organizacion", "nombre"],
                name="empresa_unica_por_organizacion",
            )
        ]

    def clean(self):
        super().clean()
        if self.sector_id and self.organizacion_id:
            if self.sector.organizacion_id != self.organizacion_id:
                raise ValidationError({
                    "sector": (
                        "El sector debe pertenecer a la misma "
                        "organización que la empresa prospectada."
                    )
                })

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.nombre


class Contacto(models.Model):
    class Tipo(models.TextChoices):
        POR_CONFIRMAR = "por_confirmar", "Por confirmar"
        DECISOR = "decisor", "Decisor"
        INFLUYENTE = "influyente", "Influyente"
        PUERTA_ENTRADA = "puerta_entrada", "Puerta de entrada"
        OTRO = "otro", "Otro"

    empresa = models.ForeignKey(
        EmpresaProspectada,
        on_delete=models.PROTECT,
        related_name="contactos",
    )
    nombre = models.CharField(max_length=200)
    cargo = models.CharField(max_length=200, blank=True)
    email = models.EmailField(blank=True)
    telefono = models.CharField(max_length=50, blank=True)
    linkedin = models.URLField(blank=True)
    tipo = models.CharField(
        max_length=20,
        choices=Tipo.choices,
        default=Tipo.POR_CONFIRMAR,
    )
    fuente = models.CharField(max_length=250, blank=True)
    evidencia_rol = models.TextField(
        blank=True,
        help_text="Evidencia que respalda su papel en la decisión comercial.",
    )
    notas = models.TextField(blank=True)
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Contacto"
        verbose_name_plural = "Contactos"
        ordering = ["nombre"]

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.nombre} - {self.empresa}"

class Senal(models.Model):
    class Tipo(models.TextChoices):
        INVERSION = "inversion", "Inversión"
        ADJUDICACION = "adjudicacion", "Adjudicación"
        EXPANSION = "expansion", "Expansión"
        CAMBIO_EJECUTIVO = "cambio_ejecutivo", "Cambio ejecutivo"
        CONTRATACION = "contratacion", "Contratación"
        OTRO = "otro", "Otro"

    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente de revisión"
        VALIDADA = "validada", "Validada"
        DESCARTADA = "descartada", "Descartada"

    empresa = models.ForeignKey(
        EmpresaProspectada,
        on_delete=models.PROTECT,
        related_name="senales",
    )
    titulo = models.CharField(max_length=250)
    tipo = models.CharField(
        max_length=20,
        choices=Tipo.choices,
        default=Tipo.OTRO,
    )
    fecha_evento = models.DateField(null=True, blank=True)
    fuente = models.CharField(max_length=250)
    enlace = models.URLField(blank=True)
    evidencia = models.TextField(
        help_text="Describe el hecho observado y su respaldo.",
    )
    hipotesis_comercial = models.TextField(
        blank=True,
        help_text="Posible necesidad comercial; separada del hecho observado.",
    )
    estado = models.CharField(
        max_length=20,
        choices=Estado.choices,
        default=Estado.PENDIENTE,
    )
    motivo_descarte = models.TextField(blank=True)
    creada_en = models.DateTimeField(auto_now_add=True)
    actualizada_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Señal"
        verbose_name_plural = "Señales"
        ordering = ["-creada_en"]

    def clean(self):
        super().clean()
        if self.estado == self.Estado.DESCARTADA:
            if not self.motivo_descarte.strip():
                raise ValidationError({
                    "motivo_descarte": "Indica por qué se descarta la señal."
                })

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.titulo
class Oportunidad(models.Model):
    class Origen(models.TextChoices):
        CONSULTA_ENTRANTE = "consulta_entrante", "Consulta entrante (caliente)"
        PROSPECCION = "prospeccion", "Prospección"

    class Canal(models.TextChoices):
        WEB = "web", "Página web"
        LINKEDIN = "linkedin", "LinkedIn"
        WHATSAPP = "whatsapp", "WhatsApp"
        EMAIL = "email", "Correo electrónico"
        TELEFONO = "telefono", "Teléfono"
        REFERIDO = "referido", "Referido"
        OTRA_RED = "otra_red", "Otra red social"
        OTRO = "otro", "Otro"

    class Estado(models.TextChoices):
        NUEVA = "nueva", "Nueva"
        EN_CONTACTO = "en_contacto", "En contacto"
        CALIFICADA = "calificada", "Calificada"
        PROPUESTA = "propuesta", "Propuesta enviada"
        GANADA = "ganada", "Ganada"
        PERDIDA = "perdida", "Perdida"
        DESCARTADA = "descartada", "Descartada"

    organizacion = models.ForeignKey(
        Organizacion,
        on_delete=models.PROTECT,
        related_name="oportunidades",
    )
    empresa = models.ForeignKey(
        EmpresaProspectada,
        on_delete=models.PROTECT,
        related_name="oportunidades",
        null=True,
        blank=True,
    )
    contacto = models.ForeignKey(
        Contacto,
        on_delete=models.PROTECT,
        related_name="oportunidades",
        null=True,
        blank=True,
    )
    senal = models.ForeignKey(
        Senal,
        on_delete=models.PROTECT,
        related_name="oportunidades",
        null=True,
        blank=True,
    )
    responsable = models.ForeignKey(
        Membresia,
        on_delete=models.PROTECT,
        related_name="oportunidades",
        null=True,
        blank=True,
    )
    titulo = models.CharField(max_length=250)
    origen = models.CharField(
        max_length=20,
        choices=Origen.choices,
    )
    canal = models.CharField(
        max_length=20,
        choices=Canal.choices,
    )
    nombre_consultante = models.CharField(max_length=200, blank=True)
    email_consultante = models.EmailField(blank=True)
    telefono_consultante = models.CharField(max_length=50, blank=True)
    necesidad = models.TextField(
        help_text="Describe la consulta recibida o la necesidad detectada.",
    )
    estado = models.CharField(
        max_length=20,
        choices=Estado.choices,
        default=Estado.NUEVA,
    )
    proxima_accion = models.TextField(blank=True)
    fecha_proxima_accion = models.DateField(null=True, blank=True)
    motivo_cierre = models.TextField(blank=True)
    notas = models.TextField(blank=True)
    creada_en = models.DateTimeField(auto_now_add=True)
    actualizada_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Oportunidad"
        verbose_name_plural = "Oportunidades"
        ordering = ["-creada_en"]

    @property
    def es_caliente(self):
        return self.origen == self.Origen.CONSULTA_ENTRANTE

    def clean(self):
        super().clean()
        errores = {}

        if self.empresa_id and self.organizacion_id:
            if self.empresa.organizacion_id != self.organizacion_id:
                errores["empresa"] = (
                    "La empresa debe pertenecer a la misma organización."
                )

        if self.contacto_id:
            if not self.empresa_id:
                errores["contacto"] = (
                    "Selecciona la empresa del contacto."
                )
            elif self.contacto.empresa_id != self.empresa_id:
                errores["contacto"] = (
                    "El contacto debe pertenecer a la empresa seleccionada."
                )

        if self.senal_id:
            if not self.empresa_id:
                errores["senal"] = (
                    "Selecciona la empresa de la señal."
                )
            elif self.senal.empresa_id != self.empresa_id:
                errores["senal"] = (
                    "La señal debe pertenecer a la empresa seleccionada."
                )
            elif self.senal.estado != Senal.Estado.VALIDADA:
                errores["senal"] = (
                    "La señal debe estar validada."
                )

        if self.responsable_id:
            if (
                self.organizacion_id
                and self.responsable.organizacion_id != self.organizacion_id
            ):
                errores["responsable"] = (
                    "El responsable debe pertenecer a la misma organización."
                )
            elif not self.responsable.activa:
                errores["responsable"] = (
                    "El responsable debe tener una membresía activa."
                )

        if self.origen == self.Origen.PROSPECCION and not self.empresa_id:
            errores["empresa"] = (
                "Una oportunidad de prospección debe tener una empresa."
            )

        if self.estado in (
            self.Estado.PERDIDA,
            self.Estado.DESCARTADA,
        ) and not self.motivo_cierre.strip():
            errores["motivo_cierre"] = (
                "Indica por qué se pierde o descarta la oportunidad."
            )

        if errores:
            raise ValidationError(errores)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.titulo