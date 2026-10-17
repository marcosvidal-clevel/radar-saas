from tempfile import TemporaryDirectory
from io import BytesIO
from datetime import datetime, timezone

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from docx import Document

from core.models import Membresia, Organizacion
from .models import Candidato, DocumentoCandidato, Entrevista, HistorialEstadoPostulacion, Postulacion, Vacante


class SeleccionVistasTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org_a = Organizacion.objects.create(nombre="Selección A", slug="seleccion-a")
        cls.org_b = Organizacion.objects.create(nombre="Selección B", slug="seleccion-b")
        Usuario = get_user_model()
        cls.usuario = Usuario.objects.create_user(username="seleccion", password="clave", is_staff=True)
        cls.ajeno = Usuario.objects.create_user(username="seleccion-ajeno", password="clave", is_staff=True)
        Membresia.objects.create(usuario=cls.usuario, organizacion=cls.org_a, rol=Membresia.Rol.SUPERVISOR)
        Membresia.objects.create(usuario=cls.ajeno, organizacion=cls.org_b, rol=Membresia.Rol.SUPERVISOR)
        permisos = Permission.objects.filter(
            content_type__app_label="talento",
            codename__in=("view_vacante", "add_vacante", "change_vacante", "view_postulacion", "add_postulacion", "change_postulacion", "view_candidato", "add_candidato", "add_documentocandidato", "view_documentocandidato", "view_entrevista", "add_entrevista", "change_entrevista"),
        )
        cls.usuario.user_permissions.add(*permisos)
        cls.ajeno.user_permissions.add(*permisos)
        cls.candidato = Candidato.objects.create(organizacion=cls.org_a, nombre="Candidato Selección")
        cls.candidato_ajeno = Candidato.objects.create(organizacion=cls.org_b, nombre="Candidato Ajeno")
        cls.vacante = Vacante.objects.create(organizacion=cls.org_a, titulo="Ingeniero de pruebas")
        cls.vacante_ajena = Vacante.objects.create(organizacion=cls.org_b, titulo="Vacante ajena")

    def setUp(self):
        self.media = TemporaryDirectory()
        self.override = override_settings(MEDIA_ROOT=self.media.name)
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.addCleanup(self.media.cleanup)

    def test_listado_aisla_y_filtra(self):
        self.client.force_login(self.usuario)
        respuesta = self.client.get(reverse("seleccion_vacantes"), {"q": "Ingeniero", "estado": "borrador"})
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, self.vacante.titulo)
        self.assertNotContains(respuesta, self.vacante_ajena.titulo)

    def test_ficha_no_revela_postulaciones_sin_permiso(self):
        self.usuario.user_permissions.remove(
            Permission.objects.get(content_type__app_label="talento", codename="add_postulacion")
        )
        self.client.force_login(self.usuario)
        respuesta = self.client.get(reverse("seleccion_detalle_vacante", args=[self.vacante.pk]))
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotContains(respuesta, "Vincular candidato")

    def test_crea_vacante_con_csrf_y_relaciones_validas(self):
        self.client.force_login(self.usuario)
        respuesta = self.client.post(reverse("seleccion_nueva_vacante"), {
            "organizacion": self.org_a.pk, "titulo": "Nueva vacante", "estado": Vacante.Estado.BORRADOR,
            "descripcion": "Descripción", "requisitos": "Requisitos", "region": "RM", "ciudad": "Santiago",
            "publicar_web": "", "activa": "on",
        })
        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(Vacante.objects.filter(titulo="Nueva vacante").exists())

    def test_postula_candidato_con_cv_vigente_y_aisla(self):
        permisos = Permission.objects.filter(content_type__app_label="talento", codename="add_postulacion")
        self.usuario.user_permissions.add(*permisos)
        documento = DocumentoCandidato.objects.create(
            candidato=self.candidato, tipo=DocumentoCandidato.Tipo.CURRICULUM,
            nombre="CV", archivo=SimpleUploadedFile("cv.pdf", b"pdf", content_type="application/pdf"),
        )
        self.client.force_login(self.usuario)
        respuesta = self.client.post(reverse("seleccion_detalle_vacante", args=[self.vacante.pk]), {
            "candidato": self.candidato.pk, "documento_cv": documento.pk,
            "fuente": Postulacion.Fuente.MANUAL, "observaciones": "Prueba",
        })
        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(Postulacion.objects.filter(vacante=self.vacante, candidato=self.candidato).exists())

    def test_rechaza_candidato_de_otra_organizacion(self):
        self.usuario.user_permissions.add(*Permission.objects.filter(content_type__app_label="talento", codename="add_postulacion"))
        self.client.force_login(self.usuario)
        respuesta = self.client.post(reverse("seleccion_detalle_vacante", args=[self.vacante.pk]), {
            "candidato": self.candidato_ajeno.pk, "fuente": Postulacion.Fuente.MANUAL,
        })
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(Postulacion.objects.exists())

    def test_rechaza_duplicado_incluso_en_modelo(self):
        Postulacion.objects.create(vacante=self.vacante, candidato=self.candidato)
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            Postulacion.objects.create(vacante=self.vacante, candidato=self.candidato)

    def test_vinculacion_duplicada_muestra_error_en_formulario(self):
        self.usuario.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="talento",
            codename="add_postulacion",
        ))
        Postulacion.objects.create(vacante=self.vacante, candidato=self.candidato)
        self.client.force_login(self.usuario)

        respuesta = self.client.post(
            reverse("seleccion_detalle_vacante", args=[self.vacante.pk]),
            {
                "candidato": self.candidato.pk,
                "fuente": Postulacion.Fuente.MANUAL,
                "observaciones": "Mantener estos datos",
            },
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Postulación con este Vacante y Candidato ya existe.")
        self.assertContains(respuesta, "Mantener estos datos")
        self.assertEqual(
            Postulacion.objects.filter(
                vacante=self.vacante,
                candidato=self.candidato,
            ).count(),
            1,
        )

    def test_membresia_inactiva_bloquea_seleccion(self):
        Membresia.objects.filter(usuario=self.usuario).update(activa=False)
        self.client.force_login(self.usuario)
        self.assertEqual(self.client.get(reverse("seleccion_vacantes")).status_code, 403)

    def test_csrf_rechaza_post_sin_token(self):
        self.client = self.client_class(enforce_csrf_checks=True)
        self.client.force_login(self.usuario)
        respuesta = self.client.post(reverse("seleccion_nueva_vacante"), {"titulo": "Sin CSRF"})
        self.assertEqual(respuesta.status_code, 403)

    def test_actualiza_estado_y_observaciones_sin_cambiar_relaciones(self):
        postulacion = Postulacion.objects.create(
            vacante=self.vacante, candidato=self.candidato,
            fuente=Postulacion.Fuente.REFERIDO, observaciones="Inicial",
        )
        self.client.force_login(self.usuario)
        respuesta = self.client.post(reverse("seleccion_detalle_vacante", args=[self.vacante.pk]), {
            "accion": "actualizar_postulacion", "postulacion": postulacion.pk,
            "estado": Postulacion.Estado.ENTREVISTA, "observaciones": "Llamar mañana",
            "candidato": self.candidato_ajeno.pk, "fuente": Postulacion.Fuente.WEB,
        })
        self.assertEqual(respuesta.status_code, 302)
        postulacion.refresh_from_db()
        self.assertEqual(postulacion.estado, Postulacion.Estado.ENTREVISTA)
        self.assertEqual(postulacion.observaciones, "Llamar mañana")
        self.assertEqual(postulacion.candidato_id, self.candidato.pk)
        self.assertEqual(postulacion.fuente, Postulacion.Fuente.REFERIDO)

    def test_actualizacion_rechaza_estado_invalido_y_conserva_valores(self):
        postulacion = Postulacion.objects.create(vacante=self.vacante, candidato=self.candidato)
        self.client.force_login(self.usuario)
        respuesta = self.client.post(reverse("seleccion_detalle_vacante", args=[self.vacante.pk]), {
            "accion": "actualizar_postulacion", "postulacion": postulacion.pk,
            "estado": "inventado", "observaciones": "Texto enviado",
        })
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Texto enviado")
        postulacion.refresh_from_db()
        self.assertEqual(postulacion.estado, Postulacion.Estado.RECIBIDA)

    def test_actualizacion_requiere_change_y_csrf(self):
        postulacion = Postulacion.objects.create(vacante=self.vacante, candidato=self.candidato)
        self.usuario.user_permissions.remove(Permission.objects.get(content_type__app_label="talento", codename="change_postulacion"))
        self.client.force_login(self.usuario)
        self.assertEqual(self.client.post(reverse("seleccion_detalle_vacante", args=[self.vacante.pk]), {
            "accion": "actualizar_postulacion", "postulacion": postulacion.pk,
            "estado": Postulacion.Estado.ENTREVISTA,
        }).status_code, 403)
        cliente = self.client_class(enforce_csrf_checks=True)
        cliente.force_login(self.usuario)
        self.usuario.user_permissions.add(Permission.objects.get(content_type__app_label="talento", codename="change_postulacion"))
        self.assertEqual(cliente.post(reverse("seleccion_detalle_vacante", args=[self.vacante.pk]), {
            "accion": "actualizar_postulacion", "postulacion": postulacion.pk,
            "estado": Postulacion.Estado.ENTREVISTA,
        }).status_code, 403)

    def test_crea_candidato_y_postulacion_desde_vacante_sin_cv(self):
        self.client.force_login(self.usuario)
        respuesta = self.client.post(reverse("seleccion_nuevo_candidato", args=[self.vacante.pk]), {
            "nombre": "Candidato nuevo", "email": "nuevo@example.com", "profesion": "Analista",
        })
        self.assertEqual(respuesta.status_code, 302)
        candidato = Candidato.objects.get(email="nuevo@example.com")
        self.assertEqual(candidato.organizacion_id, self.org_a.pk)
        self.assertTrue(Postulacion.objects.filter(vacante=self.vacante, candidato=candidato).exists())

    def test_crea_cv_extrae_texto_y_aisla_organizacion(self):
        self.client.force_login(self.usuario)
        respuesta = self.client.post(reverse("seleccion_nuevo_candidato", args=[self.vacante.pk]), {
            "nombre": "Candidato con CV", "email": "cv@example.com",
            "cv": SimpleUploadedFile("cv.txt", b"contenido", content_type="text/plain"),
        })
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(Candidato.objects.filter(email="cv@example.com").exists())
        self.assertContains(respuesta, "PDF, DOC o DOCX")

    def test_crea_cv_docx_y_extrae_texto(self):
        archivo_docx = BytesIO()
        documento = Document()
        documento.add_paragraph("Experiencia sintética desde Selección")
        documento.save(archivo_docx)
        self.client.force_login(self.usuario)
        respuesta = self.client.post(reverse("seleccion_nuevo_candidato", args=[self.vacante.pk]), {
            "nombre": "Candidato DOCX", "email": "docx@example.com",
            "cv": SimpleUploadedFile("cv.docx", archivo_docx.getvalue(), content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        })
        self.assertEqual(respuesta.status_code, 302)
        documento_guardado = DocumentoCandidato.objects.get(candidato__email="docx@example.com")
        self.assertIn("Experiencia sintética desde Selección", documento_guardado.texto_extraido)

    def test_detecta_coincidencia_y_vincula_sin_sobrescribir(self):
        candidato = Candidato.objects.create(organizacion=self.org_a, nombre="Original", email="igual@example.com")
        self.client.force_login(self.usuario)
        respuesta = self.client.post(reverse("seleccion_nuevo_candidato", args=[self.vacante.pk]), {
            "nombre": "Intento distinto", "email": "igual@example.com",
        })
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Candidato existente encontrado")
        respuesta = self.client.post(reverse("seleccion_nuevo_candidato", args=[self.vacante.pk]), {
            "candidato_existente": candidato.pk, "email": "igual@example.com",
        })
        self.assertEqual(respuesta.status_code, 302, respuesta.content.decode())
        candidato.refresh_from_db()
        self.assertEqual(candidato.nombre, "Original")
        self.assertTrue(Postulacion.objects.filter(vacante=self.vacante, candidato=candidato).exists())

    def test_nuevo_candidato_desde_vacante_requiere_permisos_y_csrf(self):
        self.usuario.user_permissions.remove(Permission.objects.get(content_type__app_label="talento", codename="add_candidato"))
        self.client.force_login(self.usuario)
        self.assertEqual(self.client.get(reverse("seleccion_nuevo_candidato", args=[self.vacante.pk])).status_code, 403)
        cliente = self.client_class(enforce_csrf_checks=True)
        self.usuario.user_permissions.add(Permission.objects.get(content_type__app_label="talento", codename="add_candidato"))
        cliente.force_login(self.usuario)
        self.assertEqual(cliente.post(reverse("seleccion_nuevo_candidato", args=[self.vacante.pk]), {"nombre": "Sin token"}).status_code, 403)

    def test_edita_vacante_y_conserva_postulaciones(self):
        postulacion = Postulacion.objects.create(vacante=self.vacante, candidato=self.candidato)
        self.client.force_login(self.usuario)
        respuesta = self.client.post(reverse("seleccion_editar_vacante", args=[self.vacante.pk]), {
            "titulo": "Título actualizado", "descripcion": "Nueva descripción", "requisitos": "Requisitos nuevos",
            "region": "Valparaíso", "ciudad": "Viña del Mar", "estado": Vacante.Estado.CERRADA, "activa": "",
        })
        self.assertEqual(respuesta.status_code, 302)
        self.vacante.refresh_from_db()
        self.assertEqual(self.vacante.titulo, "Título actualizado")
        self.assertEqual(self.vacante.organizacion_id, self.org_a.pk)
        self.assertFalse(self.vacante.activa)
        self.assertTrue(Postulacion.objects.filter(pk=postulacion.pk).exists())
        self.assertEqual(Postulacion.objects.get(pk=postulacion.pk).estado, Postulacion.Estado.RECIBIDA)

    def test_edicion_vacante_conserva_valores_y_rechaza_estado_invalido(self):
        self.client.force_login(self.usuario)
        respuesta = self.client.post(reverse("seleccion_editar_vacante", args=[self.vacante.pk]), {
            "titulo": "Título enviado", "descripcion": "Descripción enviada", "requisitos": "Req",
            "region": "RM", "ciudad": "Santiago", "estado": "no_existe", "activa": "on",
        })
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Título enviado")
        self.vacante.refresh_from_db()
        self.assertEqual(self.vacante.titulo, "Ingeniero de pruebas")

    def test_edicion_vacante_requiere_change_aislamiento_y_csrf(self):
        self.usuario.user_permissions.remove(Permission.objects.get(content_type__app_label="talento", codename="change_vacante"))
        self.client.force_login(self.usuario)
        self.assertEqual(self.client.get(reverse("seleccion_editar_vacante", args=[self.vacante.pk])).status_code, 403)
        self.client.force_login(self.ajeno)
        self.assertEqual(self.client.get(reverse("seleccion_editar_vacante", args=[self.vacante.pk])).status_code, 404)
        self.usuario.user_permissions.add(Permission.objects.get(content_type__app_label="talento", codename="change_vacante"))
        cliente = self.client_class(enforce_csrf_checks=True)
        cliente.force_login(self.usuario)
        self.assertEqual(cliente.post(reverse("seleccion_editar_vacante", args=[self.vacante.pk]), {"titulo": "Sin CSRF"}).status_code, 403)

    def test_resumen_muestra_todas_las_etapas_y_filtra_la_lista(self):
        Postulacion.objects.create(vacante=self.vacante, candidato=self.candidato, estado=Postulacion.Estado.RECIBIDA)
        candidato_dos = Candidato.objects.create(organizacion=self.org_a, nombre="Candidato dos")
        Postulacion.objects.create(vacante=self.vacante, candidato=candidato_dos, estado=Postulacion.Estado.ENTREVISTA)
        self.client.force_login(self.usuario)
        respuesta = self.client.get(reverse("seleccion_detalle_vacante", args=[self.vacante.pk]), {"etapa": Postulacion.Estado.ENTREVISTA})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context["total_postulaciones"], 2)
        self.assertEqual(respuesta.context["resumen_postulaciones"][Postulacion.Estado.RECIBIDA], 1)
        self.assertEqual(respuesta.context["resumen_postulaciones"][Postulacion.Estado.ENTREVISTA], 1)
        self.assertEqual(list(respuesta.context["postulaciones"]), [Postulacion.objects.get(candidato=candidato_dos)])
        self.assertContains(respuesta, "Candidato dos")
        self.assertContains(respuesta, "Descartada (0)")

    def test_filtro_invalido_equivale_a_todas_y_etapa_vacia_es_clara(self):
        Postulacion.objects.create(vacante=self.vacante, candidato=self.candidato)
        self.client.force_login(self.usuario)
        respuesta = self.client.get(reverse("seleccion_detalle_vacante", args=[self.vacante.pk]), {"etapa": "no_valida"})
        self.assertEqual(respuesta.context["etapa_postulacion"], "")
        vacia = self.client.get(reverse("seleccion_detalle_vacante", args=[self.vacante.pk]), {"etapa": Postulacion.Estado.FINALISTA})
        self.assertContains(vacia, "No hay postulaciones consultables en la etapa seleccionada.")

    def test_actualizacion_conserva_el_filtro_y_sin_permiso_no_revela_conteos(self):
        postulacion = Postulacion.objects.create(vacante=self.vacante, candidato=self.candidato)
        self.client.force_login(self.usuario)
        respuesta = self.client.post(reverse("seleccion_detalle_vacante", args=[self.vacante.pk]), {
            "accion": "actualizar_postulacion", "postulacion": postulacion.pk,
            "estado": Postulacion.Estado.ENTREVISTA, "etapa": Postulacion.Estado.RECIBIDA,
        })
        self.assertEqual(respuesta.url, reverse("seleccion_detalle_vacante", args=[self.vacante.pk]) + "?etapa=recibida")
        self.usuario.user_permissions.remove(Permission.objects.get(content_type__app_label="talento", codename="view_postulacion"))
        sin_permiso = self.client.get(reverse("seleccion_detalle_vacante", args=[self.vacante.pk]))
        self.assertIsNone(sin_permiso.context["total_postulaciones"])

    def test_cambio_de_etapa_registra_historial_con_usuario_y_fecha(self):
        postulacion = Postulacion.objects.create(vacante=self.vacante, candidato=self.candidato)
        self.client.force_login(self.usuario)
        respuesta = self.client.post(reverse("seleccion_detalle_vacante", args=[self.vacante.pk]), {
            "accion": "actualizar_postulacion", "postulacion": postulacion.pk,
            "estado": Postulacion.Estado.ENTREVISTA,
        })
        self.assertEqual(respuesta.status_code, 302)
        historial = HistorialEstadoPostulacion.objects.get(postulacion=postulacion)
        self.assertEqual(historial.estado_anterior, Postulacion.Estado.RECIBIDA)
        self.assertEqual(historial.estado_nuevo, Postulacion.Estado.ENTREVISTA)
        self.assertEqual(historial.usuario, self.usuario)
        self.assertIsNotNone(historial.creado_en)

    def test_no_duplica_historial_si_estado_no_cambia_ni_si_falla(self):
        postulacion = Postulacion.objects.create(vacante=self.vacante, candidato=self.candidato)
        self.client.force_login(self.usuario)
        datos = {"accion": "actualizar_postulacion", "postulacion": postulacion.pk, "estado": Postulacion.Estado.RECIBIDA}
        self.assertEqual(self.client.post(reverse("seleccion_detalle_vacante", args=[self.vacante.pk]), datos).status_code, 302)
        self.assertEqual(HistorialEstadoPostulacion.objects.count(), 0)
        datos["estado"] = "estado-invalido"
        self.assertEqual(self.client.post(reverse("seleccion_detalle_vacante", args=[self.vacante.pk]), datos).status_code, 200)
        self.assertEqual(HistorialEstadoPostulacion.objects.count(), 0)

    def test_historial_aisla_postulaciones_ajenas(self):
        postulacion = Postulacion.objects.create(vacante=self.vacante, candidato=self.candidato)
        HistorialEstadoPostulacion.objects.create(
            postulacion=postulacion, estado_anterior=Postulacion.Estado.RECIBIDA,
            estado_nuevo=Postulacion.Estado.ENTREVISTA, usuario=self.usuario,
        )
        self.client.force_login(self.ajeno)
        self.assertEqual(self.client.get(reverse("seleccion_detalle_vacante", args=[self.vacante.pk])).status_code, 404)

    def test_crea_y_edita_entrevista_sin_cambiar_etapa(self):
        postulacion = Postulacion.objects.create(vacante=self.vacante, candidato=self.candidato)
        self.client.force_login(self.usuario)
        datos = {"fecha_hora": "2030-05-10T15:30", "motivo": " entrevista inicial ", "entrevistador": "Ana", "modalidad": Entrevista.Modalidad.VIDEOLLAMADA, "lugar_enlace": "https://meet.example", "observaciones": "Primera", "estado": Entrevista.Estado.PROGRAMADA}
        respuesta = self.client.post(reverse("seleccion_nueva_entrevista", args=[postulacion.pk]), datos)
        self.assertEqual(respuesta.status_code, 302)
        entrevista = Entrevista.objects.get(postulacion=postulacion)
        self.assertEqual(postulacion.estado, Postulacion.Estado.RECIBIDA)
        self.assertEqual(entrevista.creado_por, self.usuario)
        respuesta = self.client.post(reverse("seleccion_editar_entrevista", args=[entrevista.pk]), {**datos, "estado": Entrevista.Estado.REALIZADA})
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(Entrevista.objects.get(pk=entrevista.pk).estado, Entrevista.Estado.REALIZADA)

    def test_motivo_obligatorio_y_no_acepta_espacios(self):
        postulacion = Postulacion.objects.create(vacante=self.vacante, candidato=self.candidato)
        self.client.force_login(self.usuario)
        datos = {"fecha_hora": "2030-05-10T15:30", "motivo": "   ", "entrevistador": "Ana", "modalidad": Entrevista.Modalidad.VIDEOLLAMADA, "estado": Entrevista.Estado.PROGRAMADA}
        respuesta = self.client.post(reverse("seleccion_nueva_entrevista", args=[postulacion.pk]), datos)
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "El motivo de la entrevista es obligatorio.")
        self.assertContains(respuesta, "   ")
        self.assertFalse(Entrevista.objects.filter(postulacion=postulacion).exists())

    def test_entrevista_legacy_sin_motivo_se_muestra_sin_inventar(self):
        postulacion = Postulacion.objects.create(vacante=self.vacante, candidato=self.candidato)
        Entrevista.objects.create(postulacion=postulacion, creado_por=self.usuario, fecha_hora=datetime(2030, 5, 10, 15, tzinfo=timezone.utc), entrevistador="A", modalidad=Entrevista.Modalidad.PRESENCIAL)
        self.client.force_login(self.usuario)
        respuesta = self.client.get(reverse("seleccion_agenda_entrevistas"))
        self.assertContains(respuesta, "Sin motivo registrado")

    def test_agenda_filtra_ordena_y_a_isla(self):
        postulacion = Postulacion.objects.create(vacante=self.vacante, candidato=self.candidato)
        Entrevista.objects.create(postulacion=postulacion, creado_por=self.usuario, fecha_hora=datetime(2030, 5, 11, 15, tzinfo=timezone.utc), entrevistador="B", modalidad=Entrevista.Modalidad.TELEFONO)
        Entrevista.objects.create(postulacion=postulacion, creado_por=self.usuario, fecha_hora=datetime(2030, 5, 10, 15, tzinfo=timezone.utc), entrevistador="A", modalidad=Entrevista.Modalidad.PRESENCIAL)
        self.client.force_login(self.usuario)
        respuesta = self.client.get(reverse("seleccion_agenda_entrevistas"), {"estado": Entrevista.Estado.PROGRAMADA, "desde": "2030-05-10", "hasta": "2030-05-11"})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(list(respuesta.context["pagina_entrevistas"])[0].entrevistador, "A")

    def test_entrevista_requiere_permiso_y_csrf(self):
        postulacion = Postulacion.objects.create(vacante=self.vacante, candidato=self.candidato)
        self.usuario.user_permissions.remove(Permission.objects.get(content_type__app_label="talento", codename="add_entrevista"))
        self.client.force_login(self.usuario)
        self.assertEqual(self.client.get(reverse("seleccion_nueva_entrevista", args=[postulacion.pk])).status_code, 403)
        cliente = self.client_class(enforce_csrf_checks=True)
        self.usuario.user_permissions.add(Permission.objects.get(content_type__app_label="talento", codename="add_entrevista"))
        cliente.force_login(self.usuario)
        self.assertEqual(cliente.post(reverse("seleccion_nueva_entrevista", args=[postulacion.pk]), {"fecha_hora": "2030-05-10T15:30"}).status_code, 403)
