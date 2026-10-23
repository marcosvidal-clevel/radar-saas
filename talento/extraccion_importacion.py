"""Extracción básica de campos de contacto desde texto ya leído."""
import re

def extraer_datos(texto):
    texto = str(texto or "")[:200000]
    datos = {}
    correo = re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", texto)
    if correo:
        datos["email"] = correo.group()
    telefono = re.search(r"(?:\+?56\s*)?9\s*\d{4}\s*\d{4}", texto)
    if telefono:
        datos["telefono"] = telefono.group().strip()
    for campo, etiqueta in (("nombre", "nombre"), ("direccion", "direcci[oó]n|domicilio")):
        resultado = re.search(r"(?im)^\s*(?:" + etiqueta + r")\s*:\s*(.{3,160})$", texto)
        if resultado:
            datos[campo] = resultado.group(1).strip()
    return datos
