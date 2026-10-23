"""Preparación de registros desde texto y nombres de archivos.

No guarda adjuntos: entrega un manifiesto para que un servicio de almacenamiento
autorizado los persista posteriormente.
"""
from .clasificacion_importacion import clasificar_adjunto, observaciones_minimas
from .extraccion_importacion import extraer_datos
from .rut_importacion import extraer_rut


def preparar_importacion(*, texto="", adjuntos=()):
    adjuntos = list(adjuntos or ())
    datos = extraer_datos(texto)
    datos["rut"] = extraer_rut(texto)
    manifiesto = []
    for adjunto in adjuntos:
        nombre = str(adjunto.get("nombre") or "")
        texto_adjunto = str(adjunto.get("texto") or "")
        tipo = clasificar_adjunto(nombre, texto_adjunto)
        manifiesto.append({
            "nombre": nombre,
            "tipo": tipo,
            "identificador_origen": str(adjunto.get("identificador_origen") or ""),
        })
        extraidos = extraer_datos(texto_adjunto)
        for campo, valor in extraidos.items():
            if not datos.get(campo):
                datos[campo] = valor
        if not datos["rut"]:
            datos["rut"] = extraer_rut(texto_adjunto)
    tipos = [archivo["tipo"] for archivo in manifiesto]
    datos["tipos_documentos"] = tipos
    return {
        "datos": datos,
        "documentos": manifiesto,
        "observaciones": observaciones_minimas(datos, tipos),
    }
