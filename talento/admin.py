from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.utils.html import format_html
from django.urls import reverse

from core.admin_permisos import OrganizacionAdminMixin
from core.models import Membresia

from .models import Candidato, DocumentoCandidato


@admin.register(Candidato)
class CandidatoAdmin(OrganizacionAdminMixin, admin.ModelAdmin):

    list_display = (
        "nombre",
        "organizacion",
        "profesion",
        "especialidad",
        "region",
        "estado",
        "fuente",
        "activo",
    )

    list_filter = (
        "estado",
        "fuente",
        "activo",
        "region",
    )

    search_fields = (
        "nombre",
        "email",
        "telefono",
        "profesion",
        "especialidad",
        "competencias",
        "experiencia",
    )

    readonly_fields = (
        "creado_en",
        "actualizado_en",
    )

    list_select_related = ("organizacion",)

    fieldsets = (
        (
            "Identificación",
            {
                "fields": (
                    "organizacion",
                    "nombre",
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
                    "activo",
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

    list_display = (
        "nombre",
        "candidato",
        "tipo",
        "vigente",
        "es_cv_principal",
        "enlace_descarga",
        "creado_en",
    )

    list_filter = (
        "tipo",
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

        return queryset.exclude(
            tipo=DocumentoCandidato.Tipo.EVALUACION
        )

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
