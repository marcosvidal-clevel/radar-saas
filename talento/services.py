from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from core.models import Membresia

from .models import Candidato, CandidatoProcedencia, DocumentoCandidato


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
def consolidar_candidato(canonico, duplicado, usuario):
    """Consolida explícitamente una ficha, preservando relaciones y archivos."""
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

    conflictos = []
    for field in ("email", "telefono", "linkedin", "profesion", "especialidad", "region", "ciudad", "experiencia", "competencias", "notas"):
        left, right = getattr(canonico, field), getattr(duplicado, field)
        if left and right and left != right:
            conflictos.append(field)
    if conflictos:
        raise ValidationError({"datos": f"Conflictos en: {', '.join(conflictos)}."})
    if set(duplicado.postulaciones.values_list("vacante_id", flat=True)) & set(canonico.postulaciones.values_list("vacante_id", flat=True)):
        raise ValidationError("Las fichas tienen postulaciones para la misma vacante.")

    for field in ("email", "telefono", "linkedin", "profesion", "especialidad", "region", "ciudad", "experiencia", "competencias", "notas"):
        if not getattr(canonico, field) and getattr(duplicado, field):
            setattr(canonico, field, getattr(duplicado, field))
    canonico.save()

    duplicado.documentos.update(candidato=canonico, es_cv_principal=False)
    duplicado.postulaciones.update(candidato=canonico)
    CandidatoProcedencia.objects.filter(candidato=duplicado).update(candidato=canonico)
    duplicado.consolidado_en = canonico
    duplicado.save(update_fields=("consolidado_en", "actualizado_en"))
    return canonico
