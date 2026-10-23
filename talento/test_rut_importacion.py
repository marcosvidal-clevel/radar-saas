"""Pruebas de extracción y validación del RUT chileno."""
from django.test import SimpleTestCase

from talento.rut_importacion import normalizar_rut
from talento.preparacion_importacion import preparar_importacion


class RutImportacionTests(SimpleTestCase):
    def test_rut_valido_con_y_sin_puntos(self):
        self.assertEqual(normalizar_rut("12.345.678-5"), "12345678-5")
        self.assertEqual(normalizar_rut("12345678-5"), "12345678-5")

    def test_rut_incorrecto_se_ignora(self):
        self.assertEqual(normalizar_rut("12.345.678-9"), "")

    def test_texto_y_adjunto_se_combinan(self):
        resultado = preparar_importacion(
            texto="Nombre: Persona Ejemplo",
            adjuntos=[{"nombre": "CV.pdf", "texto": "RUT: 12.345.678-5"}],
        )
        self.assertEqual(resultado["datos"]["rut"], "12345678-5")
        self.assertEqual(resultado["documentos"][0]["tipo"], "curriculum")

    def test_rut_ausente_no_impide_preparacion(self):
        resultado = preparar_importacion(texto="Nombre: Persona Ejemplo")
        self.assertEqual(resultado["datos"]["rut"], "")
        self.assertTrue(any("RUT" in nota for nota in resultado["observaciones"]))
