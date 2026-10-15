
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import RequestFactory, TestCase

from core.models import Membresia, Organizacion
from .models import Candidato


class SeguridadCandidatosTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        Usuario = get_user_model()

        cls.organizacion_a = Organizacion.objects.create(
            nombre="Empresa A",
            slug="empresa-a",
        )
        cls.organizacion_b = Organizacion.objects.create(
            nombre="Empresa B",
            slug="empresa-b",
        )

        cls.administrador = Usuario.objects.create_user(
            username="admin_a",
            password="clave-prueba",
            is_staff=True,
        )
        cls.supervisor = Usuario.objects.create_user(
            username="supervisor_a",
            password="clave-prueba",
            is_staff=True,
        )
        cls.colaborador = Usuario.objects.create_user(
            username="colaborador_a",
            password="clave-prueba",
            is_staff=True,
        )
        cls.usuario_comercial = Usuario.objects.create_user(
            username="comercial_a",
            password="clave-prueba",
            is_staff=True,
        )
        cls.superusuario = Usuario.objects.create_superuser(
            username="superusuario",
            password="clave-prueba",
            email="superusuario@example.com",
        )

        for usuario, rol in (
            (cls.administrador, Membresia.Rol.ADMINISTRADOR),
            (cls.supervisor, Membresia.Rol.SUPERVISOR),
            (cls.colaborador, Membresia.Rol.COLABORADOR),
            (cls.usuario_comercial, Membresia.Rol.ADMINISTRADOR),
        ):
            Membresia.objects.create(
                usuario=usuario,
                organizacion=cls.organizacion_a,
                rol=rol,
                activa=True,
            )

        grupo_talento = Group.objects.create(
            name="RADAR — Acceso talento"
        )

        permisos_talento = Permission.objects.filter(
            content_type__app_label="talento",
            codename__in=(
                "add_candidato",
                "change_candidato",
                "delete_candidato",
                "view_candidato",
            ),
        )

        grupo_talento.permissions.add(*permisos_talento)

        for usuario in (
            cls.administrador,
            cls.supervisor,
            cls.colaborador,
        ):
            usuario.groups.add(grupo_talento)

        grupo_comercial = Group.objects.create(
            name="RADAR — Acceso comercial"
        )
        cls.usuario_comercial.groups.add(grupo_comercial)

        cls.candidato_a = Candidato.objects.create(
            organizacion=cls.organizacion_a,
            nombre="Candidato Empresa A",
        )
        cls.candidato_b = Candidato.objects.create(
            organizacion=cls.organizacion_b,
            nombre="Candidato Empresa B",
        )

    def setUp(self):
        self.factory = RequestFactory()
        self.administracion = admin.site._registry[Candidato]

    def solicitud(self, usuario):
        request = self.factory.get(
            "/admin/talento/candidato/"
        )
        request.user = usuario
        return request

    def test_administrador_solo_ve_su_organizacion(self):
        candidatos = self.administracion.get_queryset(
            self.solicitud(self.administrador)
        )

        self.assertIn(self.candidato_a, candidatos)
        self.assertNotIn(self.candidato_b, candidatos)

    def test_supervisor_solo_ve_su_organizacion(self):
        candidatos = self.administracion.get_queryset(
            self.solicitud(self.supervisor)
        )

        self.assertIn(self.candidato_a, candidatos)
        self.assertNotIn(self.candidato_b, candidatos)

    def test_colaborador_solo_ve_su_organizacion(self):
        candidatos = self.administracion.get_queryset(
            self.solicitud(self.colaborador)
        )

        self.assertIn(self.candidato_a, candidatos)
        self.assertNotIn(self.candidato_b, candidatos)

    def test_administrador_puede_modificar_su_candidato(self):
        self.assertTrue(
            self.administracion.has_change_permission(
                self.solicitud(self.administrador),
                self.candidato_a,
            )
        )

    def test_administrador_no_modifica_candidato_ajeno(self):
        self.assertFalse(
            self.administracion.has_change_permission(
                self.solicitud(self.administrador),
                self.candidato_b,
            )
        )

    def test_supervisor_puede_modificar_su_candidato(self):
        self.assertTrue(
            self.administracion.has_change_permission(
                self.solicitud(self.supervisor),
                self.candidato_a,
            )
        )

    def test_supervisor_no_elimina_candidato_ajeno(self):
        self.assertFalse(
            self.administracion.has_delete_permission(
                self.solicitud(self.supervisor),
                self.candidato_b,
            )
        )

    def test_colaborador_puede_consultar_su_candidato(self):
        self.assertTrue(
            self.administracion.has_view_permission(
                self.solicitud(self.colaborador),
                self.candidato_a,
            )
        )

    def test_colaborador_no_puede_agregar_candidatos(self):
        self.assertFalse(
            self.administracion.has_add_permission(
                self.solicitud(self.colaborador)
            )
        )

    def test_usuario_comercial_no_accede_a_talento(self):
        self.assertFalse(
            self.administracion.has_view_permission(
                self.solicitud(self.usuario_comercial),
                self.candidato_a,
            )
        )

    def test_superusuario_ve_ambas_organizaciones(self):
        candidatos = self.administracion.get_queryset(
            self.solicitud(self.superusuario)
        )

        self.assertIn(self.candidato_a, candidatos)
        self.assertIn(self.candidato_b, candidatos)

    def test_comercial_no_ingresa_al_listado_talento(self):
        self.client.force_login(self.usuario_comercial)

        respuesta = self.client.get(
            "/admin/talento/candidato/"
        )

        self.assertEqual(respuesta.status_code, 403)

    def test_administrador_ingresa_al_listado_talento(self):
        self.client.force_login(self.administrador)

        respuesta = self.client.get(
            "/admin/talento/candidato/"
        )

        self.assertEqual(respuesta.status_code, 200)

    def test_administrador_no_accede_a_candidato_ajeno(self):
        self.client.force_login(self.administrador)

        respuesta = self.client.get(
            f"/admin/talento/candidato/{self.candidato_b.pk}/change/"
        )

        self.assertEqual(respuesta.status_code, 302)

    def test_administrador_accede_a_su_candidato(self):
        self.client.force_login(self.administrador)

        respuesta = self.client.get(
            f"/admin/talento/candidato/{self.candidato_a.pk}/change/"
        )

        self.assertEqual(respuesta.status_code, 200)
