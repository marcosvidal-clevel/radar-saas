"""Lectura paginada desde clientes autenticados, sin almacenar credenciales.

Los clientes Gmail y Drive son inyectados por la capa de integración.
Esta capa nunca elimina ni modifica mensajes o archivos de origen.
"""
import base64

from .fuentes_importacion import importar_carpeta_drive, importar_mensaje


def _texto_base64url(valor):
    if not valor:
        return ""
    return base64.urlsafe_b64decode(valor + "=" * (-len(valor) % 4)).decode(
        "utf-8", errors="replace"
    )


def _cuerpo_gmail(payload):
    if payload.get("mimeType", "").startswith("text/plain") and payload.get("body", {}).get("data"):
        return _texto_base64url(payload["body"]["data"])
    for parte in payload.get("parts") or ():
        texto = _cuerpo_gmail(parte)
        if texto:
            return texto
    return ""


def _partes_adjuntas(payload):
    if payload.get("filename") and payload.get("body", {}).get("attachmentId"):
        yield payload
    for parte in payload.get("parts") or ():
        yield from _partes_adjuntas(parte)


def importar_gmail_api(*, organizacion, servicio, consulta="has:attachment", limite=100):
    """Consume API Gmail users.messages.list/get y attachments.get.

    servicio es un cliente googleapiclient autenticado. No requiere permisos
    de escritura; la consulta y el límite los define el llamador.
    """
    resultados = []
    pagina = None
    while len(resultados) < limite:
        argumentos = {"userId": "me", "q": consulta, "maxResults": min(100, limite - len(resultados))}
        if pagina:
            argumentos["pageToken"] = pagina
        respuesta = servicio.users().messages().list(**argumentos).execute()
        mensajes = respuesta.get("messages") or []
        for referencia in mensajes:\n            try:\n            except Exception as exc:\n                resultados.append({"estado": "error", "mensaje_id": referencia.get("id"),\n                                   "observacion": f"{type(exc).__name__}: {exc}"})\n        pagina = respuesta.get("nextPageToken")
        if not pagina or not mensajes:
            break
    return resultados


def importar_drive_api(*, organizacion, servicio, carpeta_id, limite=100):
    """Lee archivos binarios desde una carpeta usando Drive API v3.

    Requiere cliente autorizado con permiso de lectura de los archivos.
    Los documentos nativos de Google necesitan exportación previa.
    """
    resultados = []
    pagina = None
    while len(resultados) < limite:
        parametros = {
            "q": f"'{carpeta_id}' in parents and trashed = false",
            "fields": "nextPageToken,files(id,name,mimeType)",
            "pageSize": min(100, limite - len(resultados)),
        }
        # googleapiclient usa pageSize, no page_size.
        parametros["pageSize"] = parametros.pop("page_size")
        if pagina:
            parametros["pageToken"] = pagina
        respuesta = servicio.files().list(**parametros).execute()
        for archivo in respuesta.get("files") or ():
            if archivo.get("mimeType", "").startswith("application/vnd.google-apps."):
                resultados.append({"estado": "pendiente", "archivo_id": archivo["id"],
                                   "observacion": "Documento nativo requiere exportación"})
                continue
            contenido = servicio.files().get_media(fileId=archivo["id"]).execute()
            resultados.extend(importar_carpeta_drive(
                organizacion=organizacion, carpeta_id=carpeta_id,
                archivos=[{**archivo, "contenido": contenido}],
            ))
            if len(resultados) >= limite:
                break
\n            try:\n            except Exception as exc:\n                resultados.append({"estado": "error", "archivo_id": archivo.get("id"),\n                                   "observacion": f"{type(exc).__name__}: {exc}"})\n        pagina = respuesta.get("nextPageToken")
        if not pagina or not respuesta.get("files"):
            break
    return resultados
