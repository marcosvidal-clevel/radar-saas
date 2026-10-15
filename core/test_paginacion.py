from datetime import date, timedelta
from html.parser import HTMLParser
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import (
    Organizacion,
    Membresia,
    Sector,
    EmpresaProspectada,
    Oportunidad,
)


class EnlacesHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.enlaces = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.enlaces.append(href)


@override_settings(ALLOWED_HOSTS=["testserver"])
class PaginacionPanelTests(TestCase):
    HOY = date(2026, 10, 14)

    @classmethod
    def setUpTestData(cls):
        Usuario = get_user_model()
        cls.usuario = Usuario.objects.create_user(
            username="gestor_paginacion",
            is_staff=True,
        )
        cls.usuario.user_permissions.add(
            *Permission.objects.filter(content_type__app_label="core")
        )

        cls.organizacion = Organizacion.objects.create(
            nombre="Organización de paginación",
            slug="organizacion-paginacion",
        )
        cls.otra_organizacion = Organizacion.objects.create(
            nombre="Organización privada",
            slug="organizacion-privada",
        )
        cls.membresia = Membresia.objects.create(
            usuario=cls.usuario,
            organizacion=cls.organizacion,
            rol=Membresia.Rol.ADMINISTRADOR,
        )
        sector = Sector.objects.create(
            organizacion=cls.organizacion,
            nombre="Ingeniería",
        )
        empresa = EmpresaProspectada.objects.create(
            organizacion=cls.organizacion,
            sector=sector,
            nombre="Empresa de paginación",
        )

        cls.ids = []
        for numero in range(25):
            oportunidad = Oportunidad.objects.create(
                organizacion=cls.organizacion,
                empresa=empresa,
                titulo=f"Lote & prueba {numero:02d}",
                origen=Oportunidad.Origen.PROSPECCION,
                canal=Oportunidad.Canal.WEB,
                estado=Oportunidad.Estado.NUEVA,
                necesidad="Necesidad ficticia",
                responsable=cls.membresia,
                fecha_proxima_accion=cls.HOY + timedelta(days=7),
            )
            cls.ids.append(oportunidad.pk)

        # Misma fecha para comprobar el desempate por identificador.
        Oportunidad.objects.filter(pk__in=cls.ids).update(
            creada_en=timezone.now()
        )

        cls.ajena = Oportunidad.objects.create(
            organizacion=cls.otra_organizacion,
            titulo="Registro privado ajeno",
            origen=Oportunidad.Origen.CONSULTA_ENTRANTE,
            canal=Oportunidad.Canal.WEB,
            necesidad="Necesidad privada",
        )
        cls.cerrada = Oportunidad.objects.create(
            organizacion=cls.organizacion,
            titulo="Registro cerrado ganado",
            origen=Oportunidad.Origen.CONSULTA_ENTRANTE,
            canal=Oportunidad.Canal.WEB,
            necesidad="Necesidad ficticia",
            estado=Oportunidad.Estado.GANADA,
        )

    def setUp(self):
        self.client.force_login(self.usuario)
        parche = patch(
            "core.views.timezone.localdate",
            return_value=self.HOY,
        )
        parche.start()
        self.addCleanup(parche.stop)

    def abrir_panel(self, parametros=None):
        return self.client.get(
            reverse("panel_comercial"),
            parametros or {},
        )

    def ids_pagina(self, respuesta):
        return [
            oportunidad.pk
            for oportunidad in respuesta.context["pagina_oportunidades"]
        ]

    def test_paginas_sin_duplicados_y_total_completo(self):
        primera = self.abrir_panel()
        segunda = self.abrir_panel({"pagina": "2"})

        self.assertEqual(primera.status_code, 200)
        self.assertEqual(segunda.status_code, 200)

        ids_primera = self.ids_pagina(primera)
        ids_segunda = self.ids_pagina(segunda)
        esperados = sorted(self.ids, reverse=True)

        self.assertEqual(ids_primera, esperados[:20])
        self.assertEqual(ids_segunda, esperados[20:])
        self.assertFalse(set(ids_primera) & set(ids_segunda))
        self.assertEqual(
            set(ids_primera + ids_segunda),
            set(self.ids),
        )

        for respuesta in (primera, segunda):
            self.assertEqual(
                respuesta.context["total_activas"], 25
            )
            self.assertEqual(
                respuesta.context["pagina_oportunidades"].paginator.count,
                25,
            )
            self.assertNotContains(respuesta, self.ajena.titulo)
            self.assertNotContains(respuesta, self.cerrada.titulo)

    def test_prospeccion_futura_aparece_en_lista_general(self):
        respuesta = self.abrir_panel()

        self.assertEqual(len(self.ids_pagina(respuesta)), 20)
        self.assertContains(
            respuesta,
            "Todas las oportunidades activas",
        )
        self.assertContains(respuesta, "Prospección")
        self.assertEqual(respuesta.context["total_calientes"], 0)
        self.assertEqual(respuesta.context["total_vencidas"], 0)
        self.assertEqual(respuesta.context["total_para_hoy"], 0)
        self.assertEqual(respuesta.context["total_sin_fecha"], 0)
        self.assertFalse(respuesta.context["seguimientos"])

    def test_enlace_siguiente_conserva_busqueda_y_filtros(self):
        parametros = {
            "q": "Lote & prueba",
            "estado": Oportunidad.Estado.NUEVA,
            "canal": Oportunidad.Canal.WEB,
            "responsable": str(self.membresia.pk),
        }
        respuesta = self.abrir_panel(parametros)

        lector = EnlacesHTML()
        lector.feed(respuesta.content.decode())
        siguientes = [
            enlace
            for enlace in lector.enlaces
            if parse_qs(urlsplit(enlace).query).get("pagina") == ["2"]
        ]
        self.assertEqual(len(siguientes), 1)

        enlace = siguientes[0]
        consulta = parse_qs(urlsplit(enlace).query)
        for nombre, valor in parametros.items():
            self.assertEqual(consulta[nombre], [str(valor)])

        self.assertEqual(
            urlsplit(enlace).fragment,
            "oportunidades-activas",
        )

        segunda = self.client.get(
            reverse("panel_comercial") + "?" + urlsplit(enlace).query
        )
        self.assertEqual(segunda.status_code, 200)
        self.assertEqual(len(self.ids_pagina(segunda)), 5)
        self.assertEqual(segunda.context["total_activas"], 25)

    def test_pagina_invalida_no_produce_error(self):
        casos = (
            ("texto", 1),
            ("0", 2),
            ("-1", 2),
            ("999", 2),
        )
        for valor, esperada in casos:
            with self.subTest(pagina=valor):
                respuesta = self.abrir_panel({"pagina": valor})
                self.assertEqual(respuesta.status_code, 200)
                self.assertEqual(
                    respuesta.context["pagina_oportunidades"].number,
                    esperada,
                )
                self.assertNotContains(respuesta, self.ajena.titulo)

    def test_colaborador_solo_pagina_sus_asignadas(self):
        self.membresia.rol = Membresia.Rol.COLABORADOR
        self.membresia.save()

        Oportunidad.objects.filter(
            pk__in=self.ids[1:]
        ).update(responsable=None)

        respuesta = self.abrir_panel({"pagina": "2"})

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(
            self.ids_pagina(respuesta),
            [self.ids[0]],
        )
        self.assertEqual(respuesta.context["total_activas"], 1)
        self.assertEqual(
            respuesta.context["pagina_oportunidades"].paginator.num_pages,
            1,
        )
        self.assertFalse(respuesta.context["puede_crear"])
        self.assertNotContains(respuesta, self.ajena.titulo)
        self.assertNotContains(
            respuesta,
            reverse(
                "admin:core_oportunidad_change",
                args=[self.ids[1]],
            ),
        )

    def test_sin_resultados_muestra_lista_vacia(self):
        respuesta = self.abrir_panel({
            "q": "zzzinexistente",
            "pagina": "99",
        })

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context["total_activas"], 0)
        self.assertEqual(self.ids_pagina(respuesta), [])
        self.assertContains(
            respuesta,
            "No hay oportunidades activas para esta selección.",
        )

    def test_cambiar_filtros_reinicia_paginacion_del_formulario(self):
        respuesta = self.abrir_panel({"pagina": "2"})

        self.assertEqual(respuesta.status_code, 200)
        self.assertNotContains(respuesta, 'name="pagina"')
        self.assertContains(respuesta, 'name="q"')
        self.assertContains(respuesta, 'name="estado"')
        self.assertContains(respuesta, 'name="canal"')
        self.assertContains(respuesta, 'name="responsable"')