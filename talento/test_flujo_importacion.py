"""Pruebas del flujo completo de importación con almacenamiento temporal."""
import tempfile

from django.test import TestCase, override_settings

from core.models import Organizacion
from talento.flujo_importacion import importar_candidato
from talento.models import AdjuntoImportado, Candidato


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
        self.assertEqual(resultado["errores_documentos"], 0)
        self.assertEqual(AdjuntoImportado.objects.filter(candidato_id=resultado["candidato_id"]).count(), 1)
        self.assertTrue(Candidato.objects.filter(pk=resultado["candidato_id"]).exists())

    def test_rut_y_direccion_persisten_en_ficha(self):
        resultado = importar_candidato(
            organizacion=self.organizacion, origen="prueba",
            identificador="mensaje-004",
            texto="Nombre: Persona Ejemplo\nRUT: 12.345.678-5\nDirección: Calle Ficticia 123",
        )
        candidato = Candidato.objects.get(pk=resultado["candidato_id"])
        self.assertEqual(candidato.rut, "12345678-5")
        self.assertEqual(candidato.direccion, "Calle Ficticia 123")

    def test_organizaciones_no_comparten_fichas(self):
        segunda = Organizacion.objects.create(
            nombre="Segunda organización", slug="segunda-organizacion"
        )
        primero = importar_candidato(
            organizacion=self.organizacion, origen="prueba", identificador="compartido",
        )
        segundo = importar_candidato(
            organizacion=segunda, origen="prueba", identificador="compartido",
        )
        self.assertNotEqual(primero["candidato_id"], segundo["candidato_id"])

    def test_pdf_se_guarda_y_reintento_no_lo_duplica(self):
        argumentos = dict(
            organizacion=self.organizacion,
            origen="prueba",
            identificador="mensaje-pdf",
            adjuntos=[{
                "nombre": "CV_persona.pdf",
                "contenido": b"%PDF-1.4\\n%%EOF",
                "identificador_origen": "adjunto-pdf-001",
            }],
        )
        primero = importar_candidato(**argumentos)
        segundo = importar_candidato(**argumentos)
        self.assertEqual(primero["errores_documentos"], 0)
        self.assertEqual(segundo["errores_documentos"], 0)
        candidato = Candidato.objects.get(pk=primero["candidato_id"])
        self.assertEqual(candidato.documentos.count(), 1)
        self.assertEqual(candidato.documentos.first().tipo, "curriculum")

    def test_archivo_grande_se_conserva_en_otros_documentos(self):
        resultado = importar_candidato(
            organizacion=self.organizacion, origen="prueba",
            identificador="mensaje-grande",
            adjuntos=[{"nombre": "respaldo.zip", "contenido": b"x" * (10 * 1024 * 1024 + 1),
                       "identificador_origen": "archivo-grande"}],
        )
        self.assertEqual(resultado["errores_documentos"], 0)
        self.assertEqual(AdjuntoImportado.objects.filter(candidato_id=resultado["candidato_id"]).count(), 1)

    def test_piloto_ficticio_importa_lote_sin_bloquear_incompletos(self):
        casos = [
            ("piloto-completo", "Nombre: Persona Completa\\nRUT: 12.345.678-5\\nCorreo: completa@example.com", [
                {"nombre": "CV_persona.pdf", "contenido": b"%PDF-1.4\\n%%EOF", "identificador_origen": "cv-1"},
                {"nombre": "titulo_profesional.pdf", "contenido": b"%PDF-1.4\\n%%EOF", "identificador_origen": "titulo-1"},
                {"nombre": "certificado.pdf", "contenido": b"%PDF-1.4\\n%%EOF", "identificador_origen": "otro-1"},
            ]),
            ("piloto-sin-archivos", "Nombre: Persona Sin Adjuntos", []),
            ("piloto-sin-datos", "", [
                {"nombre": "respaldo.zip", "contenido": b"contenido de prueba", "identificador_origen": "otro-2"},
            ]),
        ]
        ids = []
        for identificador, texto, adjuntos in casos:
            resultado = importar_candidato(
                organizacion=self.organizacion, origen="piloto-sintetico",
                identificador=identificador, texto=texto, adjuntos=adjuntos,
            )
            self.assertTrue(resultado["creado"])
            self.assertEqual(resultado["errores_documentos"], 0)
            ids.append(resultado["candidato_id"])
        self.assertEqual(len(set(ids)), 3)
        self.assertEqual(Candidato.objects.filter(pk__in=ids).count(), 3)
        self.assertEqual(AdjuntoImportado.objects.filter(candidato_id__in=ids).count(), 1)
        self.assertEqual(sum(Candidato.objects.get(pk=pk).documentos.count() for pk in ids), 3)
        for identificador, texto, adjuntos in casos:
            resultado = importar_candidato(
                organizacion=self.organizacion, origen="piloto-sintetico",
                identificador=identificador, texto=texto, adjuntos=adjuntos,
            )
            self.assertFalse(resultado["creado"])
        self.assertEqual(Candidato.objects.filter(pk__in=ids).count(), 3)
        self.assertEqual(AdjuntoImportado.objects.filter(candidato_id__in=ids).count(), 1)
        self.assertEqual(sum(Candidato.objects.get(pk=pk).documentos.count() for pk in ids), 3)
