"""Isolated settings for the RADAR Django test suite."""

import atexit
import os
import tempfile
from pathlib import Path

from . import settings as base_settings
from .settings import *  # noqa: F401,F403


def _required(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} must be set to run RADAR tests")
    return value


def _normalize_host(value):
    value = value.strip().lower()
    if value in {"", "localhost"}:
        return "127.0.0.1"
    return value


TEST_DB_NAME = _required("RADAR_TEST_DB_NAME")
TEST_DB_USER = _required("RADAR_TEST_DB_USER")
TEST_DB_PASSWORD = _required("RADAR_TEST_DB_PASSWORD")
TEST_DB_HOST = os.environ.get("RADAR_TEST_DB_HOST", "127.0.0.1").strip()
TEST_DB_PORT = os.environ.get("RADAR_TEST_DB_PORT", "5432").strip()
TEST_DB_SSLMODE = os.environ.get("RADAR_TEST_DB_SSLMODE", "prefer").strip()

DEVELOPMENT_DATABASE = base_settings.DATABASES["default"]
if TEST_DB_NAME == DEVELOPMENT_DATABASE["NAME"]:
    raise RuntimeError("RADAR_TEST_DB_NAME cannot be the development database")

same_endpoint = (
    _normalize_host(TEST_DB_HOST) == _normalize_host(DEVELOPMENT_DATABASE["HOST"])
    and TEST_DB_PORT == str(DEVELOPMENT_DATABASE["PORT"])
)
same_credentials = (
    TEST_DB_USER == DEVELOPMENT_DATABASE["USER"]
    and TEST_DB_PASSWORD == DEVELOPMENT_DATABASE["PASSWORD"]
)
if same_endpoint and same_credentials:
    raise RuntimeError("Test PostgreSQL credentials match the development database")
if TEST_DB_NAME.startswith("test_"):
    raise RuntimeError(
        "RADAR_TEST_DB_NAME must be the connection database, not Django's test database"
    )

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": TEST_DB_NAME,
        "USER": TEST_DB_USER,
        "PASSWORD": TEST_DB_PASSWORD,
        "HOST": TEST_DB_HOST,
        "PORT": TEST_DB_PORT,
        "OPTIONS": {"sslmode": TEST_DB_SSLMODE},
        "CONN_MAX_AGE": 0,
        "TEST": {"NAME": f"test_{TEST_DB_NAME}"},
    }
}

_media_temp = tempfile.TemporaryDirectory(prefix="radar-test-media-")
atexit.register(_media_temp.cleanup)
MEDIA_ROOT = Path(_media_temp.name).resolve()

_private_media = (base_settings.BASE_DIR / "media_privada").resolve()
if MEDIA_ROOT == _private_media or _private_media in MEDIA_ROOT.parents:
    _media_temp.cleanup()
    raise RuntimeError("Test MEDIA_ROOT cannot be media_privada or inside it")

ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]
DEBUG = False
SECRET_KEY = "radar-test-only-not-a-secret"
