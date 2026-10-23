from django.urls import path
from . import views

urlpatterns = [
    path("organizaciones/<int:organizacion_id>/conexiones/", views.conexiones, name="google_conexiones"),
    path("organizaciones/<int:organizacion_id>/conectar/", views.iniciar_oauth, name="google_iniciar_oauth"),
    path("callback/", views.callback_oauth, name="google_oauth_callback"),
    path("organizaciones/<int:organizacion_id>/conexiones/<int:conexion_id>/desconectar/", views.desconectar, name="google_desconectar"),
]
