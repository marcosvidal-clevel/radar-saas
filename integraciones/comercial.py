"""Authenticated, idempotent commercial ingress. No outgoing communications."""

import hashlib
import json
import re
import secrets

from django.conf import settings
from django.core.exceptions import RequestDataTooBig, ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.debug import sensitive_variables
from django.views.decorators.http import require_POST

from core.models import Oportunidad, Organizacion
from .models import RecepcionComercial


MAX_BODY = 32768
TEXT_FIELDS = {
    "received_at": 100, "nombre": 200, "empresa": 200, "email": 254,
    "telefono": 50, "necesidad": 4000, "sector": 200, "consulta": 8000,
    "autorizacion_contacto": 2000,
}
FIELDS = {*TEXT_FIELDS, "schema_version", "source_message_id", "test_mode"}


def digest(value):
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode()).hexdigest()


class PayloadError(ValueError):
    pass


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise PayloadError("campo_repetido")
        result[key] = value
    return result


def normalize(data):
    if not isinstance(data, dict) or set(data) - FIELDS:
        raise PayloadError("estructura_invalida")
    if type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise PayloadError("version_invalida")
    message = data.get("source_message_id")
    if not isinstance(message, str) or not re.fullmatch(r"[A-Za-z0-9._:-]{1,200}", message):
        raise PayloadError("mensaje_id_invalido")
    if type(data.get("test_mode")) is not bool:
        raise PayloadError("modo_requerido")
    normalized = {
        "schema_version": 1, "source_message_id": message,
        "test_mode": data["test_mode"],
    }
    for key, limit in TEXT_FIELDS.items():
        value = data.get(key, "")
        if not isinstance(value, str) or len(value) > limit or "\x00" in value:
            raise PayloadError("campo_invalido")
        value.encode("utf-8")
        normalized[key] = value.strip()
    normalized["email"] = normalized["email"].lower()
    return normalized


@transaction.atomic
def receive(config, site, payload):
    # The organisation lock serializes receives even when different message IDs
    # arrive together. Unique DB constraint is a second line of protection.
    org = Organizacion.objects.select_for_update().get(
        pk=config["organizacion_id"], activa=True,
    )
    body_hash = digest(payload)
    key = dict(organizacion=org, buzon=config["buzon"],
               mensaje_id=payload["source_message_id"], es_prueba=payload["test_mode"])
    existing = RecepcionComercial.objects.filter(**key).first()
    if existing:
        if existing.contenido_hash != body_hash:
            return {"error": "mensaje_con_contenido_distinto"}, 409
        return {"recepcion_id": existing.pk, "duplicado": True,
                "test_mode": existing.es_prueba}, 200
    observations = [f"Falta {key}" for key in ("nombre", "empresa", "email", "necesidad")
                    if not payload[key]]
    email = payload["email"]
    if email:
        try:
            validate_email(email)
        except ValidationError:
            observations.append("Correo inválido; conservar original para revisión")
            email = ""
    try:
        date = parse_datetime(payload["received_at"])
    except ValueError:
        date = None
    if date is None or timezone.is_naive(date):
        observations.append("Fecha de origen ausente, inválida o sin zona horaria")
    if not payload["autorizacion_contacto"]:
        observations.append("Sin texto de autorización de contacto")
    fingerprint = digest({k: v.casefold() for k, v in payload.items()
                          if k in TEXT_FIELDS and k != "received_at"})
    if RecepcionComercial.objects.filter(
        organizacion=org, buzon=config["buzon"], es_prueba=payload["test_mode"],
        similitud_hash=fingerprint,
    ).exists():
        observations.append("Contenido similar a otro mensaje; revisar sin descartar")
    record = RecepcionComercial.objects.create(
        **key, sitio=site, contenido=payload, contenido_hash=body_hash,
        similitud_hash=fingerprint, observaciones=observations,
    )
    if not payload["test_mode"]:
        record.oportunidad = Oportunidad.objects.create(
            organizacion=org,
            titulo=(payload["necesidad"] or "Consulta web pendiente de antecedentes")[:250],
            origen=Oportunidad.Origen.CONSULTA_ENTRANTE, canal=Oportunidad.Canal.WEB,
            nombre_consultante=payload["nombre"], email_consultante=email,
            telefono_consultante=payload["telefono"],
            necesidad=payload["necesidad"] or payload["consulta"] or "Pendiente de antecedentes",
            proxima_accion="Revisar consulta y antecedentes recibidos",
            notas=f"Recepción de integración {record.pk}. Revisar contenido y observaciones antes de contactar.",
        )
        record.save(update_fields=["oportunidad"])
    return {"recepcion_id": record.pk, "duplicado": False,
            "test_mode": record.es_prueba, "requiere_revision": bool(observations)}, 201


@csrf_exempt
@require_POST
@sensitive_variables("authorization", "token", "config")
def commercial_ingress(request, site):
    if not request.is_secure():
        return JsonResponse({"error": "https_requerido"}, status=400)
    config = getattr(settings, "RADAR_MAKE_INGRESS", {}).get(site)
    if not isinstance(config, dict):
        return JsonResponse({"error": "integracion_no_disponible"}, status=404)
    expected = config.get("token_sha256", "")
    if (not re.fullmatch(r"[0-9a-f]{64}", str(expected))
            or type(config.get("organizacion_id")) is not int
            or not isinstance(config.get("buzon"), str)
            or type(config.get("test_mode")) is not bool):
        return JsonResponse({"error": "integracion_no_disponible"}, status=503)
    authorization = request.headers.get("Authorization", "")
    token = authorization.removeprefix("Bearer ")
    if (not authorization.startswith("Bearer ") or not 32 <= len(token) <= 512
            or not secrets.compare_digest(hashlib.sha256(token.encode()).hexdigest(), expected)):
        return JsonResponse({"error": "no_autorizado"}, status=401)
    if request.content_type != "application/json":
        return JsonResponse({"error": "json_requerido"}, status=415)
    try:
        if int(request.META.get("CONTENT_LENGTH") or 0) > MAX_BODY:
            return JsonResponse({"error": "cuerpo_demasiado_grande"}, status=413)
        raw = request.body
        if len(raw) > MAX_BODY:
            return JsonResponse({"error": "cuerpo_demasiado_grande"}, status=413)
        payload = normalize(json.loads(raw, object_pairs_hook=unique_object))
    except RequestDataTooBig:
        return JsonResponse({"error": "cuerpo_demasiado_grande"}, status=413)
    except (ValueError, UnicodeError, RecursionError):
        return JsonResponse({"error": "consulta_invalida"}, status=400)
    if payload["test_mode"] != config["test_mode"]:
        return JsonResponse({"error": "modo_no_coincide"}, status=409)
    try:
        result, status = receive(config, site, payload)
    except Organizacion.DoesNotExist:
        return JsonResponse({"error": "integracion_no_disponible"}, status=503)
    return JsonResponse(result, status=status)
