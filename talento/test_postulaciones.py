from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import RequestFactory, TestCase

from core.models import Membresia, Organizacion
from talento.models import Candidato, Vacante, Postulacion


class SeguridadPostulacionesTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.org_a = Organizacion.objects.create(
            nombre="Organización A",
            slug="organizacion-a-test",
        )
        cls.org_b = Organizacion.objects.create(
            nombre="Organización B",
            slug="organizacion-b-test",
        )

        Usuario = get_user_model()
        cls.usuario = Usuario.objects.create_user(
            username="admin_postulaciones_a",
            password="clave-prueba",
            is_staff=True,
        )

        Membresia.objects.create(
            usuario=cls.usuario,
            organizacion=cls.org_a,
            rol=Membresia.Rol.ADMINISTRADOR,
            activa=True,
        )

        cls.candidato_a = Candidato.objects.create(
            organizacion=cls.org_a,
            nombre="Candidato A",
        )
        cls.candidato_b = Candidato.objects.create(
            organizacion=cls.org_b,
            nombre="Candidato B",
        )

        cls.vacante_a = Vacante.objects.create(
            organizacion=cls.org_a,
            titulo="Vacante A",
        )
        cls.vacante_b = Vacante.objects.create(
            organizacion=cls.org_b,
            titulo="Vacante B",
        )

        cls.postulacion_a = Postulacion.objects.create(
            vacante=cls.vacante_a,
            candidato=cls.candidato_a,
        )
        cls.postulacion_b = Postulacion.objects.create(
            vacante=cls.vacante_b,
            candidato=cls.candidato_b,
        )

    def test_rechaza_candidato_de_otra_organizacion(self):
        with self.assertRaises(ValidationError):
            Postulacion.objects.create(
                vacante=self.vacante_a,
                candidato=self.candidato_b,
            )

    def test_administrador_no_ve_postulaciones_ajenas(self):
        solicitud = RequestFactory().get("/admin/")
        solicitud.user = self.usuario

        administrador = admin.site._registry[Postulacion]
        registros = administrador.get_queryset(solicitud)

        self.assertIn(self.postulacion_a, registros)
        self.assertNotIn(self.postulacion_b, registros)

    def test_selector_vacantes_excluye_organizacion_ajena(self):
        solicitud = RequestFactory().get("/admin/")
        solicitud.user = self.usuario

        administrador = admin.site._registry[Postulacion]
        campo = administrador.formfield_for_foreignkey(
            Postulacion._meta.get_field("vacante"),
            solicitud,
        )

        self.assertIn(self.vacante_a, campo.queryset)
        self.assertNotIn(self.vacante_b, campo.queryset)

    def test_selector_candidatos_excluye_organizacion_ajena(self):
        solicitud = RequestFactory().get("/admin/")
        solicitud.user = self.usuario

        administrador = admin.site._registry[Postulacion]
        campo = administrador.formfield_for_foreignkey(
            Postulacion._meta.get_field("candidato"),
            solicitud,
        )

        self.assertIn(self.candidato_a, campo.queryset)
        self.assertNotIn(self.candidato_b, campo.queryset)
