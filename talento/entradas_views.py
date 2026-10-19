from pathlib import Path

from django.contrib import admin, messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from .models import EntradaPendiente, Candidato
from .entradas_forms import EntradaForm, ResolverEntradaForm
from .entradas_services import autorizar, guardar_entrada, resolver_entrada


def _visibles(request):
    if not request.user.is_staff or not request.user.has_perm("talento.view_entradapendiente"):
        raise PermissionDenied
    qs = EntradaPendiente.objects.select_related("organizacion", "candidato", "documento")
    if request.user.is_superuser:
        return qs
    return qs.exclude(tipo_documento="evaluacion").filter(organizacion__activa=True, organizacion__membresias__usuario=request.user,
                     organizacion__membresias__activa=True).filter(
        Q(clasificacion_confirmada=True) | Q(organizacion__membresias__rol__in=["admin", "supervisor"])
    ).distinct()


def _context(request, **kwargs):
    return {**admin.site.each_context(request), **kwargs}


@login_required
@require_GET
def bandeja(request):
    from django.core.paginator import Paginator
    qs = _visibles(request).order_by("-creado_en", "-pk")
    state = request.GET.get("estado", "")
    if state in EntradaPendiente.Seguimiento.values:
        qs = qs.filter(seguimiento=state)
    return render(request, "talento/entradas_lista.html", _context(
        request, title="Entradas pendientes de candidatos", entradas=Paginator(qs, 50).get_page(request.GET.get("page")),
        estados=EntradaPendiente.Seguimiento.choices, estado=state,
    ))


@login_required
@require_http_methods(["GET", "POST"])
def editar(request, pk=None):
    if not request.user.is_staff:
        raise PermissionDenied
    entrada = get_object_or_404(_visibles(request), pk=pk) if pk else None
    permiso = "change" if entrada else "add"
    if not request.user.has_perm(f"talento.{permiso}_entradapendiente"):
        raise PermissionDenied
    if entrada:
        autorizar(request.user, entrada.organizacion, "talento.change_entradapendiente")
        if entrada.seguimiento == "resuelto":
            return redirect("entrada_detalle", pk=pk)
    form = EntradaForm(request.POST or None, request.FILES or None, usuario=request.user, instance=entrada)
    if request.method == "POST" and form.is_valid():
        try:
            saved = guardar_entrada(usuario=request.user, organizacion=form.cleaned_data["organizacion"],
                datos=form.cleaned_data, fuente=form.cleaned_data["fuente_revision"],
                archivo=form.cleaned_data.get("archivo"), entrada_id=pk)
        except ValidationError as error:
            form.add_error(None, " ".join(error.messages))
        else:
            messages.success(request, "Entrada conservada; no se creó ningún candidato.")
            return redirect("entrada_detalle", pk=saved.pk)
    return render(request, "talento/entrada_form.html", _context(request, title="Revisar y completar" if entrada else "Nueva entrada pendiente", form=form))


@login_required
@require_GET
def detalle(request, pk):
    entrada = get_object_or_404(_visibles(request), pk=pk)
    # Las coincidencias son solo advertencias; nunca un enlace automático.
    candidatos = Candidato.objects.none()
    if request.user.has_perm("talento.view_candidato"):
        q = Q(pk__in=[])
        if entrada.nombre:
            q |= Q(nombre__iexact=entrada.nombre)
        if entrada.email and entrada.email_estado == "disponible":
            q |= Q(email__iexact=entrada.email)
        if entrada.telefono and entrada.telefono_estado == "disponible":
            q |= Q(telefono=entrada.telefono)
        q |= Q(documentos__sha256=entrada.sha256)
        candidatos = Candidato.objects.filter(q, organizacion=entrada.organizacion).distinct()[:20]
    return render(request, "talento/entrada_detalle.html", _context(
        request, title=f"Entrada {entrada.identificador_origen}", entrada=entrada,
        candidatos=candidatos, revisiones=entrada.revisiones.select_related("usuario"),
    ))


@login_required
@require_http_methods(["GET", "POST"])
def resolver(request, pk):
    entrada = get_object_or_404(_visibles(request), pk=pk)
    autorizar(request.user, entrada.organizacion, "talento.change_entradapendiente")
    if not request.user.has_perm("talento.view_candidato"):
        raise PermissionDenied
    form = ResolverEntradaForm(request.POST or None, entrada=entrada)
    if request.method == "POST" and form.is_valid():
        try:
            resolver_entrada(entrada_id=pk, usuario=request.user, fuente=form.cleaned_data["fuente"],
                             candidato_id=getattr(form.cleaned_data["candidato"], "pk", None))
        except ValidationError as error:
            form.add_error(None, " ".join(error.messages))
        else:
            messages.success(request, "Entrada resuelta. Archivo y revisiones originales conservados.")
            return redirect("entrada_detalle", pk=pk)
    return render(request, "talento/entrada_form.html", _context(request, title="Resolver identidad y destino", form=form, resolver=True))


@login_required
@require_GET
def descargar(request, pk):
    entrada = get_object_or_404(_visibles(request), pk=pk)
    autorizar(request.user, entrada.organizacion, "talento.view_entradapendiente", gestionar=False)
    try:
        response = FileResponse(entrada.archivo.open("rb"), as_attachment=True, filename=Path(entrada.nombre_archivo_original).name)
    except (FileNotFoundError, OSError):
        raise Http404 from None
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response
