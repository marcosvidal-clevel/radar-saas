"""Servicio inicial para registrar candidatos importados sin descartar fichas incompletas.

La entrada ya debe contener datos extraídos por un lector autorizado. No interpreta
adjuntos ni ejecuta llamadas externas. Se requiere organización explícita.
"""
import hashlib
import json

from django.db import transaction

from .clasificacion_importacion import observaciones_minimas
from .models import Candidato


@transaction.atomic
def registrar_candidato_importado(*, organizacion, datos, origen, identificador):
    if not origen or not identificador:
        raise ValueError("La procedencia e identificador son obligatorios para evitar duplicados.")
    datos = dict(datos or {})
    campos = ("nombre", "rut", "direccion", "email", "telefono", "profesion", "experiencia")
    valores = {campo: str(datos.get(campo) or "").strip() for campo in campos}
    if not valores["nombre"]:
        valores["nombre"] = f"Pendiente de identificación ({identificador[:35]})"
    tipos = datos.get("tipos_documentos") or []
    observaciones = observaciones_minimas(datos, tipos)
    valores["notas"] = "\n".join(observaciones)
    candidato, creado = Candidato.objects.get_or_create(
        organizacion=organizacion,
        origen_importacion=str(origen),
        identificador_origen=str(identificador),
        defaults=valores,
    )
    return candidato, creado, observaciones
