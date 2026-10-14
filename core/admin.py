from django.contrib import admin

from .admin_permisos import OrganizacionAdminMixin
from .models import (
    Organizacion,
    Membresia,
    Sector,
    EmpresaProspectada,
    Contacto,
    Senal,
    Oportunidad,
)


class SoloSuperusuarioAdmin(admin.ModelAdmin):
    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(Organizacion)
class OrganizacionAdmin(SoloSuperusuarioAdmin):
    list_display = ("nombre", "slug", "activa")
    search_fields = ("nombre",)
    prepopulated_fields = {"slug": ("nombre",)}

    def get_queryset(self, request):
        queryset = super().get_queryset(request)

        if request.user.is_superuser:
            return queryset

        organizaciones = Membresia.objects.filter(
            usuario=request.user,
            activa=True,
            organizacion__activa=True,
        ).values_list("organizacion_id", flat=True)

        return queryset.filter(pk__in=organizaciones)


@admin.register(Membresia)
class MembresiaAdmin(OrganizacionAdminMixin, SoloSuperusuarioAdmin):
    list_display = ("usuario", "organizacion", "rol", "activa")
    list_filter = ("organizacion", "rol", "activa")
    search_fields = ("usuario__username", "organizacion__nombre")

    # Permite buscar responsables de la propia organización.
    # No permite editar ni crear membresías.
    def has_view_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True

        return (
            request.user.has_perm("core.view_membresia")
            and self.objeto_permitido(request, obj)
        )

    def get_queryset(self, request):
        queryset = super().get_queryset(request)

        if request.user.is_superuser:
            return queryset

        return queryset.filter(activa=True)


@admin.register(Sector)
class SectorAdmin(OrganizacionAdminMixin, admin.ModelAdmin):
    list_display = ("nombre", "organizacion", "activo")
    list_filter = ("organizacion", "activo")
    search_fields = ("nombre", "organizacion__nombre")


@admin.register(EmpresaProspectada)
class EmpresaProspectadaAdmin(OrganizacionAdminMixin, admin.ModelAdmin):
    list_display = ("nombre", "organizacion", "sector", "pais", "activa")
    list_filter = ("organizacion", "sector", "pais", "activa")
    search_fields = ("nombre", "sitio_web", "descripcion")
    readonly_fields = ("creada_en", "actualizada_en")
    list_select_related = ("organizacion", "sector")


@admin.register(Contacto)
class ContactoAdmin(OrganizacionAdminMixin, admin.ModelAdmin):
    organizacion_lookup = "empresa__organizacion_id"

    list_display = ("nombre", "empresa", "cargo", "tipo", "activo")
    list_filter = ("empresa__organizacion", "tipo", "activo")
    search_fields = ("nombre", "cargo", "email", "empresa__nombre")
    readonly_fields = ("creado_en", "actualizado_en")
    list_select_related = ("empresa",)


@admin.register(Senal)
class SenalAdmin(OrganizacionAdminMixin, admin.ModelAdmin):
    organizacion_lookup = "empresa__organizacion_id"

    list_display = ("titulo", "empresa", "tipo", "estado", "fecha_evento")
    list_filter = ("empresa__organizacion", "tipo", "estado")
    search_fields = ("titulo", "empresa__nombre", "fuente", "evidencia")
    readonly_fields = ("creada_en", "actualizada_en")
    list_select_related = ("empresa",)


@admin.register(Oportunidad)
class OportunidadAdmin(OrganizacionAdminMixin, admin.ModelAdmin):
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