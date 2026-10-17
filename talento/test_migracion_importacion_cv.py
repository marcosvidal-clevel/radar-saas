from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class ImportacionCVMigrationTests(TransactionTestCase):
    """Verifica 0012 sin abrir ni reprocesar archivos históricos."""

    migrate_from = ("talento", "0011_entrevista_recomendacion_entrevista_resultado")
    migrate_to = ("talento", "0012_importacion_cv")

    def test_preserva_datos_anteriores_y_aplica_unicidad_por_organizacion(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        self.addCleanup(executor.migrate, latest)
        from_targets = [
            self.migrate_from if app == "talento" else (app, target)
            for app, target in latest
        ]
        to_targets = [
            self.migrate_to if app == "talento" else (app, target)
            for app, target in latest
        ]
        executor.migrate(from_targets)
        old_apps = MigrationExecutor(connection).loader.project_state(
            from_targets
        ).apps
        OldOrganization = old_apps.get_model("core", "Organizacion")
        OldCandidate = old_apps.get_model("talento", "Candidato")
        OldDocument = old_apps.get_model("talento", "DocumentoCandidato")

        organization = OldOrganization.objects.create(
            nombre="Organización histórica sintética",
            slug="organizacion-historica-sintetica",
        )
        other_organization = OldOrganization.objects.create(
            nombre="Otra organización histórica sintética",
            slug="otra-organizacion-historica-sintetica",
        )
        old_candidate = OldCandidate.objects.create(
            organizacion=organization,
            nombre="Candidato histórico sintético",
            email="historico@example.invalid",
        )
        old_document = OldDocument.objects.create(
            candidato=old_candidate,
            tipo="curriculum",
            nombre="CV histórico sintético",
            archivo="curriculums/historico/sintetico.pdf",
            vigente=True,
        )
        old_file_reference = old_document.archivo

        executor = MigrationExecutor(connection)
        executor.migrate(to_targets)
        new_apps = MigrationExecutor(connection).loader.project_state(
            to_targets
        ).apps
        NewCandidate = new_apps.get_model("talento", "Candidato")
        NewDocument = new_apps.get_model("talento", "DocumentoCandidato")

        migrated_candidate = NewCandidate.objects.get(pk=old_candidate.pk)
        migrated_document = NewDocument.objects.get(pk=old_document.pk)
        self.assertEqual(migrated_candidate.nombre, "Candidato histórico sintético")
        self.assertEqual(migrated_candidate.email, "historico@example.invalid")
        self.assertEqual(migrated_document.archivo, old_file_reference)
        self.assertEqual(migrated_document.sha256, "")

        manual_one = NewCandidate.objects.create(
            organizacion_id=organization.pk,
            nombre="Manual uno",
        )
        manual_two = NewCandidate.objects.create(
            organizacion_id=organization.pk,
            nombre="Manual dos",
        )
        self.assertEqual(manual_one.origen_importacion, "")
        self.assertEqual(manual_two.identificador_origen, "")

        NewCandidate.objects.create(
            organizacion_id=organization.pk,
            nombre="Importado uno",
            origen_importacion="fuente-sintetica",
            identificador_origen="id-001",
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                NewCandidate.objects.create(
                    organizacion_id=organization.pk,
                    nombre="Importado repetido",
                    origen_importacion="fuente-sintetica",
                    identificador_origen="id-001",
                )
        NewCandidate.objects.create(
            organizacion_id=other_organization.pk,
            nombre="Importado otra organización",
            origen_importacion="fuente-sintetica",
            identificador_origen="id-001",
    )
