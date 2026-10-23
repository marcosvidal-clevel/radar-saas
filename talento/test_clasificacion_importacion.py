"""Regresiones de clasificación conservadora de documentos."""
from django.test import SimpleTestCase

from talento.clasificacion_importacion import clasificar_adjunto


class ClasificacionImportacionTests(SimpleTestCase):
    def test_descripcion_de_experiencia_no_es_automaticamente_cv(self):
        self.assertEqual(
            clasificar_adjunto("carta_presentacion.pdf", "Experiencia laboral: 10 años"),
            "otro",
        )

    def test_mencion_de_grado_no_es_titulo_acreditado(self):
        self.assertEqual(
            clasificar_adjunto("carta_presentacion.pdf", "Grado académico: magíster"),
            "otro",
        )

    def test_identifica_cv_y_titulo_explicitos(self):
        self.assertEqual(clasificar_adjunto("CV_Ana.pdf"), "curriculum")
        self.assertEqual(clasificar_adjunto("titulo_profesional.pdf"), "titulo")
        self.assertEqual(clasificar_adjunto("adjunto.pdf", "Curriculum Vitae"), "curriculum")
