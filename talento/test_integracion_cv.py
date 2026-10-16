from io import BytesIO
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from docx import Document
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

from core.models import Membresia, Organizacion
from talento.models import Candidato, DocumentoCandidato


def crear_pdf(texto):
    """Genera un PDF de una página con texto, sin documentos externos."""
    escritor = PdfWriter()
    pagina = escritor.add_blank_page(width=612, height=792)
    fuente = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    })
    pagina[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({NameObject("/F1"): fuente}),
    })
    contenido = DecodedStreamObject()
    contenido.set_data(
        f"BT /F1 12 Tf 72 720 Td ({texto}) Tj ET".encode("ascii")
    )
    pagina[NameObject("/Contents")] = contenido
    salida = BytesIO()
    escritor.write(salida)
    return salida.getvalue()


def crear_docx(texto):
    documento = Document()
    documento.add_paragraph(texto)
    salida = BytesIO()
    documento.save(salida)
    return salida.getvalue()


class CargaBusquedaCVIntegracionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organizacion = Organizacion.objects.create(
            nombre="Organizacion sintetica A", slug="integracion-a"
        )
        organizacion_ajena = Organizacion.objects.create(
            nombre="Organizacion sintetica B", slug="integracion-b"
        )
        permisos = list(Permission.objects.filter(
            content_type__app_label="talento",
            codename__in=(
                "view_candidato",
                "add_documentocandidato",
                "view_documentocandidato",
            ),
        ))
        for atributo, organizacion in (
            ("administrador", cls.organizacion),
            ("administrador_ajeno", organizacion_ajena),
        ):
            usuario = get_user_model().objects.create_user(
                username=atributo, is_staff=True
            )
            usuario.user_permissions.add(*permisos)
            Membresia.objects.create(
                usuario=usuario,
                organizacion=organizacion,
                rol=Membresia.Rol.ADMINISTRADOR,
            )
            setattr(cls, atributo, usuario)
        cls.candidato = Candidato.objects.create(
            organizacion=cls.organizacion, nombre="Perfil sintetico A"
        )
        cls.candidato_ajeno = Candidato.objects.create(
            organizacion=organizacion_ajena, nombre="Perfil sintetico B"
        )

    def setUp(self):
        directorio = TemporaryDirectory()
        self.addCleanup(directorio.cleanup)
        self.media_root = directorio.name
        configuracion = override_settings(
            MEDIA_ROOT=self.media_root,
            STORAGES={
                "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
                "staticfiles": {
                    "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
                },
            },
        )
        configuracion.enable()
        self.addCleanup(configuracion.disable)

    def comprobar_carga_busqueda_y_aislamiento(self, extension, contenido, tipo_mime):
        palabra = "Zafirocurricular"
        url_busqueda = reverse("admin:talento_candidato_changelist")
        self.client.force_login(self.administrador)

        # La palabra no aparece en el perfil ni en el nombre del documento.
        respuesta = self.client.get(url_busqueda, {"q": palabra})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(list(respuesta.context["cl"].queryset), [])

        respuesta = self.client.post(
            reverse("admin:talento_documentocandidato_add"),
            {
                "candidato": self.candidato.pk,
                "tipo": DocumentoCandidato.Tipo.CURRICULUM,
                "nombre": "Curriculum sintetico",
                "archivo": SimpleUploadedFile(
                    f"perfil.{extension}", contenido, content_type=tipo_mime
                ),
                "vigente": "on",
                "es_cv_principal": "on",
                "_save": "Guardar",
            },
        )
        self.assertEqual(respuesta.status_code, 302)
        documento = DocumentoCandidato.objects.get(candidato=self.candidato)
        self.assertIn(palabra, documento.texto_extraido)
        self.assertEqual(documento.archivo.storage.location, self.media_root)
        self.assertTrue(documento.archivo.storage.exists(documento.archivo.name))

        respuesta = self.client.get(url_busqueda, {"q": palabra})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(list(respuesta.context["cl"].queryset), [self.candidato])

        url_descarga = reverse("descargar_documento_candidato", args=[documento.pk])
        respuesta = self.client.get(url_descarga)
        self.addCleanup(respuesta.close)
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(b"".join(respuesta.streaming_content), contenido)
        respuesta.close()

        # El usuario ajeno tiene permisos: la restricción es por organización.
        self.client.force_login(self.administrador_ajeno)
        respuesta = self.client.get(url_busqueda)
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(
            list(respuesta.context["cl"].queryset), [self.candidato_ajeno]
        )
        respuesta = self.client.get(url_busqueda, {"q": palabra})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(list(respuesta.context["cl"].queryset), [])
        self.assertNotContains(respuesta, self.candidato.nombre)
        respuesta = self.client.get(url_descarga)
        self.assertEqual(respuesta.status_code, 403)
        self.assertFalse(respuesta.streaming)

    def test_carga_pdf_extrae_busca_y_aisla_cv(self):
        self.comprobar_carga_busqueda_y_aislamiento(
            "pdf", crear_pdf("Experiencia Zafirocurricular"), "application/pdf"
        )

    def test_carga_docx_extrae_busca_y_aisla_cv(self):
        self.comprobar_carga_busqueda_y_aislamiento(
            "docx",
            crear_docx("Experiencia Zafirocurricular"),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
