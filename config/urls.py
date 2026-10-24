
from django.contrib import admin
from django.urls import path
from talento import entradas_views
from integraciones.comercial import commercial_ingress

from core.views import (
    detalle_oportunidad,
    nueva_oportunidad,
    panel_comercial,
)

from talento.views import (
    candidatos,
    coincidencias_candidato,
    descargar_documento_candidato,
    detalle_candidato,
    editar_candidato,
    nuevo_candidato,
    nuevo_candidato_vacante,
    detalle_vacante,
    editar_vacante,
    nueva_entrevista,
    editar_entrevista,
    agenda_entrevistas,
    agregar_antecedente,
    nueva_vacante,
    vacantes,
    inicio_seleccion,
)


urlpatterns = [
    path("integraciones/make/comercial/<slug:site>/", commercial_ingress, name="make_comercial"),
    path("seleccion/entradas/", entradas_views.bandeja, name="entradas_pendientes"),
    path("seleccion/entradas/nueva/", entradas_views.editar, name="entrada_nueva"),
    path("seleccion/entradas/<int:pk>/", entradas_views.detalle, name="entrada_detalle"),
    path("seleccion/entradas/<int:pk>/editar/", entradas_views.editar, name="entrada_editar"),
    path("seleccion/entradas/<int:pk>/resolver/", entradas_views.resolver, name="entrada_resolver"),
    path("seleccion/entradas/<int:pk>/archivo/", entradas_views.descargar, name="entrada_descargar"),
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
    path(
        "talento/candidatos/",
        candidatos,
        name="talento_candidatos",
    ),
    path(
        "talento/candidatos/<int:pk>/",
        detalle_candidato,
        name="talento_detalle_candidato",
    ),
    path(
        "talento/candidatos/<int:pk>/antecedentes/agregar/",
        agregar_antecedente,
        name="talento_agregar_antecedente",
    ),
    path(
        "talento/candidatos/<int:pk>/coincidencias/",
        coincidencias_candidato,
        name="talento_coincidencias_candidato",
    ),
    path(
        "talento/candidatos/nuevo/",
        nuevo_candidato,
        name="talento_nuevo_candidato",
    ),
    path(
        "talento/candidatos/<int:pk>/editar/",
        editar_candidato,
        name="talento_editar_candidato",
    ),
    path("seleccion/", inicio_seleccion, name="seleccion_inicio"),
    path("seleccion/vacantes/", vacantes, name="seleccion_vacantes"),
    path("seleccion/vacantes/nueva/", nueva_vacante, name="seleccion_nueva_vacante"),
    path("seleccion/vacantes/<int:pk>/candidatos/nuevo/", nuevo_candidato_vacante, name="seleccion_nuevo_candidato"),
    path("seleccion/vacantes/<int:pk>/editar/", editar_vacante, name="seleccion_editar_vacante"),
    path("seleccion/entrevistas/", agenda_entrevistas, name="seleccion_agenda_entrevistas"),
    path("seleccion/postulaciones/<int:pk>/entrevistas/nueva/", nueva_entrevista, name="seleccion_nueva_entrevista"),
    path("seleccion/entrevistas/<int:pk>/editar/", editar_entrevista, name="seleccion_editar_entrevista"),
    path("seleccion/vacantes/<int:pk>/", detalle_vacante, name="seleccion_detalle_vacante"),
]
