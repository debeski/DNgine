from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dngine.core.first_party_packages import PACKAGE_GROUPS, catalog_entry_from_source, discover_package_source_manifests
from dngine.core.plugin_signing import MANIFEST_FILENAME, SIGNATURE_FILENAME, sha256_file, load_private_signing_key, sign_manifest


def _group_labels(package_id: str) -> tuple[str, str]:
    for group in PACKAGE_GROUPS:
        if group.package_id == package_id:
            return group.label, group.label_ar
    return package_id, package_id


def build_first_party_packages(
    *,
    output_dir: Path,
    catalog_path: Path,
    private_key_path: Path,
) -> dict[str, object]:
    output_dir = Path(output_dir)
    catalog_path = Path(catalog_path)
    private_key = load_private_signing_key(private_key_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    catalog_entries: list[dict[str, object]] = []
    built_archives: list[Path] = []
    for source in discover_package_source_manifests(ROOT / "first_party_packages"):
        if not source.plugins:
            continue
        category_label, category_label_ar = _group_labels(source.package_id)
        package_root = ROOT / "first_party_packages" / source.package_id
        files_payload: list[dict[str, str]] = []
        plugins_payload: list[dict[str, object]] = []
        dependency_payload: list[dict[str, str]] = []

        for plugin in source.plugins:
            seen: set[str] = set()
            for relative_path in plugin.files:
                normalized = str(relative_path).replace("\\", "/").strip()
                if not normalized or normalized in seen:
                    continue
                seen.add(normalized)
                absolute_path = package_root / normalized
                if not absolute_path.exists():
                    raise FileNotFoundError(f"Missing package file '{normalized}' for '{source.package_id}'.")
                files_payload.append(
                    {
                        "path": normalized,
                        "sha256": sha256_file(absolute_path),
                    }
                )
            plugins_payload.append(
                {
                    "plugin_id": plugin.plugin_id,
                    "package_name": source.package_id,
                    "source_type": "signed",
                    "entry": plugin.entry,
                    "primary_relative_path": plugin.entry,
                    "dependency_manifest": plugin.dependency_manifest,
                }
            )
            if plugin.dependency_manifest:
                dependency_payload.append(
                    {
                        "plugin_id": plugin.plugin_id,
                        "manifest": plugin.dependency_manifest,
                    }
                )

        manifest = {
            "version": 1,
            "origin": "signed",
            "package_id": source.package_id,
            "display_name": source.display_name,
            "display_name_ar": source.display_name_ar,
            "category_label": category_label,
            "category_label_ar": category_label_ar,
            "package_version": source.package_version,
            "signer": source.signer,
            "plugins": plugins_payload,
            "group_plugin_ids": list(source.category_plugins),
            "dependencies": dependency_payload,
            "files": sorted(files_payload, key=lambda item: item["path"]),
        }
        signature_payload = sign_manifest(manifest, signer=source.signer, private_key=private_key)
        archive_path = output_dir / f"{source.package_id}-{source.package_version}.zip"
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(MANIFEST_FILENAME, json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
            archive.writestr(SIGNATURE_FILENAME, json.dumps(signature_payload, indent=2, ensure_ascii=False) + "\n")
            for file_entry in manifest["files"]:
                relative_path = str(file_entry["path"])
                archive.write(package_root / relative_path, relative_path)
        built_archives.append(archive_path)
        catalog_entries.append(
            catalog_entry_from_source(
                source,
                download_url=(Path("..") / "dist" / "first_party_packages" / archive_path.name).as_posix(),
            )
        )

    catalog_payload = {
        "version": 1,
        "packages": sorted(catalog_entries, key=lambda item: str(item.get("display_name", item.get("package_id", ""))).lower()),
    }
    catalog_path.write_text(json.dumps(catalog_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {
        "archives": [str(path) for path in built_archives],
        "catalog_path": str(catalog_path),
        "count": len(built_archives),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build and sign first-party plugin packages.")
    parser.add_argument("--output-dir", default=str(ROOT / "dist" / "first_party_packages"))
    parser.add_argument("--catalog-path", default=str(ROOT / "dngine" / "first_party_catalog.json"))
    parser.add_argument("--private-key", default=str(ROOT / "tools" / "first_party_signing_private_key.pem"))
    args = parser.parse_args()

    result = build_first_party_packages(
        output_dir=Path(args.output_dir),
        catalog_path=Path(args.catalog_path),
        private_key_path=Path(args.private_key),
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
