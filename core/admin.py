from django.contrib import admin
from .models import Organizacion


@admin.register(Organizacion)
class OrganizacionAdmin(admin.ModelAdmin):
    list_display = ("nombre", "slug", "activa")
    search_fields = ("nombre",)
    prepopulated_fields = {"slug": ("nombre",)}