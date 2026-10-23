"""Pruebas unitarias de reglas de importación, sin acceder a datos reales."""
from django.test import SimpleTestCase

from talento.clasificacion_importacion import clasificar_adjunto, observaciones_minimas
from talento.extraccion_importacion import extraer_datos


class ReglasImportacionTests(SimpleTestCase):
    def test_cv_y_titulo(self):
        self.assertEqual(clasificar_adjunto("CV_persona.pdf"), "curriculum")
        self.assertEqual(clasificar_adjunto("Titulo_profesional.pdf"), "titulo")
        self.assertEqual(clasificar_adjunto("certificado.pdf"), "otro")

    def test_datos_faltantes_no_bloquean(self):
        resultado = observaciones_minimas({}, [])
        self.assertTrue(any("RUT" in item for item in resultado))
        self.assertTrue(any("CV" in item for item in resultado))

    def test_extraer_contacto(self):
        datos = extraer_datos("Nombre: Persona Ejemplo\nDirección: Calle Ficticia 123\ncontacto@example.org")
        self.assertEqual(datos["nombre"], "Persona Ejemplo")
        self.assertEqual(datos["email"], "contacto@example.org")
