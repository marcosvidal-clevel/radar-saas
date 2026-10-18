"""Production settings. Local development continues using config.settings."""

import os
from pathlib import Path

from . import settings as base_settings
from .settings import *  # noqa: F401,F403


def required(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} must be set in production")
    return value


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name, required_value=False):
    value = required(name) if required_value else os.environ.get(name, "")
    return [item.strip() for item in value.split(",") if item.strip()]


SECRET_KEY = required("RADAR_SECRET_KEY")
DEBUG = False
ALLOWED_HOSTS = env_list("RADAR_ALLOWED_HOSTS", required_value=True)

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": required("RADAR_DB_NAME"),
        "USER": required("RADAR_DB_USER"),
        "PASSWORD": required("RADAR_DB_PASSWORD"),
        "HOST": required("RADAR_DB_HOST"),
        "PORT": os.environ.get("RADAR_DB_PORT", "5432"),
        "CONN_MAX_AGE": int(os.environ.get("RADAR_DB_CONN_MAX_AGE", "60")),
        "OPTIONS": {"sslmode": os.environ.get("RADAR_DB_SSLMODE", "require")},
    },
}

STATIC_ROOT = Path(os.environ.get("RADAR_STATIC_ROOT", base_settings.BASE_DIR / "staticfiles"))
MEDIA_ROOT = Path(os.environ.get("RADAR_MEDIA_ROOT", "/var/lib/radar/media_privada"))
STATIC_URL = os.environ.get("RADAR_STATIC_URL", "/static/")

SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = int(os.environ.get("RADAR_HSTS_SECONDS", "31536000"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = env_bool("RADAR_HSTS_PRELOAD", False)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

CSRF_TRUSTED_ORIGINS = env_list("RADAR_CSRF_TRUSTED_ORIGINS", required_value=True)

# Forwarded HTTPS headers are ignored unless the deployment explicitly enables
# them and supplies the proxy networks enforced by TrustedProxyHeadersMiddleware.
if env_bool("RADAR_TRUST_PROXY_HEADERS"):
    TRUSTED_PROXY_IPS = env_list("RADAR_TRUSTED_PROXY_IPS", required_value=True)
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    MIDDLEWARE = [
        "config.proxy.TrustedProxyHeadersMiddleware",
        *base_settings.MIDDLEWARE,
    ]

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"require_debug_false": {"()": "django.utils.log.RequireDebugFalse"}},
    "formatters": {
        "safe": {"format": "{levelname} {asctime} {name} {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "safe"},
        "mail_admins": {
            "class": "django.utils.log.AdminEmailHandler",
            "level": "ERROR",
            "filters": ["require_debug_false"],
        },
    },
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "django.request": {"handlers": ["console", "mail_admins"], "level": "WARNING", "propagate": False},
    },
}
