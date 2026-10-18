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
from .busqueda_asistida import resaltar_coincidencias, terminos_para_resaltado


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
                "change_candidato",
                "view_candidato",
                "add_documentocandidato",
                "change_documentocandidato",
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
            es_cv_principal=True,
        )
        DocumentoCandidato.objects.filter(pk=documento.pk).update(
            texto_extraido="Experiencia Zafirocurricular"
        )
        return documento

    def test_coincidencias_resalta_acentos_y_escapa_contenido(self):
        marcado = resaltar_coincidencias(
            "Ingeniería <script>alert('x')</script> y prevención",
            ["ingeniería", "prevención"],
        )
        self.assertIn("<mark class=\"coincidencia\">Ingeniería</mark>", marcado)
        self.assertIn("&lt;script&gt;", marcado)
        self.assertNotIn("<script>", marcado)

    def test_coincidencias_muestra_cv_autorizado_y_descarga_original(self):
        documento = self.crear_documento(self.candidato)
        self.client.force_login(self.usuario)
        respuesta = self.client.get(
            reverse("talento_coincidencias_candidato", args=[self.candidato.pk]),
            {"q": "Zafirocurricular"},
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "<mark class=\"coincidencia\">Zafirocurricular</mark>", html=True)
        self.assertContains(respuesta, reverse("descargar_documento_candidato", args=[documento.pk]))
        self.assertContains(respuesta, "No confirma capacitación, experiencia")

    def test_coincidencias_asistidas_omite_conectores(self):
        terminos = terminos_para_resaltado(
            "Busco a alguien con capacitación en AutoCAD",
            "asistida",
        )
        self.assertIn("AutoCAD", terminos)
        self.assertNotIn("busco", [termino.casefold() for termino in terminos])
        self.assertNotIn("alguien", [termino.casefold() for termino in terminos])

    def test_coincidencias_no_expone_documento_de_otra_organizacion(self):
        self.crear_documento(self.candidato_ajeno)
        self.client.force_login(self.usuario)
        respuesta = self.client.get(
            reverse("talento_coincidencias_candidato", args=[self.candidato_ajeno.pk]),
            {"q": "Zafirocurricular"},
        )
        self.assertEqual(respuesta.status_code, 404)

    def test_coincidencias_sin_texto_muestra_mensaje(self):
        documento = self.crear_documento(self.candidato)
        DocumentoCandidato.objects.filter(pk=documento.pk).update(texto_extraido="")
        self.client.force_login(self.usuario)
        respuesta = self.client.get(
            reverse("talento_coincidencias_candidato", args=[self.candidato.pk]),
            {"q": "algo"},
        )
        self.assertContains(respuesta, "no tiene texto extraído disponible")

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

    def test_filtro_individual_por_profesion(self):
        Candidato.objects.create(
            organizacion=self.organizacion_a,
            nombre="Candidato Arquitectura",
            profesion="Arquitecto",
        )
        self.client.force_login(self.usuario)

        respuesta = self.client.get(
            reverse("talento_candidatos"), {"profesion": "Arquitecto"}
        )

        self.assertContains(respuesta, "Candidato Arquitectura")
        self.assertNotContains(respuesta, "Candidato Zafiro")
        self.assertContains(respuesta, "Arquitecto")

    def test_filtros_combinados_con_texto_y_estado(self):
        Candidato.objects.create(
            organizacion=self.organizacion_a,
            nombre="Candidato Senior",
            profesion="Ingeniero civil",
            especialidad="Estructuras",
            region="Valparaíso",
            estado=Candidato.Estado.CONTRATADO,
        )
        self.client.force_login(self.usuario)

        respuesta = self.client.get(
            reverse("talento_candidatos"),
            {
                "q": "Senior",
                "profesion": "Ingeniero civil",
                "especialidad": "Estructuras",
                "region": "Valparaíso",
                "estado": Candidato.Estado.CONTRATADO,
            },
        )

        self.assertContains(respuesta, "Candidato Senior")
        self.assertNotContains(respuesta, "Candidato Zafiro")
        self.assertEqual(
            respuesta.context["parametros_filtros"],
            "q=Senior&profesion=Ingeniero+civil&especialidad=Estructuras&region=Valpara%C3%ADso&estado=contratado",
        )

    def test_opciones_y_resultados_excluyen_otra_organizacion(self):
        self.candidato_ajeno.profesion = "Profesión ajena"
        self.candidato_ajeno.especialidad = "Especialidad ajena"
        self.candidato_ajeno.region = "Región ajena"
        self.candidato_ajeno.save()
        self.client.force_login(self.usuario)

        respuesta = self.client.get(reverse("talento_candidatos"))

        self.assertNotContains(respuesta, "Candidato Rubí")
        self.assertNotContains(respuesta, "Profesión ajena")
        self.assertNotContains(respuesta, "Especialidad ajena")
        self.assertNotContains(respuesta, "Región ajena")

    def test_valor_invalido_se_ignora_y_no_amplia_resultados(self):
        self.client.force_login(self.usuario)

        respuesta = self.client.get(
            reverse("talento_candidatos"), {"profesion": "No autorizada"}
        )

        self.assertContains(respuesta, self.candidato.nombre)
        self.assertNotContains(respuesta, "No autorizada")

    def test_filtros_conservan_total_y_parametros_en_paginacion(self):
        Candidato.objects.bulk_create([
            Candidato(
                organizacion=self.organizacion_a,
                nombre=f"Ingeniero {numero:02d}",
                profesion="Ingeniero civil",
            )
            for numero in range(21)
        ])
        self.client.force_login(self.usuario)

        respuesta = self.client.get(
            reverse("talento_candidatos"),
            {"profesion": "Ingeniero civil", "pagina": 2},
        )

        self.assertEqual(respuesta.context["total_resultados"], 22)
        self.assertEqual(len(respuesta.context["pagina_candidatos"]), 2)
        self.assertContains(respuesta, "profesion=Ingeniero+civil&pagina=1")

    def test_limpiar_elimina_todos_los_filtros(self):
        self.client.force_login(self.usuario)
        respuesta = self.client.get(
            reverse("talento_candidatos"),
            {"q": "Zafiro", "profesion": "Ingeniero civil"},
        )
        self.assertContains(respuesta, "Limpiar")
        self.assertContains(respuesta, "(1)")

    def datos_edicion(self, **extras):
        datos = {
            "organizacion": self.organizacion_a.pk,
            "nombre": "Candidato actualizado",
            "fuente": Candidato.Fuente.OTRO,
            "estado": Candidato.Estado.DISPONIBLE,
            "activo": "on",
        }
        datos.update(extras)
        return datos

    def test_edita_candidato_sin_cv_y_conserva_documento(self):
        documento = self.crear_documento(self.candidato)
        documento.refresh_from_db()
        texto_anterior = documento.texto_extraido
        self.client.force_login(self.usuario)

        respuesta = self.client.post(
            reverse("talento_editar_candidato", args=[self.candidato.pk]),
            self.datos_edicion(),
        )

        self.assertEqual(respuesta.status_code, 302)
        self.candidato.refresh_from_db()
        documento.refresh_from_db()
        self.assertEqual(self.candidato.nombre, "Candidato actualizado")
        self.assertEqual(documento.texto_extraido, texto_anterior)

    def test_reemplaza_cv_principal_actualiza_busqueda_y_descarga(self):
        documento = self.crear_documento(self.candidato)
        documento_pk = documento.pk
        DocumentoCandidato.objects.filter(pk=documento.pk).update(
            texto_extraido="PalabraAntigua"
        )
        self.client.force_login(self.usuario)

        respuesta = self.client.post(
            reverse("talento_editar_candidato", args=[self.candidato.pk]),
            self.datos_edicion(
                cv=SimpleUploadedFile(
                    "nuevo.pdf",
                    self.pdf_sintetico("PalabraNueva"),
                    content_type="application/pdf",
                )
            ),
        )

        self.assertEqual(respuesta.status_code, 302)
        documento.refresh_from_db()
        self.assertEqual(documento.pk, documento_pk)
        self.assertIn("PalabraNueva", documento.texto_extraido)
        resultados_nuevos = self.client.get(
            reverse("talento_candidatos"), {"q": "PalabraNueva"}
        )
        resultados_antiguos = self.client.get(
            reverse("talento_candidatos"), {"q": "PalabraAntigua"}
        )
        self.assertContains(resultados_nuevos, "Candidato actualizado")
        self.assertNotContains(resultados_antiguos, "Candidato actualizado")
        descarga = self.client.get(
            reverse("descargar_documento_candidato", args=[documento.pk])
        )
        self.assertEqual(descarga.status_code, 200)
        self.assertIn(b"PalabraNueva", b"".join(descarga.streaming_content))

    def test_reemplaza_solo_cv_principal_y_conserva_otros_documentos(self):
        principal = self.crear_documento(self.candidato)
        secundario = DocumentoCandidato.objects.create(
            candidato=self.candidato,
            tipo=DocumentoCandidato.Tipo.CURRICULUM,
            nombre="CV secundario",
            archivo=SimpleUploadedFile("secundario.pdf", b"secundario"),
            es_cv_principal=False,
        )
        self.client.force_login(self.usuario)

        self.client.post(
            reverse("talento_editar_candidato", args=[self.candidato.pk]),
            self.datos_edicion(
                cv=SimpleUploadedFile(
                    "reemplazo.pdf",
                    self.pdf_sintetico("CVPrincipalNuevo"),
                    content_type="application/pdf",
                )
            ),
        )

        principal.refresh_from_db()
        secundario.refresh_from_db()
        self.assertIn("CVPrincipalNuevo", principal.texto_extraido)
        self.assertEqual(secundario.nombre, "CV secundario")
        self.assertTrue(secundario.archivo.name)

    def test_edicion_rechaza_archivo_invalido_sin_cambios(self):
        self.client.force_login(self.usuario)
        nombre_anterior = self.candidato.nombre
        respuesta = self.client.post(
            reverse("talento_editar_candidato", args=[self.candidato.pk]),
            self.datos_edicion(
                nombre="Nombre no guardado",
                cv=SimpleUploadedFile("invalido.exe", b"no"),
            ),
        )
        self.assertEqual(respuesta.status_code, 200)
        self.candidato.refresh_from_db()
        self.assertEqual(self.candidato.nombre, nombre_anterior)

    def test_usuario_ajeno_no_puede_editar_candidato(self):
        self.client.force_login(self.usuario_ajeno)
        respuesta = self.client.get(
            reverse("talento_editar_candidato", args=[self.candidato.pk])
        )
        self.assertEqual(respuesta.status_code, 404)

    def test_usuario_sin_permiso_no_ve_boton_editar(self):
        self.client.force_login(self.usuario_sin_permisos)
        respuesta = self.client.get(reverse("talento_candidatos"))
        self.assertEqual(respuesta.status_code, 403)

    def test_reproduccion_cv_antiguo_sin_principal_sigue_en_busqueda(self):
        antiguo = self.crear_documento(self.candidato)
        antiguo.es_cv_principal = False
        antiguo.save(update_fields=("es_cv_principal",))
        self.client.force_login(self.usuario)

        respuesta = self.client.post(
            reverse("talento_editar_candidato", args=[self.candidato.pk]),
            self.datos_edicion(
                cv=SimpleUploadedFile(
                    "nuevo.pdf",
                    self.pdf_sintetico("PalabraNueva"),
                    content_type="application/pdf",
                )
            ),
        )

        self.assertEqual(respuesta.status_code, 302)
        antiguos = self.client.get(
            reverse("talento_candidatos"), {"q": "Zafirocurricular"}
        )
        self.assertNotContains(antiguos, "Candidato actualizado")
        antiguo.refresh_from_db()
        self.assertFalse(antiguo.vigente)

        nuevos = self.client.get(
            reverse("talento_candidatos"), {"q": "PalabraNueva"}
        )
        self.assertContains(nuevos, "Candidato actualizado")

    def test_reproduccion_creacion_cv_sin_permiso_documental(self):
        Usuario = get_user_model()
        usuario = Usuario.objects.get(pk=self.usuario.pk)
        usuario.user_permissions.remove(*Permission.objects.filter(
            content_type__app_label="talento",
            codename__in=(
                "add_documentocandidato",
                "change_documentocandidato",
            ),
        ))
        self.client.force_login(usuario)

        respuesta = self.client.post(
            reverse("talento_nuevo_candidato"),
            {
                "organizacion": self.organizacion_a.pk,
                "nombre": "CV Sin Permiso",
                "fuente": Candidato.Fuente.OTRO,
                "estado": Candidato.Estado.DISPONIBLE,
                "cv": SimpleUploadedFile(
                    "sin-permiso.pdf",
                    self.pdf_sintetico("SinPermiso"),
                    content_type="application/pdf",
                ),
            },
        )

        self.assertEqual(respuesta.status_code, 403)
        self.assertFalse(Candidato.objects.filter(nombre="CV Sin Permiso").exists())

    def test_reemplazo_sin_change_documento_no_modifica_nada(self):
        documento = self.crear_documento(self.candidato)
        nombre_anterior = self.candidato.nombre
        usuario = get_user_model().objects.get(pk=self.usuario.pk)
        usuario.user_permissions.remove(Permission.objects.get(
            content_type__app_label="talento",
            codename="change_documentocandidato",
        ))
        usuario = get_user_model().objects.get(pk=self.usuario.pk)
        self.client.force_login(usuario)

        respuesta = self.client.post(
            reverse("talento_editar_candidato", args=[self.candidato.pk]),
            self.datos_edicion(
                nombre="No debe guardarse",
                cv=SimpleUploadedFile(
                    "sin-cambio.pdf",
                    self.pdf_sintetico("NoDebeGuardar"),
                    content_type="application/pdf",
                ),
            ),
        )

        self.assertEqual(respuesta.status_code, 403)
        self.candidato.refresh_from_db()
        documento.refresh_from_db()
        self.assertEqual(self.candidato.nombre, nombre_anterior)
        self.assertNotIn("NoDebeGuardar", documento.texto_extraido)

    def antecedentes_datos(self, **extra):
        contenido = extra.pop("contenido", "Antecedente sintetico")
        datos = {
            "nombre": "Título sintético",
            "tipo": DocumentoCandidato.Tipo.TITULO,
            "observaciones": "Documento emitido para pruebas.",
            "archivo": SimpleUploadedFile(
                "titulo.pdf",
                self.pdf_sintetico(contenido),
                content_type="application/pdf",
            ),
        }
        datos.update(extra)
        return datos

    def test_agrega_antecedente_clasificado_y_no_reemplaza_cv(self):
        cv = self.crear_documento(self.candidato)
        self.client.force_login(self.usuario)

        respuesta = self.client.post(
            reverse("talento_agregar_antecedente", args=[self.candidato.pk]),
            self.antecedentes_datos(),
        )

        self.assertEqual(respuesta.status_code, 302)
        antecedente = self.candidato.documentos.get(tipo=DocumentoCandidato.Tipo.TITULO)
        self.assertFalse(antecedente.es_cv_principal)
        self.assertEqual(antecedente.estado_extraccion, DocumentoCandidato.EstadoExtraccion.NO_APLICA)
        self.assertEqual(antecedente.agregado_por, self.usuario)
        self.assertIsNotNone(antecedente.creado_en)
        cv.refresh_from_db()
        self.assertTrue(cv.es_cv_principal)
        self.assertEqual(self.candidato.documentos.count(), 2)

    def test_antecedente_acepta_clasificaciones_y_rechaza_evaluacion(self):
        self.client.force_login(self.usuario)
        for tipo in (
            DocumentoCandidato.Tipo.CAPACITACION,
            DocumentoCandidato.Tipo.CERTIFICACION,
            DocumentoCandidato.Tipo.RECOMENDACION,
            DocumentoCandidato.Tipo.EXPERIENCIA,
            DocumentoCandidato.Tipo.OTRO,
        ):
            respuesta = self.client.post(
                reverse("talento_agregar_antecedente", args=[self.candidato.pk]),
                self.antecedentes_datos(
                    tipo=tipo,
                    nombre=f"Antecedente {tipo}",
                    contenido=f"Antecedente {tipo}",
                ),
            )
            self.assertEqual(respuesta.status_code, 302)
        respuesta = self.client.post(
            reverse("talento_agregar_antecedente", args=[self.candidato.pk]),
            self.antecedentes_datos(tipo=DocumentoCandidato.Tipo.EVALUACION),
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Escoja una opción válida")
        self.assertFalse(self.candidato.documentos.filter(tipo=DocumentoCandidato.Tipo.EVALUACION).exists())

    def test_antecedente_rechaza_duplicado_por_hash(self):
        self.client.force_login(self.usuario)
        datos = self.antecedentes_datos()
        respuesta = self.client.post(
            reverse("talento_agregar_antecedente", args=[self.candidato.pk]),
            datos,
        )
        self.assertEqual(respuesta.status_code, 302)
        cantidad = self.candidato.documentos.count()
        respuesta = self.client.post(
            reverse("talento_agregar_antecedente", args=[self.candidato.pk]),
            self.antecedentes_datos(nombre="Título repetido"),
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "ya existe en el expediente")
        self.assertEqual(self.candidato.documentos.count(), cantidad)

    def test_antecedente_exige_permisos_rol_y_aislamiento(self):
        self.client.force_login(self.usuario_sin_permisos)
        self.assertEqual(
            self.client.get(reverse("talento_agregar_antecedente", args=[self.candidato.pk])).status_code,
            403,
        )
        self.client.force_login(self.usuario)
        self.assertEqual(
            self.client.get(reverse("talento_agregar_antecedente", args=[self.candidato_ajeno.pk])).status_code,
            404,
        )
        membresia = Membresia.objects.get(usuario=self.usuario)
        membresia.rol = Membresia.Rol.COLABORADOR
        membresia.save(update_fields=("rol",))
        self.assertEqual(
            self.client.get(reverse("talento_agregar_antecedente", args=[self.candidato.pk])).status_code,
            403,
        )

    def test_antecedente_no_permite_manipular_candidato_ni_organizacion(self):
        self.client.force_login(self.usuario)
        respuesta = self.client.post(
            reverse("talento_agregar_antecedente", args=[self.candidato.pk]),
            self.antecedentes_datos(candidato=self.candidato_ajeno.pk, organizacion=self.organizacion_b.pk),
        )
        self.assertEqual(respuesta.status_code, 302)
        antecedente = self.candidato.documentos.get()
        self.assertEqual(antecedente.candidato_id, self.candidato.pk)
        self.assertFalse(self.candidato_ajeno.documentos.exists())
