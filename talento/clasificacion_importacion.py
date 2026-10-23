"""Reglas de importación: clasificación prioritaria y observaciones no bloqueantes."""
import re
import unicodedata
from pathlib import Path


def normalizar(texto):
    texto = unicodedata.normalize("NFKD", str(texto or ""))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", texto.lower()).strip()


def clasificar_adjunto(nombre_archivo, texto=""):
    nombre = normalizar(Path(str(nombre_archivo or "")).stem)
    contenido = normalizar(texto)[:20000]
    if re.search(r"\b(cv|curriculum|curriculo|hoja de vida|resume)\b", nombre):
        return "curriculum"
    if re.search(r"\b(titulo|diploma de titulo|certificado de titulo)\b", nombre):
        return "titulo"
    if re.search(r"\b(curriculum vitae|experiencia laboral|perfil profesional)\b", contenido):
        return "curriculum"
    if re.search(r"\b(titulo profesional|titulo academico|grado academico)\b", contenido):
        return "titulo"
    return "otro"


def observaciones_minimas(datos, tipos_documentos):
    datos = datos or {}
    campos = (("rut", "RUT"), ("nombre", "nombre"), ("direccion", "dirección"),
              ("email", "correo"), ("telefono", "celular"))
    observaciones = [
        f"No se identificó {etiqueta}."
        for clave, etiqueta in campos
        if not str(datos.get(clave) or "").strip()
    ]
    tipos = set(tipos_documentos or ())
    if "curriculum" not in tipos:
        observaciones.append("No se identificó CV.")
    if "titulo" not in tipos:
        observaciones.append("No se identificó título profesional.")
    return observaciones
