from io import BytesIO
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from core.models import Organizacion
from talento.extraccion_cv import ErrorExtraccionCV, extraer_texto_cv
from talento.models import Candidato, DocumentoCandidato


class ExtraccionNulTests(TestCase):
    def test_pdf_con_nul_se_guarda_sin_alterar_archivo(self):
        with TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            organizacion = Organizacion.objects.create(nombre="Sintetica", slug="nul")
            candidato = Candidato.objects.create(
                organizacion=organizacion, nombre="Perfil sintetico"
            )
            original = b"%PDF-1.4 archivo sintetico inmutable"
            with patch(
                "talento.extraccion_cv.extraer_texto_pdf", return_value="Perfil\x00 sintetico\x00"
            ):
                documento = DocumentoCandidato.objects.create(
                    candidato=candidato,
                    nombre="CV sintetico",
                    tipo=DocumentoCandidato.Tipo.CURRICULUM,
                    archivo=SimpleUploadedFile("cv.pdf", original),
                )
            documento.refresh_from_db()
            self.assertEqual(documento.texto_extraido, "Perfil sintetico")
            self.assertEqual(documento.estado_extraccion, "extraido")
            with documento.archivo.open("rb") as archivo:
                self.assertEqual(archivo.read(), original)

    def test_docx_tambien_elimina_nul(self):
        with patch("talento.extraccion_cv.extraer_texto_docx", return_value="A\x00B"):
            self.assertEqual(extraer_texto_cv(BytesIO(), "cv.docx"), "AB")

    def test_otros_errores_se_conservan(self):
        with patch("talento.extraccion_cv.extraer_texto_pdf", side_effect=ValueError("sintetico")):
            with self.assertRaises(ErrorExtraccionCV) as error:
                extraer_texto_cv(BytesIO(), "cv.pdf")
            self.assertIsInstance(error.exception.__cause__, ValueError)
