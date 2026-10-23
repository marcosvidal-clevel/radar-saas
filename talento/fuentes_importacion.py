"""Adaptadores de datos descargados desde correo y Drive.

No requieren credenciales: los conectores autenticados suministran los mensajes
y los bytes descargados. Se conservan identificadores para reintentos idempotentes.
"""
from .flujo_importacion import importar_candidato


def importar_mensaje(*, organizacion, mensaje):
    """Importa cuerpo y adjuntos de un mensaje normalizado.

    mensaje: id, cuerpo, asunto, remitente, adjuntos con nombre/contenido/id.
    """
    identificador = str(mensaje.get("id") or "").strip()
    if not identificador:
        raise ValueError("Se requiere ID estable del mensaje.")
    cuerpo = "\n".join(
        str(mensaje.get(campo) or "") for campo in ("asunto", "remitente", "cuerpo")
    )
    adjuntos = [
        {**adjunto, "identificador_origen": str(
            adjunto.get("identificador_origen") or adjunto.get("id") or f"{identificador}:{indice}"
        )}
        for indice, adjunto in enumerate(mensaje.get("adjuntos") or ())
    ]
    return importar_candidato(
        organizacion=organizacion, origen="gmail",
        identificador=identificador, texto=cuerpo, adjuntos=adjuntos,
    )


def importar_carpeta_drive(*, organizacion, carpeta_id, archivos):
    """Importa cada archivo descargado de una carpeta como registro independiente.

    archivos: iterable de dicts con id, nombre, contenido y texto opcional.
    """
    if not carpeta_id:
        raise ValueError("Se requiere ID de carpeta.")
    resultados = []
    for archivo in archivos:
        identificador = str(archivo.get("id") or "").strip()
        if not identificador:
            resultados.append({"estado": "error", "observacion": "Archivo sin ID de Drive"})
            continue
        resultados.append(importar_candidato(
            organizacion=organizacion, origen=f"drive:{carpeta_id}",
            identificador=identificador,
            texto=str(archivo.get("texto") or ""),
            adjuntos=[{
                "nombre": archivo.get("nombre") or archivo.get("name") or "archivo",
                "contenido": archivo.get("contenido"),
                "identificador_origen": identificador,
                "texto": archivo.get("texto") or "",
            }],
        ))
    return resultados
