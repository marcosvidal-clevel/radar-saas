import hashlib
from pathlib import Path

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files import File
from django.db import transaction
from django.db.models import Q

from core.models import Membresia, Organizacion
from .models import (
    Candidato, CandidatoProcedencia, DocumentoCandidato, DocumentoProcedencia,
    EntradaPendiente, RevisionEntrada,
)


CAMPOS = (
    "nombre", "identidad_estado", "profesion", "profesion_estado", "region", "ciudad",
    "ubicacion_estado", "telefono", "telefono_estado", "email", "email_estado",
    "correo_remitente", "tipo_documento", "clasificacion_confirmada", "limitacion_lectura",
    "informacion_por_completar", "seguimiento", "motivo_pendiente",
)
ORIGEN = ("origen_importacion", "identificador_origen", "clave_documental")


def autorizar(usuario, organizacion, permiso, *, gestionar=True):
    if not usuario.is_active or not organizacion.activa or not usuario.has_perm(permiso):
        raise PermissionDenied
    if usuario.is_superuser:
        return
    roles = (Membresia.Rol.ADMINISTRADOR, Membresia.Rol.SUPERVISOR) if gestionar else (
        Membresia.Rol.ADMINISTRADOR, Membresia.Rol.SUPERVISOR, Membresia.Rol.COLABORADOR,
    )
    if not Membresia.objects.filter(usuario=usuario, organizacion=organizacion, activa=True, rol__in=roles).exists():
        raise PermissionDenied


def huella(archivo):
    digest = hashlib.sha256()
    for chunk in archivo.chunks():
        digest.update(chunk)
    archivo.seek(0)
    return digest.hexdigest()


def auditar(entrada, usuario, fuente, accion):
    if not fuente or not fuente.strip():
        raise ValidationError("Indique la fuente de esta revisión o confirmación.")
    datos = {f: getattr(entrada, f) for f in CAMPOS + ORIGEN}
    datos.update(contexto_recepcion=entrada.contexto_recepcion, sha256=entrada.sha256, archivo=entrada.archivo.name,
                 candidato_id=entrada.candidato_id, documento_id=entrada.documento_id)
    anterior = entrada.revisiones.order_by("-pk").first()
    cambios = {k: {"antes": anterior.datos.get(k), "despues": v}
               for k, v in datos.items() if anterior and anterior.datos.get(k) != v}
    datos["cambios"] = cambios
    revision = RevisionEntrada(entrada=entrada, usuario=usuario, fuente=fuente.strip(), accion=accion, datos=datos)
    revision.full_clean()
    revision.save()


def guardar_entrada(*, usuario, organizacion, datos, fuente, archivo=None, entrada_id=None):
    saved_name = None
    storage = None
    try:
        with transaction.atomic():
            org = Organizacion.objects.select_for_update().get(pk=organizacion.pk)
            permiso = "change" if entrada_id else "add"
            autorizar(usuario, org, f"talento.{permiso}_entradapendiente")
            if not fuente or not fuente.strip():
                raise ValidationError("Indique la fuente de la revisión.")
            if entrada_id:
                entrada = EntradaPendiente.objects.select_for_update().get(pk=entrada_id, organizacion=org)
                if entrada.tipo_documento == "evaluacion":
                    raise ValidationError("Las evaluaciones requieren su flujo restringido.")
                if entrada.seguimiento == "resuelto":
                    raise ValidationError("La entrada resuelta conserva su historial y no se puede editar.")
                if archivo or any(f in datos and datos[f] != getattr(entrada, f) for f in ORIGEN):
                    raise ValidationError("Archivo y procedencia originales son inmutables.")
                if "contexto_recepcion" in datos and datos["contexto_recepcion"] != entrada.contexto_recepcion:
                    raise ValidationError("El contexto de recepción original es inmutable.")
            else:
                if archivo is None:
                    raise ValidationError("Se requiere conservar el archivo original.")
                entrada = EntradaPendiente(organizacion=org, creado_por=usuario)
                for f in ORIGEN:
                    setattr(entrada, f, datos.get(f, ""))
                entrada.archivo = archivo
                entrada.nombre_archivo_original = Path(archivo.name).name
                entrada.sha256 = huella(archivo)
                entrada.contexto_recepcion = datos.get("contexto_recepcion", {})
            validar_contexto(entrada.contexto_recepcion, org)
            rechazar_evaluacion(org, entrada.sha256)
            for f in CAMPOS:
                if f in datos:
                    setattr(entrada, f, datos[f])
            if entrada.seguimiento == "resuelto":
                raise ValidationError("Use la operación explícita de resolución.")
            entrada.actualizado_por = usuario
            entrada.full_clean()
            if not entrada.pk:
                # Guardar solo tras validar; limpiar exclusivamente esta copia si falla la transacción.
                entrada.archivo.save(entrada.nombre_archivo_original, archivo, save=False)
                saved_name, storage = entrada.archivo.name, entrada.archivo.storage
            entrada.save()
            auditar(entrada, usuario, fuente, "actualizar" if entrada_id else "crear")
            return entrada
    except Exception:
        if saved_name:
            storage.delete(saved_name)
        raise


