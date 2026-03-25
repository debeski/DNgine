from __future__ import annotations

import io
import json
import os
import shutil
import tempfile
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from cryptography.fernet import Fernet
except Exception:  # pragma: no cover - optional until dependency is installed
    Fernet = None

from micro_toolkit import __version__


SCHEDULE_DAYS = {
    "daily": 1,
    "weekly": 7,
    "monthly": 30,
}

BACKUP_EXTENSION = ".mtkbak"


def encryption_available() -> bool:
    return Fernet is not None


def create_encrypted_snapshot(
    *,
    runtime_root: Path,
    app_root: Path,
    data_root: Path,
    output_root: Path,
    backup_path: Path,
    key_path: Path,
    reason: str,
    schedule: str,
) -> Path:
    if Fernet is None:
        raise RuntimeError("The 'cryptography' package is required for encrypted backups.")

    runtime_root = Path(runtime_root)
    app_root = Path(app_root)
    data_root = Path(data_root)
    output_root = Path(output_root)
    backup_path = Path(backup_path)
    key = _ensure_key(key_path)
    created_at = datetime.now(timezone.utc).isoformat()

    manifest = {
        "version": 1,
        "app_version": __version__,
        "created_at": created_at,
        "reason": str(reason or "manual"),
        "schedule": str(schedule or "manual"),
    }

    archive_bytes = io.BytesIO()
    with zipfile.ZipFile(archive_bytes, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, indent=2))
        _write_tree_to_archive(archive, app_root, "snapshot/app", exclude_roots={data_root / "backups", data_root / "runtime" / "qt_material"})
        _write_tree_to_archive(archive, data_root, "snapshot/data", exclude_roots={data_root / "backups"})
        _write_tree_to_archive(archive, output_root, "snapshot/output")
        for root_file in ("LICENSE", "README.md", "requirements.txt", "micro-toolkit.spec", "build_linux.sh", "build_windows.sh", "build_windows.bat", "build_macos.sh"):
            candidate = runtime_root / root_file
            if candidate.exists() and candidate.is_file():
                archive.write(candidate, f"snapshot/root/{candidate.name}")

    encrypted = Fernet(key).encrypt(archive_bytes.getvalue())
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    backup_path.write_bytes(encrypted)
    return backup_path


def restore_encrypted_snapshot(
    *,
    backup_path: Path,
    key_path: Path,
    runtime_root: Path,
    app_root: Path,
    data_root: Path,
    output_root: Path,
) -> dict[str, object]:
    if Fernet is None:
        raise RuntimeError("The 'cryptography' package is required for encrypted backup restore.")

    backup_path = Path(backup_path)
    key_path = Path(key_path)
    if not backup_path.exists():
        raise FileNotFoundError(f"Backup archive not found: {backup_path}")
    key = _ensure_key(key_path)
    decrypted = Fernet(key).decrypt(backup_path.read_bytes())

    restored: list[str] = []
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        archive_root = temp_root / "payload.zip"
        archive_root.write_bytes(decrypted)
        with zipfile.ZipFile(archive_root, "r") as archive:
            archive.extractall(temp_root / "snapshot_unpack")
        unpacked = temp_root / "snapshot_unpack"
        manifest_path = unpacked / "manifest.json"
        if manifest_path.exists():
            json.loads(manifest_path.read_text(encoding="utf-8"))

        _restore_tree(unpacked / "snapshot" / "app", app_root)
        restored.append(str(app_root))
        _restore_tree(unpacked / "snapshot" / "data", data_root, skip_names={"backups"})
        restored.append(str(data_root))
        _restore_tree(unpacked / "snapshot" / "output", output_root)
        restored.append(str(output_root))
        root_snapshot = unpacked / "snapshot" / "root"
        if root_snapshot.exists():
            _restore_tree(root_snapshot, runtime_root)
            restored.append(str(runtime_root))
    return {
        "backup_path": str(backup_path),
        "restored_paths": restored,
    }


