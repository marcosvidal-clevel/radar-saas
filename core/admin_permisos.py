from django.core.exceptions import PermissionDenied

from .models import Membresia


class OrganizacionAdminMixin:
    # Cada administrador indicará cómo llegar a la organización.
    organizacion_lookup = "organizacion_id"

    def organizaciones_permitidas(self, request):
        return Membresia.objects.filter(
            usuario=request.user,
            activa=True,
            organizacion__activa=True,
        ).values_list("organizacion_id", flat=True)

    def get_queryset(self, request):
        queryset = super().get_queryset(request)

        if request.user.is_superuser:
            return queryset

        return queryset.filter(
            **{
                f"{self.organizacion_lookup}__in":
                    self.organizaciones_permitidas(request)
            }
        )

    def objeto_permitido(self, request, obj=None):
        if request.user.is_superuser:
            return True

        organizaciones = self.organizaciones_permitidas(request)

        if obj is None:
            return organizaciones.exists()

        return self.get_queryset(request).filter(pk=obj.pk).exists()

    def has_module_permission(self, request):
        return (
            super().has_module_permission(request)
            and self.objeto_permitido(request)
        )

    def has_view_permission(self, request, obj=None):
        return (
            super().has_view_permission(request, obj)
            and self.objeto_permitido(request, obj)
        )

    def has_add_permission(self, request):
        return (
            super().has_add_permission(request)
            and self.objeto_permitido(request)
        )

    def has_change_permission(self, request, obj=None):
        return (
            super().has_change_permission(request, obj)
            and self.objeto_permitido(request, obj)
        )

    def has_delete_permission(self, request, obj=None):
        return (
            super().has_delete_permission(request, obj)
            and self.objeto_permitido(request, obj)
        )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if not request.user.is_superuser:
            modelo = db_field.remote_field.model
            rutas = {
                "organizacion": "pk",
                "sector": "organizacion_id",
                "empresaprospectada": "organizacion_id",
                "contacto": "empresa__organizacion_id",
                "senal": "empresa__organizacion_id",
                "membresia": "organizacion_id",
            }
            ruta = rutas.get(modelo._meta.model_name)

            if ruta:
                queryset = modelo._default_manager.filter(
                    **{
                        f"{ruta}__in":
                            self.organizaciones_permitidas(request)
                    }
                )

                if modelo == Membresia:
                    queryset = queryset.filter(activa=True)

                kwargs["queryset"] = queryset

        return super().formfield_for_foreignkey(
            db_field, request, **kwargs
        )

    def get_list_filter(self, request):
        filtros = super().get_list_filter(request)

        if request.user.is_superuser:
            return filtros

        # Estos filtros podrían mostrar nombres de otras organizaciones.
        filtros_compartidos = {
            "organizacion",
            "empresa__organizacion",
            "sector",
        }

        return [
            filtro
            for filtro in filtros
            if filtro not in filtros_compartidos
        ]

    def save_model(self, request, obj, form, change):
        if not request.user.is_superuser:
            valor = obj

            for parte in self.organizacion_lookup.split("__"):
                valor = getattr(valor, parte)

            if valor not in self.organizaciones_permitidas(request):
                raise PermissionDenied(
                    "No puedes guardar datos de esta organización."
                )

        super().save_model(request, obj, form, change)