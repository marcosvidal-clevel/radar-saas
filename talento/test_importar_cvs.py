import hashlib
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from docx import Document
from pypdf import PdfWriter

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core import management
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import CommandError
from django.test import TestCase, override_settings

from core.models import Membresia, Organizacion
from .models import Candidato, DocumentoCandidato


@override_settings(MEDIA_ROOT="/tmp/radar-import-command-tests")
class ImportarCVsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organizacion = Organizacion.objects.create(
            nombre="Organización sintética", slug="org-import-tests"
        )
        cls.otra_organizacion = Organizacion.objects.create(
            nombre="Otra organización sintética", slug="otra-org-import-tests"
        )
        user_model = get_user_model()
        cls.usuario = user_model.objects.create_user(
            username="importador-tests", password="x"
        )
        permisos = Permission.objects.filter(
            content_type__app_label="talento",
            codename__in=("add_candidato", "add_documentocandidato"),
        )
        cls.usuario.user_permissions.add(*permisos)
        Membresia.objects.create(
            organizacion=cls.organizacion,
            usuario=cls.usuario,
            rol=Membresia.Rol.ADMINISTRADOR,
        )

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.pdf = self.root / "cv.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=72, height=72)
        with self.pdf.open("wb") as handle:
            writer.write(handle)
        document = Document()
        document.add_paragraph("Texto sintético de CV")
        document.save(self.root / "cv.docx")

    def tearDown(self):
        self.temp.cleanup()
        media = Path("/tmp/radar-import-command-tests")
        if media.exists():
            for path in sorted(media.rglob("*"), reverse=True):
                if path.is_file() or path.is_symlink():
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()
            media.rmdir()

    def manifest(self, records, organization=None, user=None, name="manifest.json"):
        path = self.root / name
        path.write_text(json.dumps({
            "organizacion": organization or self.organizacion.slug,
            "usuario_ejecutor": user or self.usuario.username,
            "registros": records,
        }), encoding="utf-8")
        return path.name

    def record(self, row, filename="cv.pdf", **extra):
        value = {
            "id_fila": row,
            "identificador_origen": f"id-{row}",
            "origen_importacion": "fuente-tests",
            "nombre": f"Persona sintética {row}",
            "archivo": filename,
        }
        value.update(extra)
        return value

    def run_command(self, manifest, *extra):
        output = __import__("io").StringIO()
        management.call_command(
            "importar_cvs", str(self.root), manifest, *extra, stdout=output
        )
        return output.getvalue()

    def test_preview_no_escribe_y_reporta_archivos_invalidos(self):
        records = [
            self.record("ok"),
            self.record("missing", "missing.pdf"),
            self.record("bad", "not.txt"),
            self.record("incomplete", "cv.pdf", nombre=""),
        ]
        manifest = self.manifest(records)
        (self.root / "not.txt").write_text("no CV", encoding="utf-8")
        output = self.run_command(manifest)
        self.assertIn("PREVISUALIZACION", output)
        self.assertIn("SIN_CAMBIOS", output)
        self.assertEqual(Candidato.objects.count(), 0)
        self.assertEqual(DocumentoCandidato.objects.count(), 0)

    def test_importa_pdf_y_docx_y_guarda_sha256_y_extraccion(self):
        manifest = self.manifest([
            self.record("pdf"),
            self.record("docx", "cv.docx"),
        ])
        output = self.run_command(manifest, "--importar")
        self.assertIn("IMPORTADOS 2 ERRORES 0", output)
        documentos = list(DocumentoCandidato.objects.order_by("pk"))
        self.assertEqual(len(documentos), 2)
        self.assertTrue(all(len(documento.sha256) == 64 for documento in documentos))
        self.assertEqual(documentos[1].estado_extraccion, DocumentoCandidato.EstadoExtraccion.EXTRAIDO)

    def test_reejecucion_y_duplicados_dentro_de_organizacion(self):
        manifest = self.manifest([
            self.record("one"),
            self.record("same", "cv.pdf"),
        ])
        self.run_command(manifest, "--importar")
        output = self.run_command(manifest)
        self.assertIn("duplicado=2", output)
        self.assertEqual(Candidato.objects.count(), 1)

    def test_mismo_sha256_en_otra_organizacion_no_se_bloquea(self):
        self.run_command(self.manifest([self.record("one")]), "--importar")
        other_user = get_user_model().objects.create_user(username="other-importer")
        perms = Permission.objects.filter(
            content_type__app_label="talento",
            codename__in=("add_candidato", "add_documentocandidato"),
        )
        other_user.user_permissions.add(*perms)
        Membresia.objects.create(
            organizacion=self.otra_organizacion,
            usuario=other_user,
            rol=Membresia.Rol.SUPERVISOR,
        )
        output = self.run_command(
            self.manifest(
                [self.record("other")],
                organization=self.otra_organizacion.slug,
                user=other_user.username,
                name="other.json",
            ),
            "--importar",
        )
        self.assertIn("IMPORTADOS 1 ERRORES 0", output)

    def test_permisos_rutas_inseguras_y_symlink(self):
        no_role = get_user_model().objects.create_user(username="sin-rol")
        with self.assertRaises(CommandError):
            self.run_command(
                self.manifest([self.record("no")], user=no_role.username),
            )
        outside = self.root.parent / "outside-cv.pdf"
        outside.write_bytes(b"outside")
        try:
            output = self.run_command(self.manifest([
                self.record("traversal", "../outside-cv.pdf"),
                self.record("absolute", str(outside)),
            ]))
            self.assertIn("ruta_fuera_de_carpeta", output)
            symlink = self.root / "link.pdf"
            try:
                symlink.symlink_to(self.pdf)
            except OSError:
                self.skipTest("El filesystem no permite symlinks")
            output = self.run_command(self.manifest([self.record("link", "link.pdf")]))
            self.assertIn("enlace_simbolico", output)
        finally:
            outside.unlink(missing_ok=True)

    def test_limpia_archivo_si_falla_la_guardada(self):
        manifest = self.manifest([self.record("failure")])
        with patch.object(DocumentoCandidato, "save", side_effect=RuntimeError("synthetic")):
            output = self.run_command(manifest, "--importar")
        self.assertIn("IMPORTADOS 0 ERRORES 1", output)
        self.assertEqual(Candidato.objects.count(), 0)
        media = Path("/tmp/radar-import-command-tests")
        self.assertFalse(media.exists() and any(path.is_file() for path in media.rglob("*")))

    def test_sha256_se_actualiza_en_carga_normal_y_error_de_lectura(self):
        candidato = Candidato.objects.create(
            organizacion=self.organizacion, nombre="Carga sintética"
        )
        documento = DocumentoCandidato.objects.create(
            candidato=candidato,
            tipo=DocumentoCandidato.Tipo.CURRICULUM,
            nombre="CV",
            es_cv_principal=True,
            archivo=SimpleUploadedFile("normal.pdf", b"pdf-bytes"),
        )
        self.assertEqual(documento.sha256, hashlib.sha256(b"pdf-bytes").hexdigest())
        documento.archivo = SimpleUploadedFile("reemplazo.pdf", b"new-bytes")
        documento.save()
        self.assertEqual(documento.sha256, hashlib.sha256(b"new-bytes").hexdigest())
        broken = DocumentoCandidato.objects.create(
            candidato=candidato,
            tipo=DocumentoCandidato.Tipo.CURRICULUM,
            nombre="Roto",
            es_cv_principal=False,
            archivo=SimpleUploadedFile("broken.pdf", b"not-a-pdf"),
        )
        self.assertEqual(broken.estado_extraccion, DocumentoCandidato.EstadoExtraccion.ERROR)
        self.assertNotEqual(broken.estado_extraccion, DocumentoCandidato.EstadoExtraccion.EXTRAIDO)

    def test_avisa_documentos_anteriores_sin_huella(self):
        candidato = Candidato.objects.create(
            organizacion=self.organizacion, nombre="Legado sintético"
        )
        documento = DocumentoCandidato.objects.create(
            candidato=candidato,
            tipo=DocumentoCandidato.Tipo.CURRICULUM,
            nombre="Legado",
            archivo=SimpleUploadedFile("legacy.pdf", b"legacy"),
        )
        DocumentoCandidato.objects.filter(pk=documento.pk).update(sha256="")
        output = self.run_command(self.manifest([self.record("new")]))
        self.assertIn("duplicacion_no_comprobable=1", output)
