from django.contrib import admin
from .models import (
    Organizacion,
    Membresia,
    Sector,
    EmpresaProspectada,
    Contacto,
    Senal,
)
from django.contrib import admin
from .models import (
    Organizacion,
    Membresia,
    Sector,
    EmpresaProspectada,
    Contacto,
    Senal,
    Oportunidad,
)
@admin.register(Organizacion)
class OrganizacionAdmin(admin.ModelAdmin):
    list_display = ("nombre", "slug", "activa")
    search_fields = ("nombre",)
    prepopulated_fields = {"slug": ("nombre",)}


@admin.register(Membresia)
class MembresiaAdmin(admin.ModelAdmin):
    list_display = ("usuario", "organizacion", "rol", "activa")
    list_filter = ("organizacion", "rol", "activa")
    search_fields = ("usuario__username", "organizacion__nombre")


@admin.register(Sector)
class SectorAdmin(admin.ModelAdmin):
    list_display = ("nombre", "organizacion", "activo")
    list_filter = ("organizacion", "activo")
    search_fields = ("nombre", "organizacion__nombre")


@admin.register(EmpresaProspectada)
class EmpresaProspectadaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "organizacion", "sector", "pais", "activa")
    list_filter = ("organizacion", "sector", "pais", "activa")
    search_fields = ("nombre", "sitio_web", "descripcion")
    readonly_fields = ("creada_en", "actualizada_en")
    list_select_related = ("organizacion", "sector")


@admin.register(Contacto)
class ContactoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "empresa", "cargo", "tipo", "activo")
    list_filter = ("empresa__organizacion", "tipo", "activo")
    search_fields = ("nombre", "cargo", "email", "empresa__nombre")
    readonly_fields = ("creado_en", "actualizado_en")
    list_select_related = ("empresa",)


@admin.register(Senal)
class SenalAdmin(admin.ModelAdmin):
    list_display = ("titulo", "empresa", "tipo", "estado", "fecha_evento")
    list_filter = ("empresa__organizacion", "tipo", "estado")
    search_fields = ("titulo", "empresa__nombre", "fuente", "evidencia")
    readonly_fields = ("creada_en", "actualizada_en")
    list_select_related = ("empresa",)

@admin.register(Oportunidad)
class OportunidadAdmin(admin.ModelAdmin):
    list_display = (
        "titulo",
        "organizacion",
        "empresa",
        "caliente",
        "canal",
        "estado",
        "responsable",
        "fecha_proxima_accion",
    )
    list_filter = (
        "organizacion",
        "origen",
        "canal",
        "estado",
    )
    search_fields = (
        "titulo",
        "empresa__nombre",
        "nombre_consultante",
        "email_consultante",
        "telefono_consultante",
        "necesidad",
    )
    readonly_fields = ("creada_en", "actualizada_en")
    list_select_related = (
        "organizacion",
        "empresa",
        "responsable__usuario",
        "responsable__organizacion",
    )
    autocomplete_fields = (
        "empresa",
        "contacto",
        "senal",
        "responsable",
    )

    @admin.display(boolean=True, description="Caliente")
    def caliente(self, obj):
        return obj.es_caliente