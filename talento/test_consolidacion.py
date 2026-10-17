import json
import hashlib
import inspect
import importlib
import tempfile
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core import management
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from core.models import Membresia, Organizacion

from .models import Candidato, CandidatoProcedencia, DocumentoCandidato, Postulacion, Vacante
from .services import consolidar_candidato


@override_settings(MEDIA_ROOT="/tmp/radar-consolidacion-tests")
class ConsolidacionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = Organizacion.objects.create(nombre="Org consolidación", slug="org-consolidacion")
        cls.other_org = Organizacion.objects.create(nombre="Otra org", slug="otra-org")
        user_model = get_user_model()
        cls.admin = user_model.objects.create_user(username="gestor-consolidacion")
        cls.other_user = user_model.objects.create_user(username="gestor-otra")
        permissions = Permission.objects.filter(
            content_type__app_label="talento",
            codename__in=(
                "change_candidato", "add_candidato", "add_documentocandidato",
                "change_documentocandidato",
            ),
        )
        cls.admin.user_permissions.add(*permissions)
        cls.other_user.user_permissions.add(
            permissions.get(codename="change_candidato")
        )
        Membresia.objects.create(organizacion=cls.org, usuario=cls.admin, rol=Membresia.Rol.ADMINISTRADOR)
        Membresia.objects.create(organizacion=cls.other_org, usuario=cls.other_user, rol=Membresia.Rol.SUPERVISOR)

    def doc(self, candidate, name, principal=True):
        return DocumentoCandidato.objects.create(
            candidato=candidate,
            tipo=DocumentoCandidato.Tipo.CURRICULUM,
            nombre=name,
            es_cv_principal=principal,
            vigente=True,
            archivo=SimpleUploadedFile(name, b"synthetic pdf"),
        )

    def candidates(self):
        canonical = Candidato.objects.create(
            organizacion=self.org, nombre="Persona canónica", profesion="Ingeniería"
        )
        duplicate = Candidato.objects.create(
            organizacion=self.org, nombre="Persona duplicada", experiencia="Experiencia complementaria",
            origen_importacion="fuente", identificador_origen="origen-2",
        )
        CandidatoProcedencia.objects.create(
            candidato=duplicate, organizacion=self.org,
            origen_importacion="fuente", identificador_origen="origen-2", sha256="a" * 64,
        )
        return canonical, duplicate

    def test_migracion_0014_solo_backfill_db_y_usa_procedencias(self):
        migration = importlib.import_module(
            "talento.migrations.0014_candidato_consolidado_en_candidatoprocedencia"
        )
        source = inspect.getsource(migration.crear_procedencias_existentes)
        self.assertNotIn(".open(", source)
        self.assertNotIn("archivo.open", source)
        self.assertIn("origen_importacion", source)
        self.assertIn("identificador_origen", source)

    def test_consolida_preserva_documentos_y_marca_origen(self):
        canonical, duplicate = self.candidates()
        first = self.doc(canonical, "canonical.pdf")
        second = self.doc(duplicate, "duplicate.pdf")
        DocumentoCandidato.objects.filter(pk=first.pk).update(
            sha256="a" * 64, texto_extraido="texto canónico", vigente=True
        )
        DocumentoCandidato.objects.filter(pk=second.pk).update(
            sha256="b" * 64, texto_extraido="texto adicional", vigente=True
        )

        result = consolidar_candidato(canonical, duplicate, self.admin)

        duplicate.refresh_from_db()
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(result.pk, canonical.pk)
        self.assertEqual(duplicate.consolidado_en_id, canonical.pk)
        self.assertEqual(duplicate.experiencia, "Experiencia complementaria")
        self.assertEqual(second.candidato_id, canonical.pk)
        self.assertTrue(first.vigente)
        self.assertTrue(second.vigente)
        self.assertTrue(first.es_cv_principal)
        self.assertFalse(second.es_cv_principal)
        self.assertEqual(second.sha256, "b" * 64)
        self.assertEqual(second.texto_extraido, "texto adicional")
        self.assertEqual(first.sha256, "a" * 64)
        self.assertEqual(first.texto_extraido, "texto canónico")
        with first.archivo.open("rb") as handle:
            self.assertEqual(handle.read(), b"synthetic pdf")
        with second.archivo.open("rb") as handle:
            self.assertEqual(handle.read(), b"synthetic pdf")

    def test_transfiere_documentos_solo_con_permiso_sobre_cada_documento(self):
        canonical, duplicate = self.candidates()
        self.doc(duplicate, "duplicate.pdf")
        limited = get_user_model().objects.create_user(username="gestor-sin-documentos")
        limited.user_permissions.add(Permission.objects.get(
            content_type__app_label="talento", codename="change_candidato"
        ))
        Membresia.objects.create(
            organizacion=self.org, usuario=limited, rol=Membresia.Rol.SUPERVISOR
        )
        with self.assertRaises(PermissionDenied):
            consolidar_candidato(canonical, duplicate, limited)
        duplicate.refresh_from_db()
        self.assertIsNone(duplicate.consolidado_en_id)

    def test_fallo_revierte_toda_la_consolidacion(self):
        canonical, duplicate = self.candidates()
        self.doc(canonical, "canonical.pdf")
        moved = self.doc(duplicate, "duplicate.pdf", principal=True)
        real_save = Candidato.save
        calls = 0

        def fail_on_duplicate(instance, *args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("fallo sintético")
            return real_save(instance, *args, **kwargs)

        with mock.patch.object(Candidato, "save", fail_on_duplicate):
            with self.assertRaises(RuntimeError):
                consolidar_candidato(canonical, duplicate, self.admin)
        canonical.refresh_from_db()
        duplicate.refresh_from_db()
        moved.refresh_from_db()
        self.assertEqual(canonical.profesion, "Ingeniería")
        self.assertIsNone(duplicate.consolidado_en_id)
        self.assertEqual(moved.candidato_id, duplicate.pk)
        self.assertTrue(moved.es_cv_principal)
    def test_rechaza_autorreferencia_ciclo_conflicto_y_otra_organizacion(self):
        canonical, duplicate = self.candidates()
        with self.assertRaises(ValidationError):
            consolidar_candidato(canonical, canonical, self.admin)
        duplicate.consolidado_en = canonical
        duplicate.save(update_fields=("consolidado_en",))
        with self.assertRaises(ValidationError):
            consolidar_candidato(canonical, duplicate, self.admin)
        duplicate.consolidado_en = None
        duplicate.save(update_fields=("consolidado_en",))
        other = Candidato.objects.create(organizacion=self.other_org, nombre="Otra persona")
        with self.assertRaises(ValidationError):
            consolidar_candidato(canonical, other, self.admin)

    def test_rechaza_usuario_sin_gestion_sobre_ambas_fichas(self):
        canonical, duplicate = self.candidates()
        with self.assertRaises(PermissionDenied):
            consolidar_candidato(canonical, duplicate, self.other_user)

    def test_rechaza_conflicto_de_postulaciones(self):
        canonical, duplicate = self.candidates()
        vacancy = Vacante.objects.create(
            organizacion=self.org, titulo="Vacante sintética", descripcion="Descripción"
        )
        Postulacion.objects.create(vacante=vacancy, candidato=canonical)
        Postulacion.objects.create(vacante=vacancy, candidato=duplicate)
        with self.assertRaises(ValidationError):
            consolidar_candidato(canonical, duplicate, self.admin)

    def test_reimportacion_mismo_origen_se_omite_y_archivo_distinto_queda_pendiente(self):
        root = Path(tempfile.mkdtemp())
        try:
            (root / "cv.pdf").write_bytes(b"same file")
            manifest = root / "manifest.json"
            row = {
                "identificador_origen": "stable-1", "origen_importacion": "batch",
                "nombre": "Persona importada", "archivo": "cv.pdf",
            }
            manifest.write_text(json.dumps({
                "organizacion": self.org.slug,
                "usuario_ejecutor": self.admin.username,
                "registros": [row],
            }), encoding="utf-8")
            management.call_command("importar_cvs", str(root), "manifest.json", "--importar")
            output = __import__("io").StringIO()
            management.call_command("importar_cvs", str(root), "manifest.json", stdout=output)
            self.assertIn("duplicado=1", output.getvalue())
            self.assertEqual(Candidato.objects.filter(organizacion=self.org).count(), 1)
            (root / "cv.pdf").write_bytes(b"different file")
            output = __import__("io").StringIO()
            management.call_command("importar_cvs", str(root), "manifest.json", stdout=output)
            self.assertIn("pendiente_revision=1", output.getvalue())
            self.assertEqual(Candidato.objects.filter(identificador_origen="stable-1").count(), 1)
        finally:
            for path in sorted(root.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()
            root.rmdir()

    def test_reimportacion_de_ambas_procedencias_despues_de_consolidar(self):
        canonical, duplicate = self.candidates()
        canonical.origen_importacion = "fuente-a"
        canonical.identificador_origen = "origen-a"
        canonical.save(update_fields=("origen_importacion", "identificador_origen"))
        first = self.doc(canonical, "a.pdf")
        second = self.doc(duplicate, "b.pdf")
        first_hash = hashlib.sha256(b"synthetic pdf").hexdigest()
        second_hash = first_hash
        DocumentoCandidato.objects.filter(pk=first.pk).update(sha256=first_hash)
        DocumentoCandidato.objects.filter(pk=second.pk).update(sha256=second_hash)
        CandidatoProcedencia.objects.filter(
            candidato=duplicate, origen_importacion="fuente", identificador_origen="origen-2"
        ).update(sha256=second_hash)
        CandidatoProcedencia.objects.create(
            candidato=canonical, organizacion=self.org,
            origen_importacion="fuente-a", identificador_origen="origen-a",
            sha256=first_hash,
        )

        root = Path(tempfile.mkdtemp())
        try:
            rows = []
            for filename, source, identifier, content in (
                ("a.pdf", "fuente-a", "origen-a", b"synthetic pdf"),
                ("b.pdf", "fuente", "origen-2", b"synthetic pdf"),
            ):
                (root / filename).write_bytes(content)
                rows.append({
                    "identificador_origen": identifier,
                    "origen_importacion": source,
                    "nombre": "Persona reimportada",
                    "archivo": filename,
                })
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({
                "organizacion": self.org.slug,
                "usuario_ejecutor": self.admin.username,
                "registros": rows,
            }), encoding="utf-8")
            consolidar_candidato(canonical, duplicate, self.admin)
            canonical.refresh_from_db()
            self.assertEqual(
                set(CandidatoProcedencia.objects.filter(organizacion=self.org)
                    .values_list("candidato_id", flat=True)),
                {canonical.pk},
            )
            candidate_count = Candidato.objects.filter(organizacion=self.org).count()
            document_count = DocumentoCandidato.objects.filter(
                candidato=canonical
            ).count()

            output = __import__("io").StringIO()
            management.call_command("importar_cvs", str(root), "manifest.json", stdout=output)
            self.assertIn("duplicado=2", output.getvalue())
            self.assertEqual(Candidato.objects.filter(organizacion=self.org).count(), candidate_count)
            self.assertEqual(DocumentoCandidato.objects.filter(candidato=canonical).count(), document_count)

            for filename, content in (("a.pdf", b"different-a"), ("b.pdf", b"different-b")):
                (root / filename).write_bytes(content)
            output = __import__("io").StringIO()
            management.call_command("importar_cvs", str(root), "manifest.json", stdout=output)
            self.assertIn("pendiente_revision=2", output.getvalue())
            self.assertEqual(Candidato.objects.filter(organizacion=self.org).count(), candidate_count)
            self.assertEqual(DocumentoCandidato.objects.filter(candidato=canonical).count(), document_count)
            duplicate.refresh_from_db()
            self.assertEqual(duplicate.consolidado_en_id, canonical.pk)
            self.assertEqual(DocumentoCandidato.objects.filter(candidato=canonical).count(), 2)
        finally:
            for path in sorted(root.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()
            root.rmdir()
