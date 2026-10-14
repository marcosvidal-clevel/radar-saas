from django.contrib import admin
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import render
from django.utils import timezone

from .models import Oportunidad


@staff_member_required(login_url="admin:login")
def panel_comercial(request):
    administrador = admin.site._registry[Oportunidad]

    if not administrador.has_view_permission(request):
        raise PermissionDenied(
            "No tienes acceso al panel comercial."
        )

    # Reutiliza el aislamiento y los permisos por rol.
    oportunidades = administrador.get_queryset(request).select_related(
        "organizacion",
        "empresa",
        "responsable__usuario",
        "responsable__organizacion",
    )

    estados_cerrados = (
        Oportunidad.Estado.GANADA,
        Oportunidad.Estado.PERDIDA,
        Oportunidad.Estado.DESCARTADA,
    )
    activas = oportunidades.exclude(estado__in=estados_cerrados)

    hoy = timezone.localdate()

    calientes = activas.filter(
        origen=Oportunidad.Origen.CONSULTA_ENTRANTE
    )
    vencidas = activas.filter(fecha_proxima_accion__lt=hoy)
    para_hoy = activas.filter(fecha_proxima_accion=hoy)
    sin_fecha = activas.filter(fecha_proxima_accion__isnull=True)

    contexto = {
        "hoy": hoy,
        "total_activas": activas.count(),
        "total_calientes": calientes.count(),
        "total_vencidas": vencidas.count(),
        "total_para_hoy": para_hoy.count(),
        "total_sin_fecha": sin_fecha.count(),
        "calientes": calientes.order_by("-creada_en")[:20],
        "seguimientos": activas.filter(
            fecha_proxima_accion__lte=hoy
        ).order_by("fecha_proxima_accion", "pk")[:20],
        "sin_fecha": sin_fecha.order_by("-creada_en")[:20],
        "puede_crear": administrador.has_add_permission(request),
    }

    return render(
        request,
        "core/panel_comercial.html",
        contexto,
    )