def validar_contexto(contexto, organizacion):
    if not isinstance(contexto, dict):
        raise ValidationError("El contexto de recepción debe ser un objeto.")
    candidato_id = contexto.get("candidato_contexto_id")
    if candidato_id is not None:
        if not isinstance(candidato_id, int) or isinstance(candidato_id, bool) or not Candidato.objects.filter(pk=candidato_id, organizacion=organizacion).exists():
            raise ValidationError("Candidato de contexto ajeno o inexistente.")


def rechazar_evaluacion(organizacion, sha256):
    if DocumentoCandidato.objects.filter(candidato__organizacion=organizacion,
            sha256=sha256, tipo=DocumentoCandidato.Tipo.EVALUACION).exists():
        raise ValidationError("Archivo de evaluación: requiere el flujo restringido.")


def inspeccionar_recepcion(*, usuario, organizacion, datos, fuente, archivo):
    """Valida sin escribir; la clave de recepción, nunca el hash, da idempotencia."""
    autorizar(usuario, organizacion, "talento.add_entradapendiente")
    if not isinstance(fuente, str) or not fuente.strip():
        raise ValidationError("Indique la fuente de la recepción.")
    if datos.get("tipo_documento") == "evaluacion":
        raise ValidationError("Las evaluaciones requieren su flujo restringido.")
    digest = huella(archivo)
    rechazar_evaluacion(organizacion, digest)
    validar_contexto(datos.get("contexto_recepcion", {}), organizacion)
    actual = EntradaPendiente.objects.filter(organizacion=organizacion,
        **{k: datos.get(k, "") for k in ORIGEN}).first()
    if actual:
        if actual.sha256 != digest or actual.contexto_recepcion != datos.get("contexto_recepcion", {}):
            raise ValidationError("Conflicto: recepción existente con otro archivo o contexto.")
        with actual.archivo.open("rb") as original:
            if huella(original) != digest:
                raise ValidationError("Conflicto: archivo conservado alterado.")
        return actual
    entrada = EntradaPendiente(organizacion=organizacion, creado_por=usuario, actualizado_por=usuario,
        archivo=archivo, nombre_archivo_original=Path(archivo.name).name, sha256=digest,
        contexto_recepcion=datos.get("contexto_recepcion", {}),
        **{k: v for k, v in datos.items() if k in CAMPOS + ORIGEN})
    entrada.full_clean()
    return None


def recibir_entrada(*, usuario, organizacion, datos, fuente, archivo):
    """Conserva cada recepción una sola vez sin alterar revisiones posteriores."""
    with transaction.atomic():
        org = Organizacion.objects.select_for_update().get(pk=organizacion.pk)
        actual = inspeccionar_recepcion(usuario=usuario, organizacion=org, datos=datos, fuente=fuente, archivo=archivo)
        if actual:
            return actual, False
        return guardar_entrada(usuario=usuario, organizacion=org, datos=datos, fuente=fuente, archivo=archivo), True


