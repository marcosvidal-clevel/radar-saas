
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TransactionTestCase, override_settings
from django.urls import reverse

from core.models import Membresia, Organizacion
from talento.models import Candidato, DocumentoCandidato


class SeguridadDescargasTests(TransactionTestCase):

    @classmethod
    def setUpClass(cls):
        cls.directorio = TemporaryDirectory()
        cls.configuracion = override_settings(
            MEDIA_ROOT=cls.directorio.name
        )
        cls.configuracion.enable()
        try:
            super().setUpClass()
        except Exception:
            cls.configuracion.disable()
            cls.directorio.cleanup()
            raise

    @classmethod
    def tearDownClass(cls):
        try:
            super().tearDownClass()
        finally:
            cls.configuracion.disable()
            cls.directorio.cleanup()

    def setUp(self):
        Usuario = get_user_model()

        self.organizacion_a = Organizacion.objects.create(
            nombre="Empresa Descargas A",
            slug="empresa-descargas-a",
        )
        self.organizacion_b = Organizacion.objects.create(
            nombre="Empresa Descargas B",
            slug="empresa-descargas-b",
        )

        self.administrador = Usuario.objects.create_user(
            username="admin_descargas",
            password="clave-prueba",
            is_staff=True,
        )
        self.colaborador = Usuario.objects.create_user(
            username="colaborador_descargas",
            password="clave-prueba",
            is_staff=True,
        )
        self.usuario_ajeno = Usuario.objects.create_user(
            username="ajeno_descargas",
            password="clave-prueba",
            is_staff=True,
        )
        self.usuario_sin_permisos = Usuario.objects.create_user(
            username="sin_permisos_descargas",
            password="clave-prueba",
            is_staff=True,
        )
        self.superusuario = Usuario.objects.create_superuser(
            username="super_descargas",
            password="clave-prueba",
            email="super_descargas@example.com",
        )

        for usuario, organizacion, rol in (
            (
                self.administrador,
                self.organizacion_a,
                Membresia.Rol.ADMINISTRADOR,
            ),
            (
                self.colaborador,
                self.organizacion_a,
                Membresia.Rol.COLABORADOR,
            ),
            (
                self.usuario_ajeno,
                self.organizacion_b,
                Membresia.Rol.ADMINISTRADOR,
            ),
        ):
            Membresia.objects.create(
                usuario=usuario,
                organizacion=organizacion,
                rol=rol,
                activa=True,
            )

        grupo = Group.objects.create(
            name="RADAR - Permisos de descargas"
        )

        permiso = Permission.objects.get(
            content_type__app_label="talento",
            codename="view_documentocandidato",
        )
        grupo.permissions.add(permiso)

        for usuario in (
            self.administrador,
            self.colaborador,
            self.usuario_ajeno,
        ):
            usuario.groups.add(grupo)

        self.candidato = Candidato.objects.create(
            organizacion=self.organizacion_a,
            nombre="Candidato de descarga",
        )

        self.documento = DocumentoCandidato.objects.create(
            candidato=self.candidato,
            nombre="Currículum de prueba",
            tipo=DocumentoCandidato.Tipo.CURRICULUM,
            archivo=SimpleUploadedFile(
                "curriculum.pdf",
                b"%PDF-1.4\nContenido de prueba",
                content_type="application/pdf",
            ),
        )

        self.evaluacion = DocumentoCandidato.objects.create(
            candidato=self.candidato,
            nombre="Evaluación reservada",
            tipo=DocumentoCandidato.Tipo.EVALUACION,
            archivo=SimpleUploadedFile(
                "evaluacion.pdf",
                b"%PDF-1.4\nEvaluacion de prueba",
                content_type="application/pdf",
            ),
        )

    def url(self, documento):
        return reverse(
            "descargar_documento_candidato",
            args=[documento.pk],
        )

    def test_administrador_descarga_documento_propio(self):
        self.client.force_login(self.administrador)

        respuesta = self.client.get(self.url(self.documento))

        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.streaming)
        self.assertEqual(
            b"".join(respuesta.streaming_content),
            b"%PDF-1.4\nContenido de prueba",
        )
        respuesta.close()

    def test_colaborador_autorizado_descarga_documento(self):
        self.client.force_login(self.colaborador)

        respuesta = self.client.get(self.url(self.documento))

        self.assertEqual(respuesta.status_code, 200)
        respuesta.close()

    def test_usuario_otra_empresa_no_descarga(self):
        self.client.force_login(self.usuario_ajeno)

        respuesta = self.client.get(self.url(self.documento))

        self.assertEqual(respuesta.status_code, 403)

    def test_usuario_sin_permiso_no_descarga(self):
        self.client.force_login(self.usuario_sin_permisos)

        respuesta = self.client.get(self.url(self.documento))

        self.assertEqual(respuesta.status_code, 403)

    def test_usuario_anonimo_no_descarga(self):
        respuesta = self.client.get(self.url(self.documento))

        self.assertEqual(respuesta.status_code, 302)

    def test_administrador_no_descarga_evaluacion(self):
        self.client.force_login(self.administrador)

        respuesta = self.client.get(self.url(self.evaluacion))

        self.assertEqual(respuesta.status_code, 403)

    def test_superusuario_descarga_evaluacion(self):
        self.client.force_login(self.superusuario)

        respuesta = self.client.get(self.url(self.evaluacion))

        self.assertEqual(respuesta.status_code, 200)
        respuesta.close()

    def test_documento_inexistente_devuelve_404(self):
        self.client.force_login(self.administrador)

        url = reverse(
            "descargar_documento_candidato",
            args=[999999],
        )

        respuesta = self.client.get(url)

        self.assertEqual(respuesta.status_code, 404)

    def test_archivo_fisico_inexistente_devuelve_404(self):
        self.client.force_login(self.administrador)

        self.documento.archivo.delete(save=False)

        respuesta = self.client.get(self.url(self.documento))

        self.assertEqual(respuesta.status_code, 404)

    def test_descarga_rechaza_post(self):
        self.client.force_login(self.administrador)

        respuesta = self.client.post(self.url(self.documento))

        self.assertEqual(respuesta.status_code, 405)
