
from django.contrib import admin
from django.urls import path

from core.views import (
    detalle_oportunidad,
    nueva_oportunidad,
    panel_comercial,
)

from talento.views import descargar_documento_candidato


urlpatterns = [
    path(
        "admin/",
        admin.site.urls,
    ),
    path(
        "panel/",
        panel_comercial,
        name="panel_comercial",
    ),
    path(
        "oportunidades/nueva/",
        nueva_oportunidad,
        name="nueva_oportunidad",
    ),
    path(
        "oportunidades/<int:pk>/",
        detalle_oportunidad,
        name="detalle_oportunidad",
    ),
    path(
        "talento/documentos/<int:pk>/descargar/",
        descargar_documento_candidato,
        name="descargar_documento_candidato",
    ),
]
