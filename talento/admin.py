
from django.contrib import admin

from core.admin_permisos import OrganizacionAdminMixin
from .models import Candidato


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
