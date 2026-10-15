from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .models import Membresia, Oportunidad, Organizacion


@override_settings(ALLOWED_HOSTS=["testserver"])
class SeguimientoOportunidadTests(TestCase):
    HOY = date(2026, 10, 14)

    @classmethod
    def setUpTestData(cls):
        Usuario = get_user_model()

        cls.gestor = Usuario.objects.create_user(
            username="gestor_seguimiento",
            is_staff=True,
        )
        cls.colaborador = Usuario.objects.create_user(
            username="colaborador_seguimiento",
            is_staff=True,
        )
        cls.lector = Usuario.objects.create_user(
            username="lector_seguimiento",
            is_staff=True,
        )

        permisos = Permission.objects.filter(
            content_type__app_label="core"
        )
        cls.gestor.user_permissions.add(*permisos)
        cls.colaborador.user_permissions.add(*permisos)
        cls.lector.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="core",
                codename="view_oportunidad",
            )
        )

        cls.organizacion = Organizacion.objects.create(
            nombre="Organización seguimiento",
            slug="organizacion-seguimiento",
        )
        cls.otra_organizacion = Organizacion.objects.create(
            nombre="Organización ajena seguimiento",
            slug="organizacion-ajena-seguimiento",
        )

        cls.membresia_gestor = Membresia.objects.create(
            usuario=cls.gestor,
            organizacion=cls.organizacion,
            rol=Membresia.Rol.ADMINISTRADOR,
        )
        cls.membresia_colaborador = Membresia.objects.create(
            usuario=cls.colaborador,
            organizacion=cls.organizacion,
            rol=Membresia.Rol.COLABORADOR,
        )
        Membresia.objects.create(
            usuario=cls.lector,
            organizacion=cls.organizacion,
            rol=Membresia.Rol.ADMINISTRADOR,
        )

        cls.oportunidad = Oportunidad.objects.create(
            organizacion=cls.organizacion,
            titulo="Consulta para seguimiento",
            origen=Oportunidad.Origen.CONSULTA_ENTRANTE,
            canal=Oportunidad.Canal.WHATSAPP,
            estado=Oportunidad.Estado.EN_CONTACTO,
            necesidad="Necesidad ficticia de seguimiento",
            responsable=cls.membresia_colaborador,
            proxima_accion="Acción original",
            fecha_proxima_accion=cls.HOY,
        )
        cls.no_asignada = Oportunidad.objects.create(
            organizacion=cls.organizacion,
            titulo="Consulta asignada al gestor",
            origen=Oportunidad.Origen.CONSULTA_ENTRANTE,
            canal=Oportunidad.Canal.WEB,
            necesidad="Necesidad ficticia",
            responsable=cls.membresia_gestor,
        )
        cls.ajena = Oportunidad.objects.create(
            organizacion=cls.otra_organizacion,
            titulo="Consulta privada ajena",
            origen=Oportunidad.Origen.CONSULTA_ENTRANTE,
            canal=Oportunidad.Canal.WEB,
            necesidad="Necesidad privada",
        )

    def setUp(self):
        self.client.force_login(self.gestor)
        parche = patch(
            "core.views.timezone.localdate",
            return_value=self.HOY,
        )
        parche.start()
        self.addCleanup(parche.stop)

    def url(self, oportunidad=None):
        return reverse(
            "detalle_oportunidad",
            args=[(oportunidad or self.oportunidad).pk],
        )

    def datos(self, **cambios):
        datos = {
            "estado": Oportunidad.Estado.EN_CONTACTO,
            "proxima_accion": "Llamar para confirmar la necesidad",
            "fecha_proxima_accion": "2026-10-15",
            "motivo_cierre": "",
        }
        datos.update(cambios)
        return datos

    def valores_guardados(self, oportunidad=None):
        oportunidad = oportunidad or self.oportunidad
        oportunidad.refresh_from_db()
        return (
            oportunidad.estado,
            oportunidad.proxima_accion,
            oportunidad.fecha_proxima_accion,
            oportunidad.motivo_cierre,
            oportunidad.actualizada_en,
        )

    def test_formulario_muestra_datos_actuales_y_fecha_iso(self):
        respuesta = self.client.get(self.url())

        self.assertEqual(respuesta.status_code, 200)
        formulario = respuesta.context["formulario"]
        self.assertEqual(
            formulario["proxima_accion"].value(),
            "Acción original",
        )
        self.assertContains(respuesta, 'type="date"')
        self.assertContains(respuesta, 'value="2026-10-14"')

    def test_gestor_actualiza_y_recibe_confirmacion(self):
        respuesta = self.client.post(
            self.url(),
            self.datos(),
            follow=True,
        )

        self.assertRedirects(respuesta, self.url())
        self.oportunidad.refresh_from_db()
        self.assertEqual(
            self.oportunidad.proxima_accion,
            "Llamar para confirmar la necesidad",
        )
        self.assertEqual(
            self.oportunidad.fecha_proxima_accion,
            date(2026, 10, 15),
        )
        self.assertContains(
            respuesta,
            "Seguimiento actualizado correctamente.",
        )

    def test_colaborador_actualiza_su_asignada(self):
        self.client.force_login(self.colaborador)

        respuesta = self.client.post(
            self.url(),
            self.datos(
                estado=Oportunidad.Estado.CALIFICADA,
            ),
        )

        self.assertRedirects(respuesta, self.url())
        self.oportunidad.refresh_from_db()
        self.assertEqual(
            self.oportunidad.estado,
            Oportunidad.Estado.CALIFICADA,
        )
        self.assertEqual(
            self.oportunidad.responsable_id,
            self.membresia_colaborador.pk,
        )

    def test_campos_adicionales_no_modifican_asignacion_ni_titulo(self):
        self.client.force_login(self.colaborador)
        titulo_original = self.oportunidad.titulo

        respuesta = self.client.post(
            self.url(),
            self.datos(
                organizacion=str(self.otra_organizacion.pk),
                responsable=str(self.membresia_gestor.pk),
                titulo="Título manipulado",
                necesidad="Necesidad manipulada",
            ),
        )

        self.assertRedirects(respuesta, self.url())
        self.oportunidad.refresh_from_db()
        self.assertEqual(
            self.oportunidad.organizacion_id,
            self.organizacion.pk,
        )
        self.assertEqual(
            self.oportunidad.responsable_id,
            self.membresia_colaborador.pk,
        )
        self.assertEqual(
            self.oportunidad.titulo,
            titulo_original,
        )
        self.assertEqual(
            self.oportunidad.necesidad,
            "Necesidad ficticia de seguimiento",
        )

    def test_lector_no_recibe_formulario_ni_puede_guardar(self):
        self.client.force_login(self.lector)
        originales = self.valores_guardados()

        consulta = self.client.get(self.url())
        self.assertEqual(consulta.status_code, 200)
        self.assertIsNone(consulta.context["formulario"])
        self.assertNotContains(consulta, "Guardar seguimiento")

        respuesta = self.client.post(self.url(), self.datos())
        self.assertEqual(respuesta.status_code, 403)
        self.assertEqual(self.valores_guardados(), originales)

    def test_registro_ajeno_no_se_modifica(self):
        originales = self.valores_guardados(self.ajena)

        respuesta = self.client.post(
            self.url(self.ajena),
            self.datos(),
        )

        self.assertEqual(respuesta.status_code, 404)
        self.assertEqual(
            self.valores_guardados(self.ajena),
            originales,
        )

    def test_colaborador_no_modifica_oportunidad_de_otro(self):
        self.client.force_login(self.colaborador)
        originales = self.valores_guardados(self.no_asignada)

        respuesta = self.client.post(
            self.url(self.no_asignada),
            self.datos(),
        )

        self.assertEqual(respuesta.status_code, 404)
        self.assertEqual(
            self.valores_guardados(self.no_asignada),
            originales,
        )

    def test_membresia_inactiva_impide_guardar(self):
        originales = self.valores_guardados()
        self.membresia_gestor.activa = False
        self.membresia_gestor.save()

        respuesta = self.client.post(self.url(), self.datos())

        self.assertEqual(respuesta.status_code, 403)
        self.assertEqual(self.valores_guardados(), originales)

    def test_cierre_sin_motivo_muestra_un_solo_error_y_no_guarda(self):
        originales = self.valores_guardados()

        for estado in (
            Oportunidad.Estado.PERDIDA,
            Oportunidad.Estado.DESCARTADA,
        ):
            with self.subTest(estado=estado):
                respuesta = self.client.post(
                    self.url(),
                    self.datos(
                        estado=estado,
                        motivo_cierre="   ",
                    ),
                )

                self.assertEqual(respuesta.status_code, 200)
                errores = respuesta.context[
                    "formulario"
                ].errors["motivo_cierre"]
                self.assertEqual(len(errores), 1)
                self.assertEqual(
                    self.valores_guardados(),
                    originales,
                )
                self.assertEqual(
                    respuesta.context["oportunidad"].estado,
                    Oportunidad.Estado.EN_CONTACTO,
                )

    def test_fecha_invalida_no_guarda_cambios_parciales(self):
        originales = self.valores_guardados()

        respuesta = self.client.post(
            self.url(),
            self.datos(
                estado=Oportunidad.Estado.CALIFICADA,
                fecha_proxima_accion="fecha-invalida",
            ),
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn(
            "fecha_proxima_accion",
            respuesta.context["formulario"].errors,
        )
        self.assertEqual(self.valores_guardados(), originales)

    def test_cierre_con_motivo_sale_del_panel_activo(self):
        respuesta = self.client.post(
            self.url(),
            self.datos(
                estado=Oportunidad.Estado.PERDIDA,
                motivo_cierre="  El cliente canceló el proyecto.  ",
            ),
        )

        self.assertRedirects(respuesta, self.url())
        self.oportunidad.refresh_from_db()
        self.assertEqual(
            self.oportunidad.estado,
            Oportunidad.Estado.PERDIDA,
        )
        self.assertEqual(
            self.oportunidad.motivo_cierre,
            "El cliente canceló el proyecto.",
        )

        panel = self.client.get(reverse("panel_comercial"))
        self.assertEqual(panel.status_code, 200)
        self.assertEqual(panel.context["total_activas"], 1)
        self.assertNotContains(panel, self.oportunidad.titulo)

    def test_post_sin_token_csrf_es_rechazado(self):
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.gestor)
        originales = self.valores_guardados()

        respuesta = cliente.post(self.url(), self.datos())

        self.assertEqual(respuesta.status_code, 403)
        self.assertEqual(self.valores_guardados(), originales)