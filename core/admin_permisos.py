
from django.core.exceptions import PermissionDenied
from django.db.models import Q

from .models import Membresia


class OrganizacionAdminMixin:
    organizacion_lookup = "organizacion_id"

    ROLES_GESTION = (
        Membresia.Rol.ADMINISTRADOR,
        Membresia.Rol.SUPERVISOR,
    )

    def membresias_usuario(self, request):
        return Membresia.objects.filter(
            usuario=request.user,
            activa=True,
            organizacion__activa=True,
        )

    def organizaciones_permitidas(self, request, roles=None):
        membresias = self.membresias_usuario(request)

        if roles is not None:
            membresias = membresias.filter(rol__in=roles)

        return membresias.values_list(
            "organizacion_id",
            flat=True,
        )

    def es_oportunidad(self):
        return self.model._meta.model_name == "oportunidad"

    def organizacion_objeto(self, obj):
        valor = obj

        for parte in self.organizacion_lookup.split("__"):
            valor = getattr(valor, parte)

        return valor

    def rol_en_organizacion(self, request, organizacion_id):
        return self.membresias_usuario(request).filter(
            organizacion_id=organizacion_id,
        ).values_list(
            "rol",
            flat=True,
        ).first()

    def get_queryset(self, request):
        queryset = super().get_queryset(request)

        if request.user.is_superuser:
            return queryset

        queryset = queryset.filter(
            **{
                f"{self.organizacion_lookup}__in":
                    self.organizaciones_permitidas(request)
            }
        )

        if self.es_oportunidad():
            organizaciones_gestion = (
                self.organizaciones_permitidas(
                    request,
                    self.ROLES_GESTION,
                )
            )

            queryset = queryset.filter(
                Q(
                    organizacion_id__in=organizaciones_gestion
                )
                | Q(
                    responsable__usuario=request.user,
                    responsable__activa=True,
                )
            )

        return queryset

    def objeto_permitido(self, request, obj=None):
        if request.user.is_superuser:
            return True

        if obj is None:
            return self.membresias_usuario(request).exists()

        return self.get_queryset(request).filter(
            pk=obj.pk
        ).exists()

    def puede_segun_rol(self, request, accion, obj=None):
        if request.user.is_superuser:
            return True

        if accion == "view":
            return self.objeto_permitido(request, obj)

        roles = (
            (Membresia.Rol.ADMINISTRADOR,)
            if accion == "delete"
            else self.ROLES_GESTION
        )

        if obj is None:
            if self.organizaciones_permitidas(
                request,
                roles,
            ).exists():
                return True

            if accion == "change" and self.es_oportunidad():
                return self.get_queryset(request).filter(
                    responsable__usuario=request.user,
                    responsable__rol=Membresia.Rol.COLABORADOR,
                ).exists()

            return False

        if not self.objeto_permitido(request, obj):
            return False

        rol = self.rol_en_organizacion(
            request,
            self.organizacion_objeto(obj),
        )

        if rol in roles:
            return True

        return (
            accion == "change"
            and self.es_oportunidad()
            and rol == Membresia.Rol.COLABORADOR
            and obj.responsable_id is not None
            and obj.responsable.usuario_id == request.user.pk
            and obj.responsable.activa
        )

    def has_module_permission(self, request):
        return (
            super().has_module_permission(request)
            and self.objeto_permitido(request)
        )

    def has_view_permission(self, request, obj=None):
        return (
            super().has_view_permission(request, obj)
            and self.puede_segun_rol(
                request,
                "view",
                obj,
            )
        )

    def has_add_permission(self, request):
        return (
            super().has_add_permission(request)
            and self.puede_segun_rol(
                request,
                "add",
            )
        )

    def has_change_permission(self, request, obj=None):
        return (
            super().has_change_permission(request, obj)
            and self.puede_segun_rol(
                request,
                "change",
                obj,
            )
        )

    def has_delete_permission(self, request, obj=None):
        return (
            super().has_delete_permission(request, obj)
            and self.puede_segun_rol(
                request,
                "delete",
                obj,
            )
        )

    def get_readonly_fields(self, request, obj=None):
        campos = list(
            super().get_readonly_fields(request, obj)
        )

        if (
            not request.user.is_superuser
            and obj is not None
            and self.es_oportunidad()
            and self.rol_en_organizacion(
                request,
                obj.organizacion_id,
            ) == Membresia.Rol.COLABORADOR
        ):
            campos.extend(
                ("organizacion", "responsable")
            )

        return tuple(dict.fromkeys(campos))

    def formfield_for_foreignkey(
        self,
        db_field,
        request,
        **kwargs,
    ):
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

            ruta = rutas.get(
                modelo._meta.model_name
            )

            if ruta:
                organizaciones = (
                    self.organizaciones_permitidas(request)
                )

                if db_field.name == "organizacion":
                    organizaciones = (
                        self.organizaciones_permitidas(
                            request,
                            self.ROLES_GESTION,
                        )
                    )

                queryset = modelo._default_manager.filter(
                    **{
                        f"{ruta}__in": organizaciones
                    }
                )

                if modelo == Membresia:
                    queryset = queryset.filter(
                        activa=True
                    )

                kwargs["queryset"] = queryset

        return super().formfield_for_foreignkey(
            db_field,
            request,
            **kwargs,
        )

    def get_list_filter(self, request):
        filtros = super().get_list_filter(request)

        if request.user.is_superuser:
            return filtros

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
            organizacion_id = (
                self.organizacion_objeto(obj)
            )

            rol_destino = self.rol_en_organizacion(
                request,
                organizacion_id,
            )

            if change:
                original = self.get_queryset(
                    request
                ).filter(
                    pk=obj.pk
                ).first()

                if (
                    original is None
                    or not self.has_change_permission(
                        request,
                        original,
                    )
                ):
                    raise PermissionDenied(
                        "No puedes modificar este registro."
                    )

                rol_original = self.rol_en_organizacion(
                    request,
                    self.organizacion_objeto(original),
                )

                if rol_original == Membresia.Rol.COLABORADOR:
                    if not self.es_oportunidad():
                        raise PermissionDenied(
                            "No tienes permiso para modificar "
                            "este registro."
                        )

                    if (
                        organizacion_id
                        != self.organizacion_objeto(original)
                        or obj.responsable_id
                        != original.responsable_id
                    ):
                        raise PermissionDenied(
                            "No puedes cambiar la organización "
                            "ni el responsable de esta oportunidad."
                        )

                elif rol_destino not in self.ROLES_GESTION:
                    raise PermissionDenied(
                        "No puedes trasladar el registro "
                        "a esta organización."
                    )

            elif (
                not self.has_add_permission(request)
                or rol_destino not in self.ROLES_GESTION
            ):
                raise PermissionDenied(
                    "No puedes crear registros "
                    "en esta organización."
                )

        super().save_model(
            request,
            obj,
            form,
            change,
        )
