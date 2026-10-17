#!/usr/bin/env python3
"""Create and restore RADAR PostgreSQL/document backups.

This tool never deletes backup data. It expects a write pause for a coherent
database/filesystem snapshot and uses RADAR_DB_* environment variables.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_NAME = "manifest.json"
DUMP_NAME = "database.dump"
VERSION = "1"


def fail(message):
    raise RuntimeError(message)


def outside_repo(path):
    resolved = path.resolve()
    if resolved == REPO_ROOT or REPO_ROOT in resolved.parents:
        fail("El destino debe estar fuera del repositorio")
    return resolved


def new_directory(path):
    path = outside_repo(Path(path))
    if path.exists():
        if not path.is_dir() or any(path.iterdir()):
            fail("El destino debe ser un directorio nuevo y vacío")
    else:
        path.mkdir(parents=True)
    path.chmod(0o700)
    return path


def db_environment():
    required = ("RADAR_DB_NAME", "RADAR_DB_USER", "RADAR_DB_PASSWORD", "RADAR_DB_HOST")
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        fail("Faltan variables PostgreSQL obligatorias")
    return {
        "name": os.environ["RADAR_DB_NAME"],
        "user": os.environ["RADAR_DB_USER"],
        "password": os.environ["RADAR_DB_PASSWORD"],
        "host": os.environ["RADAR_DB_HOST"],
        "port": os.environ.get("RADAR_DB_PORT", "5432"),
    }


def command_env(db):
    env = os.environ.copy()
    env["PGPASSWORD"] = db["password"]
    return env


def pg_command(program, arguments, db):
    container = os.environ.get("RADAR_PG_CLIENT_CONTAINER", "").strip()
    if container:
        command = ["docker", "exec", "-i", "-e", f"PGPASSWORD={db['password']}" ]
        client_user = os.environ.get("RADAR_PG_CLIENT_USER", "").strip()
        if client_user:
            command.extend(["--user", client_user])
        command.extend([container, program, *arguments])
        return command
    return [program, *arguments]


def run(command, env, input_text=None):
    try:
        result = subprocess.run(
            command,
            env=env,
            input=input_text,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise RuntimeError("Falló un comando de PostgreSQL") from error
    return result.stdout


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative_files(media_root):
    if not media_root.is_dir():
        fail("MEDIA_ROOT no existe o no es un directorio")
    files = []
    for path in sorted(media_root.rglob("*")):
        relative = path.relative_to(media_root)
        if path.is_symlink():
            fail("MEDIA_ROOT contiene un enlace simbólico")
        if path.is_dir():
            continue
        if not path.is_file() or relative.is_absolute() or ".." in relative.parts:
            fail("MEDIA_ROOT contiene una ruta no regular")
        files.append((relative.as_posix(), path))
    return files


def backup(args):
    db = db_environment()
    destination = new_directory(args.destination)
    media_root = Path(args.media_root).resolve()
    files = relative_files(media_root)
    dump = destination / DUMP_NAME
    dump_arguments = [
        "--format=custom", "--no-owner", "--no-acl",
        "--dbname", db["name"],
        "--username", db["user"], "--host", db["host"], "--port", db["port"],
    ]
    if os.environ.get("RADAR_PG_CLIENT_CONTAINER", "").strip():
        with dump.open("wb") as output:
            try:
                subprocess.run(pg_command("pg_dump", dump_arguments, db), env=command_env(db), stdout=output, stderr=subprocess.PIPE, check=True)
            except (OSError, subprocess.CalledProcessError) as error:
                raise RuntimeError("Falló un comando de PostgreSQL") from error
    else:
        run(["pg_dump", "--file", str(dump), *dump_arguments], command_env(db))
    dump.chmod(0o600)
    entries = []
    for relative, source in files:
        target = destination / "documents" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.parent.chmod(0o700)
        target.write_bytes(source.read_bytes())
        target.chmod(0o600)
        entries.append({"path": relative, "sha256": sha256(target), "size": target.stat().st_size})
    manifest = {
        "backup_version": VERSION,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "schema_version": args.schema_version,
        "database_dump": {"path": DUMP_NAME, "sha256": sha256(dump), "size": dump.stat().st_size},
        "documents": entries,
    }
    manifest_path = destination / MANIFEST_NAME
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest_path.chmod(0o600)
    print("Respaldo creado")


def safe_target(root, relative):
    path = (root / relative).resolve()
    if root not in path.parents or path == root:
        fail("El manifiesto contiene una ruta insegura")
    return path


def validate_backup(source):
    manifest_path = source / MANIFEST_NAME
    if not manifest_path.is_file() or manifest_path.is_symlink():
        fail("Manifiesto ausente o inseguro")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise RuntimeError("Manifiesto inválido") from error
    if manifest.get("backup_version") != VERSION:
        fail("Versión de respaldo no compatible")
    dump_info = manifest.get("database_dump", {})
    dump = safe_target(source, dump_info.get("path", ""))
    if not dump.is_file() or dump.is_symlink() or sha256(dump) != dump_info.get("sha256"):
        fail("Dump ausente, alterado o incompleto")
    for entry in manifest.get("documents", []):
        path = safe_target(source / "documents", entry.get("path", ""))
        if not path.is_file() or path.is_symlink() or sha256(path) != entry.get("sha256") or path.stat().st_size != entry.get("size"):
            fail("Documento ausente, alterado o incompleto")
    return manifest, dump


def restore(args):
    db = db_environment()
    source = Path(args.backup).resolve()
    if not source.is_dir():
        fail("El respaldo no existe")
    manifest, dump = validate_backup(source)
    media_root = new_directory(args.media_root)
    target_db = args.database
    check = run(pg_command("psql", ["--no-password", "--dbname", db["name"], "--username", db["user"], "--host", db["host"], "--port", db["port"], "--tuples-only", "--no-align", "--command", "select 1 from pg_database where datname = '" + target_db.replace("'", "''") + "'"], db), command_env(db))
    if check.strip() == "1":
        fail("La base destino ya existe")
    run(pg_command("createdb", ["--username", db["user"], "--host", db["host"], "--port", db["port"], target_db], db), command_env(db))
    restore_arguments = ["--exit-on-error", "--no-owner", "--no-acl", "--dbname", target_db, "--username", db["user"], "--host", db["host"], "--port", db["port"]]
    if os.environ.get("RADAR_PG_CLIENT_CONTAINER", "").strip():
        try:
            with dump.open("rb") as dump_handle:
                subprocess.run(pg_command("pg_restore", restore_arguments, db), env=command_env(db), stdin=dump_handle, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        except (OSError, subprocess.CalledProcessError) as error:
            raise RuntimeError("Falló un comando de PostgreSQL") from error
    else:
        run(["pg_restore", *restore_arguments, str(dump)], command_env(db))
    for entry in manifest["documents"]:
        target = safe_target(media_root, entry["path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.parent.chmod(0o700)
        target.write_bytes(safe_target(source / "documents", entry["path"]).read_bytes())
        target.chmod(0o600)
    print("Restauración completada")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    create = subparsers.add_parser("backup")
    create.add_argument("--destination", required=True)
    create.add_argument("--media-root", required=True)
    create.add_argument("--schema-version", required=True)
    create.set_defaults(function=backup)
    restore_parser = subparsers.add_parser("restore")
    restore_parser.add_argument("--backup", required=True)
    restore_parser.add_argument("--media-root", required=True)
    restore_parser.add_argument("--database", required=True)
    restore_parser.set_defaults(function=restore)
    try:
        args = parser.parse_args()
        args.function(args)
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
