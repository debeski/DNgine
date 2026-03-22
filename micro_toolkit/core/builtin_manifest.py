from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BuiltinManifestEntry:
    relative_path: str
    sha256: str
    plugins: tuple[tuple[str, str], ...]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_builtin_manifest(path: Path) -> dict[str, BuiltinManifestEntry]:
    manifest_path = Path(path)
    if not manifest_path.exists():
        return {}
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    files = payload.get("files", {})
    if not isinstance(files, dict):
        return {}

    entries: dict[str, BuiltinManifestEntry] = {}
    for relative_path, file_payload in files.items():
        if not isinstance(file_payload, dict):
            continue
        plugins = file_payload.get("plugins", [])
        plugin_pairs: list[tuple[str, str]] = []
        if isinstance(plugins, list):
            for item in plugins:
                if not isinstance(item, dict):
                    continue
                plugin_id = str(item.get("plugin_id", "")).strip()
                class_name = str(item.get("class_name", "")).strip()
                if plugin_id and class_name:
                    plugin_pairs.append((plugin_id, class_name))
        sha256 = str(file_payload.get("sha256", "")).strip()
        rel = str(relative_path).replace("\\", "/").strip()
        if rel and sha256 and plugin_pairs:
            entries[rel] = BuiltinManifestEntry(
                relative_path=rel,
                sha256=sha256,
                plugins=tuple(plugin_pairs),
            )
    return entries


def write_builtin_manifest(path: Path, files: dict[str, BuiltinManifestEntry]) -> Path:
    manifest_path = Path(path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "trusted_origins": ["builtin", "signed", "custom"],
        "files": {
            relative_path: {
                "sha256": entry.sha256,
                "plugins": [
                    {
                        "plugin_id": plugin_id,
                        "class_name": class_name,
                    }
                    for plugin_id, class_name in entry.plugins
                ],
            }
            for relative_path, entry in sorted(files.items())
        },
    }
    manifest_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest_path
