"""Pruebas del flujo completo de importación con almacenamiento temporal."""
import tempfile

from django.test import TestCase, override_settings

from core.models import Organizacion
from talento.flujo_importacion import importar_candidato
from talento.models import Candidato


class FlujoImportacionTests(TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        self.ajuste = override_settings(MEDIA_ROOT=self.temporal.name)
        self.ajuste.enable()
        self.addCleanup(self.ajuste.disable)
        self.organizacion = Organizacion.objects.create(nombre="Organización de prueba", slug="organizacion-prueba")

    def test_ficha_incompleta_no_se_descarta(self):
        resultado = importar_candidato(
            organizacion=self.organizacion, origen="prueba",
            identificador="mensaje-001", texto="", adjuntos=[],
        )
        self.assertTrue(resultado["creado"])
        candidato = Candidato.objects.get(pk=resultado["candidato_id"])
        self.assertIn("Pendiente de identificación", candidato.nombre)
        self.assertTrue(any("RUT" in item for item in resultado["observaciones"]))

    def test_reintento_no_duplica_ficha(self):
        argumentos = dict(organizacion=self.organizacion, origen="prueba",
                          identificador="mensaje-002", texto="Nombre: Persona Ejemplo")
        primero = importar_candidato(**argumentos)
        segundo = importar_candidato(**argumentos)
        self.assertEqual(primero["candidato_id"], segundo["candidato_id"])
        self.assertFalse(segundo["creado"])

    def test_archivo_incompatible_no_bloquea_ficha(self):
        resultado = importar_candidato(
            organizacion=self.organizacion, origen="prueba",
            identificador="mensaje-003",
            adjuntos=[{"nombre": "foto.jpg", "contenido": b"datos", "identificador_origen": "a1"}],
        )
        self.assertEqual(resultado["errores_documentos"], 1)
        self.assertTrue(Candidato.objects.filter(pk=resultado["candidato_id"]).exists())

    def test_rut_y_direccion_persisten_en_ficha(self):
        resultado = importar_candidato(
            organizacion=self.organizacion, origen="prueba",
            identificador="mensaje-004",
            texto="Nombre: Persona Ejemplo\\nRUT: 12.345.678-5\\nDirección: Calle Ficticia 123",
        )
        candidato = Candidato.objects.get(pk=resultado["candidato_id"])
        self.assertEqual(candidato.rut, "12345678-5")
        self.assertEqual(candidato.direccion, "Calle Ficticia 123")
