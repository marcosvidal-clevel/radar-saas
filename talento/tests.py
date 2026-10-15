
from django.contrib import admin
from django.contrib.auth import get_user_model
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
        cls.superusuario = Usuario.objects.create_superuser(
            username="superusuario",
            password="clave-prueba",
            email="superusuario@example.com",
        )

        for usuario, rol in (
            (cls.administrador, Membresia.Rol.ADMINISTRADOR),
            (cls.supervisor, Membresia.Rol.SUPERVISOR),
            (cls.colaborador, Membresia.Rol.COLABORADOR),
        ):
            Membresia.objects.create(
                usuario=usuario,
                organizacion=cls.organizacion_a,
                rol=rol,
                activa=True,
            )

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
        request = self.factory.get("/admin/talento/candidato/")
        request.user = usuario
        return request

    def test_administrador_solo_ve_su_organizacion(self):
        request = self.solicitud(self.administrador)
        candidatos = self.administracion.get_queryset(request)

        self.assertIn(self.candidato_a, candidatos)
        self.assertNotIn(self.candidato_b, candidatos)

    def test_supervisor_solo_ve_su_organizacion(self):
        request = self.solicitud(self.supervisor)
        candidatos = self.administracion.get_queryset(request)

        self.assertIn(self.candidato_a, candidatos)
        self.assertNotIn(self.candidato_b, candidatos)

    def test_colaborador_solo_ve_su_organizacion(self):
        request = self.solicitud(self.colaborador)
        candidatos = self.administracion.get_queryset(request)

        self.assertIn(self.candidato_a, candidatos)
        self.assertNotIn(self.candidato_b, candidatos)

    def test_administrador_no_modifica_candidato_ajeno(self):
        request = self.solicitud(self.administrador)

        self.assertFalse(
            self.administracion.has_change_permission(
                request,
                self.candidato_b,
            )
        )

    def test_supervisor_no_elimina_candidato_ajeno(self):
        request = self.solicitud(self.supervisor)

        self.assertFalse(
            self.administracion.has_delete_permission(
                request,
                self.candidato_b,
            )
        )

    def test_colaborador_no_puede_agregar_candidatos(self):
        request = self.solicitud(self.colaborador)

        self.assertFalse(
            self.administracion.has_add_permission(request)
        )

    def test_superusuario_ve_ambas_organizaciones(self):
        request = self.solicitud(self.superusuario)
        candidatos = self.administracion.get_queryset(request)

        self.assertIn(self.candidato_a, candidatos)
        self.assertIn(self.candidato_b, candidatos)
