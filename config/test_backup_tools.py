import tempfile
from pathlib import Path
from unittest import TestCase

from scripts.radar_backup import validate_backup


class BackupToolValidationTests(TestCase):
    def make_backup(self, root, relative="documents/cv.txt"):
        (root / "documents").mkdir()
        (root / "database.dump").write_bytes(b"synthetic dump")
        document = root / relative
        document.parent.mkdir(parents=True, exist_ok=True)
        document.write_bytes(b"synthetic document")
        import hashlib

        def digest(path):
            return hashlib.sha256(path.read_bytes()).hexdigest()

        (root / "manifest.json").write_text(
            '{"backup_version":"1","database_dump":{"path":"database.dump","sha256":"%s","size":14},"documents":[{"path":"cv.txt","sha256":"%s","size":18}]}\n'
            % (digest(root / "database.dump"), digest(document)),
            encoding="utf-8",
        )

    def test_valida_sumas_y_rutas_relativas(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_backup(root)
            manifest, dump = validate_backup(root)
            self.assertEqual(manifest["backup_version"], "1")
            self.assertEqual(dump.name, "database.dump")

    def test_rechaza_ruta_fuera_del_directorio_y_symlink(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_backup(root, "../outside.txt")
            with self.assertRaises(RuntimeError):
                validate_backup(root)
