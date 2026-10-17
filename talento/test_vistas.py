from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

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
            rol=Membresia.Rol.COLABORADOR,
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
            codename__in=("view_candidato", "view_documentocandidato"),
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
