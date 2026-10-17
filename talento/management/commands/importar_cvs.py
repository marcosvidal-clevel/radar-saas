"""Preview and import candidate CV batches from a local manifest."""

import hashlib
import json
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files import File
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction

from core.models import Membresia, Organizacion
from talento.models import (
    Candidato,
    CandidatoProcedencia,
    DocumentoCandidato,
    DocumentoProcedencia,
)


ALLOWED_SUFFIXES = {".pdf", ".doc", ".docx"}
MAX_BYTES = 10 * 1024 * 1024
TEXT_FIELDS = (
    "nombre", "email", "telefono", "linkedin", "profesion",
    "especialidad", "region", "ciudad", "experiencia", "competencias",
    "notas",
)


def _inside(root, path):
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return path != root


def _safe_path(root, relative):
    if isinstance(relative, Path):
        relative = str(relative)
    if not isinstance(relative, str) or not relative.strip():
        return None, "ruta_ausente"
    candidate = Path(relative)
    if candidate.is_absolute():
        return None, "ruta_fuera_de_carpeta"
    root = root.resolve()
    raw_path = root / candidate
    current = root
    for part in candidate.parts:
        if part in ("", "."):
            continue
        current /= part
        if current.is_symlink():
            return None, "enlace_simbolico"
    path = raw_path.resolve(strict=False)
    if not _inside(root, path):
        return None, "ruta_fuera_de_carpeta"
    return path, None


