import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError, close_old_connections, connections, transaction
from django.test import Client, TestCase, TransactionTestCase, override_settings, skipUnlessDBFeature
from django.urls import reverse

from core.models import Oportunidad, Organizacion
from .models import RecepcionComercial


TOKEN = "synthetic-test-token-at-least-32-characters"
OTHER_TOKEN = "another-synthetic-test-token-with-32-characters"


class CommercialIngressTests(TestCase):
    def setUp(self):
        self.org = Organizacion.objects.create(nombre="Org sintética", slug="test-org")
        self.other = Organizacion.objects.create(nombre="Otra org", slug="other-org")
        self.config = {"piloto": self.entry(self.org, TOKEN),
                       "otro": self.entry(self.other, OTHER_TOKEN)}
        self.override = override_settings(RADAR_MAKE_INGRESS=self.config)
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.url = reverse("make_comercial", args=["piloto"])
        self.payload = {
            "schema_version": 1, "source_message_id": "synthetic-001",
            "test_mode": True, "received_at": "2026-10-24T12:00:00Z",
            "nombre": "Contacto sintético", "empresa": "Empresa ficticia",
            "email": "contact@example.test", "telefono": "+56000000000",
            "necesidad": "Gerencia técnica", "sector": "Infraestructura",
            "consulta": "Consulta sintética; no contactar",
            "autorizacion_contacto": "Texto sintético de autorización para responder",
        }

    def entry(self, org, token, test=True):
        return {"organizacion_id": org.pk, "buzon": "forms@example.test",
                "test_mode": test, "token_sha256": hashlib.sha256(token.encode()).hexdigest()}

    def post(self, payload=None, *, token=TOKEN, url=None, secure=True):
        return self.client.post(
            url or self.url, json.dumps(self.payload if payload is None else payload),
            content_type="application/json", secure=secure,
            HTTP_AUTHORIZATION="Bearer " + token,
        )

    def test_disabled_by_default(self):
        with override_settings(RADAR_MAKE_INGRESS={}):
            self.assertEqual(self.post().status_code, 404)
        self.assertEqual(RecepcionComercial.objects.count(), 0)

    def test_valid_test_receipt_does_not_create_opportunity(self):
        result = self.post()
        self.assertEqual(result.status_code, 201)
        record = RecepcionComercial.objects.get()
        self.assertTrue(record.es_prueba)
        self.assertEqual(record.organizacion, self.org)
        self.assertEqual(record.buzon, "forms@example.test")
        self.assertEqual(record.contenido["telefono"], "+56000000000")
        self.assertEqual(record.observaciones, [])
        self.assertEqual(Oportunidad.objects.count(), 0)

    def test_exact_replay_returns_same_receipt(self):
        first = self.post().json()
        second = self.post()
        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.json()["duplicado"])
        self.assertEqual(first["recepcion_id"], second.json()["recepcion_id"])
        self.assertEqual(RecepcionComercial.objects.count(), 1)

    def test_reordered_json_is_not_a_new_message(self):
        self.post()
        self.assertEqual(self.post(dict(reversed(list(self.payload.items())))).status_code, 200)

    def test_same_id_different_payload_is_conflict_without_overwrite(self):
        self.post()
        changed = {**self.payload, "consulta": "Otro contenido"}
        self.assertEqual(self.post(changed).status_code, 409)
        self.assertEqual(RecepcionComercial.objects.get().contenido["consulta"], self.payload["consulta"])

    def test_similar_message_with_new_id_is_kept_for_review(self):
        self.post()
        result = self.post({**self.payload, "source_message_id": "synthetic-002"})
        self.assertEqual(result.status_code, 201)
        self.assertEqual(RecepcionComercial.objects.count(), 2)
        self.assertTrue(result.json()["requiere_revision"])

    def test_cross_organization_token_denied(self):
        result = self.post(url=reverse("make_comercial", args=["otro"]))
        self.assertEqual(result.status_code, 401)
        self.assertEqual(RecepcionComercial.objects.count(), 0)

    def test_same_message_id_different_organization_is_independent(self):
        self.post()
        result = self.post(url=reverse("make_comercial", args=["otro"]), token=OTHER_TOKEN)
        self.assertEqual(result.status_code, 201)
        self.assertEqual(RecepcionComercial.objects.count(), 2)

    def test_payload_cannot_choose_organization_or_mailbox(self):
        for key in ["organizacion_id", "buzon", "site", "estado", "oportunidad_id"]:
            with self.subTest(key=key):
                self.assertEqual(self.post({**self.payload, key: "override"}).status_code, 400)
        self.assertEqual(RecepcionComercial.objects.count(), 0)

    def test_missing_and_wrong_credentials_denied(self):
        self.assertEqual(self.post(token="wrong-token-but-long-enough-for-this-test").status_code, 401)
        result = self.client.post(self.url, "{}", content_type="application/json", secure=True)
        self.assertEqual(result.status_code, 401)

    def test_https_required_even_for_valid_credential(self):
        self.assertEqual(self.post(secure=False).status_code, 400)

    def test_non_post_rejected(self):
        self.assertEqual(self.client.get(self.url, secure=True).status_code, 405)

    def test_invalid_json_and_non_object_rejected(self):
        for raw in ["{", "[]", "null", '"text"', '{"schema_version":1,"schema_version":1}']:
            result = self.client.post(self.url, raw, content_type="application/json",
                                      secure=True, HTTP_AUTHORIZATION="Bearer " + TOKEN)
            self.assertEqual(result.status_code, 400)

    def test_oversize_and_wrong_content_type_rejected(self):
        result = self.post({**self.payload, "consulta": "x" * 33000})
        self.assertEqual(result.status_code, 413)
        result = self.client.post(self.url, "data", content_type="text/plain", secure=True,
                                  HTTP_AUTHORIZATION="Bearer " + TOKEN)
        self.assertEqual(result.status_code, 415)

    def test_field_limits_and_types_rejected(self):
        for key, value in [("email", None), ("nombre", "x" * 201), ("consulta", "bad\x00text"),
                           ("source_message_id", ""), ("source_message_id", "bad/id"),
                           ("schema_version", True), ("test_mode", "true")]:
            with self.subTest(key=key):
                self.assertEqual(self.post({**self.payload, key: value}).status_code, 400)

    def test_incomplete_fields_preserved_with_observations(self):
        sparse = {key: self.payload[key] for key in ["schema_version", "source_message_id", "test_mode"]}
        result = self.post(sparse)
        self.assertEqual(result.status_code, 201)
        self.assertTrue(result.json()["requiere_revision"])
        self.assertIn("Falta nombre", RecepcionComercial.objects.get().observaciones)

    def test_inactive_organization_rejected(self):
        self.org.activa = False
        self.org.save()
        self.assertEqual(self.post().status_code, 503)

    def test_invalid_configuration_fails_closed(self):
        for field, value in [("token_sha256", "bad"), ("organizacion_id", True), ("test_mode", "false")]:
            with self.subTest(field=field):
                config = {"piloto": {**self.config["piloto"], field: value}}
                with override_settings(RADAR_MAKE_INGRESS=config):
                    self.assertEqual(self.post().status_code, 503)

    def test_client_cannot_change_server_test_mode(self):
        self.assertEqual(self.post({**self.payload, "test_mode": False}).status_code, 409)
        self.assertEqual(Oportunidad.objects.count(), 0)

    def production(self):
        self.config["piloto"]["test_mode"] = False
        return {**self.payload, "test_mode": False}

    def test_production_creates_opportunity_once(self):
        payload = self.production()
        self.assertEqual(self.post(payload).status_code, 201)
        self.assertEqual(self.post(payload).status_code, 200)
        opportunity = Oportunidad.objects.get()
        self.assertEqual(opportunity.organizacion, self.org)
        self.assertEqual(opportunity.telefono_consultante, "+56000000000")
        self.assertEqual(opportunity.origen, "consulta_entrante")
        self.assertEqual(RecepcionComercial.objects.get().oportunidad, opportunity)

    def test_invalid_email_preserved_without_blocking_production(self):
        payload = {**self.production(), "email": "not-an-email"}
        self.assertEqual(self.post(payload).status_code, 201)
        self.assertEqual(Oportunidad.objects.get().email_consultante, "")
        self.assertEqual(RecepcionComercial.objects.get().contenido["email"], "not-an-email")

    def test_empty_production_consultation_is_reviewable(self):
        payload = {key: value for key, value in self.production().items()
                   if key in {"schema_version", "source_message_id", "test_mode"}}
        self.assertEqual(self.post(payload).status_code, 201)
        self.assertTrue(Oportunidad.objects.get().necesidad)

    def test_partial_failure_rolls_back_receipt_and_can_retry(self):
        payload = self.production()
        with patch("integraciones.comercial.Oportunidad.objects.create", side_effect=RuntimeError("synthetic")):
            with self.assertRaises(RuntimeError):
                self.post(payload)
        self.assertEqual(RecepcionComercial.objects.count(), 0)
        self.assertEqual(Oportunidad.objects.count(), 0)
        self.assertEqual(self.post(payload).status_code, 201)

    def test_database_unique_constraint_enforces_idempotence(self):
        self.post()
        record = RecepcionComercial.objects.get()
        record.pk = None
        with self.assertRaises(IntegrityError), transaction.atomic():
            record.save(force_insert=True)

    def test_csrf_exemption_does_not_replace_bearer_authentication(self):
        client = Client(enforce_csrf_checks=True)
        response = client.post(self.url, json.dumps(self.payload), content_type="application/json",
                               secure=True, HTTP_AUTHORIZATION="Bearer " + TOKEN)
        self.assertEqual(response.status_code, 201)

    def test_no_payload_or_secret_in_success_response(self):
        response = self.post().content.decode()
        self.assertNotIn(TOKEN, response)
        self.assertNotIn(self.payload["email"], response)

    def test_admin_receipts_not_visible_to_non_superuser(self):
        user = get_user_model().objects.create_user("staff", is_staff=True)
        self.client.force_login(user)
        response = self.client.get(reverse("admin:integraciones_recepcioncomercial_changelist"), secure=True)
        self.assertEqual(response.status_code, 403)


class ConcurrentIngressTests(TransactionTestCase):
    @skipUnlessDBFeature("has_select_for_update")
    def test_parallel_replay_creates_one_receipt_and_one_opportunity(self):
        org = Organizacion.objects.create(nombre="Concurrencia", slug="concurrent")
        config = {"piloto": {
            "organizacion_id": org.pk, "buzon": "forms@example.test", "test_mode": False,
            "token_sha256": hashlib.sha256(TOKEN.encode()).hexdigest(),
        }}
        barrier = Barrier(2)

        def deliver():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return Client().post(
                    reverse("make_comercial", args=["piloto"]),
                    json.dumps({"schema_version": 1, "source_message_id": "parallel-001",
                                "test_mode": False}),
                    content_type="application/json", secure=True,
                    HTTP_AUTHORIZATION="Bearer " + TOKEN,
                ).status_code
            finally:
                connections.close_all()

        with override_settings(RADAR_MAKE_INGRESS=config), ThreadPoolExecutor(max_workers=2) as executor:
            responses = list(executor.map(lambda _: deliver(), range(2)))
        self.assertEqual(sorted(responses), [200, 201])
        self.assertEqual(RecepcionComercial.objects.count(), 1)
        self.assertEqual(Oportunidad.objects.count(), 1)
