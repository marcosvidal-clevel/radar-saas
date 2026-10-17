from tempfile import TemporaryDirectory
from io import BytesIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from docx import Document
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

from core.models import Membresia, Organizacion
from .models import Candidato, DocumentoCandidato


class VistasTalentoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organizacion_a = Organizacion.objects.create(
            nombre="Talento A", slug="talento-a"
        )
        cls.organizacion_b = Organizacion.objects.create(
            nombre="Talento B", slug="talento-b"
        )
        Usuario = get_user_model()
        cls.usuario = Usuario.objects.create_user(
            username="talento_usuario", is_staff=True
        )
        cls.usuario_sin_permisos = Usuario.objects.create_user(
            username="talento_sin_permisos", is_staff=True
        )
        cls.usuario_ajeno = Usuario.objects.create_user(
            username="talento_ajeno", is_staff=True
        )
        Membresia.objects.create(
            usuario=cls.usuario,
            organizacion=cls.organizacion_a,
            rol=Membresia.Rol.ADMINISTRADOR,
            activa=True,
        )
        Membresia.objects.create(
            usuario=cls.usuario_ajeno,
            organizacion=cls.organizacion_b,
            rol=Membresia.Rol.ADMINISTRADOR,
            activa=True,
        )
        permisos = list(Permission.objects.filter(
            content_type__app_label="talento",
            codename__in=(
                "add_candidato",
                "view_candidato",
                "view_documentocandidato",
            ),
        ))
        cls.usuario.user_permissions.add(*permisos)
        cls.usuario_ajeno.user_permissions.add(*permisos)
        cls.candidato = Candidato.objects.create(
            organizacion=cls.organizacion_a,
            nombre="Candidato Zafiro",
            profesion="Ingeniero civil",
        )
        cls.candidato_ajeno = Candidato.objects.create(
            organizacion=cls.organizacion_b,
            nombre="Candidato Rubí",
        )

    def setUp(self):
        self.directorio = TemporaryDirectory()
        self.addCleanup(self.directorio.cleanup)
        self.configuracion = override_settings(MEDIA_ROOT=self.directorio.name)
        self.configuracion.enable()
        self.addCleanup(self.configuracion.disable)

    def crear_documento(self, candidato, tipo=DocumentoCandidato.Tipo.CURRICULUM):
        documento = DocumentoCandidato.objects.create(
            candidato=candidato,
            tipo=tipo,
            nombre="CV sintético",
            archivo=SimpleUploadedFile(
                "cv-sintetico.pdf",
                b"%PDF-1.4 contenido sintetico",
                content_type="application/pdf",
            ),
        )
        DocumentoCandidato.objects.filter(pk=documento.pk).update(
            texto_extraido="Experiencia Zafirocurricular"
        )
        return documento

    @staticmethod
    def pdf_sintetico(texto="Experiencia Zafirocurricular"):
        salida = BytesIO()
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
        escritor.write(salida)
        return salida.getvalue()

    @staticmethod
    def docx_sintetico(texto="Experiencia Docx Sintetica"):
        documento = Document()
        documento.add_paragraph(texto)
        salida = BytesIO()
        documento.save(salida)
        return salida.getvalue()

    def test_busqueda_incluye_contenido_cv_y_aisla_organizacion(self):
        self.crear_documento(self.candidato)
        self.crear_documento(self.candidato_ajeno)
        self.client.force_login(self.usuario)

        respuesta = self.client.get(
            reverse("talento_candidatos"), {"q": "Zafirocurricular"}
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, self.candidato.nombre)
        self.assertNotContains(respuesta, self.candidato_ajeno.nombre)

    def test_busqueda_acepta_terminos_fragmentados(self):
        documento = self.crear_documento(self.candidato)
        DocumentoCandidato.objects.filter(pk=documento.pk).update(
            texto_extraido="Subgerente de Proye ctos"
        )
        self.client.force_login(self.usuario)

        respuesta = self.client.get(
            reverse("talento_candidatos"), {"q": "Proyectos"}
        )

        self.assertContains(respuesta, self.candidato.nombre)

    def test_listado_pagina_20_conserva_busqueda(self):
        Candidato.objects.bulk_create([
            Candidato(
                organizacion=self.organizacion_a,
                nombre=f"Candidato {numero:02d}",
            )
            for numero in range(21)
        ])
        self.client.force_login(self.usuario)

        respuesta = self.client.get(
            reverse("talento_candidatos"), {"q": "Candidato", "pagina": 2}
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(len(respuesta.context["pagina_candidatos"]), 2)
        self.assertContains(respuesta, "q=Candidato&pagina=1")

    def test_ficha_muestra_documento_descargable_autorizado(self):
        documento = self.crear_documento(self.candidato)
        self.client.force_login(self.usuario)

        respuesta = self.client.get(
            reverse("talento_detalle_candidato", args=[self.candidato.pk])
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, self.candidato.nombre)
        self.assertContains(respuesta, reverse(
            "descargar_documento_candidato", args=[documento.pk]
        ))

    def test_ficha_no_expone_candidato_ajeno(self):
        self.client.force_login(self.usuario)
        respuesta = self.client.get(
            reverse("talento_detalle_candidato", args=[self.candidato_ajeno.pk])
        )
        self.assertEqual(respuesta.status_code, 404)

    def test_listado_rechaza_falta_de_permiso(self):
        self.client.force_login(self.usuario_sin_permisos)
        respuesta = self.client.get(reverse("talento_candidatos"))
        self.assertEqual(respuesta.status_code, 403)

    def test_membresia_inactiva_bloquea_listado_y_ficha(self):
        membresia = Membresia.objects.get(usuario=self.usuario)
        membresia.activa = False
        membresia.save(update_fields=("activa",))
        self.client.force_login(self.usuario)

        self.assertEqual(
            self.client.get(reverse("talento_candidatos")).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(
                reverse("talento_detalle_candidato", args=[self.candidato.pk])
            ).status_code,
            403,
        )

    def test_crea_candidato_y_extrae_cv_pdf(self):
        self.client.force_login(self.usuario)
        respuesta = self.client.post(
            reverse("talento_nuevo_candidato"),
            {
                "organizacion": self.organizacion_a.pk,
                "nombre": "Nuevo Candidato PDF",
                "profesion": "Analista",
                "fuente": Candidato.Fuente.OTRO,
                "estado": Candidato.Estado.DISPONIBLE,
                "activo": "on",
                "cv": SimpleUploadedFile(
                    "perfil.pdf",
                    self.pdf_sintetico(),
                    content_type="application/pdf",
                ),
            },
        )
        self.assertEqual(respuesta.status_code, 302)
        ficha = self.client.get(respuesta.url)
        self.assertContains(ficha, "Candidato creado correctamente.")
        candidato = Candidato.objects.get(nombre="Nuevo Candidato PDF")
        documento = candidato.documentos.get()
        self.assertEqual(documento.tipo, DocumentoCandidato.Tipo.CURRICULUM)
        self.assertEqual(documento.estado_extraccion, DocumentoCandidato.EstadoExtraccion.EXTRAIDO)

    def test_crea_candidato_y_extrae_cv_docx(self):
        self.client.force_login(self.usuario)
        respuesta = self.client.post(
            reverse("talento_nuevo_candidato"),
            {
                "organizacion": self.organizacion_a.pk,
                "nombre": "Nuevo Candidato DOCX",
                "fuente": Candidato.Fuente.OTRO,
                "estado": Candidato.Estado.DISPONIBLE,
                "activo": "on",
                "cv": SimpleUploadedFile(
                    "perfil.docx",
                    self.docx_sintetico(),
                    content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                ),
            },
        )
        self.assertEqual(respuesta.status_code, 302)
        documento = DocumentoCandidato.objects.get(
            candidato__nombre="Nuevo Candidato DOCX"
        )
        self.assertEqual(documento.estado_extraccion, DocumentoCandidato.EstadoExtraccion.EXTRAIDO)
        self.assertIn("Docx Sintetica", documento.texto_extraido)

    def test_formulario_invalido_conserva_datos_y_no_crea_candidato(self):
        self.client.force_login(self.usuario)
        respuesta = self.client.post(
            reverse("talento_nuevo_candidato"),
            {
                "organizacion": self.organizacion_a.pk,
                "nombre": "Candidato Inválido",
                "email": "correo-no-valido",
                "fuente": Candidato.Fuente.OTRO,
                "estado": Candidato.Estado.DISPONIBLE,
            },
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Candidato Inválido")
        self.assertFalse(Candidato.objects.filter(nombre="Candidato Inválido").exists())

    def test_archivo_no_valido_no_crea_candidato(self):
        self.client.force_login(self.usuario)
        respuesta = self.client.post(
            reverse("talento_nuevo_candidato"),
            {
                "organizacion": self.organizacion_a.pk,
                "nombre": "Candidato Archivo Inválido",
                "fuente": Candidato.Fuente.OTRO,
                "estado": Candidato.Estado.DISPONIBLE,
                "cv": SimpleUploadedFile("perfil.exe", b"no", content_type="application/octet-stream"),
            },
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(Candidato.objects.filter(nombre="Candidato Archivo Inválido").exists())

    def test_no_puede_crear_en_otra_organizacion(self):
        self.client.force_login(self.usuario)
        respuesta = self.client.post(
            reverse("talento_nuevo_candidato"),
            {
                "organizacion": self.organizacion_b.pk,
                "nombre": "Candidato Ajeno",
                "fuente": Candidato.Fuente.OTRO,
                "estado": Candidato.Estado.DISPONIBLE,
            },
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(Candidato.objects.filter(nombre="Candidato Ajeno").exists())

    def test_usuario_sin_permiso_no_puede_crear(self):
        self.client.force_login(self.usuario_sin_permisos)
        respuesta = self.client.get(reverse("talento_nuevo_candidato"))
        self.assertEqual(respuesta.status_code, 403)

    def test_csrf_bloquea_post_sin_token(self):
        from django.test import Client

        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.usuario)
        respuesta = cliente.post(
            reverse("talento_nuevo_candidato"),
            {"nombre": "Candidato CSRF"},
        )
        self.assertEqual(respuesta.status_code, 403)
