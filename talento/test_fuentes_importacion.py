"""Pruebas de adaptadores normalizados de Gmail y Drive."""
import tempfile

from django.test import TestCase, override_settings

from core.models import Organizacion
from talento.fuentes_importacion import importar_carpeta_drive, importar_mensaje
from talento.models import Candidato, AdjuntoImportado


class FuentesImportacionTests(TestCase):
    def setUp(self):
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        ajuste = override_settings(MEDIA_ROOT=temporal.name)
        ajuste.enable()
        self.addCleanup(ajuste.disable)
        self.organizacion = Organizacion.objects.create(
            nombre="Prueba fuentes", slug="prueba-fuentes"
        )

    def test_gmail_importa_cuerpo_y_adjunto_desconocido(self):
        mensaje = {
            "id": "mail-1", "asunto": "Postulación", "remitente": "candidato@example.com",
            "cuerpo": "Nombre: Persona Ejemplo",
            "adjuntos": [{"id": "a1", "nombre": "anexo.zip", "contenido": b"datos"}],
        }
        primero = importar_mensaje(organizacion=self.organizacion, mensaje=mensaje)
        segundo = importar_mensaje(organizacion=self.organizacion, mensaje=mensaje)
        self.assertTrue(primero["creado"])
        self.assertFalse(segundo["creado"])
        self.assertEqual(Candidato.objects.count(), 1)
        self.assertEqual(AdjuntoImportado.objects.count(), 1)

    def test_drive_reintento_idempotente(self):
        archivos = [{"id": "drive-1", "nombre": "respaldo.jpg", "contenido": b"datos"}]
        importar_carpeta_drive(organizacion=self.organizacion, carpeta_id="carpeta-1", archivos=archivos)
        importar_carpeta_drive(organizacion=self.organizacion, carpeta_id="carpeta-1", archivos=archivos)
        self.assertEqual(Candidato.objects.count(), 1)
        self.assertEqual(AdjuntoImportado.objects.count(), 1)
