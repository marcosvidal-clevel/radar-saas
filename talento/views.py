
from pathlib import Path

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET

from core.models import Membresia
from .models import DocumentoCandidato


@login_required
@require_GET
def descargar_documento_candidato(request, pk):
    if not request.user.is_staff:
        raise PermissionDenied(
            "No tienes autorización para descargar documentos."
        )

    if not request.user.has_perm(
        "talento.view_documentocandidato"
    ):
        raise PermissionDenied(
            "No tienes permiso para consultar documentos."
        )

    documento = get_object_or_404(
        DocumentoCandidato.objects.select_related(
            "candidato__organizacion"
        ),
        pk=pk,
    )

    if not request.user.is_superuser:
        membresia = Membresia.objects.filter(
            usuario=request.user,
            organizacion_id=documento.candidato.organizacion_id,
            activa=True,
            rol__in=(
                Membresia.Rol.ADMINISTRADOR,
                Membresia.Rol.SUPERVISOR,
                Membresia.Rol.COLABORADOR,
            ),
        ).exists()

        if not membresia:
            raise PermissionDenied(
                "No tienes acceso a documentos de esta organización."
            )

        if documento.tipo == DocumentoCandidato.Tipo.EVALUACION:
            raise PermissionDenied(
                "Este documento tiene acceso restringido."
            )

    if not documento.archivo:
        raise Http404("El documento no tiene archivo asociado.")

    try:
        archivo = documento.archivo.open("rb")
    except (FileNotFoundError, OSError):
        raise Http404("El archivo solicitado no está disponible.")

    nombre_descarga = (
        Path(documento.archivo.name).name
    )

    return FileResponse(
        archivo,
        as_attachment=True,
        filename=nombre_descarga,
    )
