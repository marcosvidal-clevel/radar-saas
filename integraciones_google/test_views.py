"""Pruebas de autorización y aislamiento de las vistas de conexiones Google."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models import Membresia, Organizacion
from integraciones_google.models import ConexionGoogle


class VistasConexionGoogleTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_user(username="admin-a", password="test-pass-123")
        self.colaborador = User.objects.create_user(username="colaborador-a", password="test-pass-123")
        self.admin_b = User.objects.create_user(username="admin-b", password="test-pass-123")
        self.org_a = Organizacion.objects.create(nombre="Org A", slug="org-a")
        self.org_b = Organizacion.objects.create(nombre="Org B", slug="org-b")
        Membresia.objects.create(usuario=self.admin, organizacion=self.org_a, rol=Membresia.Rol.ADMINISTRADOR)
        Membresia.objects.create(usuario=self.colaborador, organizacion=self.org_a, rol=Membresia.Rol.COLABORADOR)
        Membresia.objects.create(usuario=self.admin_b, organizacion=self.org_b, rol=Membresia.Rol.ADMINISTRADOR)
        self.conexion_a = ConexionGoogle.objects.create(
            organizacion=self.org_a, cuenta_email="radar-a@example.com",
            token_cifrado="cifrado-falso-de-prueba", scopes=["gmail.readonly"],
        )

    def test_usuario_anonimo_debe_autenticarse(self):
        response = self.client.get(reverse("google_conexiones", args=[self.org_a.pk]))
        self.assertEqual(response.status_code, 302)

    def test_administrador_solo_ve_conexiones_de_su_organizacion(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("google_conexiones", args=[self.org_a.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "radar-a@example.com")
        self.assertNotContains(response, "cifrado-falso-de-prueba")

    def test_administrador_no_puede_consultar_otra_organizacion(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("google_conexiones", args=[self.org_b.pk]))
        self.assertEqual(response.status_code, 403)

    def test_colaborador_no_puede_administrar_conexiones(self):
        self.client.force_login(self.colaborador)
        response = self.client.get(reverse("google_conexiones", args=[self.org_a.pk]))
        self.assertEqual(response.status_code, 403)

    def test_desconexion_exige_post(self):
        self.client.force_login(self.admin)
        url = reverse("google_desconectar", args=[self.org_a.pk, self.conexion_a.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 405)
        self.conexion_a.refresh_from_db()
        self.assertTrue(self.conexion_a.activa)

    def test_administrador_no_puede_desconectar_conexion_de_otra_organizacion(self):
        self.client.force_login(self.admin)
        otra = ConexionGoogle.objects.create(
            organizacion=self.org_b, cuenta_email="radar-b@example.com",
            token_cifrado="cifrado-falso", scopes=[],
        )
        url = reverse("google_desconectar", args=[self.org_a.pk, otra.pk])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 404)
        otra.refresh_from_db()
        self.assertTrue(otra.activa)


    def test_colaborador_no_puede_iniciar_oauth(self):
        self.client.force_login(self.colaborador)
        response = self.client.get(reverse("google_iniciar_oauth", args=[self.org_a.pk]))
        self.assertEqual(response.status_code, 403)

    def test_callback_rechaza_state_ausente_o_no_vinculado_a_sesion(self):
        self.client.force_login(self.admin)
        session = self.client.session
        session["google_oauth_org"] = self.org_a.pk
        session["google_oauth_state"] = "state-esperado"
        session.save()
        response = self.client.get(reverse("google_oauth_callback"), {"state": "state-ajeno", "code": "codigo-falso"})
        self.assertEqual(response.status_code, 403)

    def test_callback_con_error_de_google_no_guarda_conexion(self):
        self.client.force_login(self.admin)
        before = ConexionGoogle.objects.count()
        response = self.client.get(reverse("google_oauth_callback"), {"error": "access_denied"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(ConexionGoogle.objects.count(), before)

    def test_desconexion_revoca_token_remoto_y_limpia_token_local(self):
        import json
        from unittest.mock import Mock, patch
        self.client.force_login(self.admin)
        with patch("talento.oauth_google.descifrar_token", return_value=json.dumps({"refresh_token": "token-prueba"})), patch("requests.post") as enviar:
            enviar.return_value = Mock(status_code=200)
            respuesta = self.client.post(reverse("google_desconectar", args=[self.org_a.pk, self.conexion_a.pk]))
        self.assertEqual(respuesta.status_code, 302)
        enviar.assert_called_once_with(
            "https://oauth2.googleapis.com/revoke",
            data={"token": "token-prueba"},
            timeout=10,
        )
        self.conexion_a.refresh_from_db()
        self.assertFalse(self.conexion_a.activa)
        self.assertEqual(self.conexion_a.token_cifrado, "")

    def test_desconexion_limpia_token_local_si_falla_revocacion_remota(self):
        import json
        from unittest.mock import patch
        self.client.force_login(self.admin)
        with patch("talento.oauth_google.descifrar_token", return_value=json.dumps({"refresh_token": "token-prueba"})), patch("requests.post", side_effect=TimeoutError("Sin respuesta")):
            respuesta = self.client.post(reverse("google_desconectar", args=[self.org_a.pk, self.conexion_a.pk]))
        self.assertEqual(respuesta.status_code, 302)
        self.conexion_a.refresh_from_db()
        self.assertFalse(self.conexion_a.activa)
        self.assertEqual(self.conexion_a.token_cifrado, "")
