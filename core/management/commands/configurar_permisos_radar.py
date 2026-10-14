from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


class Command(BaseCommand):
    help = (
        "Configura el grupo de acceso comercial de RADAR. "
        "No modifica usuarios ni membresías."
    )

    @transaction.atomic
    def handle(self, *args, **options):
        modelos_comerciales = (
            "sector",
            "empresaprospectada",
            "contacto",
            "senal",
            "oportunidad",
        )
        acciones = ("view", "add", "change", "delete")

        codigos = {
            f"{accion}_{modelo}"
            for modelo in modelos_comerciales
            for accion in acciones
        }
        codigos.add("view_membresia")

        permisos = Permission.objects.filter(
            content_type__app_label="core",
            codename__in=codigos,
        )

        encontrados = set(
            permisos.values_list("codename", flat=True)
        )
        faltantes = codigos - encontrados

        if faltantes:
            raise CommandError(
                "Faltan permisos. Comprueba las migraciones: "
                + ", ".join(sorted(faltantes))
            )

        grupo, creado = Group.objects.get_or_create(
            name="RADAR — Acceso comercial"
        )
        grupo.permissions.set(permisos)

        estado = "creado" if creado else "actualizado"

        self.stdout.write(
            self.style.SUCCESS(
                f"Grupo {estado}: {grupo.name}"
            )
        )
        self.stdout.write(
            f"Permisos configurados: {permisos.count()}"
        )
        self.stdout.write(
            "No se modificaron usuarios ni membresías."
        )
        self.stdout.write(
            "Los roles y el aislamiento por organización "
            "siguen controlados por el administrador de RADAR."
        )