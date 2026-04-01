from __future__ import annotations

import json
import os
import shutil
import tempfile
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

from dngine.core.plugin_manager import PluginManager, PluginSpec
from dngine.core.plugin_security import scan_plugin_path
from dngine.core.plugin_signing import (
    MANIFEST_FILENAME,
    SIGNATURE_FILENAME,
    verify_installed_signed_package,
    verify_signed_archive,
)
from dngine.core.shell_registry import is_system_component


CATALOG_FILENAME = "first_party_catalog.json"


class _PackageInstallContext:
    def __init__(self):
        self.log_messages: list[dict[str, str]] = []

    def log(self, message: str, level: str = "INFO") -> None:
        self.log_messages.append({"level": str(level), "message": str(message)})

    def progress(self, _value: float) -> None:
        return None


class PluginPackageManager:
    def __init__(
        self,
        plugin_manager: PluginManager,
        custom_plugins_root: Path,
        signed_plugins_root: Path,
        package_catalog_root: Path,
        package_cache_root: Path,
        state_manager,
        dependency_manager,
        bundled_catalog_path: Path,
        signers_path: Path,
    ):
        self.plugin_manager = plugin_manager
        self.custom_plugins_root = Path(custom_plugins_root)
        self.signed_plugins_root = Path(signed_plugins_root)
        self.package_catalog_root = Path(package_catalog_root)
        self.package_cache_root = Path(package_cache_root)
        self.state_manager = state_manager
        self.dependency_manager = dependency_manager
        self.bundled_catalog_path = Path(bundled_catalog_path)
        self.signers_path = Path(signers_path)
        self.custom_plugins_root.mkdir(parents=True, exist_ok=True)
        self.signed_plugins_root.mkdir(parents=True, exist_ok=True)
        self.package_catalog_root.mkdir(parents=True, exist_ok=True)
        self.package_cache_root.mkdir(parents=True, exist_ok=True)

    def catalog_path(self) -> Path:
        return self.package_catalog_root / CATALOG_FILENAME

    def import_plugin_file(self, source_file: Path) -> list[str]:
        source_file = Path(source_file)
        if not source_file.exists() or source_file.suffix != ".py":
            raise ValueError("Choose a valid Python plugin file.")
        report = scan_plugin_path(source_file)
        self._reject_critical_report(report)
        specs = self.plugin_manager.inspect_path(source_file)
        if not specs:
            raise ValueError("No compatible plugin class was found in the selected file.")
        plugin_id = specs[0].plugin_id
        self._ensure_no_conflicts(specs, target_package_name=plugin_id, allowed_source_type="custom")
        target_dir = self.custom_plugins_root / plugin_id
        if target_dir.exists():
            shutil.rmtree(target_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, target_dir / source_file.name)
        for sibling in self._matching_sidecars(source_file):
            if sibling.is_file():
                shutil.copy2(sibling, target_dir / sibling.name)
            elif sibling.is_dir():
                shutil.copytree(sibling, target_dir / sibling.name, dirs_exist_ok=True)
        self._initialize_custom_plugins([spec.plugin_id for spec in specs], report.as_dict())
        self.plugin_manager.invalidate_cache(clear_instances=True)
        return [spec.plugin_id for spec in specs]

    def import_plugin_folder(self, source_dir: Path) -> list[str]:
        source_dir = Path(source_dir)
        if not source_dir.is_dir():
            raise ValueError("Choose a valid plugin folder.")
        report = scan_plugin_path(source_dir)
        self._reject_critical_report(report)
        specs = self.plugin_manager.inspect_path(source_dir)
        if not specs:
            raise ValueError("No compatible plugins were found in the selected folder.")
        self._ensure_no_conflicts(specs, target_package_name=source_dir.name, allowed_source_type="custom")
        target_dir = self.custom_plugins_root / source_dir.name
        if target_dir.exists():
            shutil.rmtree(target_dir)
        shutil.copytree(source_dir, target_dir)
        self._initialize_custom_plugins([spec.plugin_id for spec in specs], report.as_dict())
        self.plugin_manager.invalidate_cache(clear_instances=True)
        return [spec.plugin_id for spec in specs]

    def import_plugin_package(self, archive_path: Path) -> list[str]:
        archive_path = Path(archive_path)
        if not archive_path.exists():
            raise ValueError("Choose a valid plugin package archive.")
        if self._archive_is_signed(archive_path):
            payload = self.install_signed_package_archive(archive_path)
            return [str(item) for item in payload.get("plugin_ids", [])]
        return self._import_custom_plugin_package(archive_path)

    def import_backup(self, archive_path: Path) -> list[str]:
        return self.import_plugin_package(archive_path)

    def refresh_catalog(self, source: str | None = None) -> dict[str, object]:
        default_source = self._default_catalog_source()
        requested_source = str(source or "").strip()
        if requested_source:
            source_value = requested_source
            relative_to = Path.cwd()
        else:
            source_value = str(default_source)
            relative_to = self.bundled_catalog_path.parent if not isinstance(default_source, Path) else default_source.parent
        payload = self._read_json_source(source_value, relative_to=relative_to)
        packages = payload.get("packages", [])
        if not isinstance(packages, list):
            raise ValueError("First-party package catalog is invalid.")
        payload["source"] = source_value
        target_path = self.catalog_path()
        target_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return {
            "catalog_path": str(target_path),
            "count": len(packages),
            "source": source_value,
        }

    def list_catalog_packages(self) -> list[dict[str, object]]:
        catalog = self._load_catalog_payload()
        installed = {entry["package_id"]: entry for entry in self.list_installed_packages()}
        rows: list[dict[str, object]] = []
        for entry in catalog.get("packages", []):
            if not isinstance(entry, dict):
                continue
            package_id = str(entry.get("package_id", "")).strip()
            if not package_id:
                continue
            installed_entry = installed.get(package_id, {})
            rows.append(
                {
                    "package_id": package_id,
                    "display_name": str(entry.get("display_name", package_id)),
                    "display_name_ar": str(entry.get("display_name_ar", "")),
                    "category_label": str(entry.get("category_label", "")),
                    "category_label_ar": str(entry.get("category_label_ar", "")),
                    "package_version": str(entry.get("package_version", "")),
                    "installed": bool(installed_entry),
                    "installed_version": str(installed_entry.get("package_version", "")),
                    "plugin_ids": list(entry.get("plugin_ids", [])),
                    "group_plugin_ids": list(entry.get("group_plugin_ids", entry.get("plugin_ids", []))),
                    "download_url": str(entry.get("download_url", "")),
                    "signer": str(entry.get("signer", "")),
                    "update_available": bool(
                        installed_entry and self._version_key(str(entry.get("package_version", ""))) > self._version_key(str(installed_entry.get("package_version", "")))
                    ),
                }
            )
        for package_id, installed_entry in installed.items():
            if package_id not in {row["package_id"] for row in rows}:
                rows.append(
                    {
                        "package_id": package_id,
                        "display_name": installed_entry.get("display_name", package_id),
                        "display_name_ar": installed_entry.get("display_name_ar", ""),
                        "category_label": installed_entry.get("category_label", ""),
                        "category_label_ar": installed_entry.get("category_label_ar", ""),
                        "package_version": installed_entry.get("package_version", ""),
                        "installed": True,
                        "installed_version": installed_entry.get("package_version", ""),
                        "plugin_ids": list(installed_entry.get("plugin_ids", [])),
                        "group_plugin_ids": list(installed_entry.get("group_plugin_ids", installed_entry.get("plugin_ids", []))),
                        "download_url": "",
                        "signer": installed_entry.get("signer", ""),
                        "update_available": False,
                    }
                )
        return sorted(rows, key=lambda row: str(row.get("display_name", row.get("package_id", ""))).lower())

    def list_installed_packages(self) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for package_root in sorted(self.signed_plugins_root.iterdir() if self.signed_plugins_root.exists() else []):
            if not package_root.is_dir():
                continue
            try:
                verification = verify_installed_signed_package(package_root, self.signers_path)
            except Exception:
                continue
            manifest = verification.manifest
            rows.append(
                {
                    "package_id": verification.package_id,
                    "display_name": str(manifest.get("display_name", verification.package_id)),
                    "display_name_ar": str(manifest.get("display_name_ar", "")),
                    "category_label": str(manifest.get("category_label", "")),
                    "category_label_ar": str(manifest.get("category_label_ar", "")),
                    "package_version": verification.package_version,
                    "plugin_ids": [str(item.get("plugin_id", "")).strip() for item in manifest.get("plugins", []) if isinstance(item, dict)],
                    "group_plugin_ids": list(manifest.get("group_plugin_ids", [])),
                    "signer": verification.signer,
                    "install_path": str(package_root),
                }
            )
        return rows

    def available_updates(self) -> list[dict[str, object]]:
        return [entry for entry in self.list_catalog_packages() if bool(entry.get("update_available"))]

    def install_catalog_package(self, package_id: str) -> dict[str, object]:
        package_id = str(package_id or "").strip()
        if not package_id:
            raise ValueError("package_id is required.")
        catalog = self._load_catalog_payload()
        entry = next(
            (
                item
                for item in catalog.get("packages", [])
                if isinstance(item, dict) and str(item.get("package_id", "")).strip() == package_id
            ),
            None,
        )
        if entry is None:
            raise ValueError(f"Unknown package id: {package_id}")
        download_target = self._resolve_download_target(entry, catalog)
        archive_path = self._obtain_archive(download_target, package_id)
        return self.install_signed_package_archive(archive_path)

    def install_signed_package_archive(self, archive_path: Path) -> dict[str, object]:
        verification = verify_signed_archive(archive_path, self.signers_path)
        manifest = verification.manifest
        package_id = verification.package_id
        if not package_id:
            raise ValueError("Signed package manifest is missing a package id.")
        plugins = [entry for entry in manifest.get("plugins", []) if isinstance(entry, dict)]
        self._ensure_manifest_conflicts(plugins, package_id=package_id)

        target_dir = self.signed_plugins_root / package_id
        temp_dir = self.signed_plugins_root / f".{package_id}.installing"
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        if target_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
        temp_dir.mkdir(parents=True, exist_ok=True)
        try:
            with zipfile.ZipFile(archive_path, "r") as archive:
                for name in archive.namelist():
                    if name.endswith("/"):
                        continue
                    destination = temp_dir / Path(name)
                    self._ensure_within_root(destination, temp_dir)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(name) as source_handle, destination.open("wb") as dest_handle:
                        shutil.copyfileobj(source_handle, dest_handle)
            verify_installed_signed_package(temp_dir, self.signers_path)
            if target_dir.exists():
                shutil.rmtree(target_dir)
            temp_dir.replace(target_dir)
        except Exception:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise

        self.plugin_manager.invalidate_cache(clear_instances=True)
        specs = [
            spec
            for spec in self.plugin_manager.discover_plugins(include_disabled=True)
            if spec.source_type == "signed" and spec.package_name == package_id
        ]
        plugin_ids = [spec.plugin_id for spec in specs]
        self._initialize_signed_plugins(plugin_ids)
        dependency_results: list[dict[str, str]] = []
        dependency_errors: list[dict[str, str]] = []
        for spec in specs:
            summary = self.dependency_manager.summary_for_spec(spec)
            if not summary.has_manifest:
                continue
            try:
                repair = self.dependency_manager.runtime_dir(spec.plugin_id).exists()
                dependency_results.append(
                    self.dependency_manager.install_for_spec(
                        spec,
                        _PackageInstallContext(),
                        repair=repair,
                    )
                )
            except Exception as exc:
                dependency_errors.append({"plugin_id": spec.plugin_id, "error": str(exc)})
        self.plugin_manager.invalidate_cache(clear_instances=True)
        return {
            "package_id": package_id,
            "package_version": verification.package_version,
            "signer": verification.signer,
            "plugin_ids": plugin_ids,
            "install_path": str(target_dir),
            "dependency_results": dependency_results,
            "dependency_errors": dependency_errors,
        }

    def remove_package(self, package_id: str) -> dict[str, object]:
        package_id = str(package_id or "").strip()
        if not package_id:
            raise ValueError("package_id is required.")
        target_dir = self.signed_plugins_root / package_id
        if not target_dir.exists():
            return {"package_id": package_id, "removed": False, "plugin_ids": []}
        self.plugin_manager.invalidate_cache(clear_instances=True)
        specs = [
            spec
            for spec in self.plugin_manager.discover_plugins(include_disabled=True)
            if spec.source_type == "signed" and spec.package_name == package_id
        ]
        plugin_ids = [spec.plugin_id for spec in specs]
        for spec in specs:
            self.dependency_manager.clear_for_spec(spec)
            self.state_manager.reset(spec.plugin_id)
        shutil.rmtree(target_dir)
        self.plugin_manager.invalidate_cache(clear_instances=True)
        return {"package_id": package_id, "removed": True, "plugin_ids": plugin_ids}

    def export_plugins(self, specs: list[PluginSpec], destination: Path) -> Path:
        destination = Path(destination)
        if not specs:
            raise ValueError("Select at least one plugin to export.")
        blocked = [spec.plugin_id for spec in specs if is_system_component(spec.plugin_id)]
        if blocked:
            raise ValueError("System components cannot be exported as plugins.")
        non_custom = [spec.plugin_id for spec in specs if spec.source_type != "custom"]
        if non_custom:
            raise ValueError("Only custom plugins can be exported.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            manifest_plugins = []
            archive_root = temp_root / "plugins"
            archive_root.mkdir(parents=True, exist_ok=True)
            for spec in specs:
                package_name = spec.package_name or spec.plugin_id
                package_root = archive_root / package_name
                package_root.mkdir(parents=True, exist_ok=True)
                manifest_plugins.append(
                    {
                        "plugin_id": spec.plugin_id,
                        "package_name": package_name,
                        "source_type": spec.source_type,
                        "primary_relative_path": spec.primary_relative_path,
                    }
                )
                for source_path, relative_path in self._package_files(spec):
                    dest_path = package_root / relative_path
                    dest_path.parent.mkdir(parents=True, exist_ok=True)
                    if source_path.is_file():
                        shutil.copy2(source_path, dest_path)
            (temp_root / MANIFEST_FILENAME).write_text(
                json.dumps({"version": 1, "plugins": manifest_plugins}, indent=2),
                encoding="utf-8",
            )
            with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for file_path in temp_root.rglob("*"):
                    if file_path.is_file():
                        archive.write(file_path, file_path.relative_to(temp_root).as_posix())
        return destination

    def _import_custom_plugin_package(self, archive_path: Path) -> list[str]:
        imported_ids: list[str] = []
        with zipfile.ZipFile(archive_path, "r") as archive:
            try:
                manifest = json.loads(archive.read(MANIFEST_FILENAME).decode("utf-8"))
            except Exception as exc:
                raise ValueError(f"Invalid plugin package file: {exc}") from exc
            plugins = manifest.get("plugins", [])
            if not isinstance(plugins, list) or not plugins:
                raise ValueError("Plugin package archive does not contain any plugins.")

            existing_by_id = {spec.plugin_id: spec for spec in self.plugin_manager.discover_plugins(include_disabled=True)}
            for entry in plugins:
                plugin_id = str(entry.get("plugin_id", "")).strip()
                package_name = str(entry.get("package_name", "")).strip()
                if not plugin_id or not package_name:
                    raise ValueError("Plugin package manifest is missing plugin metadata.")
                existing = existing_by_id.get(plugin_id)
                if existing is not None and not (existing.source_type == "custom" and existing.package_name == package_name):
                    raise ValueError(f"Cannot import '{plugin_id}' because that plugin id already exists.")
                target_dir = self.custom_plugins_root / package_name
                if target_dir.exists():
                    shutil.rmtree(target_dir)
                try:
                    target_dir.mkdir(parents=True, exist_ok=True)
                    prefix = f"plugins/{package_name}/"
                    for name in archive.namelist():
                        if not name.startswith(prefix) or name.endswith("/"):
                            continue
                        relative_name = name[len(prefix):]
                        if not relative_name:
                            continue
                        destination = target_dir / relative_name
                        self._ensure_within_root(destination, target_dir)
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        with archive.open(name) as source_handle, destination.open("wb") as dest_handle:
                            shutil.copyfileobj(source_handle, dest_handle)
                    report = scan_plugin_path(target_dir)
                    self._reject_critical_report(report)
                    self._initialize_custom_plugins([plugin_id], report.as_dict())
                    imported_ids.append(plugin_id)
                except Exception:
                    if target_dir.exists():
                        shutil.rmtree(target_dir)
                    raise
        self.plugin_manager.invalidate_cache(clear_instances=True)
        return imported_ids

    def _archive_is_signed(self, archive_path: Path) -> bool:
        with zipfile.ZipFile(archive_path, "r") as archive:
            if MANIFEST_FILENAME not in archive.namelist() or SIGNATURE_FILENAME not in archive.namelist():
                return False
            try:
                manifest = json.loads(archive.read(MANIFEST_FILENAME).decode("utf-8"))
            except Exception:
                return False
        return str(manifest.get("origin", "")).strip().lower() == "signed"

    def _default_catalog_source(self) -> str | Path:
        env_override = str(os.environ.get("DNGINE_FIRST_PARTY_CATALOG", "")).strip()
        if env_override:
            return env_override
        return self.bundled_catalog_path

    def _load_catalog_payload(self) -> dict[str, object]:
        target = self.catalog_path()
        if target.exists():
            try:
                payload = json.loads(target.read_text(encoding="utf-8"))
            except Exception:
                payload = {}
            if isinstance(payload, dict):
                return payload
        self.refresh_catalog()
        payload = json.loads(target.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {"packages": []}

    def _read_json_source(self, source: str, *, relative_to: Path) -> dict[str, object]:
        parsed = urllib.parse.urlparse(source)
        if parsed.scheme in {"http", "https"}:
            with urllib.request.urlopen(source, timeout=20) as response:
                payload = response.read().decode("utf-8")
        else:
            source_path = Path(source)
            if not source_path.is_absolute():
                source_path = (relative_to / source_path).resolve()
            payload = source_path.read_text(encoding="utf-8")
        data = json.loads(payload)
        if not isinstance(data, dict):
            raise ValueError("Catalog payload must be a JSON object.")
        return data

    def _resolve_download_target(self, entry: dict[str, object], catalog: dict[str, object]) -> str:
        download_url = str(entry.get("download_url", "")).strip()
        if not download_url:
            raise ValueError(f"Package '{entry.get('package_id', '')}' does not have a download URL.")
        parsed = urllib.parse.urlparse(download_url)
        if parsed.scheme in {"http", "https", "file"}:
            return download_url
        source = str(catalog.get("source", "")).strip()
        if source:
            source_parsed = urllib.parse.urlparse(source)
            if source_parsed.scheme in {"http", "https"}:
                return urllib.parse.urljoin(source, download_url)
            source_path = Path(source)
            if source_path.is_file():
                return str((source_path.parent / download_url).resolve())
            if source_path.is_dir():
                return str((source_path / download_url).resolve())
        return str((self.bundled_catalog_path.parent / download_url).resolve())

    def _obtain_archive(self, target: str, package_id: str) -> Path:
        parsed = urllib.parse.urlparse(target)
        if parsed.scheme in {"http", "https"}:
            cache_path = self.package_cache_root / f"{package_id}.zip"
            with urllib.request.urlopen(target, timeout=60) as response, cache_path.open("wb") as handle:
                shutil.copyfileobj(response, handle)
            return cache_path
        if parsed.scheme == "file":
            return Path(urllib.request.url2pathname(parsed.path))
        return Path(target).expanduser().resolve()

    def _ensure_manifest_conflicts(self, plugins: list[dict[str, object]], *, package_id: str) -> None:
        existing_by_id = {spec.plugin_id: spec for spec in self.plugin_manager.discover_plugins(include_disabled=True)}
        for entry in plugins:
            plugin_id = str(entry.get("plugin_id", "")).strip()
            if not plugin_id:
                raise ValueError("Signed package manifest is missing plugin ids.")
            existing = existing_by_id.get(plugin_id)
            if existing is None:
                continue
            if existing.source_type == "signed" and existing.package_name == package_id:
                continue
            raise ValueError(f"Cannot install '{plugin_id}' because that plugin id already exists.")

    def _package_files(self, spec: PluginSpec) -> list[tuple[Path, Path]]:
        files: list[tuple[Path, Path]] = []
        if spec.container_path.is_dir():
            for file_path in sorted(spec.container_path.rglob("*")):
                if file_path.is_file() and "__pycache__" not in file_path.parts:
                    files.append((file_path, file_path.relative_to(spec.container_path)))
            return files
        files.append((spec.file_path, Path(spec.file_path.name)))
        for sibling in self._matching_sidecars(spec.file_path):
            if sibling.is_file():
                files.append((sibling, Path(sibling.name)))
            elif sibling.is_dir():
                for child in sorted(sibling.rglob("*")):
                    if child.is_file() and "__pycache__" not in child.parts:
                        files.append((child, Path(sibling.name) / child.relative_to(sibling)))
        return files

    def _matching_sidecars(self, source_file: Path) -> list[Path]:
        stem = source_file.stem
        matches: list[Path] = []
        for path in source_file.parent.iterdir():
            if path == source_file:
                continue
            if path.name.startswith(f"{stem}."):
                matches.append(path)
            elif path.name == f"{stem}_assets":
                matches.append(path)
        return matches

    def _ensure_no_conflicts(self, specs: list[PluginSpec], *, target_package_name: str, allowed_source_type: str) -> None:
        existing_by_id = {spec.plugin_id: spec for spec in self.plugin_manager.discover_plugins(include_disabled=True)}
        for spec in specs:
            existing = existing_by_id.get(spec.plugin_id)
            if existing is None:
                continue
            if existing.source_type == allowed_source_type and existing.package_name == target_package_name:
                continue
            raise ValueError(f"Cannot import '{spec.plugin_id}' because that plugin id already exists.")

    def _initialize_custom_plugins(self, plugin_ids: list[str], report: dict[str, object]) -> None:
        for plugin_id in plugin_ids:
            self.state_manager.reset(plugin_id)
            self.state_manager.set_enabled(plugin_id, False)
            self.state_manager.set_hidden(plugin_id, False)
            self.state_manager.set_trusted(plugin_id, False)
            self.state_manager.set_scan_report(plugin_id, report)

    def _initialize_signed_plugins(self, plugin_ids: list[str]) -> None:
        for plugin_id in plugin_ids:
            state = self.state_manager.get(plugin_id) if self.state_manager.has(plugin_id) else None
            if state is None:
                self.state_manager.set_enabled(plugin_id, True)
                self.state_manager.set_hidden(plugin_id, False)
                self.state_manager.set_trusted(plugin_id, True)
                self.state_manager.set_scan_report(plugin_id, {"risk_level": "low", "summary": ""})
                continue
            state["risk_level"] = "low"
            state["risk_summary"] = ""
            state["trusted"] = not bool(state.get("quarantined", False))
            self.state_manager._state[plugin_id] = state
            self.state_manager._save()

    def _reject_critical_report(self, report) -> None:
        if report.risk_level != "critical":
            return
        raise ValueError(
            "Plugin import was blocked because the static safety scan detected critical patterns. "
            f"{report.summary}"
        )

    def _ensure_within_root(self, target_path: Path, root: Path) -> None:
        resolved_target = target_path.resolve()
        resolved_root = root.resolve()
        if resolved_target != resolved_root and resolved_root not in resolved_target.parents:
            raise ValueError("Plugin package archive contains an unsafe path.")

    def _version_key(self, value: str) -> tuple[int, ...]:
        parts: list[int] = []
        for raw in str(value or "").replace("-", ".").split("."):
            raw = raw.strip()
            if not raw:
                continue
            try:
                parts.append(int(raw))
            except Exception:
                parts.append(0)
        return tuple(parts or [0])
