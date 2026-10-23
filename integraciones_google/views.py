"""Vistas OAuth para conectar una cuenta Google con permisos de solo lectura."""
import json
import logging

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseBadRequest
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from core.models import Membresia, Organizacion
from talento.oauth_google import (
    SCOPES, cuenta_permitida, cifrar_token, crear_state, validar_scopes,
    validar_state,
)
from .models import ConexionGoogle

logger = logging.getLogger(__name__)


def _organizacion_admin(request, organizacion_id):
    membresia = Membresia.objects.filter(
        usuario=request.user,
        organizacion_id=organizacion_id,
        organizacion__activa=True,
        activa=True,
        rol=Membresia.Rol.ADMINISTRADOR,
    ).select_related("organizacion").first()
    if not membresia and not request.user.is_superuser:
        raise PermissionDenied("Solo un administrador de la organización puede conectar Google.")
    if request.user.is_superuser:
        return Organizacion.objects.get(pk=organizacion_id, activa=True)
    return membresia.organizacion


@login_required
@require_GET
def iniciar_oauth(request, organizacion_id):
    organizacion = _organizacion_admin(request, organizacion_id)
    if not request.session.session_key:
        request.session.save()
    state = crear_state(request.session.session_key, organizacion.pk)
    request.session["google_oauth_org"] = organizacion.pk
    request.session["google_oauth_state"] = state
    from talento.oauth_google import url_autorizacion
    return redirect(url_autorizacion(state))


@login_required
@require_GET
def callback_oauth(request):
    state = request.GET.get("state", "")
    organizacion_id = request.session.pop("google_oauth_org", None)
    state_esperado = request.session.pop("google_oauth_state", None)
    if request.GET.get("error"):
        return HttpResponseBadRequest("Google no autorizó la conexión.")
    if not organizacion_id or not state_esperado or state != state_esperado:
        raise PermissionDenied("Respuesta OAuth no vinculada a la sesión.")
    organizacion = _organizacion_admin(request, organizacion_id)
    validar_state(state, request.session.session_key, organizacion.pk)

    from google_auth_oauthlib.flow import Flow
    from talento.oauth_google import _required_env
    redirect_uri = _required_env("GOOGLE_OAUTH_REDIRECT_URI")
    config = {"web": {
        "client_id": _required_env("GOOGLE_OAUTH_CLIENT_ID"),
        "client_secret": _required_env("GOOGLE_OAUTH_CLIENT_SECRET"),
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": [redirect_uri],
    }}
    flow = Flow.from_client_config(config, scopes=list(SCOPES), state=state)
    flow.redirect_uri = redirect_uri
    flow.fetch_token(authorization_response=request.build_absolute_uri())
    credentials = flow.credentials
    validar_scopes(credentials.scopes)
    if not credentials.refresh_token:
        return HttpResponseBadRequest(
            "Google no entregó refresh token. Revoca el acceso anterior y vuelve a autorizar."
        )

    from googleapiclient.discovery import build
    servicio = build("oauth2", "v2", credentials=credentials, cache_discovery=False)
    perfil = servicio.userinfo().get().execute()
    email = (perfil.get("email") or "").strip().lower()
    if not perfil.get("verified_email") or not cuenta_permitida(email):
        raise PermissionDenied("La cuenta Google no está verificada o no está autorizada.")

    datos_token = {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "scopes": list(credentials.scopes or SCOPES),
    }
    ConexionGoogle.objects.update_or_create(
        organizacion=organizacion,
        cuenta_email=email,
        defaults={
            "token_cifrado": cifrar_token(json.dumps(datos_token)),
            "scopes": list(credentials.scopes or SCOPES),
            "activa": True,
        },
    )
    logger.info("Cuenta Google conectada para organización %s", organizacion.pk)
    return redirect("google_conexiones", organizacion_id=organizacion.pk)


@login_required
@require_GET
def conexiones(request, organizacion_id):
    organizacion = _organizacion_admin(request, organizacion_id)
    # La vista no muestra tokens ni datos de los mensajes/documentos.
    from django.http import JsonResponse
    items = list(ConexionGoogle.objects.filter(organizacion=organizacion).values(
        "id", "cuenta_email", "scopes", "activa", "creada_en", "actualizada_en"
    ))
    for item in items:
        item["creada_en"] = item["creada_en"].isoformat()
        item["actualizada_en"] = item["actualizada_en"].isoformat()
    return JsonResponse({"conexiones": items})


@login_required
@require_POST
def desconectar(request, organizacion_id, conexion_id):
    organizacion = _organizacion_admin(request, organizacion_id)
    conexion = ConexionGoogle.objects.filter(
        pk=conexion_id, organizacion=organizacion
    ).first()
    if not conexion:
        from django.http import Http404
        raise Http404("Conexión no encontrada.")
    # Se destruye el token local. La revocación remota se puede reintentar
    # sin conservar credenciales: Google permite revocar el grant desde la cuenta.
    conexion.token_cifrado = ""
    conexion.activa = False
    conexion.save(update_fields=("token_cifrado", "activa", "actualizada_en"))
    logger.info("Cuenta Google desconectada para organización %s", organizacion.pk)
    return redirect("google_conexiones", organizacion_id=organizacion.pk)
