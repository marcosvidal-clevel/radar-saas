import os
import subprocess
import sys
from pathlib import Path
from unittest import TestCase

from django.test import RequestFactory, override_settings

from .proxy import TrustedProxyHeadersMiddleware


class ProductionSettingsTests(TestCase):
    base_environment = {
        "RADAR_SECRET_KEY": "synthetic-secret-that-is-long-enough-for-checks-0123456789",
        "RADAR_ALLOWED_HOSTS": "pilot.example.test",
        "RADAR_CSRF_TRUSTED_ORIGINS": "https://pilot.example.test",
        "RADAR_DB_NAME": "synthetic_db",
        "RADAR_DB_USER": "synthetic_user",
        "RADAR_DB_PASSWORD": "synthetic_password",
        "RADAR_DB_HOST": "db.invalid",
    }

    def load_settings(self, environment):
        command = (
            "import config.settings_production as settings; "
            "assert settings.DEBUG is False; "
            "assert settings.SESSION_COOKIE_SECURE is True; "
            "assert settings.CSRF_COOKIE_SECURE is True; "
            "assert settings.STATIC_ROOT != settings.MEDIA_ROOT; "
            "assert not str(settings.MEDIA_ROOT).startswith(str(settings.STATIC_ROOT));"
        )
        env = os.environ.copy()
        env.update(environment)
        env["DJANGO_SETTINGS_MODULE"] = "config.settings_production"
        return subprocess.run(
            [sys.executable, "-c", command],
            cwd=Path(__file__).resolve().parent.parent,
            env=env,
            capture_output=True,
            text=True,
        )

    def test_produccion_rechaza_variables_obligatorias_ausentes(self):
        required = (
            "RADAR_SECRET_KEY",
            "RADAR_ALLOWED_HOSTS",
            "RADAR_DB_NAME",
            "RADAR_DB_USER",
            "RADAR_DB_PASSWORD",
            "RADAR_DB_HOST",
            "RADAR_CSRF_TRUSTED_ORIGINS",
        )
        for variable in required:
            with self.subTest(variable=variable):
                environment = self.base_environment.copy()
                environment.pop(variable)
                resultado = self.load_settings(environment)
                self.assertNotEqual(resultado.returncode, 0)
                self.assertIn(variable, resultado.stderr)

    def test_produccion_desactiva_debug_endurece_cookies_y_separa_storage(self):
        resultado = self.load_settings(self.base_environment)
        self.assertEqual(resultado.returncode, 0, resultado.stderr)


class TrustedProxyHeadersTests(TestCase):
    def request(self, remote_addr, forwarded_proto="https"):
        request = RequestFactory().get("/", HTTP_X_FORWARDED_PROTO=forwarded_proto)
        request.META["REMOTE_ADDR"] = remote_addr
        return request

    def middleware(self):
        return TrustedProxyHeadersMiddleware(lambda request: request)

    @override_settings(TRUSTED_PROXY_IPS=["10.0.0.0/8", "192.0.2.0/24"])
    def test_ignora_forwarded_proto_desde_ip_no_confiable(self):
        request = self.middleware()(self.request("198.51.100.10"))
        self.assertNotIn("HTTP_X_FORWARDED_PROTO", request.META)

    @override_settings(TRUSTED_PROXY_IPS=["10.0.0.0/8", "192.0.2.0/24"])
    def test_acepta_forwarded_proto_solo_desde_red_configurada(self):
        request = self.middleware()(self.request("10.20.30.40"))
        self.assertEqual(request.META["HTTP_X_FORWARDED_PROTO"], "https")

    @override_settings(TRUSTED_PROXY_IPS=["10.0.0.0/8"])
    def test_cabecera_manipulada_no_cambia_proto_no_https(self):
        request = self.middleware()(self.request("198.51.100.10", forwarded_proto="http"))
        self.assertNotIn("HTTP_X_FORWARDED_PROTO", request.META)

    @override_settings(TRUSTED_PROXY_IPS=["not-an-ip-network"])
    def test_rechaza_red_proxy_invalida(self):
        with self.assertRaises(ValueError):
            self.middleware()
