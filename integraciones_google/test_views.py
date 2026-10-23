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
