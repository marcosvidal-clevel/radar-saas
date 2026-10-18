
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase

from core.models import Membresia, Organizacion
from talento.models import Candidato, DocumentoCandidato


class SeguridadDocumentosTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        Usuario = get_user_model()

        cls.organizacion_a = Organizacion.objects.create(
            nombre="Empresa Documental A",
            slug="empresa-documental-a",
        )
        cls.organizacion_b = Organizacion.objects.create(
            nombre="Empresa Documental B",
            slug="empresa-documental-b",
        )

        cls.administrador = Usuario.objects.create_user(
            username="admin_documental",
            password="clave-prueba",
            is_staff=True,
        )
        cls.colaborador = Usuario.objects.create_user(
            username="colaborador_documental",
            password="clave-prueba",
            is_staff=True,
        )
        cls.superusuario = Usuario.objects.create_superuser(
            username="super_documental",
            password="clave-prueba",
            email="super_documental@example.com",
        )

        for usuario, rol in (
            (cls.administrador, Membresia.Rol.ADMINISTRADOR),
            (cls.colaborador, Membresia.Rol.COLABORADOR),
        ):
            Membresia.objects.create(
                usuario=usuario,
                organizacion=cls.organizacion_a,
                rol=rol,
                activa=True,
            )

        grupo = Group.objects.create(
            name="RADAR - Pruebas documentales"
        )

        permisos = Permission.objects.filter(
            content_type__app_label="talento",
            content_type__model="documentocandidato",
        )
        grupo.permissions.add(*permisos)

        cls.administrador.groups.add(grupo)
        cls.colaborador.groups.add(grupo)

        cls.candidato_a = Candidato.objects.create(
            organizacion=cls.organizacion_a,
            nombre="Candidato Documental A",
        )
        cls.candidato_b = Candidato.objects.create(
            organizacion=cls.organizacion_b,
            nombre="Candidato Documental B",
        )

        cls.documento_a = DocumentoCandidato.objects.create(
            candidato=cls.candidato_a,
            nombre="CV Empresa A",
            tipo=DocumentoCandidato.Tipo.CURRICULUM,
            archivo=SimpleUploadedFile("prueba_a.pdf", b"%PDF-1.4\nDocumento de prueba"),
        )
        cls.documento_b = DocumentoCandidato.objects.create(
            candidato=cls.candidato_b,
            nombre="CV Empresa B",
            tipo=DocumentoCandidato.Tipo.CURRICULUM,
            archivo=SimpleUploadedFile("prueba_b.pdf", b"%PDF-1.4\nDocumento de prueba"),
        )
        cls.evaluacion = DocumentoCandidato.objects.create(
            candidato=cls.candidato_a,
            nombre="Evaluación reservada",
            tipo=DocumentoCandidato.Tipo.EVALUACION,
            archivo=SimpleUploadedFile("evaluacion.pdf", b"%PDF-1.4\nDocumento de prueba"),
        )
        cls.pendiente = DocumentoCandidato.objects.create(
            candidato=cls.candidato_a,
            nombre="Documento pendiente",
            tipo=DocumentoCandidato.Tipo.OTRO,
            pendiente_clasificacion=True,
            archivo=SimpleUploadedFile("pendiente.pdf", b"contenido pendiente"),
        )

    def setUp(self):
        self.factory = RequestFactory()
        self.administracion = admin.site._registry[
            DocumentoCandidato
        ]

    def solicitud(self, usuario):
        request = self.factory.get(
            "/admin/talento/documentocandidato/"
        )
        request.user = usuario
        return request

    def test_administrador_solo_ve_documentos_propios(self):
        documentos = self.administracion.get_queryset(
            self.solicitud(self.administrador)
        )
        self.assertIn(self.documento_a, documentos)
        self.assertNotIn(self.documento_b, documentos)

    def test_colaborador_solo_ve_documentos_propios(self):
        documentos = self.administracion.get_queryset(
            self.solicitud(self.colaborador)
        )
        self.assertIn(self.documento_a, documentos)
        self.assertNotIn(self.documento_b, documentos)

    def test_documento_pendiente_solo_es_visible_para_clasificador(self):
        self.assertNotIn(
            self.pendiente,
            self.administracion.get_queryset(self.solicitud(self.colaborador)),
        )
        self.assertIn(
            self.pendiente,
            self.administracion.get_queryset(self.solicitud(self.administrador)),
        )

    def test_evaluaciones_ocultas_para_administrador(self):
        documentos = self.administracion.get_queryset(
            self.solicitud(self.administrador)
        )
        self.assertNotIn(self.evaluacion, documentos)

    def test_superusuario_puede_ver_evaluaciones(self):
        documentos = self.administracion.get_queryset(
            self.solicitud(self.superusuario)
        )
        self.assertIn(self.evaluacion, documentos)
        self.assertIn(self.documento_b, documentos)

    def test_colaborador_no_puede_modificar_documento(self):
        self.assertFalse(
            self.administracion.has_change_permission(
                self.solicitud(self.colaborador),
                self.documento_a,
            )
        )

    def test_colaborador_no_puede_eliminar_documento(self):
        self.assertFalse(
            self.administracion.has_delete_permission(
                self.solicitud(self.colaborador),
                self.documento_a,
            )
        )

    def test_administrador_no_puede_guardar_documento_ajeno(self):
        documento = DocumentoCandidato.objects.get(
            pk=self.documento_b.pk
        )
        documento.nombre = "Modificación no autorizada"

        with self.assertRaises(PermissionDenied):
            self.administracion.save_model(
                self.solicitud(self.administrador),
                documento,
                None,
                True,
            )

        self.documento_b.refresh_from_db()
        self.assertEqual(
            self.documento_b.nombre,
            "CV Empresa B",
        )

    def test_administrador_no_puede_guardar_evaluacion(self):
        documento = DocumentoCandidato.objects.get(
            pk=self.evaluacion.pk
        )

        with self.assertRaises(PermissionDenied):
            self.administracion.save_model(
                self.solicitud(self.administrador),
                documento,
                None,
                True,
            )

    def test_documento_no_cv_rechaza_cv_principal(self):
        documento = DocumentoCandidato(
            candidato=self.candidato_a,
            nombre="Certificado marcado como CV",
            tipo=DocumentoCandidato.Tipo.CERTIFICACION,
            archivo="curriculums/certificado.pdf",
            es_cv_principal=True,
        )

        with self.assertRaises(ValidationError):
            documento.full_clean()

    def test_archivo_superior_a_10_mb_es_rechazado(self):
        archivo = SimpleUploadedFile(
            "archivo.pdf",
            b"x" * (10 * 1024 * 1024 + 1),
            content_type="application/pdf",
        )

        documento = DocumentoCandidato(
            candidato=self.candidato_a,
            nombre="Documento demasiado grande",
            tipo=DocumentoCandidato.Tipo.CURRICULUM,
            archivo=archivo,
        )

        with self.assertRaises(ValidationError):
            documento.full_clean()

    def test_administrador_no_accede_por_http_a_documento_ajeno(self):
        self.client.force_login(self.administrador)

        respuesta = self.client.get(
            f"/admin/talento/documentocandidato/"
            f"{self.documento_b.pk}/change/"
        )

        self.assertNotEqual(respuesta.status_code, 200)

    def test_administrador_no_accede_por_http_a_evaluacion(self):
        self.client.force_login(self.administrador)

        respuesta = self.client.get(
            f"/admin/talento/documentocandidato/"
            f"{self.evaluacion.pk}/change/"
        )

        self.assertNotEqual(respuesta.status_code, 200)
