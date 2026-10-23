"""Conectores de lectura Gmail/Drive con clientes autenticados inyectados."""
import base64
from html.parser import HTMLParser

from .fuentes_importacion import importar_carpeta_drive, importar_mensaje


def _decodificar(dato):
    return base64.urlsafe_b64decode(dato + "=" * (-len(dato) % 4))


class _ExtractorHTML(HTMLParser):
    """Convierte el cuerpo HTML a texto sin ejecutar contenido activo."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.fragmentos = []
        self._ocultar = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() in {"script", "style", "head"}:
            self._ocultar += 1
        elif tag.lower() in {"p", "div", "br", "li", "tr"} and not self._ocultar:
            self.fragmentos.append("\\n")

    def handle_endtag(self, tag):
        if tag.lower() in {"script", "style", "head"} and self._ocultar:
            self._ocultar -= 1
        elif tag.lower() in {"p", "div", "li", "tr"} and not self._ocultar:
            self.fragmentos.append("\\n")

    def handle_data(self, data):
        if not self._ocultar:
            self.fragmentos.append(data)

    def texto(self):
        return " ".join(" ".join("".join(self.fragmentos).split()).split())


def _texto(payload):
    """Prefiere texto plano; usa HTML como alternativa si no existe texto plano."""
    html = ""
    if payload.get("mimeType", "").startswith("text/plain"):
        dato = payload.get("body", {}).get("data")
        if dato:
            return _decodificar(dato).decode("utf-8", errors="replace")
    if payload.get("mimeType", "").startswith("text/html"):
        dato = payload.get("body", {}).get("data")
        if dato:
            html = _decodificar(dato).decode("utf-8", errors="replace")
    for parte in payload.get("parts") or ():
        resultado = _texto(parte)
        if resultado:
            if parte.get("mimeType", "").startswith("text/plain"):
                return resultado
            html = html or resultado
    if html:
        parser = _ExtractorHTML()
        parser.feed(html)
        return parser.texto()
    return ""


def _adjuntos(payload):
    if payload.get("filename") and (payload.get("body", {}).get("attachmentId") or payload.get("body", {}).get("data")):
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
                    cuerpo_adjunto = parte["body"]
                    adjunto_id = cuerpo_adjunto.get("attachmentId")
                    if adjunto_id:
                        respuesta_adjunto = servicio.users().messages().attachments().get(
                            userId="me", messageId=mensaje["id"], id=adjunto_id
                        ).execute()
                        dato = respuesta_adjunto.get("data") or ""
                    else:
                        dato = cuerpo_adjunto.get("data") or ""
                    adjuntos.append({
                        "id": adjunto_id or parte.get("partId") or parte["filename"],
                        "nombre": parte["filename"],
                        "contenido": _decodificar(dato),
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
    if not isinstance(carpeta_id, str) or not carpeta_id.strip() or any(c in carpeta_id for c in ("'", "\n", "\r")):
        raise ValueError("Identificador de carpeta de Drive no válido.")
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
