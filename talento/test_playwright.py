from playwright.sync_api import sync_playwright

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.urls import reverse

from core.models import Membresia, Organizacion
from talento.models import Candidato, DocumentoCandidato


class FlujosNavegadorTests(StaticLiveServerTestCase):
    password = "clave-sintetica-playwright"

    @classmethod
    def setUpClass(cls):
        test_database = settings.DATABASES["default"]["TEST"]["NAME"]
        if (
            connection.vendor != "postgresql"
            or connection.settings_dict["NAME"] != test_database
        ):
            raise RuntimeError(
                "Playwright migrations may run only on Django's isolated PostgreSQL test database"
            )
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().setUpClass()

    def setUp(self):
        super().setUp()
        self.organizacion = Organizacion.objects.create(
            nombre="Organización sintética A",
            slug="playwright-sintetica-a",
        )
        self.organizacion_ajena = Organizacion.objects.create(
            nombre="Organización sintética B",
            slug="playwright-sintetica-b",
        )
        usuario_modelo = get_user_model()
        self.usuario = usuario_modelo.objects.create_user(
            username="playwright_a",
            password=self.password,
            is_staff=True,
        )
        self.usuario_ajeno = usuario_modelo.objects.create_user(
            username="playwright_b",
            password=self.password,
            is_staff=True,
        )
        Membresia.objects.create(
            usuario=self.usuario,
            organizacion=self.organizacion,
            rol=Membresia.Rol.ADMINISTRADOR,
            activa=True,
        )
        Membresia.objects.create(
            usuario=self.usuario_ajeno,
            organizacion=self.organizacion_ajena,
            rol=Membresia.Rol.ADMINISTRADOR,
            activa=True,
        )
        permisos = Permission.objects.filter(
            content_type__app_label="talento",
            codename__in=(
                "add_candidato",
                "change_candidato",
                "view_candidato",
                "add_documentocandidato",
                "change_documentocandidato",
                "view_documentocandidato",
            ),
        )
        self.usuario.user_permissions.add(*permisos)
        self.usuario_ajeno.user_permissions.add(*permisos)

        self.candidato = Candidato.objects.create(
            organizacion=self.organizacion,
            nombre="Candidata Sintética Alondra",
            profesion="Analista de calidad",
        )
        self.documento = DocumentoCandidato.objects.create(
            candidato=self.candidato,
            nombre="CV sintético Alondra",
            tipo=DocumentoCandidato.Tipo.CURRICULUM,
            archivo=SimpleUploadedFile(
                "cv-playwright-sintetico.pdf",
                "%PDF-1.4\nContenido PDF sintético para pruebas.\n%%EOF".encode(),
                content_type="application/pdf",
            ),
            es_cv_principal=True,
        )
        DocumentoCandidato.objects.filter(pk=self.documento.pk).update(
            texto_extraido="Experiencia con QuasarunicoPlaywright y control de calidad"
        )

        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch()
        self.context = self.browser.new_context()
        self.page = self.context.new_page()

    def tearDown(self):
        try:
            try:
                self.context.close()
            finally:
                try:
                    self.browser.close()
                finally:
                    self.playwright.stop()
        finally:
            super().tearDown()

    def iniciar_sesion(self, usuario):
        self.page.goto(f"{self.live_server_url}/admin/login/")
        self.page.locator("#id_username").fill(usuario.username)
        self.page.locator("#id_password").fill(self.password)
        self.page.locator("[type=submit]").click()

    def test_inicio_sesion_y_listado_autorizado(self):
        self.page.goto(f"{self.live_server_url}{reverse('talento_candidatos')}")
        self.page.locator("#id_username").wait_for(state="visible")
        self.page.locator("#id_username").fill(self.usuario.username)
        self.page.locator("#id_password").fill(self.password)
        self.page.locator("[type=submit]").click()

        self.page.get_by_role("heading", name="Talento").wait_for()
        self.assertTrue(
            self.page.get_by_role(
                "link", name="Candidata Sintética Alondra"
            ).is_visible()
        )

    def test_busqueda_cv_abre_coincidencias_resaltadas(self):
        self.iniciar_sesion(self.usuario)
        self.page.goto(f"{self.live_server_url}{reverse('talento_candidatos')}")
        self.page.locator("#busqueda").fill("QuasarunicoPlaywright")
        self.page.get_by_role("button", name="Buscar").click()

        self.page.get_by_role(
            "link", name="Candidata Sintética Alondra"
        ).wait_for()
        self.page.get_by_role("link", name="Ver coincidencias").click()
        resaltado = self.page.locator("mark.coincidencia")
        resaltado.wait_for(state="visible")
        self.assertEqual(resaltado.inner_text(), "QuasarunicoPlaywright")

    def test_otra_organizacion_no_ve_ficha_ni_descarga(self):
        self.iniciar_sesion(self.usuario_ajeno)
        ficha = self.page.goto(
            f"{self.live_server_url}{reverse('talento_detalle_candidato', args=[self.candidato.pk])}"
        )
        self.assertEqual(ficha.status, 404)

        descarga = self.page.request.get(
            f"{self.live_server_url}{reverse('descargar_documento_candidato', args=[self.documento.pk])}"
        )
        self.assertIn(descarga.status, (403, 404))
        self.assertNotIn("Contenido PDF sintético".encode(), descarga.body())
