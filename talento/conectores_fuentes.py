"""Conectores de lectura Gmail/Drive con clientes autenticados inyectados."""
import base64

from .fuentes_importacion import importar_carpeta_drive, importar_mensaje


def _decodificar(dato):
    return base64.urlsafe_b64decode(dato + "=" * (-len(dato) % 4))


def _texto(payload):
    if payload.get("mimeType", "").startswith("text/plain"):
        dato = payload.get("body", {}).get("data")
        if dato:
            return _decodificar(dato).decode("utf-8", errors="replace")
    for parte in payload.get("parts") or ():
        resultado = _texto(parte)
        if resultado:
            return resultado
    return ""


def _adjuntos(payload):
    if payload.get("filename") and payload.get("body", {}).get("attachmentId"):
        yield payload
    for parte in payload.get("parts") or ():
        yield from _adjuntos(parte)


def importar_gmail_api(*, organizacion, servicio, consulta="has:attachment", limite=100):
    """Lee mensajes y adjuntos sin modificar la cuenta de origen."""
    if limite <= 0:
        return []
    resultados = []
    pagina = None
    while len(resultados) < limite:
        parametros = {"userId": "me", "q": consulta,
                      "maxResults": min(100, limite - len(resultados))}
        if pagina:
            parametros["pageToken"] = pagina
        respuesta = servicio.users().messages().list(**parametros).execute()
        mensajes = respuesta.get("messages") or []
        for referencia in mensajes:
            try:
                mensaje = servicio.users().messages().get(
                    userId="me", id=referencia["id"], format="full"
                ).execute()
                payload = mensaje.get("payload") or {}
                cabeceras = {
                    h.get("name", "").lower(): h.get("value", "")
                    for h in payload.get("headers") or ()
                }
                adjuntos = []
                for parte in _adjuntos(payload):
                    adjunto_id = parte["body"]["attachmentId"]
                    respuesta_adjunto = servicio.users().messages().attachments().get(
                        userId="me", messageId=mensaje["id"], id=adjunto_id
                    ).execute()
                    adjuntos.append({
                        "id": adjunto_id, "nombre": parte["filename"],
                        "contenido": _decodificar(respuesta_adjunto.get("data") or ""),
                    })
                resultados.append(importar_mensaje(
                    organizacion=organizacion,
                    mensaje={"id": mensaje["id"],
                             "asunto": cabeceras.get("subject", ""),
                             "remitente": cabeceras.get("from", ""),
                             "cuerpo": _texto(payload), "adjuntos": adjuntos},
                ))
            except Exception as exc:
                resultados.append({
                    "estado": "error", "mensaje_id": referencia.get("id"),
                    "observacion": f"{type(exc).__name__}: {exc}",
                })
            if len(resultados) >= limite:
                break
        pagina = respuesta.get("nextPageToken")
        if not pagina or not mensajes:
            break
    return resultados


def importar_drive_api(*, organizacion, servicio, carpeta_id, limite=100):
    """Lee archivos de Drive v3 sin modificar los originales."""
    if limite <= 0:
        return []
    resultados = []
    pagina = None
    while len(resultados) < limite:
        parametros = {
            "q": f"'{carpeta_id}' in parents and trashed = false",
            "fields": "nextPageToken,files(id,name,mimeType)",
            "pageSize": min(100, limite - len(resultados)),
        }
        if pagina:
            parametros["pageToken"] = pagina
        respuesta = servicio.files().list(**parametros).execute()
        archivos = respuesta.get("files") or []
        for archivo in archivos:
            try:
                tipo_mime = archivo.get("mimeType", "")
                if tipo_mime.startswith("application/vnd.google-apps."):
                    contenido = servicio.files().export(
                        fileId=archivo["id"], mimeType="application/pdf"
                    ).execute()
                    archivo_local = {**archivo, "name": (archivo.get("name") or "documento") + ".pdf", "contenido": contenido}
                else:
                    contenido = servicio.files().get_media(
                        fileId=archivo["id"]
                    ).execute()
                    archivo_local = {**archivo, "contenido": contenido}
                resultados.extend(importar_carpeta_drive(
                    organizacion=organizacion, carpeta_id=carpeta_id,
                    archivos=[archivo_local],
                ))
            except Exception as exc:
                resultados.append({
                    "estado": "error", "archivo_id": archivo.get("id"),
                    "observacion": f"{type(exc).__name__}: {exc}",
                })
            if len(resultados) >= limite:
                break
        pagina = respuesta.get("nextPageToken")
        if not pagina or not archivos:
            break
    return resultados
