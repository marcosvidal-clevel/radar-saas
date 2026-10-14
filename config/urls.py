from django.contrib import admin
from django.urls import path

from core.views import panel_comercial


urlpatterns = [
    path("admin/", admin.site.urls),
    path("panel/", panel_comercial, name="panel_comercial"),
]
