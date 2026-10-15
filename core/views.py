from urllib.parse import urlencode

from django.contrib import admin
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from .models import Membresia, Oportunidad


@staff_member_required(login_url="admin:login")
def panel_comercial(request):
    administrador = admin.site._registry[Oportunidad]

    if not administrador.has_view_permission(request):
        raise PermissionDenied(
            "No tienes acceso al panel comercial."
        )

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

    busqueda = request.GET.get("q", "").strip()[:200]
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

    if busqueda:
        activas = activas.filter(
            Q(titulo__icontains=busqueda)
            | Q(empresa__nombre__icontains=busqueda)
            | Q(nombre_consultante__icontains=busqueda)
        )

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

    paginador = Paginator(
        activas.order_by("-creada_en", "-pk"),
        20,
    )
    pagina_oportunidades = paginador.get_page(
        request.GET.get("pagina")
    )

    parametros = {}
    if busqueda:
        parametros["q"] = busqueda
    if estado:
        parametros["estado"] = estado
    if canal:
        parametros["canal"] = canal
    if responsable:
        parametros["responsable"] = responsable

    contexto = {
        "hoy": hoy,
        "total_activas": paginador.count,
        "total_calientes": calientes.count(),
        "total_vencidas": vencidas.count(),
        "total_para_hoy": para_hoy.count(),
        "total_sin_fecha": sin_fecha.count(),
        "calientes": calientes.order_by("-creada_en")[:20],
        "seguimientos": activas.filter(
            fecha_proxima_accion__lte=hoy
        ).order_by("fecha_proxima_accion", "pk")[:20],
        "sin_fecha": sin_fecha.order_by("-creada_en")[:20],
        "pagina_oportunidades": pagina_oportunidades,
        "parametros_filtros": urlencode(parametros),
        "puede_crear": administrador.has_add_permission(request),
        "estados_disponibles": estados_disponibles,
        "canales_disponibles": canales_disponibles,
        "responsables_disponibles": responsables_disponibles,
        "busqueda": busqueda,
        "filtro_estado": estado,
        "filtro_canal": canal,
        "filtro_responsable": responsable,
        "hay_filtros": bool(
            busqueda or estado or canal or responsable
        ),
    }

    return render(
        request,
        "core/panel_comercial.html",
        contexto,
    )


@staff_member_required(login_url="admin:login")
def detalle_oportunidad(request, pk):
    administrador = admin.site._registry[Oportunidad]

    if not administrador.has_view_permission(request):
        raise PermissionDenied(
            "No tienes acceso a las oportunidades comerciales."
        )

    # Busca únicamente entre los registros autorizados.
    oportunidades = administrador.get_queryset(request).select_related(
        "organizacion",
        "empresa",
        "contacto",
        "senal",
        "responsable__usuario",
        "responsable__organizacion",
    )
    oportunidad = get_object_or_404(oportunidades, pk=pk)

    if not administrador.has_view_permission(request, oportunidad):
        raise PermissionDenied(
            "No tienes acceso a esta oportunidad."
        )

    contexto = {
        "oportunidad": oportunidad,
        "hoy": timezone.localdate(),
        "puede_editar": administrador.has_change_permission(
            request,
            oportunidad,
        ),
        "esta_cerrada": oportunidad.estado in (
            Oportunidad.Estado.GANADA,
            Oportunidad.Estado.PERDIDA,
            Oportunidad.Estado.DESCARTADA,
        ),
    }

    return render(
        request,
        "core/detalle_oportunidad.html",
        contexto,
    )