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
from talento.models import Candidato, CandidatoProcedencia, DocumentoCandidato


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

    def _inspect(self, root, organization, records):
        seen_hashes = set()
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
            required = ("identificador_origen", "origen_importacion", "nombre", "archivo")
            missing = [field for field in required if not str(row.get(field, "")).strip()]
            if missing:
                item["status"] = "incompleto"
                item["error"] = "datos_requeridos_ausentes"
                report.append(item)
                continue
            path, error = _safe_path(root, row["archivo"])
            if error or path is None:
                item["status"], item["error"] = "invalido", error
                report.append(item)
                continue
            if path.suffix.lower() not in ALLOWED_SUFFIXES:
                item["status"], item["error"] = "formato_no_admitido", "extension"
                report.append(item)
                continue
            try:
                size = path.stat().st_size
            except (FileNotFoundError, OSError):
                item["status"], item["error"] = "faltante", "archivo_ausente"
                report.append(item)
                continue
            if not path.is_file():
                item["status"], item["error"] = "faltante", "archivo_no_regular"
                report.append(item)
                continue
            if size > MAX_BYTES:
                item["status"], item["error"] = "tamano_excesivo", "limite_10_mb"
                report.append(item)
                continue
            digest = _digest(path)
            item["sha256"] = digest
            procedencia = CandidatoProcedencia.objects.filter(
                organizacion=organization,
                origen_importacion=row["origen_importacion"],
                identificador_origen=row["identificador_origen"],
            ).first()
            existing = Candidato.objects.filter(
                organizacion=organization,
                origen_importacion=row["origen_importacion"],
                identificador_origen=row["identificador_origen"],
            ).first()
            if procedencia or existing:
                previous_hash = procedencia.sha256 if procedencia else ""
                if not previous_hash and existing:
                    previous_hash = DocumentoCandidato.objects.filter(
                        candidato=existing, sha256__gt=""
                    ).values_list("sha256", flat=True).first() or ""
                if previous_hash == digest:
                    item["status"], item["error"] = "duplicado", "origen_ya_importado"
                else:
                    item["status"], item["error"] = "pendiente_revision", "origen_archivo_diferente"
            elif digest in seen_hashes or DocumentoCandidato.objects.filter(
                candidato__organizacion=organization, sha256=digest
            ).exists():
                item["status"], item["error"] = "duplicado", "sha256_en_organizacion"
            elif Candidato.objects.filter(
                organizacion=organization,
                origen_importacion=row["origen_importacion"],
                identificador_origen=row["identificador_origen"],
            ).exists():
                item["status"], item["error"] = "ya_importado", "identificador_origen"
            else:
                seen_hashes.add(digest)
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

    def _import_one(self, root, organization, row, item):
        path, error = _safe_path(root, row["archivo"])
        if error or path is None:
            raise ValueError(error or "ruta_invalida")
        saved_name = None
        try:
            with transaction.atomic():
                candidate = Candidato.objects.create(
                    **self._candidate_fields(row, organization)
                )
                document = DocumentoCandidato(
                    candidato=candidate,
                    tipo=DocumentoCandidato.Tipo.CURRICULUM,
                    nombre=row.get("nombre_documento", path.name),
                    es_cv_principal=True,
                    vigente=True,
                    sha256=item["sha256"],
                )
                with path.open("rb") as source:
                    document.archivo.save(path.name, File(source), save=False)
                saved_name = document.archivo.name
                document.save()
                CandidatoProcedencia.objects.create(
                    candidato=candidate,
                    organizacion=organization,
                    origen_importacion=row["origen_importacion"],
                    identificador_origen=row["identificador_origen"],
                    sha256=item["sha256"],
                )
        except Exception:
            if saved_name:
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
        for item in report:
            counts[item["status"]] = counts.get(item["status"], 0) + 1
        mode = "IMPORTACION" if options["importar"] else "PREVISUALIZACION"
        self.stdout.write(mode)
        self.stdout.write("RESUMEN " + " ".join(f"{key}={counts[key]}" for key in sorted(counts)))
        if self.uncheckable_duplicates:
            self.stdout.write(
                "ADVERTENCIA duplicacion_no_comprobable="
                f"{self.uncheckable_duplicates} documentos_sin_sha256"
            )
        for item in report:
            if item["status"] != "valido":
                self.stdout.write(f"FILA {item['row']} ESTADO {item['status']} ERROR {item.get('error', 'ninguno')}")
        if not options["importar"]:
            self.stdout.write("SIN_CAMBIOS opcion_explicita_requerida=--importar")
            return
        imported = 0
        errors = 0
        for row, item in zip(data["registros"], report):
            if item["status"] != "valido":
                continue
            try:
                self._import_one(root, organization, row, item)
                imported += 1
            except Exception:
                errors += 1
                self.stdout.write(f"FILA {item['row']} ESTADO error_importacion")
        self.stdout.write(f"IMPORTADOS {imported} ERRORES {errors}")