def resolver_entrada(*, entrada_id, usuario, fuente, candidato_id=None):
    saved_name = None
    storage = None
    try:
        with transaction.atomic():
            initial = EntradaPendiente.objects.get(pk=entrada_id)
            org = Organizacion.objects.select_for_update().get(pk=initial.organizacion_id)
            entrada = EntradaPendiente.objects.select_for_update().get(pk=entrada_id)
            autorizar(usuario, org, "talento.change_entradapendiente")
            autorizar(usuario, org, "talento.add_documentocandidato")
            autorizar(usuario, org, "talento.add_candidatoprocedencia")
            autorizar(usuario, org, "talento.add_documentoprocedencia")
            if not fuente or not fuente.strip():
                raise ValidationError("Indique evidencia y fuente para resolver la identidad y el destino.")
            if entrada.seguimiento == "resuelto":
                if candidato_id is not None and candidato_id != entrada.candidato_id:
                    raise ValidationError("La entrada ya fue resuelta hacia otro destino.")
                return entrada
            entrada.full_clean()
            if entrada.identidad_estado != "confirmado" or not entrada.nombre.strip():
                raise ValidationError("Confirme explícitamente la identidad antes de resolver.")
            if not entrada.clasificacion_confirmada:
                raise ValidationError("Confirme la clasificación del archivo antes de resolver.")
            if Path(entrada.nombre_archivo_original).suffix.lower() not in {".pdf", ".doc", ".docx"}:
                raise ValidationError("Formato conservado solo para revisión protegida; no admite resolución documental.")
            with entrada.archivo.open("rb") as original:
                if huella(original) != entrada.sha256:
                    raise ValidationError("El archivo no coincide con su SHA-256 original.")
            valores = {"nombre": entrada.nombre.strip()}
            if entrada.profesion_estado == "confirmado":
                valores["profesion"] = entrada.profesion
            if entrada.ubicacion_estado == "confirmado":
                valores.update(region=entrada.region, ciudad=entrada.ciudad)
            for f in ("email", "telefono"):
                if getattr(entrada, f + "_estado") == "disponible":
                    valores[f] = getattr(entrada, f)
            hash_docs = DocumentoCandidato.objects.filter(candidato__organizacion=org, sha256=entrada.sha256)
            if hash_docs.filter(tipo=DocumentoCandidato.Tipo.EVALUACION).exists():
                raise ValidationError("El archivo corresponde a una evaluación restringida; use su flujo específico.")
            if candidato_id:
                autorizar(usuario, org, "talento.change_candidato")
                candidato = Candidato.objects.select_for_update().get(pk=candidato_id)
                if candidato.organizacion_id != org.pk or candidato.consolidado_en_id:
                    raise ValidationError("Destino de otra organización o consolidado; seleccione su ficha canónica.")
                if any(getattr(candidato, f) and getattr(candidato, f).strip().casefold() != v.strip().casefold() for f, v in valores.items() if v):
                    raise ValidationError("Los datos confirmados difieren de la ficha destino. Revise el conflicto; no se sobrescribirá.")
            else:
                autorizar(usuario, org, "talento.add_candidato")
                q = Q(nombre__iexact=valores["nombre"])
                for f in ("email", "telefono"):
                    if valores.get(f):
                        q |= Q(**{f + "__iexact": valores[f]})
                if Candidato.objects.filter(q, organizacion=org).exists() or hash_docs.exists():
                    raise ValidationError("Posible duplicado. Revise y seleccione una ficha existente; no se vincula automáticamente por nombre, contacto o hash.")
                candidato = Candidato(organizacion=org, **valores)
                candidato.full_clean()
                candidato.save()
            if hash_docs.exclude(candidato=candidato).exists():
                raise ValidationError("El archivo está asociado a otra ficha; requiere revisión de identidad.")
            cp = CandidatoProcedencia.objects.filter(organizacion=org, origen_importacion=entrada.origen_importacion, identificador_origen=entrada.identificador_origen).first()
            if cp and cp.candidato_id != candidato.pk:
                raise ValidationError("La procedencia ya pertenece a otro candidato.")
            # También detectar las procedencias originales sin fila auxiliar.
            if Candidato.objects.filter(organizacion=org, origen_importacion=entrada.origen_importacion, identificador_origen=entrada.identificador_origen).exclude(pk=candidato.pk).exists():
                raise ValidationError("La procedencia original pertenece a otra ficha.")
            dp = DocumentoProcedencia.objects.filter(procedencia=cp, identificador_origen=entrada.clave_documental).first() if cp else None
            if dp and (dp.documento.sha256 != entrada.sha256 or dp.documento.tipo != entrada.tipo_documento or dp.documento.candidato_id != candidato.pk):
                raise ValidationError("La clave documental existente tiene otro contenido o clasificación.")
            documento = dp.documento if dp else hash_docs.filter(candidato=candidato, tipo=entrada.tipo_documento).order_by("pk").first()
            if documento:
                autorizar(usuario, org, "talento.change_documentocandidato")
                with documento.archivo.open("rb") as original:
                    if huella(original) != entrada.sha256:
                        raise ValidationError("El archivo del destino está alterado o incompleto.")
            else:
                documento = DocumentoCandidato(candidato=candidato, tipo=entrada.tipo_documento,
                    nombre=entrada.nombre_archivo_original, vigente=True,
                    es_cv_principal=entrada.tipo_documento == "curriculum" and not candidato.documentos.filter(es_cv_principal=True, vigente=True).exists(),
                    origen_importacion=entrada.origen_importacion,
                    identificador_origen=f"{entrada.identificador_origen}:{entrada.clave_documental}",
                    agregado_por=usuario)
                with entrada.archivo.open("rb") as original:
                    documento.archivo.save(entrada.nombre_archivo_original, File(original), save=False)
                saved_name, storage = documento.archivo.name, documento.archivo.storage
                documento.full_clean()
                documento.save()
            if not cp:
                cp = CandidatoProcedencia(organizacion=org, candidato=candidato, origen_importacion=entrada.origen_importacion, identificador_origen=entrada.identificador_origen, sha256=entrada.sha256)
                cp.full_clean()
                cp.save()
            if not dp:
                dp = DocumentoProcedencia(procedencia=cp, documento=documento, identificador_origen=entrada.clave_documental)
                dp.full_clean()
                dp.save()
            entrada.candidato, entrada.documento = candidato, documento
            entrada.seguimiento = "resuelto"
            entrada.actualizado_por = usuario
            entrada.full_clean()
            entrada.save()
            auditar(entrada, usuario, fuente, "resolver")
            return entrada
    except Exception:
        if saved_name:
            storage.delete(saved_name)
        raise
