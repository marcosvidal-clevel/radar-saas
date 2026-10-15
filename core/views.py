from django.contrib import admin
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import render
from django.utils import timezone

from .models import Membresia, Oportunidad


@staff_member_required(login_url="admin:login")
def panel_comercial(request):
    administrador = admin.site._registry[Oportunidad]

    if not administrador.has_view_permission(request):
        raise PermissionDenied(
            "No tienes acceso al panel comercial."
        )

    # Primero se aplican los permisos y el aislamiento.
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

    estados_disponibles = [
        (valor, etiqueta)
        for valor, etiqueta in Oportunidad.Estado.choices
        if valor not in estados_cerrados
    ]
    canales_disponibles = list(Oportunidad.Canal.choices)

    # Solo ofrece responsables de oportunidades que el usuario puede ver.
    membresias = Membresia.objects.filter(
        pk__in=activas.values("responsable_id")
    ).select_related(
        "usuario",
        "organizacion",
    ).order_by(
        "usuario__username",
        "organizacion__nombre",
        "pk",
    )

    responsables_disponibles = [
        {
            "id": str(membresia.pk),
            "nombre": str(membresia),
        }
        for membresia in membresias
    ]

    estado = request.GET.get("estado", "").strip()
    canal = request.GET.get("canal", "").strip()
    responsable = request.GET.get("responsable", "").strip()

    estados_validos = {
        valor for valor, etiqueta in estados_disponibles
    }
    canales_validos = {
        valor for valor, etiqueta in canales_disponibles
    }
    responsables_validos = {
        opcion["id"] for opcion in responsables_disponibles
    }

    if estado not in estados_validos:
        estado = ""

    if canal not in canales_validos:
        canal = ""

    if responsable not in responsables_validos | {"sin_asignar"}:
        responsable = ""

    if estado:
        activas = activas.filter(estado=estado)

    if canal:
        activas = activas.filter(canal=canal)

    if responsable == "sin_asignar":
        activas = activas.filter(responsable__isnull=True)
    elif responsable:
        activas = activas.filter(responsable_id=responsable)

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
        "estados_disponibles": estados_disponibles,
        "canales_disponibles": canales_disponibles,
        "responsables_disponibles": responsables_disponibles,
        "filtro_estado": estado,
        "filtro_canal": canal,
        "filtro_responsable": responsable,
        "hay_filtros": bool(estado or canal or responsable),
    }

    return render(
        request,
        "core/panel_comercial.html",
        contexto,
    )