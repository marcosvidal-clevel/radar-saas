from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import Membresia, Organizacion
from .models import Candidato, DocumentoCandidato, Postulacion, Vacante


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
            codename__in=("view_vacante", "add_vacante", "view_postulacion", "add_postulacion", "change_postulacion", "view_candidato", "view_documentocandidato"),
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