class BackupManager:
    def __init__(self, config, runtime_root: Path, app_root: Path, data_root: Path, output_root: Path, logger):
        self.config = config
        self.runtime_root = Path(runtime_root)
        self.app_root = Path(app_root)
        self.data_root = Path(data_root)
        self.output_root = Path(output_root)
        self.logger = logger
        self.backups_root = self.data_root / "backups"
        self.backups_root.mkdir(parents=True, exist_ok=True)
        self.key_path = self.data_root / "backup_secret.key"

    def schedule(self) -> str:
        value = str(self.config.get("backup_schedule") or "monthly").strip().lower()
        return value if value in SCHEDULE_DAYS else "monthly"

    def set_schedule(self, schedule: str) -> str:
        normalized = str(schedule or "").strip().lower()
        if normalized not in SCHEDULE_DAYS:
            normalized = "monthly"
        self.config.set("backup_schedule", normalized)
        return normalized

    def last_backup_at(self) -> str:
        return str(self.config.get("backup_last_created_at") or "").strip()

    def backup_due(self) -> bool:
        schedule = self.schedule()
        last = self.last_backup_at()
        if not last:
            return True
        try:
            last_dt = datetime.fromisoformat(last)
        except Exception:
            return True
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) >= last_dt + timedelta(days=SCHEDULE_DAYS[schedule])

    def list_backups(self) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        for file_path in sorted(self.backups_root.glob(f"*{BACKUP_EXTENSION}"), reverse=True):
            rows.append(
                {
                    "name": file_path.name,
                    "path": str(file_path),
                    "modified_at": datetime.fromtimestamp(file_path.stat().st_mtime, tz=timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M"),
                    "size": str(file_path.stat().st_size),
                }
            )
        return rows

    def create_backup(self, *, reason: str = "manual") -> Path:
        if not encryption_available():
            raise RuntimeError("Encrypted backups require the 'cryptography' dependency.")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = self.backups_root / f"{timestamp}_{reason}{BACKUP_EXTENSION}"
        result = create_encrypted_snapshot(
            runtime_root=self.runtime_root,
            app_root=self.app_root,
            data_root=self.data_root,
            output_root=self.output_root,
            backup_path=backup_path,
            key_path=self.key_path,
            reason=reason,
            schedule=self.schedule(),
        )
        self.config.set("backup_last_created_at", datetime.now(timezone.utc).isoformat())
        self.logger.log(f"Encrypted backup created: {result}", "INFO")
        return result

    def maybe_create_scheduled_backup(self) -> Path | None:
        if not self.backup_due():
            return None
        return self.create_backup(reason=self.schedule())

    def restore_backup(self, backup_path: Path, *, elevated_requester=None) -> dict[str, object]:
        backup_path = Path(backup_path)
        targets = [self.app_root, self.data_root, self.output_root]
        needs_elevation = any(not os.access(path if path.exists() else path.parent, os.W_OK) for path in targets)
        if needs_elevation and elevated_requester is not None:
            return elevated_requester(
                "backup.restore_snapshot",
                {
                    "backup_path": str(backup_path),
                    "key_path": str(self.key_path),
                },
            )
        return restore_encrypted_snapshot(
            backup_path=backup_path,
            key_path=self.key_path,
            runtime_root=self.runtime_root,
            app_root=self.app_root,
            data_root=self.data_root,
            output_root=self.output_root,
        )


def _ensure_key(key_path: Path) -> bytes:
    key_path = Path(key_path)
    key_path.parent.mkdir(parents=True, exist_ok=True)
    if key_path.exists():
        key = key_path.read_bytes().strip()
        if key:
            return key
    if Fernet is None:
        raise RuntimeError("The 'cryptography' package is required for encrypted backups.")
    key = Fernet.generate_key()
    key_path.write_bytes(key)
    return key


def _write_tree_to_archive(archive: zipfile.ZipFile, source_root: Path, archive_prefix: str, exclude_roots: set[Path] | None = None) -> None:
    source_root = Path(source_root)
    exclude_roots = {path.resolve() for path in (exclude_roots or set())}
    if not source_root.exists():
        return
    for path in sorted(source_root.rglob("*")):
        if not path.is_file():
            continue
        if "__pycache__" in path.parts:
            continue
        resolved = path.resolve()
        if any(excluded == resolved or excluded in resolved.parents for excluded in exclude_roots):
            continue
        archive.write(path, f"{archive_prefix}/{path.relative_to(source_root).as_posix()}")


def _restore_tree(source_root: Path, target_root: Path, *, skip_names: set[str] | None = None) -> None:
    source_root = Path(source_root)
    target_root = Path(target_root)
    skip_names = skip_names or set()
    if not source_root.exists():
        return
    for path in sorted(source_root.rglob("*")):
        if any(part in skip_names for part in path.parts):
            continue
        relative = path.relative_to(source_root)
        destination = target_root / relative
        if path.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
