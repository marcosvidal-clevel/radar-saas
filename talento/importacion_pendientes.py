"""Manifest adapter for the existing private inbox services (no extraction)."""
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.files import File

from .entradas_services import CAMPOS, huella, inspeccionar_recepcion, recibir_entrada


def datos_pendientes(row, document):
    declaration = row.get("pendiente")
    if not isinstance(declaration, dict):
        raise ValidationError("pendiente debe contener motivo, fuente y datos opcionales.")
    reason, evidence = declaration.get("motivo"), declaration.get("fuente")
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 300:
        raise ValidationError("Indique un motivo breve (máximo 300 caracteres).")
    if not isinstance(evidence, str) or not evidence.strip():
        raise ValidationError("Indique la fuente de los datos explícitos.")
    explicit = declaration.get("datos", {})
    if not isinstance(explicit, dict) or set(explicit) - set(CAMPOS):
        raise ValidationError("Datos pendientes desconocidos; no se permiten destinos automáticos.")
    values = dict(explicit)
    for state, fields in (("identidad_estado", ("nombre",)), ("profesion_estado", ("profesion",)),
                          ("ubicacion_estado", ("region", "ciudad"))):
        # Receiving evidence does not confirm identity or ownership.
        values[state] = "no_confirmado" if any(values.get(f) for f in fields) else "no_consta"
    values.update(origen_importacion=row.get("origen_importacion", ""),
        identificador_origen=row.get("identificador_origen", ""),
        clave_documental=document.get("identificador_origen", ""),
        motivo_pendiente=reason.strip(), contexto_recepcion=row.get("contexto_recepcion", {}),
        tipo_documento=document.get("tipo") or "otro",
        clasificacion_confirmada=bool(document.get("tipo")))
    return values, evidence


def inspeccionar_documento(*, path, row, document, usuario, organizacion):
    values, evidence = datos_pendientes(row, document)
    with path.open("rb") as source:
        digest = huella(File(source, name=path.name))
        current = inspeccionar_recepcion(usuario=usuario, organizacion=organizacion,
            datos=values, fuente=evidence, archivo=File(source, name=path.name))
    return {"status": "duplicado" if current else "entrada_pendiente", "path": path,
            "datos": values, "fuente": evidence, "row": document, "sha256": digest}


def importar_documento(plan, usuario, organizacion):
    with Path(plan["path"]).open("rb") as source:
        if huella(File(source, name=plan["path"].name)) != plan["sha256"]:
            raise ValidationError("Archivo cambiado después de la previsualización.")
        return recibir_entrada(usuario=usuario, organizacion=organizacion,
            datos=plan["datos"], fuente=plan["fuente"], archivo=File(source, name=plan["path"].name))
