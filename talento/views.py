
from pathlib import Path

from django.contrib import admin
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404
from django.core.paginator import Paginator
from django.db import transaction
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from core.models import Membresia, Organizacion
from .forms import CandidatoForm
from .models import Candidato, DocumentoCandidato


def _administrador_candidatos():
    return admin.site._registry[Candidato]


def _documentos_consultables(request, candidato):
    if not request.user.has_perm("talento.view_documentocandidato"):
        return DocumentoCandidato.objects.none()

    documentos = DocumentoCandidato.objects.filter(
        candidato=candidato,
    ).select_related("candidato")

    if request.user.is_superuser:
        return documentos

    membresia = Membresia.objects.filter(
        usuario=request.user,
        organizacion_id=candidato.organizacion_id,
        organizacion__activa=True,
        activa=True,
        rol__in=(
            Membresia.Rol.ADMINISTRADOR,
            Membresia.Rol.SUPERVISOR,
            Membresia.Rol.COLABORADOR,
        ),
    ).exists()

    if not membresia:
        return DocumentoCandidato.objects.none()

    return documentos.exclude(tipo=DocumentoCandidato.Tipo.EVALUACION)


@login_required(login_url="admin:login")
@require_GET
def candidatos(request):
    administrador = _administrador_candidatos()

    if not request.user.is_staff or not administrador.has_view_permission(request):
        raise PermissionDenied("No tienes acceso a Talento.")

    queryset = administrador.get_queryset(request).select_related("organizacion")
    busqueda = request.GET.get("q", "").strip()[:200]
    if busqueda:
        queryset, _ = administrador.get_search_results(
            request,
            queryset,
            busqueda,
        )

    queryset = queryset.order_by("nombre", "pk").distinct()
    paginador = Paginator(queryset, 20)
    pagina = paginador.get_page(request.GET.get("pagina"))

    return render(
        request,
        "talento/candidatos.html",
        {
            "pagina_candidatos": pagina,
            "busqueda": busqueda,
            "puede_crear": administrador.has_add_permission(request),
        },
    )


@login_required(login_url="admin:login")
@require_http_methods(["GET", "POST"])
def nuevo_candidato(request):
    administrador = _administrador_candidatos()

    if not request.user.is_staff or not administrador.has_add_permission(request):
        raise PermissionDenied("No tienes permiso para crear candidatos.")

    organizaciones_permitidas = Membresia.objects.filter(
        usuario=request.user,
        activa=True,
        organizacion__activa=True,
        rol__in=administrador.ROLES_GESTION,
    ).values("organizacion")

    formulario = CandidatoForm(
        request.POST or None,
        request.FILES or None,
        organizaciones=Organizacion.objects.filter(
            pk__in=organizaciones_permitidas,
        ),
    )

    if request.method == "POST" and formulario.is_valid():
        archivo = formulario.cleaned_data.pop("cv", None)
        try:
            with transaction.atomic():
                candidato = formulario.save()
                if archivo:
                    DocumentoCandidato.objects.create(
                        candidato=candidato,
                        tipo=DocumentoCandidato.Tipo.CURRICULUM,
                        nombre=f"CV de {candidato.nombre}",
                        archivo=archivo,
                        es_cv_principal=True,
                        vigente=True,
                    )
        except Exception as error:
            if hasattr(error, "message_dict"):
                for campo, errores in error.message_dict.items():
                    for mensaje in errores:
                        formulario.add_error(campo, mensaje)
            else:
                formulario.add_error(
                    "cv" if archivo else None,
                    "No se pudo guardar el candidato o su CV.",
                )
        else:
            messages.success(request, "Candidato creado correctamente.")
            return redirect("talento_detalle_candidato", pk=candidato.pk)

    return render(
        request,
        "talento/nuevo_candidato.html",
        {"formulario": formulario},
    )


@login_required(login_url="admin:login")
@require_GET
def detalle_candidato(request, pk):
    administrador = _administrador_candidatos()

    if not request.user.is_staff or not administrador.has_view_permission(request):
        raise PermissionDenied("No tienes acceso a Talento.")

    candidatos_permitidos = administrador.get_queryset(request).select_related(
        "organizacion",
    )
    candidato = get_object_or_404(candidatos_permitidos, pk=pk)

    if not administrador.has_view_permission(request, candidato):
        raise PermissionDenied("No tienes acceso a este candidato.")

    return render(
        request,
        "talento/detalle_candidato.html",
        {
            "candidato": candidato,
            "documentos": _documentos_consultables(request, candidato),
        },
    )


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
            organizacion__activa=True,
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
