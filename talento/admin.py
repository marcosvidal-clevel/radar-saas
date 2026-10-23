
import re

from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.utils.html import format_html
from django.urls import reverse

from core.admin_permisos import OrganizacionAdminMixin

from .models import (
    Candidato,
    DocumentoCandidato,
    Vacante,
    Postulacion,
    Entrevista,
    guardar_postulacion_con_historial,
)


@admin.register(Candidato)
class CandidatoAdmin(OrganizacionAdminMixin, admin.ModelAdmin):

    list_display = (
        "nombre",
        "organizacion",
        "rut",
        "email",
        "profesion",
        "especialidad",
        "region",
        "estado",
        "fuente",
        "activo",
        "es_prueba",
        "origen_importacion",
        "revision_antecedentes",
    )

    list_filter = (
        "estado",
        "fuente",
        "activo",
        "region",
        "origen_importacion",
    )

    search_fields = (
        "nombre",
        "rut",
        "email",
        "telefono",
        "profesion",
        "especialidad",
        "competencias",
        "experiencia",
    )

    @admin.display(description="Revisión de antecedentes")
    def revision_antecedentes(self, obj):
        documentos = obj.documentos.filter(vigente=True)
        cv = documentos.filter(tipo=DocumentoCandidato.Tipo.CURRICULUM).exists()
        titulo = documentos.filter(tipo=DocumentoCandidato.Tipo.TITULO).exists()
        faltantes = []
        if not obj.rut:
            faltantes.append("RUT")
        if not cv:
            faltantes.append("CV")
        if not titulo:
            faltantes.append("título")
        return "Completo" if not faltantes else "Por revisar: " + ", ".join(faltantes)

    def get_search_results(self, request, queryset, search_term):
        resultados_normales, use_distinct = (
            super().get_search_results(
                request,
                queryset,
                search_term,
            )
        )

        if not search_term or not search_term.strip():
            return resultados_normales, use_distinct

        # Parte la consulta en términos individuales.
        terminos = [
            termino.strip("\"'")
            for termino in search_term.split()
            if termino.strip("\"'")
        ]

        # El queryset recibido ya respeta los permisos
        # y el aislamiento de organizaciones del administrador.
        resultados_fragmentados = queryset

        for termino in terminos:
            # Permite espacios entre letras.
            # "Proyectos" también puede encontrar "Proye ctos".
            patron = r"\s*".join(
                re.escape(caracter)
                for caracter in termino
            )

            resultados_fragmentados = (
                resultados_fragmentados.filter(
                    documentos__texto_extraido__iregex=patron,
                    documentos__tipo=DocumentoCandidato.Tipo.CURRICULUM,
                    documentos__vigente=True,
                )
            )

        resultados = (
            resultados_normales
            | resultados_fragmentados
        ).distinct()

        return resultados, True

    readonly_fields = (
        "creado_en",
        "actualizado_en",
        "origen_importacion",
        "identificador_origen",
    )

    list_select_related = ("organizacion",)

    fieldsets = (
        (
            "Identificación",
            {
                "fields": (
                    "organizacion",
                    "nombre",
                    "rut",
                    "direccion",
                    "email",
                    "telefono",
                    "linkedin",
                )
            },
        ),
        (
            "Perfil profesional",
            {
                "fields": (
                    "profesion",
                    "especialidad",
                    "region",
                    "ciudad",
                    "anos_experiencia",
                    "pretension_renta",
                    "experiencia",
                    "competencias",
                )
            },
        ),
        (
            "Gestión del candidato",
            {
                "fields": (
                    "fuente",
                    "estado",
                    "notas",
                    "origen_importacion",
                    "identificador_origen",
                    "activo",
                    "es_prueba",
                )
            },
        ),
        (
            "Registro",
            {
                "fields": (
                    "creado_en",
                    "actualizado_en",
                )
            },
        ),
    )


