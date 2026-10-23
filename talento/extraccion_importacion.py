"""Extracción conservadora de datos de contacto desde texto previamente leído."""
import re

PATRON_EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
PATRON_TELEFONO = re.compile(r"(?<!\d)(?:\+?56[\s.-]*)?9[\s.-]*\d{4}[\s.-]*\d{4}(?!\d)")
PATRON_NOMBRE = re.compile(r"(?im)^[ \t]*nombre[ \t]*:[ \t]*(.{3,160})$")
PATRON_DIRECCION = re.compile(r"(?im)^[ \t]*(?:direcci[oó]n|domicilio)[ \t]*:[ \t]*(.{3,160})$")


def extraer_datos(texto):
    texto = str(texto or "")[:200000]
    datos = {}
    correo = PATRON_EMAIL.search(texto)
    if correo:
        datos["email"] = correo.group()
    telefono = PATRON_TELEFONO.search(texto)
    if telefono:
        datos["telefono"] = telefono.group().strip()
    for campo, patron in (("nombre", PATRON_NOMBRE), ("direccion", PATRON_DIRECCION)):
        resultado = patron.search(texto)
        if resultado:
            datos[campo] = resultado.group(1).strip()
    return datos
