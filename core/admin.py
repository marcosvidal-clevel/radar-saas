from django.contrib import admin
from .models import Organizacion, Membresia


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