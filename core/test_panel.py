from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import (
    Organizacion,
    Membresia,
    Sector,
    EmpresaProspectada,
    Oportunidad,
)


@override_settings(ALLOWED_HOSTS=["testserver"])
class PanelComercialTests(TestCase):
    HOY = date(2026, 10, 14)

    @classmethod
    def setUpTestData(cls):
        Usuario = get_user_model()

        cls.usuario = Usuario.objects.create_user(
            username="gestor_panel",
            is_staff=True,
        )
        cls.usuario.user_permissions.add(
            *Permission.objects.filter(content_type__app_label="core")
        )
        cls.sin_permisos = Usuario.objects.create_user(
            username="sin_permisos_panel",
            is_staff=True,
        )
        cls.superusuario = Usuario.objects.create_superuser(
            username="superusuario_panel",
            email="panel@example.com",
            password="solo-para-pruebas",
        )

        cls.organizacion = Organizacion.objects.create(
            nombre="Piloto del panel",
            slug="piloto-panel",
        )
        cls.otra_organizacion = Organizacion.objects.create(
            nombre="Otra organización del panel",
            slug="otra-panel",
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

        cls.para_hoy = Oportunidad.objects.create(
            organizacion=cls.organizacion,
            titulo="Consulta asignada para hoy",
            origen=Oportunidad.Origen.CONSULTA_ENTRANTE,
            canal=Oportunidad.Canal.WHATSAPP,
            necesidad="Necesidad ficticia",
            responsable=cls.membresia,
            fecha_proxima_accion=cls.HOY,
            proxima_accion="Llamar al consultante",
        )
        cls.vencida = Oportunidad.objects.create(
            organizacion=cls.organizacion,
            titulo="Consulta vencida",
            origen=Oportunidad.Origen.CONSULTA_ENTRANTE,
            canal=Oportunidad.Canal.EMAIL,
            necesidad="Necesidad ficticia",
            fecha_proxima_accion=cls.HOY - timedelta(days=1),
        )
        cls.futura = Oportunidad.objects.create(
            organizacion=cls.organizacion,
            titulo="Consulta futura",
            origen=Oportunidad.Origen.CONSULTA_ENTRANTE,
            canal=Oportunidad.Canal.WEB,
            necesidad="Necesidad ficticia",
            fecha_proxima_accion=cls.HOY + timedelta(days=1),
        )
        cls.sin_fecha = Oportunidad.objects.create(
            organizacion=cls.organizacion,
            titulo="Consulta sin fecha",
            origen=Oportunidad.Origen.CONSULTA_ENTRANTE,
            canal=Oportunidad.Canal.TELEFONO,
            necesidad="Necesidad ficticia",
        )

        for estado in (
            Oportunidad.Estado.GANADA,
            Oportunidad.Estado.PERDIDA,
            Oportunidad.Estado.DESCARTADA,
        ):
            Oportunidad.objects.create(
                organizacion=cls.organizacion,
                titulo=f"Cerrada: {estado}",
                origen=Oportunidad.Origen.CONSULTA_ENTRANTE,
                canal=Oportunidad.Canal.WEB,
                necesidad="Necesidad ficticia",
                estado=estado,
                motivo_cierre="Cierre de prueba",
                fecha_proxima_accion=cls.HOY - timedelta(days=2),
            )

        cls.ajena = Oportunidad.objects.create(
            organizacion=cls.otra_organizacion,
            titulo="Consulta privada de otra organización",
            origen=Oportunidad.Origen.CONSULTA_ENTRANTE,
            canal=Oportunidad.Canal.WEB,
            necesidad="Necesidad ficticia ajena",
            fecha_proxima_accion=cls.HOY,
        )

    def setUp(self):
        self.client.force_login(self.usuario)
        parche = patch(
            "core.views.timezone.localdate",
            return_value=self.HOY,
        )
        parche.start()
        self.addCleanup(parche.stop)

    def abrir_panel(self, filtros=None):
        return self.client.get(
            reverse("panel_comercial"),
            filtros or {},
        )

    def test_indicadores_excluyen_cerradas_y_organizaciones_ajenas(self):
        respuesta = self.abrir_panel()
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context["total_activas"], 4)
        self.assertEqual(respuesta.context["total_calientes"], 4)
        self.assertEqual(respuesta.context["total_vencidas"], 1)
        self.assertEqual(respuesta.context["total_para_hoy"], 1)
        self.assertEqual(respuesta.context["total_sin_fecha"], 1)
        self.assertNotContains(respuesta, self.ajena.titulo)

        for estado in ("ganada", "perdida", "descartada"):
            self.assertNotContains(respuesta, f"Cerrada: {estado}")

    def test_seguimientos_ordenados_y_sin_fechas_futuras(self):
        respuesta = self.abrir_panel()
        ids = [
            oportunidad.pk
            for oportunidad in respuesta.context["seguimientos"]
        ]
        self.assertEqual(ids, [self.vencida.pk, self.para_hoy.pk])
        self.assertContains(respuesta, "Llamar al consultante")
        self.assertContains(respuesta, "Vencido")

    def test_lista_sin_fecha_contiene_solo_registros_sin_fecha(self):
        respuesta = self.abrir_panel()
        ids = [
            oportunidad.pk
            for oportunidad in respuesta.context["sin_fecha"]
        ]
        self.assertEqual(ids, [self.sin_fecha.pk])

    def test_colaborador_solo_ve_su_oportunidad_y_no_puede_crear(self):
        self.membresia.rol = Membresia.Rol.COLABORADOR
        self.membresia.save()

        respuesta = self.abrir_panel()
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context["total_activas"], 1)
        self.assertEqual(respuesta.context["total_para_hoy"], 1)
        self.assertEqual(respuesta.context["total_vencidas"], 0)
        self.assertEqual(respuesta.context["total_sin_fecha"], 0)
        self.assertFalse(respuesta.context["puede_crear"])
        self.assertContains(respuesta, self.para_hoy.titulo)
        self.assertNotContains(respuesta, self.vencida.titulo)
        self.assertNotContains(respuesta, self.futura.titulo)
        self.assertNotContains(respuesta, self.sin_fecha.titulo)
        self.assertNotContains(respuesta, self.ajena.titulo)
        self.assertNotContains(
            respuesta,
            reverse("admin:core_oportunidad_add"),
        )

    def test_sin_sesion_redirige_al_inicio_de_sesion(self):
        self.client.logout()
        respuesta = self.abrir_panel()
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn(reverse("admin:login"), respuesta.url)
        self.assertNotContains(
            respuesta,
            self.para_hoy.titulo,
            status_code=302,
        )

    def test_usuario_sin_permisos_recibe_403(self):
        self.client.force_login(self.sin_permisos)
        respuesta = self.abrir_panel()
        self.assertEqual(respuesta.status_code, 403)

    def test_membresia_inactiva_recibe_403(self):
        self.membresia.activa = False
        self.membresia.save()
        respuesta = self.abrir_panel()
        self.assertEqual(respuesta.status_code, 403)

    def test_superusuario_ve_las_dos_organizaciones(self):
        self.client.force_login(self.superusuario)
        respuesta = self.abrir_panel()
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context["total_activas"], 5)
        self.assertEqual(respuesta.context["total_para_hoy"], 2)
        self.assertContains(respuesta, self.ajena.titulo)
        self.assertTrue(respuesta.context["puede_crear"])

    def test_filtro_canal_actualiza_indicadores_y_tablas(self):
        respuesta = self.abrir_panel({
            "canal": Oportunidad.Canal.WHATSAPP,
        })
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context["total_activas"], 1)
        self.assertEqual(respuesta.context["total_calientes"], 1)
        self.assertEqual(respuesta.context["total_para_hoy"], 1)
        self.assertEqual(respuesta.context["total_vencidas"], 0)
        self.assertEqual(respuesta.context["total_sin_fecha"], 0)
        self.assertContains(respuesta, self.para_hoy.titulo)
        self.assertNotContains(respuesta, self.vencida.titulo)
        self.assertNotContains(respuesta, self.futura.titulo)
        self.assertNotContains(respuesta, self.sin_fecha.titulo)
        self.assertEqual(
            respuesta.context["filtro_canal"],
            Oportunidad.Canal.WHATSAPP,
        )
        self.assertTrue(respuesta.context["hay_filtros"])

    def test_filtro_estado_se_combina_con_canal(self):
        self.para_hoy.estado = Oportunidad.Estado.EN_CONTACTO
        self.para_hoy.save()

        respuesta = self.abrir_panel({
            "estado": Oportunidad.Estado.EN_CONTACTO,
        })
        self.assertEqual(respuesta.context["total_activas"], 1)
        self.assertContains(respuesta, self.para_hoy.titulo)
        self.assertNotContains(respuesta, self.vencida.titulo)

        respuesta = self.abrir_panel({
            "estado": Oportunidad.Estado.EN_CONTACTO,
            "canal": Oportunidad.Canal.EMAIL,
        })
        self.assertEqual(respuesta.context["total_activas"], 0)
        self.assertEqual(respuesta.context["total_calientes"], 0)
        self.assertEqual(respuesta.context["total_para_hoy"], 0)
        self.assertEqual(respuesta.context["total_vencidas"], 0)
        self.assertEqual(respuesta.context["total_sin_fecha"], 0)
        self.assertNotContains(respuesta, self.para_hoy.titulo)
        self.assertNotContains(respuesta, self.vencida.titulo)

    def test_filtro_responsable_muestra_solo_asignadas(self):
        respuesta = self.abrir_panel({
            "responsable": str(self.membresia.pk),
        })
        self.assertEqual(respuesta.context["total_activas"], 1)
        self.assertContains(respuesta, self.para_hoy.titulo)
        self.assertNotContains(respuesta, self.vencida.titulo)
        self.assertEqual(
            respuesta.context["filtro_responsable"],
            str(self.membresia.pk),
        )

    def test_filtro_sin_asignar(self):
        respuesta = self.abrir_panel({
            "responsable": "sin_asignar",
        })
        self.assertEqual(respuesta.context["total_activas"], 3)
        self.assertEqual(respuesta.context["total_para_hoy"], 0)
        self.assertEqual(respuesta.context["total_vencidas"], 1)
        self.assertEqual(respuesta.context["total_sin_fecha"], 1)
        self.assertNotContains(respuesta, self.para_hoy.titulo)
        self.assertContains(respuesta, self.vencida.titulo)
        self.assertContains(respuesta, self.futura.titulo)
        self.assertContains(respuesta, self.sin_fecha.titulo)

    def test_valores_invalidos_se_ignoran_sin_ampliar_acceso(self):
        respuesta = self.abrir_panel({
            "estado": "estado_inexistente",
            "canal": "canal_inexistente",
            "responsable": "no_es_un_identificador",
        })
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context["total_activas"], 4)
        self.assertEqual(respuesta.context["filtro_estado"], "")
        self.assertEqual(respuesta.context["filtro_canal"], "")
        self.assertEqual(respuesta.context["filtro_responsable"], "")
        self.assertFalse(respuesta.context["hay_filtros"])
        self.assertNotContains(respuesta, self.ajena.titulo)

    def test_responsable_ajeno_no_aparece_ni_permite_ver_datos(self):
        Usuario = get_user_model()
        usuario_ajeno = Usuario.objects.create_user(
            username="responsable_privado",
        )
        membresia_ajena = Membresia.objects.create(
            usuario=usuario_ajeno,
            organizacion=self.otra_organizacion,
            rol=Membresia.Rol.ADMINISTRADOR,
        )
        self.ajena.responsable = membresia_ajena
        self.ajena.save()

        respuesta = self.abrir_panel({
            "responsable": str(membresia_ajena.pk),
        })
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context["total_activas"], 4)
        opciones = {
            opcion["id"]
            for opcion in respuesta.context["responsables_disponibles"]
        }
        self.assertEqual(opciones, {str(self.membresia.pk)})
        self.assertNotContains(respuesta, usuario_ajeno.username)
        self.assertNotContains(respuesta, self.ajena.titulo)
        self.assertEqual(respuesta.context["filtro_responsable"], "")

    def test_limpiar_y_filtrar_no_amplia_acceso_del_colaborador(self):
        self.membresia.rol = Membresia.Rol.COLABORADOR
        self.membresia.save()

        respuesta = self.abrir_panel({
            "responsable": "sin_asignar",
        })
        self.assertEqual(respuesta.context["total_activas"], 0)
        self.assertNotContains(respuesta, self.vencida.titulo)

        respuesta = self.abrir_panel()
        self.assertEqual(respuesta.context["total_activas"], 1)
        self.assertFalse(respuesta.context["hay_filtros"])
        self.assertContains(respuesta, self.para_hoy.titulo)
        self.assertNotContains(respuesta, self.vencida.titulo)
        self.assertNotContains(respuesta, self.ajena.titulo)

    def test_busqueda_titulo_parcial_sin_distinguir_mayusculas(self):
        respuesta = self.abrir_panel({"q": "  ASIGNADA  "})

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context["busqueda"], "ASIGNADA")
        self.assertTrue(respuesta.context["hay_filtros"])
        self.assertEqual(respuesta.context["total_activas"], 1)
        self.assertEqual(respuesta.context["total_para_hoy"], 1)
        self.assertContains(respuesta, self.para_hoy.titulo)
        self.assertNotContains(respuesta, self.vencida.titulo)

    def test_busqueda_por_empresa_y_consultante(self):
        sector = Sector.objects.create(
            organizacion=self.organizacion,
            nombre="Sector de prueba",
        )
        empresa = EmpresaProspectada.objects.create(
            organizacion=self.organizacion,
            sector=sector,
            nombre="Empresa Horizonte",
        )
        self.para_hoy.empresa = empresa
        self.para_hoy.nombre_consultante = "Teresa Molina"
        self.para_hoy.save()

        for termino in ("horizonte", "teresa"):
            with self.subTest(termino=termino):
                respuesta = self.abrir_panel({"q": termino})
                self.assertEqual(respuesta.status_code, 200)
                self.assertEqual(
                    respuesta.context["total_activas"], 1
                )
                ids = [
                    oportunidad.pk
                    for oportunidad in respuesta.context["calientes"]
                ]
                self.assertEqual(ids, [self.para_hoy.pk])

    def test_busqueda_se_combina_con_filtros(self):
        filtros = {
            "q": "asignada",
            "estado": Oportunidad.Estado.NUEVA,
            "canal": Oportunidad.Canal.WHATSAPP,
            "responsable": str(self.membresia.pk),
        }
        respuesta = self.abrir_panel(filtros)
        self.assertEqual(respuesta.context["total_activas"], 1)

        filtros["canal"] = Oportunidad.Canal.EMAIL
        respuesta = self.abrir_panel(filtros)
        for indicador in (
            "total_activas",
            "total_calientes",
            "total_vencidas",
            "total_para_hoy",
            "total_sin_fecha",
        ):
            self.assertEqual(respuesta.context[indicador], 0)

        self.assertFalse(respuesta.context["calientes"])
        self.assertFalse(respuesta.context["seguimientos"])
        self.assertFalse(respuesta.context["sin_fecha"])

    def test_busqueda_no_muestra_ajenas_ni_cerradas(self):
        for termino in ("privada", "Cerrada:"):
            with self.subTest(termino=termino):
                respuesta = self.abrir_panel({"q": termino})
                self.assertEqual(
                    respuesta.context["total_activas"], 0
                )
                self.assertFalse(respuesta.context["calientes"])
                self.assertFalse(respuesta.context["seguimientos"])
                self.assertFalse(respuesta.context["sin_fecha"])
                self.assertNotContains(respuesta, self.ajena.titulo)

        self.membresia.rol = Membresia.Rol.COLABORADOR
        self.membresia.save()

        respuesta = self.abrir_panel({"q": "vencida"})
        self.assertEqual(respuesta.context["total_activas"], 0)
        self.assertNotContains(respuesta, self.vencida.titulo)

    def test_busqueda_vacia_y_limpiar_restauran_resultados(self):
        respuesta = self.abrir_panel({"q": "zzzinexistente"})
        self.assertEqual(respuesta.context["total_activas"], 0)

        for filtros in ({"q": "   "}, {}):
            with self.subTest(filtros=filtros):
                respuesta = self.abrir_panel(filtros)
                self.assertEqual(respuesta.context["busqueda"], "")
                self.assertFalse(respuesta.context["hay_filtros"])
                self.assertEqual(
                    respuesta.context["total_activas"], 4
                )

    def test_busqueda_escapa_html_y_limita_longitud(self):
        texto = '<script>alert("prueba")</script>'
        respuesta = self.abrir_panel({"q": texto})

        self.assertEqual(respuesta.status_code, 200)
        self.assertNotContains(respuesta, texto)
        self.assertContains(respuesta, "&lt;script&gt;")
        self.assertEqual(respuesta.context["total_activas"], 0)

        respuesta = self.abrir_panel({"q": "x" * 250})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(len(respuesta.context["busqueda"]), 200)