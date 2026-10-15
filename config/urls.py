from django.contrib import admin
from django.urls import path

from core.views import detalle_oportunidad, panel_comercial


urlpatterns = [
    path("admin/", admin.site.urls),
    path("panel/", panel_comercial, name="panel_comercial"),
    path(
        "oportunidades/<int:pk>/",
        detalle_oportunidad,
        name="detalle_oportunidad",
    ),
]