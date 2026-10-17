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

    def test_0016_a_0017_backfill_preserva_documentos_procedencias_y_clasificacion(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        self.addCleanup(executor.migrate, latest)
        from_targets = [("talento", "0016_documentocandidato_pendiente_clasificacion") if app == "talento" else (app, target) for app, target in latest]
        executor.migrate(from_targets)
        old_apps = MigrationExecutor(connection).loader.project_state(from_targets).apps
        OldOrganization = old_apps.get_model("core", "Organizacion")
        OldCandidate = old_apps.get_model("talento", "Candidato")
        OldDocument = old_apps.get_model("talento", "DocumentoCandidato")
        OldOrigin = old_apps.get_model("talento", "CandidatoProcedencia")
        organization = OldOrganization.objects.create(
            nombre="Organización 0014 sintética", slug="org-0014-sintetica"
        )
        candidate = OldCandidate.objects.create(
            organizacion=organization,
            nombre="Candidato 0014",
            origen_importacion="fuente-antigua",
            identificador_origen="persona-0014",
        )
        document = OldDocument.objects.create(
            candidato=candidate,
            tipo="curriculum",
            nombre="Documento histórico",
            archivo="curriculums/historico/0014.pdf",
            sha256="a" * 64,
            origen_importacion="fuente-antigua",
            identificador_origen="documento-0014",
        )
        OldOrigin.objects.create(
            candidato=candidate,
            organizacion=organization,
            origen_importacion="fuente-antigua",
            identificador_origen="persona-0014",
            sha256="a" * 64,
        )
        executor = MigrationExecutor(connection)
        to_targets = latest
        executor.migrate(to_targets)
        new_apps = MigrationExecutor(connection).loader.project_state(to_targets).apps
        NewDocument = new_apps.get_model("talento", "DocumentoCandidato")
        NewOrigin = new_apps.get_model("talento", "CandidatoProcedencia")
        NewLink = new_apps.get_model("talento", "DocumentoProcedencia")
        migrated = NewDocument.objects.get(pk=document.pk)
        self.assertEqual(migrated.archivo, "curriculums/historico/0014.pdf")
        self.assertEqual(migrated.sha256, "a" * 64)
        self.assertEqual(migrated.origen_importacion, "fuente-antigua")
        self.assertEqual(migrated.identificador_origen, "documento-0014")
        self.assertFalse(migrated.pendiente_clasificacion)
        NewDocument.objects.filter(pk=document.pk).update(pendiente_clasificacion=True)
        self.assertTrue(NewDocument.objects.get(pk=document.pk).pendiente_clasificacion)
        self.assertTrue(NewOrigin.objects.filter(
            candidato_id=candidate.pk,
            origen_importacion="fuente-antigua",
            identificador_origen="persona-0014",
        ).exists())
        self.assertTrue(NewLink.objects.filter(
            documento_id=document.pk,
            procedencia__candidato_id=candidate.pk,
            procedencia__origen_importacion="fuente-antigua",
            procedencia__identificador_origen="persona-0014",
            identificador_origen="documento-0014",
        ).exists())
