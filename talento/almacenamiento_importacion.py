"""Persistencia de adjuntos permitidos para fichas importadas.

Los errores de un adjunto se informan al llamador y no revierten el candidato.
"""
from pathlib import Path

from django.core.files.base import ContentFile

from .clasificacion_importacion import clasificar_adjunto
from .models import DocumentoCandidato

EXTENSIONES = {".pdf", ".doc", ".docx"}
MAX_BYTES = 10 * 1024 * 1024


def guardar_adjuntos_importados(*, candidato, adjuntos, origen):
    resultados = []
    for indice, adjunto in enumerate(adjuntos or ()):
        nombre = Path(str(adjunto.get("nombre") or f"adjunto_{indice}")).name
        identificador = str(adjunto.get("identificador_origen") or f"{indice}:{nombre}")
        registro = {"nombre": nombre, "identificador_origen": identificador}
        try:
            if Path(nombre).suffix.lower() not in EXTENSIONES:
                raise ValueError("Formato no admitido por el modelo documental actual.")
            contenido = adjunto.get("contenido")
            if not isinstance(contenido, bytes) or not contenido:
                raise ValueError("Adjunto sin contenido binario.")
            if len(contenido) > MAX_BYTES:
                raise ValueError("Adjunto superior a 10 MB.")
            existente = DocumentoCandidato.objects.filter(
                candidato=candidato, origen_importacion=str(origen),
                identificador_origen=identificador,
            ).first()
            if existente:
                registro.update(estado="existente", documento_id=existente.pk)
            else:
                tipo = clasificar_adjunto(nombre, adjunto.get("texto") or "")
                documento = DocumentoCandidato(
                    candidato=candidato, nombre=nombre[:200], tipo=tipo,
                    origen_importacion=str(origen),
                    identificador_origen=identificador,
                    es_cv_principal=(
                        tipo == "curriculum"
                        and not candidato.documentos.filter(es_cv_principal=True).exists()
                    ),
                )
                documento.archivo.save(nombre, ContentFile(contenido), save=False)
                documento.save()
                registro.update(estado="guardado", documento_id=documento.pk, tipo=tipo)
        except Exception as exc:
            registro.update(estado="error", observacion=str(exc))
        resultados.append(registro)
    return resultados
