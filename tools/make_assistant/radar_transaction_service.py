"""Draft Django service: transactional import, no deployment or network access.

Requires OportunidadExterna model installed in core and migrated before use.
Caller must supply an authenticated user; never trust organization from payload.
"""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction

def import_web_opportunity(*, user, organization_id, external_key, fields):
    from core.models import Membresia, Oportunidad
    from core.models import OportunidadExterna

    if not getattr(user, "is_authenticated", False):
        raise PermissionDenied("Authentication required")
    if type(organization_id) is not int or organization_id <= 0:
        raise ValidationError("Invalid organization")
    if not isinstance(external_key, str) or not external_key.strip() or len(external_key)>200:
        raise ValidationError("Invalid external key")
    if not Membresia.objects.filter(
        organizacion_id=organization_id, usuario=user, activa=True,
        rol__in=["admin", "supervisor"]
    ).exists():
        raise PermissionDenied("Active administrator/supervisor membership required")

    allowed={"titulo", "origen", "canal", "nombre_consultante",
             "email_consultante", "telefono_consultante", "necesidad", "estado"}
    if not isinstance(fields, dict) or set(fields) - allowed:
        raise ValidationError("Unexpected opportunity fields")
    if fields.get("origen")!="consulta_entrante" or fields.get("canal")!="web":
        raise ValidationError("Only incoming web opportunities supported")

    # Serialize imports per organization, including the initially absent key.
    # The unique database constraint remains the final concurrency safeguard.
    from core.models import Organizacion
    with transaction.atomic():
        Organizacion.objects.select_for_update().get(pk=organization_id)
        existing=OportunidadExterna.objects.filter(
            organizacion_id=organization_id,
            origen_integracion="make",
            clave_externa=external_key
        ).select_related("oportunidad").first()
        if existing:
            return existing.oportunidad, False
        opportunity=Oportunidad(organizacion_id=organization_id, **fields)
        opportunity.full_clean()
        opportunity.save()
        mapping=OportunidadExterna(
            organizacion_id=organization_id, oportunidad=opportunity,
            origen_integracion="make", clave_externa=external_key
        )
        mapping.full_clean()
        mapping.save()
        return opportunity, True
