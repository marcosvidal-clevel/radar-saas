"""Pruebas unitarias de controles OAuth de Google."""
from unittest.mock import patch

from cryptography.fernet import Fernet
from django.core.exceptions import PermissionDenied
from django.test import SimpleTestCase, override_settings

from talento.oauth_google import (
    DRIVE_SCOPE, GMAIL_SCOPE, cuenta_permitida, cifrar_token,
    crear_state, descifrar_token, validar_scopes, validar_state,
)


@override_settings(SECRET_KEY="test-secret-for-oauth-unit-tests")
class OAuthGoogleTests(SimpleTestCase):
    def test_state_valido_se_vincula_a_sesion_y_organizacion(self):
        state = crear_state("session-123", 42)
        self.assertTrue(validar_state(state, "session-123", 42))

    def test_state_de_otra_sesion_se_rechaza(self):
        state = crear_state("session-123", 42)
        with self.assertRaises(PermissionDenied):
            validar_state(state, "otra-sesion", 42)

    def test_state_de_otra_organizacion_se_rechaza(self):
        state = crear_state("session-123", 42)
        with self.assertRaises(PermissionDenied):
            validar_state(state, "session-123", 43)

    def test_state_manipulado_se_rechaza(self):
        with self.assertRaises(PermissionDenied):
            validar_state("manipulado", "session-123", 42)

    @patch.dict("os.environ", {"RADAR_OAUTH_TOKEN_KEY": Fernet.generate_key().decode()})
    def test_token_se_cifra_y_descifra(self):
        cifrado = cifrar_token("token-de-prueba")
        self.assertNotEqual(cifrado, "token-de-prueba")
        self.assertEqual(descifrar_token(cifrado), "token-de-prueba")

    @patch.dict("os.environ", {"RADAR_OAUTH_TOKEN_KEY": Fernet.generate_key().decode()})
    def test_token_alterado_no_se_descifra(self):
        cifrado = cifrar_token("token-de-prueba")
        alterado = cifrado[:-3] + "abc"
        with self.assertRaises(Exception):
            descifrar_token(alterado)

    def test_scopes_minimos_de_lectura_se_aceptan(self):
        self.assertTrue(validar_scopes([GMAIL_SCOPE, DRIVE_SCOPE]))

    def test_scopes_insuficientes_se_rechazan(self):
        with self.assertRaises(PermissionDenied):
            validar_scopes([GMAIL_SCOPE])

    def test_scopes_de_escritura_se_rechazan(self):
        with self.assertRaises(PermissionDenied):
            validar_scopes([
                GMAIL_SCOPE, DRIVE_SCOPE,
                "https://www.googleapis.com/auth/gmail.modify",
            ])

    @patch.dict("os.environ", {"GOOGLE_OAUTH_ALLOWED_EMAILS": "radar-test@example.com, otra@example.com"})
    def test_cuenta_permitida_es_comparada_sin_distinguir_mayusculas(self):
        self.assertTrue(cuenta_permitida("RADAR-TEST@example.com"))
        self.assertFalse(cuenta_permitida("desconocida@example.com"))