@admin.register(DocumentoCandidato)
class DocumentoCandidatoAdmin(
    OrganizacionAdminMixin,
    admin.ModelAdmin,
):

    organizacion_lookup = "candidato__organizacion_id"

    actions = ("extraer_texto_cvs",)

    @admin.action(
        description="Extraer texto de los CV seleccionados",
        permissions=["change"],
    )
    def extraer_texto_cvs(self, request, queryset):
        if not self.has_change_permission(request):
            raise PermissionDenied

        seleccionados = self.get_queryset(request).filter(
            pk__in=queryset.values("pk")
        ).select_related("candidato__organizacion")
        omitidos = queryset.count() - seleccionados.count()
        procesados = sin_texto = errores = 0
        for documento in seleccionados:
            if (
                documento.tipo != DocumentoCandidato.Tipo.CURRICULUM
                or not self.has_change_permission(request, documento)
            ):
                omitidos += 1
                continue
            estado = documento.extraer_texto()
            procesados += 1
            if estado == DocumentoCandidato.EstadoExtraccion.SIN_TEXTO:
                sin_texto += 1
            elif estado == DocumentoCandidato.EstadoExtraccion.ERROR:
                errores += 1

        self.message_user(
            request,
            f"Procesados: {procesados}. Sin texto: {sin_texto}. "
            f"Con error: {errores}. Omitidos: {omitidos}.",
        )

    list_display = (
        "nombre",
        "candidato",
        "tipo",
        "estado_extraccion",
        "vigente",
        "es_cv_principal",
        "enlace_descarga",
        "creado_en",
    )

    list_filter = (
        "tipo",
        "estado_extraccion",
        "vigente",
        "es_cv_principal",
    )

    search_fields = (
        "nombre",
        "candidato__nombre",
        "candidato__profesion",
    )

    readonly_fields = (
        "creado_en",
        "actualizado_en",
        "enlace_descarga",
        "estado_extraccion",
    )

    list_select_related = (
        "candidato",
        "candidato__organizacion",
    )

    fields = (
        "candidato",
        "tipo",
        "nombre",
        "archivo",
        "enlace_descarga",
        "estado_extraccion",
        "es_cv_principal",
        "vigente",
        "observaciones",
        "creado_en",
        "actualizado_en",
    )

    @admin.display(description="Descargar documento")
    def enlace_descarga(self, obj):
        if not obj or not obj.pk or not obj.archivo:
            return "Sin archivo disponible"

        url = reverse(
            "descargar_documento_candidato",
            args=[obj.pk],
        )

        return format_html(
            '<a href="{}">Descargar archivo</a>',
            url,
        )

    def organizacion_objeto(self, obj):
        return obj.candidato.organizacion_id

    def get_queryset(self, request):
        queryset = super().get_queryset(request)

        if request.user.is_superuser:
            return queryset
        queryset = queryset.exclude(
            tipo=DocumentoCandidato.Tipo.EVALUACION
        )
        puede_clasificar = (
            request.user.has_perm("talento.change_documentocandidato")
            and self.organizaciones_permitidas(request, self.ROLES_GESTION).exists()
        )
        if not puede_clasificar:
            queryset = queryset.filter(pendiente_clasificacion=False)
        return queryset

    def formfield_for_foreignkey(
        self,
        db_field,
        request,
        **kwargs,
    ):
        if db_field.name == "candidato":
            queryset = Candidato.objects.all()

            if not request.user.is_superuser:
                organizaciones = self.organizaciones_permitidas(
                    request,
                    self.ROLES_GESTION,
                )

                queryset = queryset.filter(
                    organizacion_id__in=organizaciones,
                )

            kwargs["queryset"] = queryset

        return super().formfield_for_foreignkey(
            db_field,
            request,
            **kwargs,
        )

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)

        if not request.user.is_superuser:
            campo_tipo = form.base_fields.get("tipo")

            if campo_tipo:
                campo_tipo.choices = [
                    opcion
                    for opcion in campo_tipo.choices
                    if opcion[0] != DocumentoCandidato.Tipo.EVALUACION
                ]

        return form

    def save_model(self, request, obj, form, change):
        if not request.user.is_superuser:
            if obj.tipo == DocumentoCandidato.Tipo.EVALUACION:
                raise PermissionDenied(
                    "No tienes permiso para gestionar "
                    "evaluaciones psicolaborales."
                )

            if obj.tipo != DocumentoCandidato.Tipo.OTRO:
                obj.pendiente_clasificacion = False

            rol = self.rol_en_organizacion(
                request,
                obj.candidato.organizacion_id,
            )

            if rol not in self.ROLES_GESTION:
                raise PermissionDenied(
                    "No tienes permiso para gestionar "
                    "documentos de esta organización."
                )

        super().save_model(request, obj, form, change)


@admin.register(Vacante)
class VacanteAdmin(OrganizacionAdminMixin, admin.ModelAdmin):

    list_display = (
        "titulo",
        "organizacion",
        "empresa",
        "estado",
        "activa",
    )

    list_filter = ("estado", "activa")
    search_fields = ("titulo",)
    list_select_related = ("organizacion", "empresa")


@admin.register(Postulacion)
class PostulacionAdmin(OrganizacionAdminMixin, admin.ModelAdmin):

    organizacion_lookup = "vacante__organizacion_id"

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        campo = super().formfield_for_foreignkey(
            db_field,
            request,
            **kwargs,
        )

        if db_field.name == "documento_cv":
            campo.queryset = DocumentoCandidato.objects.filter(
                tipo=DocumentoCandidato.Tipo.CURRICULUM
            )

        if request.user.is_superuser:
            return campo

        organizaciones = self.organizaciones_permitidas(
            request,
            self.ROLES_GESTION,
        )

        if db_field.name == "vacante":
            campo.queryset = Vacante.objects.filter(
                organizacion_id__in=organizaciones
            )

        elif db_field.name == "candidato":
            campo.queryset = Candidato.objects.filter(
                organizacion_id__in=organizaciones
            )

        elif db_field.name == "documento_cv":
            campo.queryset = DocumentoCandidato.objects.filter(
                candidato__organizacion_id__in=organizaciones,
                tipo=DocumentoCandidato.Tipo.CURRICULUM,
            )

        return campo

    list_display = (
        "candidato",
        "vacante",
        "estado",
        "fuente",
    )

    list_filter = ("estado", "fuente")

    search_fields = (
        "candidato__nombre",
        "vacante__titulo",
    )

    list_select_related = ("candidato", "vacante")

    def save_model(self, request, obj, form, change):
        guardar_postulacion_con_historial(obj, request.user)


@admin.register(Entrevista)
class EntrevistaAdmin(OrganizacionAdminMixin, admin.ModelAdmin):
    organizacion_lookup = "postulacion__vacante__organizacion_id"
    list_display = ("postulacion", "fecha_hora", "entrevistador", "modalidad", "estado", "creado_por")
    list_filter = ("estado", "modalidad")
    search_fields = ("postulacion__candidato__nombre", "entrevistador")
    list_select_related = ("postulacion__candidato", "postulacion__vacante", "creado_por")