def _digest(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class Command(BaseCommand):
    help = "Previsualiza o importa CV desde una carpeta y un manifiesto JSON."

    def add_arguments(self, parser):
        parser.add_argument("carpeta", type=Path)
        parser.add_argument("manifiesto", type=Path)
        parser.add_argument(
            "--importar", action="store_true",
            help="Confirma la importación; por defecto solo previsualiza.",
        )

    def _load_manifest(self, root, manifest_path):
        path, error = _safe_path(root, manifest_path)
        if error or path is None or not path.is_file():
            raise CommandError("El manifiesto debe ser un archivo dentro de la carpeta.")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            raise CommandError("Manifiesto inválido.") from exc
        if not isinstance(data, dict) or not isinstance(data.get("registros"), list):
            raise CommandError("El manifiesto debe contener una lista registros.")
        return data

    def _organization_and_user(self, data):
        organization_value = data.get("organizacion")
        user_value = data.get("usuario_ejecutor")
        if organization_value is None or not isinstance(user_value, str) or not user_value.strip():
            raise CommandError("El manifiesto requiere organizacion y usuario_ejecutor.")
        organization_query = (
            {"pk": organization_value} if str(organization_value).isdigit()
            else {"slug": organization_value}
        )
        try:
            organization = Organizacion.objects.get(**organization_query)
            user = get_user_model().objects.get(username=user_value)
        except (Organizacion.DoesNotExist, get_user_model().DoesNotExist) as exc:
            raise CommandError("Organización o usuario no encontrado.") from exc
        return organization, user

    def _authorize(self, organization, user):
        if not organization.activa:
            raise CommandError("La organización no está activa.")
        membership = Membresia.objects.filter(
            organizacion=organization,
            usuario=user,
            activa=True,
            rol__in=(Membresia.Rol.ADMINISTRADOR, Membresia.Rol.SUPERVISOR),
        ).exists()
        if not membership:
            raise CommandError("El usuario no tiene rol de gestión en la organización.")
        if not user.has_perm("talento.add_candidato"):
            raise CommandError("El usuario no tiene permiso de crear candidatos.")
        if not user.has_perm("talento.add_documentocandidato"):
            raise CommandError("El usuario no tiene permiso de crear documentos.")

    def _canonical(self, candidate):
        seen = set()
        while candidate.consolidado_en_id:
            if candidate.pk in seen:
                raise CommandError("Cadena de consolidación inválida.")
            seen.add(candidate.pk)
            candidate = Candidato.objects.get(pk=candidate.consolidado_en_id)
        return candidate

    def _existing_candidate(self, organization, row):
        candidate = Candidato.objects.filter(
            organizacion=organization,
            origen_importacion=row["origen_importacion"],
            identificador_origen=row["identificador_origen"],
        ).first()
        if candidate:
            return self._canonical(candidate)
        procedencia = CandidatoProcedencia.objects.filter(
            organizacion=organization,
            origen_importacion=row["origen_importacion"],
            identificador_origen=row["identificador_origen"],
        ).select_related("candidato").first()
        return self._canonical(procedencia.candidato) if procedencia else None

    def _documents(self, row, position):
        if "documentos" not in row:
            return [{
                "identificador_origen": str(row.get("identificador_origen", position)),
                "archivo": row.get("archivo"),
                "nombre": row.get("nombre_documento", ""),
                "tipo": DocumentoCandidato.Tipo.CURRICULUM,
            }]
        documents = row.get("documentos")
        if not isinstance(documents, list) or not documents:
            return None
        return documents

    def _inspect(self, root, organization, records):
        seen_hashes = {}
        self.uncheckable_duplicates = DocumentoCandidato.objects.filter(
            candidato__organizacion=organization,
            tipo=DocumentoCandidato.Tipo.CURRICULUM,
            sha256="",
        ).count()
        report = []
        for position, row in enumerate(records, 1):
            row_id = row.get("id_fila", position) if isinstance(row, dict) else position
            item = {"row": str(row_id), "status": "valido"}
            if not isinstance(row, dict):
                item["status"] = "incompleto"
                item["error"] = "registro_no_objeto"
                report.append(item)
                continue
            required = ("identificador_origen", "origen_importacion", "nombre")
            missing = [field for field in required if not str(row.get(field, "")).strip()]
            if missing:
                item["status"] = "incompleto"
                item["error"] = "datos_requeridos_ausentes"
                report.append(item)
                continue
            documents = self._documents(row, position)
            if documents is None:
                item["status"], item["error"] = "incompleto", "documentos_invalidos"
                report.append(item)
                continue
            plans = []
            for document_row in documents:
                if not isinstance(document_row, dict) or not str(document_row.get("archivo", "")).strip() or not str(document_row.get("identificador_origen", "")).strip():
                    plans.append({"status": "incompleto", "error": "documento_requerido_ausente"})
                    continue
                path, error = _safe_path(root, document_row["archivo"])
                if error or path is None:
                    plans.append({"status": "invalido", "error": error})
                    continue
                if path.suffix.lower() not in ALLOWED_SUFFIXES:
                    plans.append({"status": "formato_no_admitido", "error": "extension"})
                    continue
                try:
                    size = path.stat().st_size
                except (FileNotFoundError, OSError):
                    plans.append({"status": "faltante", "error": "archivo_ausente"})
                    continue
                if not path.is_file():
                    plans.append({"status": "faltante", "error": "archivo_no_regular"})
                    continue
                if size > MAX_BYTES:
                    plans.append({"status": "tamano_excesivo", "error": "limite_10_mb"})
                    continue
                tipo = document_row.get("tipo") or DocumentoCandidato.Tipo.OTRO
                if tipo == DocumentoCandidato.Tipo.EVALUACION:
                    plans.append({"status": "rechazado", "error": "evaluacion_restringida"})
                    continue
                if tipo not in DocumentoCandidato.Tipo.values:
                    plans.append({"status": "invalido", "error": "tipo_no_admitido"})
                    continue
                digest = _digest(path)
                plans.append({"status": "valido", "path": path, "sha256": digest, "row": document_row,
                              "clasificacion_pendiente": "tipo" not in document_row or not document_row.get("tipo")})
            if any(plan["status"] != "valido" for plan in plans):
                item["status"] = "incompleto" if any(plan["status"] == "incompleto" for plan in plans) else "invalido"
                item["error"] = ",".join(sorted({plan["error"] for plan in plans if plan["status"] != "valido"}))
                report.append(item)
                continue
            candidate = self._existing_candidate(organization, row)
            row_provenance = CandidatoProcedencia.objects.filter(
                organizacion=organization,
                origen_importacion=row["origen_importacion"],
                identificador_origen=row["identificador_origen"],
            ).first() if candidate else None
            statuses = []
            for plan in plans:
                drow, digest = plan["row"], plan["sha256"]
                current = DocumentoCandidato.objects.filter(
                    candidato=candidate,
                    procedencias__procedencia=row_provenance,
                    procedencias__identificador_origen=drow["identificador_origen"],
                ).first() if candidate and row_provenance else None
                if not current and candidate:
                    current = DocumentoCandidato.objects.filter(
                        candidato=candidate,
                        origen_importacion=row["origen_importacion"],
                        identificador_origen=drow["identificador_origen"],
                    ).first()
                legacy_origin = CandidatoProcedencia.objects.filter(
                    candidato=candidate,
                    organizacion=organization,
                    origen_importacion=row["origen_importacion"],
                    identificador_origen=row["identificador_origen"],
                ).first() if candidate and drow["identificador_origen"] == row["identificador_origen"] else None
                if current and current.sha256 == digest:
                    statuses.append("duplicado")
                elif current:
                    statuses.append("pendiente_revision")
                else:
                    same_candidate_hash = False
                    has_any_hash = False
                    for owner_id in DocumentoCandidato.objects.filter(
                        candidato__organizacion=organization, sha256=digest
                    ).values_list("candidato_id", flat=True):
                        has_any_hash = True
                        owner = Candidato.objects.only("pk", "consolidado_en_id").get(pk=owner_id)
                        if candidate and self._canonical(owner).pk == candidate.pk:
                            same_candidate_hash = True
                            plan["existing_document"] = DocumentoCandidato.objects.filter(
                                candidato_id=owner_id, sha256=digest
                            ).first()
                            break
                    if same_candidate_hash:
                        statuses.append("duplicado")
                    elif legacy_origin and legacy_origin.sha256 and legacy_origin.sha256 != digest:
                        statuses.append("pendiente_revision")
                    elif has_any_hash or digest in seen_hashes:
                        statuses.append("conflicto_hash")
                    else:
                        statuses.append("documento_nuevo" if not plan["clasificacion_pendiente"] else "pendiente_clasificacion")
                        seen_hashes[digest] = candidate.pk if candidate else None
            item["candidate"] = "existente" if candidate else "nuevo"
            item["document_plans"] = plans
            item["status"] = "valido" if any(s in {"documento_nuevo", "pendiente_clasificacion"} for s in statuses) and not any(s in {"pendiente_revision", "conflicto_hash"} for s in statuses) else ("pendiente_revision" if "pendiente_revision" in statuses else ("conflicto_hash" if "conflicto_hash" in statuses else "duplicado"))
            item["document_statuses"] = statuses
            report.append(item)
        return report

    def _candidate_fields(self, row, organization):
        values = {field: row.get(field, "") for field in TEXT_FIELDS}
        values.update({
            "organizacion": organization,
            "fuente": Candidato.Fuente.OTRO,
            "origen_importacion": row["origen_importacion"],
            "identificador_origen": row["identificador_origen"],
        })
        return values

    def _import_one(self, organization, row, item):
        saved_names = []
        try:
            with transaction.atomic():
                candidate = self._existing_candidate(organization, row)
                if candidate:
                    pass
                else:
                    candidate = Candidato.objects.create(**self._candidate_fields(row, organization))
                row_provenance, _ = CandidatoProcedencia.objects.get_or_create(
                    organizacion=organization,
                    origen_importacion=row["origen_importacion"],
                    identificador_origen=row["identificador_origen"],
                    defaults={"candidato": candidate},
                )
                for plan, status in zip(item["document_plans"], item["document_statuses"]):
                    if status == "duplicado" and plan.get("existing_document"):
                        DocumentoProcedencia.objects.get_or_create(
                            documento=plan["existing_document"],
                            procedencia=row_provenance,
                            identificador_origen=plan["row"]["identificador_origen"],
                        )
                        continue
                    if status not in {"documento_nuevo", "pendiente_clasificacion"}:
                        continue
                    drow = plan["row"]
                    tipo = drow.get("tipo") or DocumentoCandidato.Tipo.OTRO
                    document = DocumentoCandidato(
                        candidato=candidate,
                        tipo=tipo,
                        nombre=drow.get("nombre") or plan["path"].name,
                        es_cv_principal=(tipo == DocumentoCandidato.Tipo.CURRICULUM and not candidate.documentos.filter(es_cv_principal=True, vigente=True).exists()),
                        vigente=True,
                        sha256=plan["sha256"],
                        origen_importacion=row["origen_importacion"],
                        identificador_origen=drow["identificador_origen"],
                        pendiente_clasificacion=plan["clasificacion_pendiente"],
                    )
                    with plan["path"].open("rb") as source:
                        document.archivo.save(plan["path"].name, File(source), save=False)
                    saved_names.append(document.archivo.name)
                    document.save()
                    DocumentoProcedencia.objects.get_or_create(
                        documento=document,
                        procedencia=row_provenance,
                        identificador_origen=drow["identificador_origen"],
                    )
        except Exception:
            for saved_name in saved_names:
                default_storage.delete(saved_name)
            raise

    def handle(self, *args, **options):
        root = options["carpeta"].resolve()
        if not root.is_dir() or root.is_symlink():
            raise CommandError("La carpeta no es válida o es un enlace simbólico.")
        data = self._load_manifest(root, options["manifiesto"])
        organization, user = self._organization_and_user(data)
        self._authorize(organization, user)
        report = self._inspect(root, organization, data["registros"])
        counts = {}
        document_counts = {}
        for item in report:
            counts[item["status"]] = counts.get(item["status"], 0) + 1
            for status in item.get("document_statuses", []):
                document_counts[status] = document_counts.get(status, 0) + 1
        mode = "IMPORTACION" if options["importar"] else "PREVISUALIZACION"
        self.stdout.write(mode)
        self.stdout.write("RESUMEN " + " ".join(f"{key}={counts[key]}" for key in sorted(counts)))
        if document_counts:
            self.stdout.write("DOCUMENTOS " + " ".join(f"{key}={document_counts[key]}" for key in sorted(document_counts)))
        if self.uncheckable_duplicates:
            self.stdout.write(
                "ADVERTENCIA duplicacion_no_comprobable="
                f"{self.uncheckable_duplicates} documentos_sin_sha256"
            )
        for item in report:
            if item.get("document_statuses") or item["status"] != "valido":
                self.stdout.write(f"FILA {item['row']} CANDIDATO {item.get('candidate', 'n/a')} ESTADO {item['status']} DOCUMENTOS={','.join(item.get('document_statuses', []))} ERROR {item.get('error', 'ninguno')}")
        if not options["importar"]:
            self.stdout.write("SIN_CAMBIOS opcion_explicita_requerida=--importar")
            return
        imported = 0
        errors = 0
        for row, item in zip(data["registros"], report):
            if not any(status in {"documento_nuevo", "pendiente_clasificacion"} for status in item.get("document_statuses", [])):
                continue
            try:
                self._import_one(organization, row, item)
                imported += 1
            except Exception:
                errors += 1
                self.stdout.write(f"FILA {item['row']} ESTADO error_importacion")
        self.stdout.write(f"IMPORTADOS {imported} ERRORES {errors}")
