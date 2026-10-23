"""Pruebas de tolerancia a fallos de los conectores Gmail/Drive."""
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from talento.conectores_fuentes import _texto, importar_drive_api, importar_gmail_api


class ConectoresFuentesTests(SimpleTestCase):
    def test_gmail_incluye_correos_sin_adjuntos_con_filtro_explicito(self):
        servicio = MagicMock()
        servicio.users.return_value.messages.return_value.list.return_value.execute.return_value = {
            "messages": [{"id": "correo-solo-texto"}]
        }
        servicio.users.return_value.messages.return_value.get.return_value.execute.return_value = {
            "id": "correo-solo-texto",
            "payload": {"headers": [], "body": {"data": ""}},
        }
        with patch("talento.conectores_fuentes.importar_mensaje",
                   return_value={"candidato_id": 21}) as importar:
            resultado = importar_gmail_api(
                organizacion=object(), servicio=servicio, consulta='subject:postulacion', limite=1
            )
        self.assertEqual(resultado, [{"candidato_id": 21}])
        self.assertEqual(
            servicio.users.return_value.messages.return_value.list.call_args.kwargs["q"], "subject:postulacion"
        )
        self.assertEqual(importar.call_args.kwargs["mensaje"]["adjuntos"], [])

    def test_gmail_rechaza_busqueda_vacia_sin_acceder_al_correo(self):
        servicio = MagicMock()
        for consulta in ("", "  ", None):
            with self.subTest(consulta=consulta):
                with self.assertRaises(ValueError):
                    importar_gmail_api(
                        organizacion=object(), servicio=servicio,
                        consulta=consulta, limite=10,
                    )
        servicio.users.assert_not_called()

    def test_gmail_continua_si_un_mensaje_falla(self):
        servicio = MagicMock()
        servicio.users.return_value.messages.return_value.list.return_value.execute.return_value = {
            "messages": [{"id": "fallido"}, {"id": "correcto"}]
        }
        correcto = MagicMock()
        correcto.execute.return_value = {
            "id": "correcto",
            "payload": {"headers": [], "body": {"data": ""}},
        }
        servicio.users.return_value.messages.return_value.get.side_effect = [
            RuntimeError("mensaje ilegible"),
            correcto,
        ]
        with patch("talento.conectores_fuentes.importar_mensaje",
                   return_value={"candidato_id": 7, "creado": True}) as importar:
            resultado = importar_gmail_api(
                organizacion=object(), servicio=servicio, consulta='subject:postulacion', limite=10
            )
        self.assertEqual(len(resultado), 2)
        self.assertEqual(resultado[0]["estado"], "error")
        importar.assert_called_once()
        self.assertEqual(resultado[1]["candidato_id"], 7)

    def test_gmail_conserva_adjunto_embebido_sin_attachment_id(self):
        import base64
        servicio = MagicMock()
        servicio.users.return_value.messages.return_value.list.return_value.execute.return_value = {
            "messages": [{"id": "correo-1"}]
        }
        dato = base64.urlsafe_b64encode(b"%PDF-embebido").decode().rstrip("=")
        servicio.users.return_value.messages.return_value.get.return_value.execute.return_value = {
            "id": "correo-1",
            "payload": {
                "headers": [{"name": "Subject", "value": "Postulacion"}],
                "parts": [{"filename": "CV Ana.pdf", "partId": "parte-1",
                           "body": {"data": dato}, "mimeType": "application/pdf"}],
            },
        }
        with patch("talento.conectores_fuentes.importar_mensaje",
                   return_value={"candidato_id": 15}) as importar:
            resultado = importar_gmail_api(
                organizacion=object(), servicio=servicio, consulta='subject:postulacion', limite=1
            )
        self.assertEqual(resultado, [{"candidato_id": 15}])
        adjunto = importar.call_args.kwargs["mensaje"]["adjuntos"][0]
        self.assertEqual(adjunto["nombre"], "CV Ana.pdf")
        self.assertEqual(adjunto["contenido"], b"%PDF-embebido")
        servicio.users.return_value.messages.return_value.attachments.assert_not_called()

    def test_gmail_extrae_texto_de_html_si_no_hay_texto_plano(self):
        import base64
        html = "<html><head><title>oculto</title></head><body><p>Nombre: Ana</p><script>alert(1)</script><p>RUT: 123</p></body></html>"
        dato = base64.urlsafe_b64encode(html.encode()).decode().rstrip("=")
        texto = _texto({"mimeType": "text/html", "body": {"data": dato}})
        self.assertIn("Nombre: Ana", texto)
        self.assertIn("RUT: 123", texto)
        self.assertNotIn("alert", texto)
        self.assertNotIn("oculto", texto)

    def test_drive_exporta_documento_nativo_a_pdf(self):
        servicio = MagicMock()
        servicio.files.return_value.list.return_value.execute.return_value = {
            "files": [{"id": "doc-google", "name": "CV Ana", "mimeType": "application/vnd.google-apps.document"}]
        }
        servicio.files.return_value.export.return_value.execute.return_value = b"%PDF-test"
        with patch("talento.conectores_fuentes.importar_carpeta_drive",
                   return_value=[{"candidato_id": 11}]) as importar:
            resultado = importar_drive_api(
                organizacion=object(), servicio=servicio,
                carpeta_id="carpeta", limite=10
            )
        servicio.files.return_value.export.assert_called_once_with(
            fileId="doc-google", mimeType="application/pdf"
        )
        self.assertEqual(resultado, [{"candidato_id": 11}])
        archivo = importar.call_args.kwargs["archivos"][0]
        self.assertEqual(archivo["name"], "CV Ana.pdf")
        self.assertEqual(archivo["contenido"], b"%PDF-test")

    def test_limite_cero_no_consulta_fuentes(self):
        servicio = MagicMock()
        self.assertEqual(
            importar_gmail_api(organizacion=object(), servicio=servicio, limite=0), []
        )
        self.assertEqual(
            importar_drive_api(
                organizacion=object(), servicio=servicio,
                carpeta_id="carpeta", limite=0
            ), []
        )
        servicio.users.assert_not_called()
        servicio.files.assert_not_called()

    def test_drive_continua_si_falla_exportacion_de_documento_nativo(self):
        servicio = MagicMock()
        servicio.files.return_value.list.return_value.execute.return_value = {
            "files": [
                {"id": "fallido", "name": "doc roto", "mimeType": "application/vnd.google-apps.document"},
                {"id": "correcto", "name": "archivo.pdf", "mimeType": "application/pdf"},
            ]
        }
        servicio.files.return_value.export.return_value.execute.side_effect = RuntimeError("exportación fallida")
        servicio.files.return_value.get_media.return_value.execute.return_value = b"contenido"
        with patch("talento.conectores_fuentes.importar_carpeta_drive",
                   return_value=[{"candidato_id": 12}]) as importar:
            resultado = importar_drive_api(
                organizacion=object(), servicio=servicio,
                carpeta_id="carpeta", limite=10
            )
        self.assertEqual(resultado[0]["estado"], "error")
        self.assertEqual(resultado[1], {"candidato_id": 12})
        importar.assert_called_once()

    def test_drive_continua_si_un_archivo_falla(self):
        servicio = MagicMock()
        servicio.files.return_value.list.return_value.execute.return_value = {
            "files": [
                {"id": "fallido", "name": "error.pdf", "mimeType": "application/pdf"},
                {"id": "correcto", "name": "ok.pdf", "mimeType": "application/pdf"},
            ]
        }
        servicio.files.return_value.get_media.return_value.execute.side_effect = [
            RuntimeError("descarga fallida"), b"contenido"
        ]
        with patch("talento.conectores_fuentes.importar_carpeta_drive",
                   return_value=[{"candidato_id": 9}]) as importar:
            resultado = importar_drive_api(
                organizacion=object(), servicio=servicio,
                carpeta_id="carpeta", limite=10
            )
        self.assertEqual(len(resultado), 2)
        self.assertEqual(resultado[0]["estado"], "error")
        self.assertEqual(resultado[1]["candidato_id"], 9)
        importar.assert_called_once()

    def test_drive_no_solicita_subcarpetas_como_documentos(self):
        servicio = MagicMock()
        servicio.files.return_value.list.return_value.execute.return_value = {"files": []}
        importar_drive_api(
            organizacion=object(), servicio=servicio, carpeta_id="carpeta", limite=10,
        )
        consulta = servicio.files.return_value.list.call_args.kwargs["q"]
        self.assertIn("mimeType != 'application/vnd.google-apps.folder'", consulta)

    def test_drive_acepta_identificador_con_guion_y_guion_bajo(self):
        servicio = MagicMock()
        servicio.files.return_value.list.return_value.execute.return_value = {"files": []}
        self.assertEqual(
            importar_drive_api(
                organizacion=object(), servicio=servicio,
                carpeta_id="folder_123-ABC", limite=1,
            ), []
        )
        self.assertIn(
            "'folder_123-ABC' in parents",
            servicio.files.return_value.list.call_args.kwargs["q"],
        )

    def test_drive_rechaza_identificador_inseguro_sin_consultar_api(self):
        servicio = MagicMock()
        for carpeta_id in ("", "  ", "carpeta' or trashed = false", "carpeta\\nmaliciosa", "carpeta/con/ruta", "carpeta con espacio", None):
            with self.subTest(carpeta_id=carpeta_id):
                with self.assertRaises(ValueError):
                    importar_drive_api(
                        organizacion=object(), servicio=servicio,
                        carpeta_id=carpeta_id, limite=10,
                    )
        servicio.files.assert_not_called()
