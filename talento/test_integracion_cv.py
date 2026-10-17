from io import BytesIO
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib import admin
from django.contrib.auth.models import Permission
from django.contrib.messages import get_messages
from django.core.exceptions import PermissionDenied
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import RequestFactory, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from docx import Document
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

from core.models import Membresia, Organizacion
from talento.models import Candidato, DocumentoCandidato


class ExtraccionPDFFallbackTests(TestCase):
    def test_pdf_con_layout_vacio_usa_extraccion_estandar(self):
        pagina = type("PaginaSintetica", (), {
            "get_contents": lambda self: object(),
            "extract_text": lambda self, **kwargs: (
                "" if kwargs.get("extraction_mode") == "layout"
                else "Texto sintetico recuperable"
            ),
        })()
        lector = type("LectorSintetico", (), {"pages": [pagina]})()

        with patch("talento.extraccion_cv.PdfReader", return_value=lector):
            from talento.extraccion_cv import extraer_texto_pdf

            resultado = extraer_texto_pdf(BytesIO(b"%PDF-1.4 sintetico"))

        self.assertEqual(resultado, "Texto sintetico recuperable")


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


def crear_pdf_sin_texto():
    escritor = PdfWriter()
    escritor.add_blank_page(width=612, height=792)
    salida = BytesIO()
    escritor.write(salida)
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
                "change_documentocandidato",
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
        self.assertEqual(
            documento.estado_extraccion, DocumentoCandidato.EstadoExtraccion.EXTRAIDO
        )
        self.assertEqual(documento.archivo.storage.location, self.media_root)
        self.assertTrue(documento.archivo.storage.exists(documento.archivo.name))

        respuesta = self.client.get(url_busqueda, {"q": palabra})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(list(respuesta.context["cl"].queryset), [self.candidato])

        url_descarga = reverse("descargar_documento_candidato", args=[documento.pk])
        respuesta = self.client.get(url_descarga)
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(b"".join(respuesta.streaming_content), contenido)
        # El cliente cierra la respuesta al agotar el stream. Cerrarla otra vez
        # emite request_finished y cierra la conexión de la transacción del test.
        self.assertTrue(respuesta.closed)

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

    def comprobar_reemplazo_cv(self, extension, generar, tipo_mime):
        anterior = "Ambarcurricular"
        nueva = "Rubicurricular"
        url_busqueda = reverse("admin:talento_candidato_changelist")
        self.client.force_login(self.administrador)
        datos = {
            "candidato": self.candidato.pk,
            "tipo": DocumentoCandidato.Tipo.CURRICULUM,
            "nombre": "Curriculum sintetico",
            "vigente": "on",
            "es_cv_principal": "on",
            "_save": "Guardar",
        }
        contenido_anterior = generar(f"Experiencia {anterior}")
        contenido_nuevo = generar(f"Experiencia {nueva}")

        def subir(url, contenido):
            # El mismo nombre original también debe permitir renovar el texto.
            return self.client.post(url, {
                **datos,
                "archivo": SimpleUploadedFile(
                    f"perfil.{extension}", contenido, content_type=tipo_mime
                ),
            })

        def comprobar_busqueda(palabra, esperados):
            respuesta = self.client.get(url_busqueda, {"q": palabra})
            self.assertEqual(respuesta.status_code, 200)
            self.assertEqual(list(respuesta.context["cl"].queryset), esperados)

        respuesta = subir(
            reverse("admin:talento_documentocandidato_add"), contenido_anterior
        )
        self.assertEqual(respuesta.status_code, 302)
        documento = DocumentoCandidato.objects.get(candidato=self.candidato)
        self.assertIn(anterior, documento.texto_extraido)
        self.assertNotIn(nueva, documento.texto_extraido)
        comprobar_busqueda(anterior, [self.candidato])
        comprobar_busqueda(nueva, [])

        self.client.force_login(self.administrador_ajeno)
        comprobar_busqueda(anterior, [])
        url_descarga = reverse("descargar_documento_candidato", args=[documento.pk])
        self.assertEqual(self.client.get(url_descarga).status_code, 403)

        self.client.force_login(self.administrador)
        respuesta = subir(
            reverse("admin:talento_documentocandidato_change", args=[documento.pk]),
            contenido_nuevo,
        )
        self.assertEqual(respuesta.status_code, 302)
        documento.refresh_from_db()
        self.assertEqual(DocumentoCandidato.objects.count(), 1)
        self.assertIn(nueva, documento.texto_extraido)
        self.assertEqual(
            documento.estado_extraccion, DocumentoCandidato.EstadoExtraccion.EXTRAIDO
        )
        self.assertNotIn(anterior, documento.texto_extraido)
        comprobar_busqueda(nueva, [self.candidato])
        comprobar_busqueda(anterior, [])

        respuesta = self.client.get(url_descarga)
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(b"".join(respuesta.streaming_content), contenido_nuevo)
        self.assertTrue(respuesta.closed)

        self.client.force_login(self.administrador_ajeno)
        comprobar_busqueda(nueva, [])
        comprobar_busqueda(anterior, [])
        respuesta = self.client.get(url_descarga)
        self.assertEqual(respuesta.status_code, 403)
        self.assertFalse(respuesta.streaming)

    def test_reemplazo_pdf_actualiza_texto_busqueda_y_aislamiento(self):
        self.comprobar_reemplazo_cv("pdf", crear_pdf, "application/pdf")

    def test_reemplazo_docx_actualiza_texto_busqueda_y_aislamiento(self):
        self.comprobar_reemplazo_cv(
            "docx",
            crear_docx,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

    def guardar_documento_http(self, tipo, archivo=None, documento=None):
        self.client.force_login(self.administrador)
        datos = {
            "candidato": self.candidato.pk,
            "tipo": tipo,
            "nombre": "Documento sintetico",
            "vigente": "on",
            "_save": "Guardar",
        }
        if archivo is not None:
            datos["archivo"] = archivo
        if documento is None:
            url = reverse("admin:talento_documentocandidato_add")
        else:
            url = reverse(
                "admin:talento_documentocandidato_change", args=[documento.pk]
            )
        respuesta = self.client.post(url, datos)
        self.assertEqual(respuesta.status_code, 302)
        guardado = DocumentoCandidato.objects.get(candidato=self.candidato)
        if documento is not None:
            self.assertEqual(guardado.pk, documento.pk)
        self.assertEqual(DocumentoCandidato.objects.count(), 1)
        self.assertEqual(guardado.tipo, tipo)
        return guardado

    def comprobar_estado_y_aislamiento(self, documento, palabra, visible, contenido):
        documento.refresh_from_db()
        if visible:
            self.assertIn(palabra, documento.texto_extraido)
            self.assertEqual(
                documento.estado_extraccion,
                DocumentoCandidato.EstadoExtraccion.EXTRAIDO,
            )
        else:
            self.assertEqual(documento.texto_extraido, "")
        self.assertEqual(documento.archivo.storage.location, self.media_root)
        for usuario, esperados in (
            (self.administrador, [self.candidato] if visible else []),
            (self.administrador_ajeno, []),
        ):
            self.client.force_login(usuario)
            respuesta = self.client.get(
                reverse("admin:talento_candidato_changelist"), {"q": palabra}
            )
            self.assertEqual(respuesta.status_code, 200)
            self.assertEqual(list(respuesta.context["cl"].queryset), esperados)
            respuesta = self.client.get(reverse(
                "descargar_documento_candidato", args=[documento.pk]
            ))
            if usuario == self.administrador:
                self.assertEqual(respuesta.status_code, 200)
                self.assertEqual(b"".join(respuesta.streaming_content), contenido)
            else:
                self.assertEqual(respuesta.status_code, 403)
                self.assertFalse(respuesta.streaming)
            self.assertTrue(respuesta.closed)

    def comprobar_reemplazo_sin_texto(
        self, extension, generar, contenido_nuevo, estado_esperado
    ):
        palabra = "Esmeraldacurricular"
        contenido_anterior = generar(f"Experiencia {palabra}")
        documento = self.guardar_documento_http(
            DocumentoCandidato.Tipo.CURRICULUM,
            SimpleUploadedFile(f"perfil.{extension}", contenido_anterior),
        )
        self.comprobar_estado_y_aislamiento(
            documento, palabra, True, contenido_anterior
        )
        documento = self.guardar_documento_http(
            DocumentoCandidato.Tipo.CURRICULUM,
            SimpleUploadedFile(f"perfil.{extension}", contenido_nuevo),
            documento,
        )
        self.comprobar_estado_y_aislamiento(
            documento, palabra, False, contenido_nuevo
        )
        self.assertEqual(documento.estado_extraccion, estado_esperado)

    def test_reemplazo_pdf_danado_borra_texto_y_busqueda(self):
        self.comprobar_reemplazo_sin_texto(
            "pdf", crear_pdf, b"%PDF-1.4\narchivo sintetico truncado",
            DocumentoCandidato.EstadoExtraccion.ERROR,
        )

    def test_reemplazo_docx_danado_borra_texto_y_busqueda(self):
        self.comprobar_reemplazo_sin_texto(
            "docx", crear_docx, b"PK\x03\x04archivo sintetico truncado",
            DocumentoCandidato.EstadoExtraccion.ERROR,
        )

    def test_reemplazo_pdf_sin_texto_borra_texto_y_busqueda(self):
        self.comprobar_reemplazo_sin_texto(
            "pdf", crear_pdf, crear_pdf_sin_texto(),
            DocumentoCandidato.EstadoExtraccion.SIN_TEXTO,
        )

    def comprobar_cambios_tipo(self, extension, generar):
        palabra = "Topaciocurricular"
        contenido = generar(f"Experiencia {palabra}")
        # Un documento de otro tipo no se indexa aunque su archivo contenga texto.
        documento = self.guardar_documento_http(
            DocumentoCandidato.Tipo.OTRO,
            SimpleUploadedFile(f"perfil.{extension}", contenido),
        )
        self.comprobar_estado_y_aislamiento(documento, palabra, False, contenido)
        self.assertEqual(
            documento.estado_extraccion, DocumentoCandidato.EstadoExtraccion.NO_APLICA
        )
        nombre_archivo = documento.archivo.name
        for tipo, visible in (
            (DocumentoCandidato.Tipo.CURRICULUM, True),
            (DocumentoCandidato.Tipo.OTRO, False),
            (DocumentoCandidato.Tipo.CURRICULUM, True),
        ):
            with self.subTest(tipo=tipo, visible=visible):
                # Cambiar solo el tipo debe extraer o limpiar el texto persistido.
                documento = self.guardar_documento_http(tipo, documento=documento)
                self.assertEqual(documento.archivo.name, nombre_archivo)
                self.comprobar_estado_y_aislamiento(
                    documento, palabra, visible, contenido
                )
                if not visible:
                    self.assertEqual(
                        documento.estado_extraccion,
                        DocumentoCandidato.EstadoExtraccion.NO_APLICA,
                    )

    def test_cambios_tipo_pdf_actualizan_texto_y_busqueda(self):
        self.comprobar_cambios_tipo("pdf", crear_pdf)

    def test_cambios_tipo_docx_actualizan_texto_y_busqueda(self):
        self.comprobar_cambios_tipo("docx", crear_docx)

    def test_estado_visible_solo_lectura_y_filtro_aislado(self):
        documento = self.guardar_documento_http(
            DocumentoCandidato.Tipo.CURRICULUM,
            SimpleUploadedFile("perfil.pdf", crear_pdf("Perfil sintetico")),
        )
        url = reverse("admin:talento_documentocandidato_changelist")
        for usuario, esperados in (
            (self.administrador, [documento]),
            (self.administrador_ajeno, []),
        ):
            self.client.force_login(usuario)
            respuesta = self.client.get(url, {"estado_extraccion__exact": "extraido"})
            self.assertEqual(respuesta.status_code, 200)
            self.assertEqual(list(respuesta.context["cl"].queryset), esperados)
            self.assertContains(respuesta, "Texto extraído")
            self.assertContains(respuesta, "Estado de extracción de texto")
        self.client.force_login(self.administrador)
        respuesta = self.client.get(reverse(
            "admin:talento_documentocandidato_change", args=[documento.pk]
        ))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Texto extraído")
        self.assertNotIn("estado_extraccion", respuesta.context["adminform"].form.fields)
        respuesta = self.client.get(url, {"estado_extraccion__exact": "error"})
        self.assertEqual(list(respuesta.context["cl"].queryset), [])

    def test_error_de_almacenamiento_limpia_texto_sin_exponer_excepcion(self):
        documento = self.guardar_documento_http(
            DocumentoCandidato.Tipo.CURRICULUM,
            SimpleUploadedFile("perfil.pdf", crear_pdf("Palabraanterior")),
        )
        with patch(
            "django.core.files.storage.FileSystemStorage.open",
            side_effect=OSError("detalle tecnico privado"),
        ):
            documento.archivo = SimpleUploadedFile("nuevo.pdf", crear_pdf("Nuevo"))
            documento.save(update_fields=["archivo"])
        documento.refresh_from_db()
        self.assertEqual(documento.texto_extraido, "")
        self.assertEqual(documento.estado_extraccion, "error")
        self.client.force_login(self.administrador)
        respuesta = self.client.get(reverse(
            "admin:talento_documentocandidato_change", args=[documento.pk]
        ))
        self.assertContains(respuesta, "Error de lectura")
        self.assertNotContains(respuesta, "detalle tecnico privado")

    def test_edicion_de_metadatos_no_reprocesa_documento_pendiente(self):
        documento = self.guardar_documento_http(
            DocumentoCandidato.Tipo.CURRICULUM,
            SimpleUploadedFile("perfil.pdf", crear_pdf("Sintetico")),
        )
        DocumentoCandidato.objects.filter(pk=documento.pk).update(
            estado_extraccion="pendiente", texto_extraido=""
        )
        documento.refresh_from_db()
        with patch("talento.extraccion_cv.extraer_texto_cv") as extraer:
            documento.nombre = "Nombre actualizado"
            documento.save(update_fields=["nombre"])
        extraer.assert_not_called()
        documento.refresh_from_db()
        self.assertEqual(documento.estado_extraccion, "pendiente")


    def crear_documento_pendiente(self, contenido, extension="pdf", **campos):
        documento = DocumentoCandidato.objects.create(
            candidato=campos.pop("candidato", self.candidato),
            tipo=campos.pop("tipo", DocumentoCandidato.Tipo.CURRICULUM),
            nombre="Documento sintetico", archivo=SimpleUploadedFile(
                f"perfil.{extension}", contenido
            ), **campos,
        )
        DocumentoCandidato.objects.filter(pk=documento.pk).update(
            texto_extraido="Textoanterior", estado_extraccion="pendiente"
        )
        documento.refresh_from_db()
        return documento

    def test_accion_extrae_solo_cvs_seleccionados_y_resume_sin_exponer_contenido(self):
        pdf = self.crear_documento_pendiente(crear_pdf("Palabrasecreta"))
        docx = self.crear_documento_pendiente(crear_docx("Palabrasecreta"), "docx")
        vacio = self.crear_documento_pendiente(crear_pdf_sin_texto())
        danado = self.crear_documento_pendiente(b"%PDF-1.4\ntruncado sintetico")
        otro = self.crear_documento_pendiente(
            crear_pdf("Palabrasecreta"), tipo=DocumentoCandidato.Tipo.OTRO
        )
        ajeno = self.crear_documento_pendiente(
            crear_pdf("Palabrasecreta"), candidato=self.candidato_ajeno
        )
        no_seleccionado = self.crear_documento_pendiente(crear_pdf("Palabrasecreta"))
        seleccionados = [pdf, docx, vacio, danado, otro, ajeno]
        todos = seleccionados + [no_seleccionado]
        originales = {}
        for documento in todos:
            with documento.archivo.open("rb") as archivo:
                originales[documento.pk] = (documento.archivo.name, archivo.read())
        self.client.force_login(self.administrador)
        respuesta = self.client.post(
            reverse("admin:talento_documentocandidato_changelist"),
            {"action": "extraer_texto_cvs", "index": "0",
             "_selected_action": [documento.pk for documento in seleccionados]},
        )
        self.assertEqual(respuesta.status_code, 302)
        mensajes = " ".join(str(m) for m in get_messages(respuesta.wsgi_request))
        # Django elimina del queryset de la acción la selección de otra organización.
        self.assertIn("Procesados: 4. Sin texto: 1. Con error: 1. Omitidos: 1.", mensajes)
        self.assertNotIn("Palabrasecreta", mensajes)
        self.assertNotIn("truncado", mensajes)
        for documento, estado in (
            (pdf, "extraido"), (docx, "extraido"),
            (vacio, "sin_texto"), (danado, "error"),
        ):
            documento.refresh_from_db()
            self.assertEqual(documento.estado_extraccion, estado)
            if estado == "extraido":
                self.assertIn("Palabrasecreta", documento.texto_extraido)
            else:
                self.assertEqual(documento.texto_extraido, "")
            self.assertNotIn("Textoanterior", documento.texto_extraido)
        for documento in (otro, ajeno, no_seleccionado):
            documento.refresh_from_db()
            self.assertEqual(documento.estado_extraccion, "pendiente")
            self.assertEqual(documento.texto_extraido, "Textoanterior")
        for documento in todos:
            documento.refresh_from_db()
            self.assertEqual(documento.archivo.name, originales[documento.pk][0])
            with documento.archivo.open("rb") as archivo:
                self.assertEqual(archivo.read(), originales[documento.pk][1])

    def test_accion_directa_no_lee_documentos_ajenos(self):
        documento = self.crear_documento_pendiente(
            crear_pdf("Sintetico"), candidato=self.candidato_ajeno
        )
        request = RequestFactory().post("/admin/")
        request.user = self.administrador
        administracion = admin.site._registry[DocumentoCandidato]
        with patch.object(administracion, "message_user") as mensaje, patch(
            "talento.models.DocumentoCandidato.extraer_texto"
        ) as extraer:
            administracion.extraer_texto_cvs(
                request, DocumentoCandidato.objects.filter(pk=documento.pk)
            )
        extraer.assert_not_called()
        self.assertIn("Omitidos: 1", mensaje.call_args.args[1])
        documento.refresh_from_db()
        self.assertEqual(documento.estado_extraccion, "pendiente")

    def test_accion_sin_permiso_de_cambio_no_procesa(self):
        documento = self.crear_documento_pendiente(crear_pdf("Sintetico"))
        self.administrador.user_permissions.remove(Permission.objects.get(
            content_type__app_label="talento", codename="change_documentocandidato"
        ))
        self.client.force_login(self.administrador)
        with patch("talento.models.DocumentoCandidato.extraer_texto") as extraer:
            respuesta = self.client.get(reverse("admin:talento_documentocandidato_changelist"))
            self.assertEqual(respuesta.status_code, 200)
            self.assertNotContains(respuesta, "Extraer texto de los CV seleccionados")
            self.client.post(
                reverse("admin:talento_documentocandidato_changelist"),
                {"action": "extraer_texto_cvs", "_selected_action": [documento.pk]},
            )
        extraer.assert_not_called()
        documento.refresh_from_db()
        self.assertEqual(documento.estado_extraccion, "pendiente")

    def test_accion_colaborador_con_permiso_django_no_puede_modificar(self):
        documento = self.crear_documento_pendiente(crear_pdf("Sintetico"))
        membresia = Membresia.objects.get(usuario=self.administrador)
        membresia.rol = Membresia.Rol.COLABORADOR
        membresia.save()
        request = RequestFactory().post("/admin/")
        request.user = self.administrador
        administracion = admin.site._registry[DocumentoCandidato]
        with patch("talento.models.DocumentoCandidato.extraer_texto") as extraer:
            self.assertNotIn("extraer_texto_cvs", administracion.get_actions(request))
            with self.assertRaises(PermissionDenied):
                administracion.extraer_texto_cvs(
                    request, DocumentoCandidato.objects.filter(pk=documento.pk)
                )
        extraer.assert_not_called()


class MigracionEstadoExtraccionTests(TransactionTestCase):
    def test_documentos_anteriores_quedan_pendientes_sin_abrir_archivos(self):
        anterior = [("talento", "0005_documentocandidato_texto_extraido")]
        nueva = [("talento", "0006_documentocandidato_estado_extraccion")]
        ejecutor = MigrationExecutor(connection)
        final = ejecutor.loader.graph.leaf_nodes()
        ejecutor.migrate(anterior)
        try:
            apps = ejecutor.loader.project_state(anterior).apps
            organizacion = apps.get_model("core", "Organizacion").objects.create(
                nombre="Organizacion migracion", slug="migracion-sintetica"
            )
            candidato = apps.get_model("talento", "Candidato").objects.create(
                organizacion=organizacion, nombre="Perfil migracion"
            )
            modelo = apps.get_model("talento", "DocumentoCandidato")
            for tipo, texto in (("curriculum", ""), ("curriculum", "Texto sintetico"),
                                ("otro", "")):
                modelo.objects.create(
                    candidato=candidato, tipo=tipo, nombre="Documento sintetico",
                    archivo="sintetico-inexistente.pdf", texto_extraido=texto,
                )
            with patch(
                "django.core.files.storage.FileSystemStorage.open",
                side_effect=AssertionError("La migracion no debe abrir archivos"),
            ):
                MigrationExecutor(connection).migrate(nueva)
            self.assertEqual(
                list(DocumentoCandidato.objects.values_list("estado_extraccion", flat=True)),
                ["pendiente"] * 3,
            )
            self.assertTrue(DocumentoCandidato.objects.filter(
                texto_extraido="Texto sintetico"
            ).exists())
        finally:
            MigrationExecutor(connection).migrate(final)
