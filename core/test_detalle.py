from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Organizacion, Membresia, Oportunidad


@override_settings(ALLOWED_HOSTS=["testserver"])
class DetalleOportunidadTests(TestCase):
    HOY = date(2026, 10, 14)

    @classmethod
    def setUpTestData(cls):
        Usuario = get_user_model()

        cls.usuario = Usuario.objects.create_user(
            username="gestor_detalle",
            is_staff=True,
        )
        cls.usuario.user_permissions.add(
            *Permission.objects.filter(content_type__app_label="core")
        )
        cls.sin_permisos = Usuario.objects.create_user(
            username="sin_permisos_detalle",
            is_staff=True,
        )
        cls.superusuario = Usuario.objects.create_superuser(
            username="superusuario_detalle",
            email="detalle@example.com",
            password="solo-para-pruebas",
        )

        cls.organizacion = Organizacion.objects.create(
            nombre="Organización de detalle",
            slug="organizacion-detalle",
        )
        cls.otra_organizacion = Organizacion.objects.create(
            nombre="Organización ajena",
            slug="organizacion-ajena-detalle",
        )
        cls.membresia = Membresia.objects.create(
            usuario=cls.usuario,
            organizacion=cls.organizacion,
            rol=Membresia.Rol.ADMINISTRADOR,
        )
        Membresia.objects.create(
            usuario=cls.sin_permisos,
            organizacion=cls.organizacion,
            rol=Membresia.Rol.ADMINISTRADOR,
        )

        cls.propia = Oportunidad.objects.create(
            organizacion=cls.organizacion,
            titulo="Consulta propia del detalle",
            origen=Oportunidad.Origen.CONSULTA_ENTRANTE,
            canal=Oportunidad.Canal.WHATSAPP,
            necesidad="Buscar una jefatura de proyectos",
            responsable=cls.membresia,
            nombre_consultante="Consultante de prueba",
            fecha_proxima_accion=cls.HOY,
            proxima_accion="Confirmar alcance de la búsqueda",
        )
        cls.sin_asignar = Oportunidad.objects.create(
            organizacion=cls.organizacion,
            titulo="Consulta no asignada",
            origen=Oportunidad.Origen.CONSULTA_ENTRANTE,
            canal=Oportunidad.Canal.WEB,
            necesidad="Necesidad ficticia",
        )
        cls.ajena = Oportunidad.objects.create(
            organizacion=cls.otra_organizacion,
            titulo="Consulta privada ajena",
            origen=Oportunidad.Origen.CONSULTA_ENTRANTE,
            canal=Oportunidad.Canal.EMAIL,
            necesidad="Información privada de otra organización",
        )

    def setUp(self):
        self.client.force_login(self.usuario)
        parche = patch(
            "core.views.timezone.localdate",
            return_value=self.HOY,
        )
        parche.start()
        self.addCleanup(parche.stop)

    def abrir_ficha(self, oportunidad=None):
        oportunidad = oportunidad or self.propia
        return self.client.get(
            reverse(
                "detalle_oportunidad",
                args=[oportunidad.pk],
            )
        )

    def test_muestra_datos_y_edicion_para_administrador(self):
        respuesta = self.abrir_ficha()

        self.assertEqual(respuesta.status_code, 200)
        self.assertTemplateUsed(
            respuesta,
            "core/detalle_oportunidad.html",
        )
        self.assertContains(respuesta, self.propia.titulo)
        self.assertContains(respuesta, self.propia.necesidad)
        self.assertContains(respuesta, self.propia.proxima_accion)
        self.assertContains(respuesta, "Consultante de prueba")
        self.assertContains(respuesta, "Seguimiento para hoy")
        self.assertContains(respuesta, "Empresa por identificar")
        self.assertTrue(respuesta.context["puede_editar"])
        self.assertContains(
            respuesta,
            reverse(
                "admin:core_oportunidad_change",
                args=[self.propia.pk],
            ),
        )

    def test_registro_ajeno_o_inexistente_devuelve_404(self):
        respuesta = self.abrir_ficha(self.ajena)
        self.assertEqual(respuesta.status_code, 404)

        respuesta = self.client.get(
            reverse(
                "detalle_oportunidad",
                args=[self.ajena.pk + 10000],
            )
        )
        self.assertEqual(respuesta.status_code, 404)

    def test_colaborador_solo_consulta_su_asignada(self):
        self.membresia.rol = Membresia.Rol.COLABORADOR
        self.membresia.save()

        respuesta = self.abrir_ficha()
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.context["puede_editar"])

        respuesta = self.abrir_ficha(self.sin_asignar)
        self.assertEqual(respuesta.status_code, 404)

        respuesta = self.abrir_ficha(self.ajena)
        self.assertEqual(respuesta.status_code, 404)

    def test_usuario_solo_lectura_no_ve_boton_editar(self):
        self.usuario.user_permissions.set(
            Permission.objects.filter(
                content_type__app_label="core",
                codename="view_oportunidad",
            )
        )

        respuesta = self.abrir_ficha()

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, self.propia.titulo)
        self.assertFalse(respuesta.context["puede_editar"])
        self.assertNotContains(
            respuesta,
            "Editar en administración",
        )
        self.assertNotContains(
            respuesta,
            reverse(
                "admin:core_oportunidad_change",
                args=[self.propia.pk],
            ),
        )

    def test_usuario_sin_permisos_recibe_403(self):
        self.client.force_login(self.sin_permisos)
        respuesta = self.abrir_ficha()
        self.assertEqual(respuesta.status_code, 403)

    def test_membresia_u_organizacion_inactiva_bloquean(self):
        self.membresia.activa = False
        self.membresia.save()
        self.assertEqual(self.abrir_ficha().status_code, 403)

        self.membresia.activa = True
        self.membresia.save()
        self.organizacion.activa = False
        self.organizacion.save()
        self.assertEqual(self.abrir_ficha().status_code, 403)

    def test_sin_sesion_redirige_a_login(self):
        self.client.logout()
        respuesta = self.abrir_ficha()

        self.assertEqual(respuesta.status_code, 302)
        self.assertIn(reverse("admin:login"), respuesta.url)

    def test_superusuario_consulta_otra_organizacion(self):
        self.client.force_login(self.superusuario)
        respuesta = self.abrir_ficha(self.ajena)

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, self.ajena.titulo)
        self.assertTrue(respuesta.context["puede_editar"])

    def test_avisos_de_seguimiento_y_cierre(self):
        casos = (
            (
                self.HOY - timedelta(days=1),
                "Seguimiento vencido",
            ),
            (
                self.HOY + timedelta(days=1),
                "Seguimiento programado",
            ),
            (
                None,
                "Falta definir una fecha de seguimiento.",
            ),
        )

        for fecha, aviso in casos:
            with self.subTest(fecha=fecha):
                self.propia.fecha_proxima_accion = fecha
                self.propia.save()
                respuesta = self.abrir_ficha()
                self.assertEqual(respuesta.status_code, 200)
                self.assertContains(respuesta, aviso)

        self.propia.estado = Oportunidad.Estado.PERDIDA
        self.propia.motivo_cierre = "Proyecto cancelado"
        self.propia.save()

        respuesta = self.abrir_ficha()
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.context["esta_cerrada"])
        self.assertContains(
            respuesta,
            "Esta oportunidad está cerrada.",
        )
        self.assertContains(respuesta, "Proyecto cancelado")
        self.assertContains(respuesta, "Motivo de cierre")

    def test_notas_se_muestran_como_texto_seguro(self):
        texto = '<script>alert("prueba")</script>'
        self.propia.notas = texto
        self.propia.save()

        respuesta = self.abrir_ficha()

        self.assertEqual(respuesta.status_code, 200)
        self.assertNotContains(respuesta, texto)
        self.assertContains(respuesta, "&lt;script&gt;")

    def test_panel_enlaza_a_fichas_en_las_cuatro_tablas(self):
        respuesta = self.client.get(reverse("panel_comercial"))

        self.assertEqual(respuesta.status_code, 200)

        # Asignada para hoy: lista general, calientes y seguimientos.
        enlace_propia = reverse(
            "detalle_oportunidad",
            args=[self.propia.pk],
        )
        self.assertContains(
            respuesta,
            f'href="{enlace_propia}"',
            count=3,
        )

        # Sin fecha: lista general, calientes y tabla sin fecha.
        enlace_sin_fecha = reverse(
            "detalle_oportunidad",
            args=[self.sin_asignar.pk],
        )
        self.assertContains(
            respuesta,
            f'href="{enlace_sin_fecha}"',
            count=3,
        )

        self.assertNotContains(
            respuesta,
            reverse(
                "admin:core_oportunidad_change",
                args=[self.propia.pk],
            ),
        )