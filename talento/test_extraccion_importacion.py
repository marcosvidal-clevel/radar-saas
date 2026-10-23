"""Pruebas de extracción conservadora de contactos."""
from django.test import SimpleTestCase

from talento.extraccion_importacion import extraer_datos


class ExtraccionImportacionTests(SimpleTestCase):
    def test_nombre_y_direccion_no_absorben_siguiente_linea(self):
        datos = extraer_datos(
            "Nombre: Ana Ejemplo\nCorreo: ana@example.com\n"
            "Dirección: Calle Uno 123\nCelular: +56 9 1234 5678"
        )
        self.assertEqual(datos["nombre"], "Ana Ejemplo")
        self.assertEqual(datos["direccion"], "Calle Uno 123")
        self.assertEqual(datos["email"], "ana@example.com")
        self.assertEqual(datos["telefono"], "+56 9 1234 5678")

    def test_sin_campos_no_inventa_informacion(self):
        self.assertEqual(extraer_datos("Postulación sin datos personales"), {})
