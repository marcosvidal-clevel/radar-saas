import json

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from core.models import Membresia

from .models import Candidato, CandidatoProcedencia


def _puede_gestionar(usuario, candidato):
    return (
        usuario.is_superuser
        or (
            usuario.has_perm("talento.change_candidato")
            and Membresia.objects.filter(
                usuario=usuario,
                organizacion_id=candidato.organizacion_id,
                activa=True,
                organizacion__activa=True,
                rol__in=(Membresia.Rol.ADMINISTRADOR, Membresia.Rol.SUPERVISOR),
            ).exists()
        )
    )


def _puede_gestionar_documento(usuario, documento):
    return (
        usuario.is_superuser
        or (
            usuario.has_perm("talento.change_documentocandidato")
            and Membresia.objects.filter(
                usuario=usuario,
                organizacion_id=documento.candidato.organizacion_id,
                activa=True,
                organizacion__activa=True,
                rol__in=(Membresia.Rol.ADMINISTRADOR, Membresia.Rol.SUPERVISOR),
            ).exists()
        )
    )


@transaction.atomic
def consolidar_candidato(canonico, duplicado, usuario, *, resolucion_telefono=None):
    """Consolida sin elegir vigencia telefónica; admite conservar_canonico explícito."""
    canonico = Candidato.objects.select_for_update().get(pk=canonico.pk)
    duplicado = Candidato.objects.select_for_update().get(pk=duplicado.pk)
    if canonico.pk == duplicado.pk:
        raise ValidationError("Una ficha no puede consolidarse consigo misma.")
    if canonico.organizacion_id != duplicado.organizacion_id:
        raise ValidationError("Las fichas deben pertenecer a la misma organización.")
    if duplicado.consolidado_en_id:
        raise ValidationError("La ficha duplicada ya está consolidada.")
    if canonico.consolidado_en_id:
        raise ValidationError("La ficha canónica ya depende de otra ficha.")
    if canonico.consolidado_en_id == duplicado.pk or duplicado.consolidado_en_id == canonico.pk:
        raise ValidationError("La consolidación formaría un ciclo.")
    if not _puede_gestionar(usuario, canonico) or not _puede_gestionar(usuario, duplicado):
        raise PermissionDenied("El usuario no puede gestionar ambas fichas.")
    documentos_transferidos = list(duplicado.documentos.all())
    if any(not _puede_gestionar_documento(usuario, documento) for documento in documentos_transferidos):
        raise PermissionDenied("El usuario no puede gestionar todos los documentos transferidos.")

    conflicto_telefono = bool(
        canonico.telefono and duplicado.telefono
        and canonico.telefono != duplicado.telefono
    )
    if resolucion_telefono is not None and (
        resolucion_telefono != "conservar_canonico" or not conflicto_telefono
    ):
        raise ValidationError({"telefono": "Resolución telefónica inválida o sin conflicto."})

    conflictos = []
    for field in ("email", "telefono", "linkedin", "profesion", "especialidad", "region", "ciudad", "experiencia", "competencias", "notas"):
        left, right = getattr(canonico, field), getattr(duplicado, field)
        if left and right and left != right:
            if field == "telefono" and resolucion_telefono == "conservar_canonico":
                continue
            conflictos.append(field)
    if conflictos:
        raise ValidationError({"datos": f"Conflictos en: {', '.join(conflictos)}."})
    if set(duplicado.postulaciones.values_list("vacante_id", flat=True)) & set(canonico.postulaciones.values_list("vacante_id", flat=True)):
        raise ValidationError("Las fichas tienen postulaciones para la misma vacante.")

    nota_telefono = None
    if resolucion_telefono == "conservar_canonico":
        def origen_telefono(candidato):
            return {
                "candidato_id": candidato.pk,
                "telefono": candidato.telefono,
                "origen_importacion": candidato.origen_importacion,
                "identificador_origen": candidato.identificador_origen,
                "procedencias": list(candidato.procedencias.order_by("pk").values(
                    "organizacion_id", "origen_importacion", "identificador_origen"
                )),
            }

        nota_telefono = {
            "resolucion": "conservar_canonico",
            "vigencia": "no determinada para ninguno de los teléfonos",
            "usuario_id": usuario.pk,
            "fecha": timezone.now().isoformat(),
            "canonico": origen_telefono(canonico),
            "duplicado": origen_telefono(duplicado),
        }

    for field in ("email", "telefono", "linkedin", "profesion", "especialidad", "region", "ciudad", "experiencia", "competencias", "notas"):
        if not getattr(canonico, field) and getattr(duplicado, field):
            setattr(canonico, field, getattr(duplicado, field))
    if nota_telefono is not None:
        canonico.notas = "\n\n".join(filter(None, (
            canonico.notas,
            "Nota de consolidación telefónica:\n" + json.dumps(nota_telefono, ensure_ascii=False),
        )))
    canonico.save()

    duplicado.documentos.update(candidato=canonico, es_cv_principal=False)
    duplicado.postulaciones.update(candidato=canonico)
    CandidatoProcedencia.objects.filter(candidato=duplicado).update(candidato=canonico)
    duplicado.consolidado_en = canonico
    duplicado.save(update_fields=("consolidado_en", "actualizado_en"))
    return canonico
