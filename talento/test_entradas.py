import hashlib
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import Organizacion, Membresia
from talento.entradas_forms import EntradaForm
from talento.entradas_services import guardar_entrada, resolver_entrada
from talento.models import (
    EntradaPendiente, RevisionEntrada, Candidato, DocumentoCandidato,
    CandidatoProcedencia, DocumentoProcedencia,
)


class EntradasTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = Organizacion.objects.create(nombre="Organización sintética", slug="bandeja-a")
        cls.otra = Organizacion.objects.create(nombre="Otra sintética", slug="bandeja-b")
        cls.user = get_user_model().objects.create_user(username="gestor-bandeja", is_staff=True)
        cls.ajeno = get_user_model().objects.create_user(username="ajeno-bandeja", is_staff=True)
        permissions = Permission.objects.filter(content_type__app_label="talento")
        for user, org in ((cls.user, cls.org), (cls.ajeno, cls.otra)):
            user.user_permissions.add(*permissions)
            Membresia.objects.create(usuario=user, organizacion=org, rol="admin")

    def setUp(self):
        media = tempfile.TemporaryDirectory(prefix="radar-entradas-tests-")
        self.addCleanup(media.cleanup)
        self.media = Path(media.name)
        settings = override_settings(MEDIA_ROOT=media.name)
        settings.enable()
        self.addCleanup(settings.disable)

    def entrada(self, **kwargs):
        data = dict(origen_importacion="fuente-sintetica", identificador_origen="fila-1", clave_documental="CV_001.pdf")
        data.update(kwargs)
        return guardar_entrada(usuario=self.user, organizacion=self.org, datos=data,
            archivo=SimpleUploadedFile("CV_001.pdf", b"%PDF-1.4 sintetico"), fuente="Resumen sintético")

    def confirmar(self, entrada, **kwargs):
        data = dict(nombre="Persona sintética", identidad_estado="confirmado", tipo_documento="curriculum", clasificacion_confirmada=True)
        data.update(kwargs)
        return guardar_entrada(usuario=self.user, organizacion=self.org, entrada_id=entrada.pk,
                               datos=data, fuente="Encabezado revisado visualmente, página 1")

    def resolver(self, entrada, **kwargs):
        return resolver_entrada(entrada_id=entrada.pk, usuario=self.user, fuente="Identidad y destino corroborados documentalmente", **kwargs)

    def test_archivo_sin_nombre_no_crea_persona_ni_extrae(self):
        with patch.object(DocumentoCandidato, "extraer_texto") as extract:
            entry = self.entrada(correo_remitente="portal@chiletrabajos.cl", limitacion_lectura="Sin texto nativo", seguimiento="sin_medio_contacto")
        extract.assert_not_called()
        self.assertEqual(entry.nombre, "")
        self.assertEqual(Candidato.objects.count(), 0)
        self.assertEqual(DocumentoCandidato.objects.count(), 0)
        self.assertEqual(entry.sha256, hashlib.sha256(b"%PDF-1.4 sintetico").hexdigest())
        with entry.archivo.open("rb") as f:
            self.assertEqual(f.read(), b"%PDF-1.4 sintetico")
        self.assertEqual(entry.revisiones.get().usuario, self.user)
        self.assertEqual(entry.revisiones.get().datos["identidad_estado"], "no_consta")

    def test_confirmaciones_independientes_y_auditoria(self):
        entry = self.entrada()
        self.confirmar(entry, profesion="Actividad propuesta", profesion_estado="no_confirmado", ciudad="Ciudad propuesta", ubicacion_estado="no_confirmado", telefono_estado="ausente", email_estado="ausente", informacion_por_completar="Corroborar profesión", seguimiento="requiere_contactar")
        entry.refresh_from_db()
        self.assertEqual(entry.revisiones.count(), 2)
        self.assertEqual(entry.profesion_estado, "no_confirmado")
        revision = entry.revisiones.last()
        self.assertTrue(revision.fecha)
        self.assertEqual(revision.usuario, self.user)
        self.assertIn("página 1", revision.fuente)
        self.assertEqual(revision.datos["nombre"], "Persona sintética")
        self.assertEqual(Candidato.objects.count(), 0)

    def test_resolver_exige_identidad_y_clasificacion(self):
        entry = self.entrada()
        with self.assertRaises(ValidationError):
            self.resolver(entry)
        self.confirmar(entry, clasificacion_confirmada=False)
        with self.assertRaises(ValidationError):
            self.resolver(entry)
        self.assertFalse(Candidato.objects.exists())

    def test_resolucion_posterior_conserva_original_y_contactos_no_confirmados(self):
        entry = self.entrada()
        original = entry.archivo.name
        self.confirmar(entry, profesion="Arquitectura", profesion_estado="confirmado",
            email="no-confirmado@example.test", email_estado="no_confirmado",
            telefono="123456789", telefono_estado="no_confirmado")
        resolved = self.resolver(entry)
        self.assertEqual(resolved.seguimiento, "resuelto")
        self.assertEqual(resolved.candidato.nombre, "Persona sintética")
        self.assertEqual(resolved.candidato.email, "")
        self.assertEqual(resolved.candidato.telefono, "")
        self.assertEqual(resolved.candidato.profesion, "Arquitectura")
        self.assertEqual(resolved.candidato.ciudad, "")
        self.assertEqual(resolved.archivo.name, original)
        with resolved.documento.archivo.open("rb") as f:
            self.assertEqual(hashlib.sha256(f.read()).hexdigest(), entry.sha256)
        self.assertEqual(entry.revisiones.count(), 3)
        self.assertTrue(DocumentoProcedencia.objects.filter(documento=resolved.documento, identificador_origen="CV_001.pdf").exists())
        counts = (Candidato.objects.count(), DocumentoCandidato.objects.count(), RevisionEntrada.objects.count())
        self.resolver(resolved, candidato_id=resolved.candidato_id)
        self.assertEqual(counts, (Candidato.objects.count(), DocumentoCandidato.objects.count(), RevisionEntrada.objects.count()))

    def test_portal_no_es_contacto_personal_y_no_se_infiere_nombre(self):
        with self.assertRaises(ValidationError):
            self.entrada(email="avisos@chiletrabajos.cl", email_estado="disponible")
        entry = self.entrada(email="avisos@chiletrabajos.cl", email_estado="no_confirmado")
        self.assertEqual(entry.nombre, "")
        self.assertEqual(entry.identidad_estado, "no_consta")

    def test_evaluacion_rechazada_y_no_crea_archivo(self):
        with self.assertRaises(ValidationError):
            self.entrada(tipo_documento="evaluacion")
        self.assertEqual(list(self.media.rglob("*.pdf")), [])
        self.assertFalse(EntradaPendiente.objects.exists())

    def test_archivo_y_procedencia_no_se_sustituyen(self):
        entry = self.entrada()
        with self.assertRaises(ValidationError):
            guardar_entrada(usuario=self.user, organizacion=self.org, entrada_id=entry.pk,
                datos={"identificador_origen": "otro"}, fuente="Cambio")
        with self.assertRaises(ValidationError):
            guardar_entrada(usuario=self.user, organizacion=self.org, entrada_id=entry.pk,
                datos={}, archivo=SimpleUploadedFile("nuevo.pdf", b"otro"), fuente="Cambio")
        self.assertEqual(entry.revisiones.count(), 1)

    def test_duplicado_de_procedencia_no_sobrescribe_original(self):
        entry = self.entrada()
        with self.assertRaises(ValidationError):
            self.entrada()
        self.assertEqual(EntradaPendiente.objects.count(), 1)
        self.assertEqual(len(list(self.media.rglob("*.pdf"))), 1)
        self.assertTrue(Path(entry.archivo.path).is_file())

    def test_no_resuelve_por_hash_nombre_o_correo_automaticamente(self):
        entry = self.confirmar(self.entrada())
        Candidato.objects.create(organizacion=self.org, nombre="Persona sintética")
        with self.assertRaisesMessage(ValidationError, "duplicado"):
            self.resolver(entry)
        self.assertFalse(DocumentoCandidato.objects.exists())
        entry.refresh_from_db()
        self.assertNotEqual(entry.seguimiento, "resuelto")

    def test_vincular_destino_explicito_sin_sobrescribir(self):
        entry = self.confirmar(self.entrada())
        candidate = Candidato.objects.create(organizacion=self.org, nombre="Persona sintética", notas="Conservar", profesion="")
        self.confirmar(entry, profesion="Arquitectura", profesion_estado="confirmado")
        resolved = self.resolver(entry, candidato_id=candidate.pk)
        self.assertEqual(resolved.candidato_id, candidate.pk)
        candidate.refresh_from_db()
        self.assertEqual(candidate.notas, "Conservar")
        self.assertEqual(candidate.profesion, "")
        self.assertEqual(Candidato.objects.count(), 1)

    def test_conflicto_destino_no_sobrescribe(self):
        entry = self.confirmar(self.entrada(), email="persona@example.test", email_estado="disponible")
        candidate = Candidato.objects.create(organizacion=self.org, nombre="Persona sintética", email="otra@example.test")
        with self.assertRaises(ValidationError):
            self.resolver(entry, candidato_id=candidate.pk)
        candidate.refresh_from_db()
        self.assertEqual(candidate.email, "otra@example.test")
        self.assertFalse(DocumentoCandidato.objects.exists())

    def test_reutiliza_documento_mismo_candidato_y_preserva_principal(self):
        first = self.resolver(self.confirmar(self.entrada()))
        second = self.confirmar(self.entrada(identificador_origen="fila-2"))
        result = self.resolver(second, candidato_id=first.candidato_id)
        self.assertEqual(result.documento_id, first.documento_id)
        self.assertEqual(DocumentoCandidato.objects.count(), 1)
        self.assertEqual(DocumentoProcedencia.objects.count(), 2)
        first.documento.refresh_from_db()
        self.assertTrue(first.documento.es_cv_principal)

    def test_hash_en_otra_persona_bloquea_sin_reasignar(self):
        first = self.resolver(self.confirmar(self.entrada()))
        second = self.confirmar(self.entrada(identificador_origen="fila-2"), nombre="Otra persona sintética")
        candidate = Candidato.objects.create(organizacion=self.org, nombre="Otra persona sintética")
        with self.assertRaises(ValidationError):
            self.resolver(second, candidato_id=candidate.pk)
        first.documento.refresh_from_db()
        self.assertEqual(first.documento.candidato_id, first.candidato_id)

    def test_aislamiento_servicios_y_formulario(self):
        entry = self.confirmar(self.entrada())
        with self.assertRaises(PermissionDenied):
            resolver_entrada(entrada_id=entry.pk, usuario=self.ajeno, fuente="Intento ajeno")
        candidate = Candidato.objects.create(organizacion=self.otra, nombre="Persona sintética")
        with self.assertRaises(ValidationError):
            self.resolver(entry, candidato_id=candidate.pk)
        form = EntradaForm(usuario=self.user)
        self.assertEqual(list(form.fields["organizacion"].queryset), [self.org])

    def test_permisos_resolver_exige_creacion_documental(self):
        entry = self.confirmar(self.entrada())
        user = get_user_model().objects.get(pk=self.user.pk)
        user.user_permissions.remove(Permission.objects.get(content_type__app_label="talento", codename="add_documentocandidato"))
        with self.assertRaises(PermissionDenied):
            resolver_entrada(entrada_id=entry.pk, usuario=user, fuente="Revisión")
        self.assertFalse(Candidato.objects.exists())

    def test_colaborador_consulta_no_modifica(self):
        entry = self.entrada(tipo_documento="curriculum", clasificacion_confirmada=True)
        Membresia.objects.filter(usuario=self.user).update(rol="colaborador")
        with self.assertRaises(PermissionDenied):
            self.confirmar(entry)
        self.client.force_login(self.user)
        response = self.client.get(reverse("entrada_descargar", args=[entry.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), b"%PDF-1.4 sintetico")
        self.assertTrue(response.closed)

    def test_descarga_privada_y_bandeja_aislada(self):
        entry = self.entrada()
        self.assertEqual(self.client.get(reverse("entrada_descargar", args=[entry.pk])).status_code, 302)
        self.client.force_login(self.ajeno)
        self.assertEqual(self.client.get(reverse("entrada_descargar", args=[entry.pk])).status_code, 404)
        self.assertNotContains(self.client.get(reverse("entradas_pendientes")), entry.identificador_origen)
        self.client.force_login(self.user)
        response = self.client.get(reverse("entrada_descargar", args=[entry.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), b"%PDF-1.4 sintetico")
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertContains(self.client.get(reverse("entrada_detalle", args=[entry.pk])), "No consta")

    def test_rollback_resolucion_preserva_original_y_no_deja_copia(self):
        entry = self.confirmar(self.entrada())
        original = entry.archivo.path
        with patch("talento.entradas_services.auditar", side_effect=RuntimeError("Fallo sintético")):
            with self.assertRaises(RuntimeError):
                self.resolver(entry)
        self.assertFalse(Candidato.objects.exists())
        self.assertFalse(DocumentoCandidato.objects.exists())
        self.assertFalse(CandidatoProcedencia.objects.exists())
        self.assertFalse(DocumentoProcedencia.objects.exists())
        self.assertEqual([str(p) for p in self.media.rglob("*.pdf")], [original])
        entry.refresh_from_db()
        self.assertNotEqual(entry.seguimiento, "resuelto")

    def test_fuente_obligatoria_y_estado_resuelto_no_manual(self):
        entry = self.entrada()
        with self.assertRaises(ValidationError):
            guardar_entrada(usuario=self.user, organizacion=self.org, entrada_id=entry.pk,
                            datos={"seguimiento": "resuelto"}, fuente="Intento")
        with self.assertRaises(ValidationError):
            guardar_entrada(usuario=self.user, organizacion=self.org, entrada_id=entry.pk, datos={}, fuente="")
        self.assertEqual(RevisionEntrada.objects.count(), 1)

    def test_archivo_privado_sin_url_publica(self):
        entry = self.entrada()
        self.assertEqual(Path(entry.archivo.path).stat().st_mode & 0o777, 0o600)
        self.assertEqual(Path(entry.archivo.path).parent.stat().st_mode & 0o777, 0o700)
        with self.assertRaises(ValueError):
            _ = entry.archivo.url

    def test_interfaz_crea_revisa_y_resuelve(self):
        self.client.force_login(self.user)
        data = dict(organizacion=self.org.pk, origen_importacion="sintetico-web",
            identificador_origen="web-1", clave_documental="CV_001.pdf",
            identidad_estado="no_consta", profesion_estado="no_consta", ubicacion_estado="no_consta",
            email_estado="no_confirmado", telefono_estado="no_confirmado", tipo_documento="otro",
            seguimiento="pendiente", fuente_revision="Resumen sintético, recepción",
            archivo=SimpleUploadedFile("CV_001.pdf", b"%PDF-1.4 sintetico"))
        response = self.client.post(reverse("entrada_nueva"), data)
        self.assertEqual(response.status_code, 302)
        entry = EntradaPendiente.objects.get()
        self.assertRedirects(response, reverse("entrada_detalle", args=[entry.pk]))
        self.assertFalse(Candidato.objects.exists())
        data.pop("archivo")
        data.update(nombre="Perfil web sintético", identidad_estado="confirmado", tipo_documento="otro",
                    clasificacion_confirmada="on", fuente_revision="Identidad confirmada visualmente")
        response = self.client.post(reverse("entrada_editar", args=[entry.pk]), data)
        self.assertEqual(response.status_code, 302)
        response = self.client.post(reverse("entrada_resolver", args=[entry.pk]), {"fuente": "Confirmación documental explícita"})
        self.assertEqual(response.status_code, 302)
        entry.refresh_from_db()
        self.assertEqual(entry.seguimiento, "resuelto")
        self.assertEqual(entry.documento.tipo, "otro")
        self.assertEqual(entry.documento.estado_extraccion, "no_aplica")
        self.assertEqual(entry.revisiones.count(), 3)

    def test_interfaz_csrf_y_permisos_ajenos(self):
        from django.test import Client
        entry = self.entrada()
        self.client.force_login(self.ajeno)
        self.assertEqual(self.client.get(reverse("entrada_editar", args=[entry.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("entrada_resolver", args=[entry.pk]), {"fuente": "Ajena"}).status_code, 404)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(reverse("entrada_resolver", args=[entry.pk]), {"fuente": "Sin CSRF"}).status_code, 403)

    def test_huella_alterada_bloquea_resolucion(self):
        entry = self.confirmar(self.entrada())
        Path(entry.archivo.path).write_bytes(b"alteracion sintetica")
        with self.assertRaisesMessage(ValidationError, "SHA-256"):
            self.resolver(entry)
        self.assertFalse(Candidato.objects.exists())

    def test_archivo_otro_org_no_es_coincidencia_ni_autorizacion(self):
        entry = self.confirmar(self.entrada())
        other = Candidato.objects.create(organizacion=self.otra, nombre="Persona sintética")
        document = DocumentoCandidato.objects.create(candidato=other, nombre="Otro", tipo="otro",
            archivo=SimpleUploadedFile("otro.pdf", b"%PDF-1.4 sintetico"))
        self.assertEqual(document.sha256, entry.sha256)
        resolved = self.resolver(entry)
        self.assertNotEqual(resolved.candidato_id, other.pk)

    def test_actualizacion_sin_fuente_no_confirma_ni_modifica(self):
        entry = self.entrada()
        with self.assertRaises(ValidationError):
            guardar_entrada(usuario=self.user, organizacion=self.org, entrada_id=entry.pk,
                            datos={"nombre": "Propuesta", "identidad_estado": "confirmado"}, fuente="")
        entry.refresh_from_db()
        self.assertEqual(entry.identidad_estado, "no_consta")
        self.assertEqual(entry.nombre, "")

    def test_no_reclasifica_evaluacion_existente_para_eludir_restricciones(self):
        entry = self.confirmar(self.entrada(), tipo_documento="otro")
        candidate = Candidato.objects.create(organizacion=self.org, nombre="Persona sintética")
        evaluation = DocumentoCandidato.objects.create(candidato=candidate, nombre="Evaluación sintética", tipo="evaluacion",
            archivo=SimpleUploadedFile("evaluacion.pdf", b"%PDF-1.4 sintetico"))
        with self.assertRaisesMessage(ValidationError, "evaluación"):
            self.resolver(entry, candidato_id=candidate.pk)
        self.assertEqual(DocumentoCandidato.objects.count(), 1)
        evaluation.refresh_from_db()
        self.assertEqual(evaluation.tipo, "evaluacion")
        self.assertFalse(CandidatoProcedencia.objects.exists())
