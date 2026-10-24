from django.contrib import admin

from core.admin import SoloSuperusuarioAdmin
from .models import RecepcionComercial


@admin.register(RecepcionComercial)
class RecepcionComercialAdmin(SoloSuperusuarioAdmin):
    list_display = ("id", "organizacion", "sitio", "es_prueba", "recibida_en")
    readonly_fields = [field.name for field in RecepcionComercial._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
