from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import (
    Organizacion,
    Membresia,
    Sector,
    EmpresaProspectada,
    Contacto,
    Senal,
    Oportunidad,
)


@override_settings(ALLOWED_HOSTS=["testserver"])
class AislamientoAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        Usuario = get_user_model()

        cls.usuario = Usuario.objects.create_user(
            username="operador_prueba",
            is_staff=True,
        )
        cls.usuario.user_permissions.add(
            *Permission.objects.filter(content_type__app_label="core")
        )

        cls.superusuario = Usuario.objects.create_superuser(
            username="superusuario_prueba",
            email="prueba@example.com",
            password="solo-para-pruebas",
        )

        cls.organizacion_a = Organizacion.objects.create(
            nombre="Organización A",
            slug="organizacion-a",
        )
        cls.organizacion_b = Organizacion.objects.create(
            nombre="Organización B",
            slug="organizacion-b",
        )

        cls.membresia = Membresia.objects.create(
            organizacion=cls.organizacion_a,
            usuario=cls.usuario,
            rol=Membresia.Rol.COLABORADOR,
        )

        cls.sector_a = Sector.objects.create(
            organizacion=cls.organizacion_a,
            nombre="Sector A",
        )
        cls.sector_b = Sector.objects.create(
            organizacion=cls.organizacion_b,
            nombre="Sector B",
        )

        cls.empresa_a = EmpresaProspectada.objects.create(
            organizacion=cls.organizacion_a,
            sector=cls.sector_a,
            nombre="Empresa A",
        )
        cls.empresa_b = EmpresaProspectada.objects.create(
            organizacion=cls.organizacion_b,
            sector=cls.sector_b,
            nombre="Empresa B",
        )

        cls.contacto_a = Contacto.objects.create(
            empresa=cls.empresa_a,
            nombre="Contacto A",
        )
        cls.contacto_b = Contacto.objects.create(
            empresa=cls.empresa_b,
            nombre="Contacto B",
        )

        cls.senal_a = Senal.objects.create(
            empresa=cls.empresa_a,
            titulo="Señal A",
            fuente="Fuente de prueba",
            evidencia="Evidencia ficticia A",
            estado=Senal.Estado.VALIDADA,
        )
        cls.senal_b = Senal.objects.create(
            empresa=cls.empresa_b,
            titulo="Señal B",
            fuente="Fuente de prueba",
            evidencia="Evidencia ficticia B",
            estado=Senal.Estado.VALIDADA,
        )

        cls.oportunidad_a = Oportunidad.objects.create(
            organizacion=cls.organizacion_a,
            empresa=cls.empresa_a,
            titulo="Oportunidad A",
            origen=Oportunidad.Origen.PROSPECCION,
            canal=Oportunidad.Canal.WEB,
            necesidad="Necesidad ficticia A",
        )
        cls.oportunidad_b = Oportunidad.objects.create(
            organizacion=cls.organizacion_b,
            empresa=cls.empresa_b,
            titulo="Oportunidad B",
            origen=Oportunidad.Origen.PROSPECCION,
            canal=Oportunidad.Canal.WEB,
            necesidad="Necesidad ficticia B",
        )

    def setUp(self):
        self.client.force_login(self.usuario)

    def casos(self):
        return (
            ("sector", self.sector_a, self.sector_b),
            ("empresaprospectada", self.empresa_a, self.empresa_b),
            ("contacto", self.contacto_a, self.contacto_b),
            ("senal", self.senal_a, self.senal_b),
            ("oportunidad", self.oportunidad_a, self.oportunidad_b),
        )

    def test_listados_solo_muestran_la_organizacion_propia(self):
        for modelo, propio, ajeno in self.casos():
            with self.subTest(modelo=modelo):
                respuesta = self.client.get(
                    reverse(f"admin:core_{modelo}_changelist")
                )
                self.assertEqual(respuesta.status_code, 200)
                ids = set(
                    respuesta.context["cl"].queryset.values_list(
                        "pk", flat=True
                    )
                )
                self.assertIn(propio.pk, ids)
                self.assertNotIn(ajeno.pk, ids)

    def test_acceso_directo_no_muestra_registros_ajenos(self):
        for modelo, propio, ajeno in self.casos():
            with self.subTest(modelo=modelo):
                respuesta = self.client.get(
                    reverse(
                        f"admin:core_{modelo}_change",
                        args=[ajeno.pk],
                    )
                )
                self.assertEqual(respuesta.status_code, 302)
                self.assertNotIn("adminform", respuesta.context or {})

    def test_formulario_limita_organizaciones_y_empresas(self):
        respuesta = self.client.get(
            reverse("admin:core_oportunidad_add")
        )
        self.assertEqual(respuesta.status_code, 200)
        formulario = respuesta.context["adminform"].form

        organizaciones = set(
            formulario.fields["organizacion"].queryset.values_list(
                "pk", flat=True
            )
        )
        empresas = set(
            formulario.fields["empresa"].queryset.values_list(
                "pk", flat=True
            )
        )

        self.assertEqual(organizaciones, {self.organizacion_a.pk})
        self.assertEqual(empresas, {self.empresa_a.pk})

    def test_no_permite_mover_sector_a_otra_organizacion(self):
        respuesta = self.client.post(
            reverse(
                "admin:core_sector_change",
                args=[self.sector_a.pk],
            ),
            {
                "organizacion": self.organizacion_b.pk,
                "nombre": self.sector_a.nombre,
                "descripcion": "",
                "activo": "on",
                "_save": "Guardar",
            },
        )

        self.assertEqual(respuesta.status_code, 200)
        formulario = respuesta.context["adminform"].form
        self.assertIn("organizacion", formulario.errors)

        self.sector_a.refresh_from_db()
        self.assertEqual(
            self.sector_a.organizacion_id,
            self.organizacion_a.pk,
        )

    def test_autocompletado_no_muestra_empresas_ajenas(self):
        respuesta = self.client.get(
            reverse("admin:autocomplete"),
            {
                "app_label": "core",
                "model_name": "oportunidad",
                "field_name": "empresa",
                "term": "Empresa",
            },
        )

        self.assertEqual(respuesta.status_code, 200)
        ids = {
            resultado["id"]
            for resultado in respuesta.json()["results"]
        }
        self.assertEqual(ids, {str(self.empresa_a.pk)})

    def test_membresia_inactiva_bloquea_acceso(self):
        self.membresia.activa = False
        self.membresia.save()

        respuesta = self.client.get(
            reverse("admin:core_oportunidad_changelist")
        )
        self.assertEqual(respuesta.status_code, 403)

    def test_organizacion_inactiva_bloquea_acceso(self):
        self.organizacion_a.activa = False
        self.organizacion_a.save()

        respuesta = self.client.get(
            reverse("admin:core_oportunidad_changelist")
        )
        self.assertEqual(respuesta.status_code, 403)

    def test_operador_no_puede_administrar_membresias(self):
        respuesta = self.client.get(
            reverse("admin:core_membresia_add")
        )
        self.assertEqual(respuesta.status_code, 403)

        respuesta = self.client.get(
            reverse(
                "admin:core_membresia_change",
                args=[self.membresia.pk],
            )
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(
            respuesta.context["has_change_permission"]
        )

    def test_superusuario_ve_ambas_organizaciones(self):
        self.client.force_login(self.superusuario)

        respuesta = self.client.get(
            reverse("admin:core_oportunidad_changelist")
        )
        self.assertEqual(respuesta.status_code, 200)
        ids = set(
            respuesta.context["cl"].queryset.values_list(
                "pk", flat=True
            )
        )
        self.assertEqual(
            ids,
            {self.oportunidad_a.pk, self.oportunidad_b.pk},
        )