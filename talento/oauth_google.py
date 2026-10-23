"""Utilidades seguras para preparar OAuth de Google en modo solo lectura."""
import os
import secrets

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, PermissionDenied
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner

GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.readonly"
SCOPES = (GMAIL_SCOPE, DRIVE_SCOPE)
STATE_SALT = "radar.google.oauth.state"
STATE_MAX_AGE = 600


def _required_env(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise ImproperlyConfigured(f"Falta configurar {name} en el entorno.")
    return value


def _signer():
    return TimestampSigner(key=settings.SECRET_KEY, salt=STATE_SALT)


def crear_state(session_key, organizacion_id):
    if not session_key or not organizacion_id:
        raise ValueError("Se requiere sesión y organización.")
    nonce = secrets.token_urlsafe(32)
    return _signer().sign(f"{session_key}:{organizacion_id}:{nonce}")


def validar_state(state, session_key, organizacion_id):
    if not state or not session_key or not organizacion_id:
        raise PermissionDenied("Estado OAuth incompleto.")
    try:
        value = _signer().unsign(state, max_age=STATE_MAX_AGE)
    except (BadSignature, SignatureExpired) as exc:
        raise PermissionDenied("Estado OAuth inválido o expirado.") from exc
    if not value.startswith(f"{session_key}:{organizacion_id}:"):
        raise PermissionDenied("El estado OAuth no corresponde a esta sesión.")
    return True


def cifrar_token(token):
    if not isinstance(token, str) or not token:
        raise ValueError("Token vacío.")
    key = _required_env("RADAR_OAUTH_TOKEN_KEY").encode("ascii")
    try:
        return Fernet(key).encrypt(token.encode("utf-8")).decode("ascii")
    except (ValueError, TypeError) as exc:
        raise ImproperlyConfigured("La clave de cifrado no es válida.") from exc


def descifrar_token(token_cifrado):
    key = _required_env("RADAR_OAUTH_TOKEN_KEY").encode("ascii")
    try:
        return Fernet(key).decrypt(token_cifrado.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, TypeError) as exc:
        raise ImproperlyConfigured("No se pudo descifrar el token.") from exc


def validar_scopes(concedidos):
    """Acepta exclusivamente los dos scopes solicitados; rechaza permisos extra."""
    concedidos = set(concedidos or ())
    requeridos = set(SCOPES)
    if concedidos != requeridos:
        raise PermissionDenied(
            "Los permisos concedidos no coinciden exactamente con los permisos mínimos de lectura."
        )
    return True


def cuenta_permitida(email):
    allowed = {
        item.strip().lower()
        for item in _required_env("GOOGLE_OAUTH_ALLOWED_EMAILS").split(",")
        if item.strip()
    }
    return bool(email and email.strip().lower() in allowed)


def url_autorizacion(state):
    from google_auth_oauthlib.flow import Flow

    redirect_uri = _required_env("GOOGLE_OAUTH_REDIRECT_URI")
    config = {
        "web": {
            "client_id": _required_env("GOOGLE_OAUTH_CLIENT_ID"),
            "client_secret": _required_env("GOOGLE_OAUTH_CLIENT_SECRET"),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri],
        }
    }
    flow = Flow.from_client_config(config, scopes=list(SCOPES))
    flow.redirect_uri = redirect_uri
    url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="false",
        prompt="consent",
        state=state,
    )
    return url
