"""Persistencia de adjuntos permitidos para fichas importadas.

Los errores de un adjunto se informan al llamador y no revierten el candidato.
"""
from pathlib import Path

from django.core.files.base import ContentFile

from .clasificacion_importacion import clasificar_adjunto
from .models import AdjuntoImportado, DocumentoCandidato

EXTENSIONES = {".pdf", ".doc", ".docx"}
MAX_BYTES = 10 * 1024 * 1024


def guardar_adjuntos_importados(*, candidato, adjuntos, origen):
    resultados = []
    for indice, adjunto in enumerate(adjuntos or ()):
        nombre = Path(str(adjunto.get("nombre") or f"adjunto_{indice}")).name
        identificador = str(adjunto.get("identificador_origen") or f"{indice}:{nombre}")
        registro = {"nombre": nombre, "identificador_origen": identificador}
        try:
            contenido = adjunto.get("contenido")
            if not isinstance(contenido, bytes) or not contenido:
                raise ValueError("Adjunto sin contenido binario.")
            usar_documento = Path(nombre).suffix.lower() in EXTENSIONES and len(contenido) <= MAX_BYTES
            modelo = DocumentoCandidato if usar_documento else AdjuntoImportado
            existente = modelo.objects.filter(
                candidato=candidato, origen_importacion=str(origen),
                identificador_origen=identificador,
            ).first()
            if existente:
                registro.update(estado="existente", documento_id=existente.pk)
            else:
                tipo = clasificar_adjunto(nombre, adjunto.get("texto") or "")
                campos = dict(
                    candidato=candidato, nombre=nombre[:200 if usar_documento else 255],
                    tipo=tipo if usar_documento else "otro",
                    origen_importacion=str(origen), identificador_origen=identificador,
                )
                if usar_documento:
                    campos["es_cv_principal"] = (
                        tipo == "curriculum"
                        and not candidato.documentos.filter(es_cv_principal=True).exists()
                    )
                documento = modelo(**campos)
                documento.archivo.save(nombre, ContentFile(contenido), save=False)
                documento.save()
                registro.update(estado="guardado", documento_id=documento.pk,
                                tipo=tipo if usar_documento else "otro",
                                almacenamiento="documentos" if usar_documento else "otros_documentos")
        except Exception as exc:
            registro.update(estado="error", observacion=str(exc))
        resultados.append(registro)
    return resultados
