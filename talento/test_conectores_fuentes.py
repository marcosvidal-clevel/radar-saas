"""Pruebas de tolerancia a fallos de los conectores Gmail/Drive."""
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from talento.conectores_fuentes import _texto, importar_drive_api, importar_gmail_api


class ConectoresFuentesTests(SimpleTestCase):
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
                organizacion=object(), servicio=servicio, limite=10
            )
        self.assertEqual(len(resultado), 2)
        self.assertEqual(resultado[0]["estado"], "error")
        importar.assert_called_once()
        self.assertEqual(resultado[1]["candidato_id"], 7)

    def test_gmail_extrae_texto_de_html_si_no_hay_texto_plano(self):
        import base64
        html = "<html><head><title>oculto</title></head><body><p>Nombre: Ana</p><script>alert(1)</script><p>RUT: 123</p></body></html>"
        dato = base64.urlsafe_b64encode(html.encode()).decode().rstrip("=")
        texto = _texto({"mimeType": "text/html", "body": {"data": dato}})
        self.assertIn("Nombre: Ana", texto)
        self.assertIn("RUT: 123", texto)
        self.assertNotIn("alert", texto)
        self.assertNotIn("oculto", texto)

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
