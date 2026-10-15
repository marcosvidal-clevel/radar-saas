from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .models import (
    Contacto,
    EmpresaProspectada,
    Membresia,
    Oportunidad,
    Organizacion,
    Sector,
    Senal,
)


@override_settings(ALLOWED_HOSTS=["testserver"])
class CreacionOportunidadTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        Usuario = get_user_model()

        cls.gestor = Usuario.objects.create_user(
            username="gestor_creacion",
            is_staff=True,
        )
        cls.otro_usuario = Usuario.objects.create_user(
            username="responsable_ajeno_creacion",
            is_staff=True,
        )
        cls.sin_permisos = Usuario.objects.create_user(
            username="sin_permisos_creacion",
            is_staff=True,
        )
        cls.superusuario = Usuario.objects.create_superuser(
            username="superusuario_creacion",
            email="creacion@example.com",
            password="solo-para-pruebas",
        )

        cls.gestor.user_permissions.add(
            *Permission.objects.filter(
                content_type__app_label="core"
            )
        )

        cls.organizacion = Organizacion.objects.create(
            nombre="Organización creación",
            slug="organizacion-creacion",
        )
        cls.otra_organizacion = Organizacion.objects.create(
            nombre="Organización ajena creación",
            slug="organizacion-ajena-creacion",
        )
        cls.membresia = Membresia.objects.create(
            usuario=cls.gestor,
            organizacion=cls.organizacion,
            rol=Membresia.Rol.ADMINISTRADOR,
        )
        cls.membresia_ajena = Membresia.objects.create(
            usuario=cls.otro_usuario,
            organizacion=cls.otra_organizacion,
            rol=Membresia.Rol.ADMINISTRADOR,
        )
        cls.membresia_sin_permisos = Membresia.objects.create(
            usuario=cls.sin_permisos,
            organizacion=cls.organizacion,
            rol=Membresia.Rol.ADMINISTRADOR,
        )

        sector = Sector.objects.create(
            organizacion=cls.organizacion,
            nombre="Sector propio creación",
        )
        sector_ajeno = Sector.objects.create(
            organizacion=cls.otra_organizacion,
            nombre="Sector ajeno creación",
        )
        cls.empresa = EmpresaProspectada.objects.create(
            organizacion=cls.organizacion,
            sector=sector,
            nombre="Empresa propia creación",
        )
        cls.otra_empresa = EmpresaProspectada.objects.create(
            organizacion=cls.organizacion,
            sector=sector,
            nombre="Segunda empresa propia creación",
        )
        cls.empresa_ajena = EmpresaProspectada.objects.create(
            organizacion=cls.otra_organizacion,
            sector=sector_ajeno,
            nombre="Empresa privada ajena creación",
        )
        cls.contacto = Contacto.objects.create(
            empresa=cls.empresa,
            nombre="Contacto propio creación",
        )
        cls.contacto_ajeno = Contacto.objects.create(
            empresa=cls.empresa_ajena,
            nombre="Contacto privado ajeno creación",
        )
        cls.senal = Senal.objects.create(
            empresa=cls.empresa,
            titulo="Señal validada creación",
            fuente="Fuente ficticia",
            evidencia="Evidencia ficticia",
            estado=Senal.Estado.VALIDADA,
        )
        cls.senal_pendiente = Senal.objects.create(
            empresa=cls.empresa,
            titulo="Señal pendiente creación",
            fuente="Fuente ficticia",
            evidencia="Evidencia ficticia",
        )

    def setUp(self):
        self.client.force_login(self.gestor)
        self.url = reverse("nueva_oportunidad")

    def datos(self, **cambios):
        datos = {
            "organizacion": str(self.organizacion.pk),
            "titulo": "Consulta creada en prueba",
            "origen": Oportunidad.Origen.CONSULTA_ENTRANTE,
            "canal": Oportunidad.Canal.WEB,
            "empresa": "",
            "contacto": "",
            "senal": "",
            "responsable": str(self.membresia.pk),
            "nombre_consultante": "Consultante ficticio",
            "email_consultante": "",
            "telefono_consultante": "",
            "necesidad": "Necesidad comercial ficticia",
            "estado": Oportunidad.Estado.NUEVA,
            "proxima_accion": "Revisar la consulta",
            "fecha_proxima_accion": "",
            "motivo_cierre": "",
            "notas": "",
        }
        datos.update(cambios)
        return datos

    def comprobar_rechazo(self, datos, campo):
        cantidad = Oportunidad.objects.count()
        respuesta = self.client.post(self.url, datos)

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn(
            campo,
            respuesta.context["formulario"].errors,
        )
        self.assertEqual(
            Oportunidad.objects.count(),
            cantidad,
        )
        return respuesta

    def test_formulario_solo_ofrece_datos_autorizados(self):
        respuesta = self.client.get(self.url)

        self.assertEqual(respuesta.status_code, 200)
        formulario = respuesta.context["formulario"]

        esperados = {
            "organizacion": {self.organizacion.pk},
            "empresa": {self.empresa.pk, self.otra_empresa.pk},
            "contacto": {self.contacto.pk},
            "senal": {self.senal.pk},
            "responsable": {self.membresia.pk, self.membresia_sin_permisos.pk},
        }
        for campo, ids_esperados in esperados.items():
            with self.subTest(campo=campo):
                ids = set(
                    formulario.fields[campo].queryset.values_list(
                        "pk", flat=True
                    )
                )
                self.assertEqual(ids, ids_esperados)

        self.assertNotContains(
            respuesta,
            self.empresa_ajena.nombre,
        )

    def test_crea_consulta_sin_empresa_y_abre_ficha(self):
        respuesta = self.client.post(
            self.url,
            self.datos(),
            follow=True,
        )

        oportunidad = Oportunidad.objects.get()
        self.assertRedirects(
            respuesta,
            reverse(
                "detalle_oportunidad",
                args=[oportunidad.pk],
            ),
        )
        self.assertIsNone(oportunidad.empresa_id)
        self.assertEqual(
            oportunidad.organizacion_id,
            self.organizacion.pk,
        )
        self.assertTrue(oportunidad.es_caliente)
        self.assertContains(
            respuesta,
            "Oportunidad creada correctamente.",
        )

    def test_crea_prospeccion_con_empresa_contacto_y_senal(self):
        respuesta = self.client.post(
            self.url,
            self.datos(
                origen=Oportunidad.Origen.PROSPECCION,
                empresa=str(self.empresa.pk),
                contacto=str(self.contacto.pk),
                senal=str(self.senal.pk),
            ),
        )

        self.assertEqual(respuesta.status_code, 302)
        oportunidad = Oportunidad.objects.get()
        self.assertEqual(oportunidad.empresa_id, self.empresa.pk)
        self.assertEqual(oportunidad.contacto_id, self.contacto.pk)
        self.assertEqual(oportunidad.senal_id, self.senal.pk)
        self.assertFalse(oportunidad.es_caliente)

    def test_prospeccion_sin_empresa_no_se_guarda(self):
        self.comprobar_rechazo(
            self.datos(origen=Oportunidad.Origen.PROSPECCION),
            "empresa",
        )

    def test_no_acepta_organizacion_ajena(self):
        self.comprobar_rechazo(
            self.datos(
                organizacion=str(self.otra_organizacion.pk)
            ),
            "organizacion",
        )

    def test_no_acepta_relaciones_ajenas(self):
        casos = (
            ("empresa", self.empresa_ajena.pk),
            ("contacto", self.contacto_ajeno.pk),
            ("responsable", self.membresia_ajena.pk),
        )
        for campo, identificador in casos:
            with self.subTest(campo=campo):
                self.comprobar_rechazo(
                    self.datos(**{campo: str(identificador)}),
                    campo,
                )

    def test_contacto_y_senal_deben_coincidir_con_empresa(self):
        for campo, identificador in (
            ("contacto", self.contacto.pk),
            ("senal", self.senal.pk),
        ):
            with self.subTest(campo=campo):
                self.comprobar_rechazo(
                    self.datos(
                        empresa=str(self.otra_empresa.pk),
                        **{campo: str(identificador)},
                    ),
                    campo,
                )

    def test_senal_pendiente_no_se_acepta(self):
        self.comprobar_rechazo(
            self.datos(
                empresa=str(self.empresa.pk),
                senal=str(self.senal_pendiente.pk),
            ),
            "senal",
        )

    def test_cierre_sin_motivo_no_se_guarda(self):
        self.comprobar_rechazo(
            self.datos(
                estado=Oportunidad.Estado.PERDIDA,
                motivo_cierre="   ",
            ),
            "motivo_cierre",
        )

    def test_correo_invalido_conserva_datos_sin_crear(self):
        respuesta = self.comprobar_rechazo(
            self.datos(email_consultante="correo-invalido"),
            "email_consultante",
        )
        self.assertEqual(
            respuesta.context["formulario"]["titulo"].value(),
            "Consulta creada en prueba",
        )

    def test_supervisor_puede_crear(self):
        self.membresia.rol = Membresia.Rol.SUPERVISOR
        self.membresia.save()

        respuesta = self.client.post(self.url, self.datos())

        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(Oportunidad.objects.count(), 1)

    def test_colaborador_no_puede_abrir_ni_crear(self):
        self.membresia.rol = Membresia.Rol.COLABORADOR
        self.membresia.save()

        consulta = self.client.get(self.url)
        envio = self.client.post(self.url, self.datos())

        self.assertEqual(consulta.status_code, 403)
        self.assertEqual(envio.status_code, 403)
        self.assertEqual(Oportunidad.objects.count(), 0)

        panel = self.client.get(reverse("panel_comercial"))
        self.assertEqual(panel.status_code, 200)
        self.assertNotContains(
            panel,
            f'href="{self.url}"',
        )

    def test_usuario_sin_permisos_no_crea(self):
        self.client.force_login(self.sin_permisos)

        respuesta = self.client.post(self.url, self.datos())

        self.assertEqual(respuesta.status_code, 403)
        self.assertEqual(Oportunidad.objects.count(), 0)

    def test_membresia_u_organizacion_inactiva_bloquean(self):
        self.membresia.activa = False
        self.membresia.save()

        respuesta = self.client.post(self.url, self.datos())
        self.assertEqual(respuesta.status_code, 403)
        self.assertEqual(Oportunidad.objects.count(), 0)

        self.membresia.activa = True
        self.membresia.save()
        self.organizacion.activa = False
        self.organizacion.save()

        respuesta = self.client.post(self.url, self.datos())
        self.assertEqual(respuesta.status_code, 403)
        self.assertEqual(Oportunidad.objects.count(), 0)

    def test_rol_se_aplica_a_cada_organizacion(self):
        Membresia.objects.create(
            usuario=self.gestor,
            organizacion=self.otra_organizacion,
            rol=Membresia.Rol.COLABORADOR,
        )

        self.comprobar_rechazo(
            self.datos(
                organizacion=str(self.otra_organizacion.pk),
                responsable="",
            ),
            "organizacion",
        )

    def test_superusuario_puede_crear_en_otra_organizacion(self):
        self.client.force_login(self.superusuario)

        respuesta = self.client.post(
            self.url,
            self.datos(
                organizacion=str(self.otra_organizacion.pk),
                empresa=str(self.empresa_ajena.pk),
                responsable=str(self.membresia_ajena.pk),
            ),
        )

        self.assertEqual(respuesta.status_code, 302)
        oportunidad = Oportunidad.objects.get()
        self.assertEqual(
            oportunidad.organizacion_id,
            self.otra_organizacion.pk,
        )

    def test_sin_sesion_redirige_al_inicio_de_sesion(self):
        self.client.logout()

        respuesta = self.client.post(self.url, self.datos())

        self.assertEqual(respuesta.status_code, 302)
        self.assertIn(reverse("admin:login"), respuesta.url)
        self.assertEqual(Oportunidad.objects.count(), 0)

    def test_creacion_requiere_token_csrf(self):
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.gestor)

        respuesta = cliente.post(self.url, self.datos())

        self.assertEqual(respuesta.status_code, 403)
        self.assertEqual(Oportunidad.objects.count(), 0)

    def test_panel_enlaza_al_formulario_de_radar(self):
        respuesta = self.client.get(reverse("panel_comercial"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(
            respuesta,
            f'href="{self.url}"',
        )
        self.assertNotContains(
            respuesta,
            reverse("admin:core_oportunidad_add"),
        )