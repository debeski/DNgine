from __future__ import annotations

import hashlib
import importlib.metadata as metadata
import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from dngine.core.plugin_manager import PluginManager, PluginSpec


_REQ_NAME_PATTERN = re.compile(r"^\s*([A-Za-z0-9_.-]+)")


@dataclass(frozen=True)
class PluginDependencySummary:
    plugin_id: str
    manifest_path: Path | None
    status: str
    message: str
    warning: str = ""
    error: str = ""

    @property
    def has_manifest(self) -> bool:
        return self.manifest_path is not None


class PluginDependencyManager:
    def __init__(self, plugin_manager: PluginManager, runtime_root: Path, state_path: Path):
        self.plugin_manager = plugin_manager
        self.runtime_root = Path(runtime_root)
        self.state_path = Path(state_path)
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self._state = self._load_state()

    def _load_state(self) -> dict[str, dict[str, str]]:
        if not self.state_path.exists():
            return {}
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _save_state(self) -> None:
        self.state_path.write_text(json.dumps(self._state, indent=2), encoding="utf-8")

    def _get_state(self, plugin_id: str) -> dict[str, str]:
        state = self._state.get(plugin_id, {})
        return {
            "status": str(state.get("status", "")),
            "manifest_hash": str(state.get("manifest_hash", "")),
            "last_error": str(state.get("last_error", "")),
            "last_installed_at": str(state.get("last_installed_at", "")),
        }

    def _set_state(
        self,
        plugin_id: str,
        *,
        status: str,
        manifest_hash: str = "",
        last_error: str = "",
        last_installed_at: str = "",
    ) -> None:
        self._state[plugin_id] = {
            "status": str(status),
            "manifest_hash": str(manifest_hash),
            "last_error": str(last_error),
            "last_installed_at": str(last_installed_at),
        }
        self._save_state()

    def reset(self, plugin_id: str) -> None:
        if plugin_id in self._state:
            del self._state[plugin_id]
            self._save_state()

    def migrate_plugin_ids(self, mapping: dict[str, str]) -> bool:
        changed = False
        updated = {}
        for plugin_id, state in self._state.items():
            new_id = mapping.get(plugin_id, plugin_id)
            updated[new_id] = state
            if new_id != plugin_id:
                changed = True
        if changed:
            self._state = updated
            self._save_state()
        return changed

    def runtime_dir(self, plugin_id: str) -> Path:
        return self.runtime_root / plugin_id

    def site_packages_dir(self, plugin_id: str) -> Path:
        return self.runtime_dir(plugin_id) / "site-packages"

    def dependency_paths_for_spec(self, spec: PluginSpec) -> list[str]:
        summary = self.summary_for_spec(spec)
        if summary.status not in {"installed", "conflict"}:
            return []
        site_packages = self.site_packages_dir(spec.plugin_id)
        if not site_packages.exists():
            return []
        return [str(site_packages)]

    def manifest_for_spec(self, spec: PluginSpec) -> Path | None:
        if spec.source_type not in {"custom", "signed"}:
            return None
        stem = spec.file_path.stem
        preferred = spec.file_path.with_name(f"{stem}.deps")
        fallback = spec.file_path.with_name(f"{stem}.deps.txt")
        if preferred.exists():
            return preferred
        if fallback.exists():
            return fallback
        return None

    def summary_for_spec(self, spec: PluginSpec) -> PluginDependencySummary:
        manifest_path = self.manifest_for_spec(spec)
        if manifest_path is None:
            return PluginDependencySummary(
                plugin_id=spec.plugin_id,
                manifest_path=None,
                status="none",
                message="no_dependencies",
            )

        warning = self._manifest_warning(spec)
        state = self._get_state(spec.plugin_id)
        site_packages = self.site_packages_dir(spec.plugin_id)
        manifest_hash = self._file_hash(manifest_path)

        if state["status"] == "installed" and state["manifest_hash"] == manifest_hash and site_packages.exists():
            status = "installed"
            message = "installed"
        elif state["status"] == "failed" and state["manifest_hash"] == manifest_hash:
            status = "failed"
            message = "install_failed"
        elif site_packages.exists():
            status = "stale"
            message = "repair_available"
        else:
            status = "missing"
            message = "missing"

        conflict_warning = self._conflict_warning(spec, manifest_path)
        if conflict_warning:
            warning = f"{warning}\n{conflict_warning}".strip() if warning else conflict_warning
            if status == "installed":
                status = "conflict"
                message = "conflict"

        return PluginDependencySummary(
            plugin_id=spec.plugin_id,
            manifest_path=manifest_path,
            status=status,
            message=message,
            warning=warning,
            error=state["last_error"],
        )

    def clear_for_spec(self, spec: PluginSpec) -> bool:
        runtime_dir = self.runtime_dir(spec.plugin_id)
        removed = False
        if runtime_dir.exists():
            shutil.rmtree(runtime_dir)
            removed = True
        self.reset(spec.plugin_id)
        return removed

    def install_for_spec(self, spec: PluginSpec, context, *, repair: bool = False) -> dict[str, str]:
        manifest_path = self.manifest_for_spec(spec)
        if manifest_path is None:
            raise RuntimeError("This plugin does not declare any dependency sidecar.")
        manifest_hash = self._file_hash(manifest_path)
        site_packages = self.site_packages_dir(spec.plugin_id)
        runtime_dir = self.runtime_dir(spec.plugin_id)

        if repair and runtime_dir.exists():
            context.log(f"Clearing previous dependency runtime for '{spec.plugin_id}'.")
            shutil.rmtree(runtime_dir, ignore_errors=True)

        runtime_dir.mkdir(parents=True, exist_ok=True)
        site_packages.mkdir(parents=True, exist_ok=True)
        self._set_state(spec.plugin_id, status="installing", manifest_hash=manifest_hash)

        try:
            context.log(f"Installing dependency sidecar for '{spec.plugin_id}' from {manifest_path.name}.")
            exit_code = self._run_pip_install(manifest_path, site_packages)
            if exit_code != 0:
                raise RuntimeError(f"pip exited with status {exit_code}.")
        except Exception as exc:
            self._set_state(
                spec.plugin_id,
                status="failed",
                manifest_hash=manifest_hash,
                last_error=str(exc),
            )
            raise

        installed_at = datetime.now().isoformat(timespec="seconds")
        self._set_state(
            spec.plugin_id,
            status="installed",
            manifest_hash=manifest_hash,
            last_error="",
            last_installed_at=installed_at,
        )
        return {
            "plugin_id": spec.plugin_id,
            "manifest_path": str(manifest_path),
            "site_packages": str(site_packages),
            "installed_at": installed_at,
            "repair": "yes" if repair else "no",
        }

    def _run_pip_install(self, manifest_path: Path, target_dir: Path) -> int:
        try:
            from pip._internal.cli.main import main as pip_main
        except Exception as exc:  # pragma: no cover - depends on build environment
            raise RuntimeError(
                "Bundled pip support is unavailable in this build. Rebuild DNgine with pip support included."
            ) from exc

        args = [
            "install",
            "--disable-pip-version-check",
            "--no-input",
            "--upgrade",
            "--target",
            str(target_dir),
            "-r",
            str(manifest_path),
        ]
        return int(pip_main(args))

    def _manifest_warning(self, spec: PluginSpec) -> str:
        preferred = spec.file_path.with_name(f"{spec.file_path.stem}.deps")
        fallback = spec.file_path.with_name(f"{spec.file_path.stem}.deps.txt")
        if preferred.exists() and fallback.exists():
            return "Both .deps and .deps.txt sidecars exist. Using .deps."
        return ""

    def _conflict_warning(self, spec: PluginSpec, manifest_path: Path) -> str:
        requirements = self._parse_requirements(manifest_path)
        warnings: list[str] = []

        exact_pins = {item["name"]: item["exact_version"] for item in requirements if item["name"] and item["exact_version"]}
        for name, version in exact_pins.items():
            try:
                installed_version = metadata.version(name)
            except metadata.PackageNotFoundError:
                installed_version = ""
            except Exception:
                installed_version = ""
            if installed_version and installed_version != version:
                warnings.append(f"{name}=={version} requested, runtime has {installed_version}.")

        if exact_pins:
            for other in self.plugin_manager.discover_plugins(include_disabled=True):
                if other.plugin_id == spec.plugin_id or other.source_type not in {"custom", "signed"}:
                    continue
                other_manifest = self.manifest_for_spec(other)
                if other_manifest is None:
                    continue
                for item in self._parse_requirements(other_manifest):
                    other_name = item["name"]
                    other_version = item["exact_version"]
                    if not other_name or not other_version:
                        continue
                    current_version = exact_pins.get(other_name)
                    if current_version and current_version != other_version:
                        warnings.append(
                            f"{other_name} pins conflict with {other.plugin_id} ({current_version} vs {other_version})."
                        )
        return "\n".join(dict.fromkeys(warnings))

    def _parse_requirements(self, manifest_path: Path) -> list[dict[str, str]]:
        items: list[dict[str, str]] = []
        try:
            lines = manifest_path.read_text(encoding="utf-8").splitlines()
        except Exception:
            return items
        for line in lines:
            raw = line.strip()
            if not raw or raw.startswith("#") or raw.startswith("-"):
                continue
            match = _REQ_NAME_PATTERN.match(raw)
            if not match:
                continue
            name = match.group(1).lower().replace("_", "-")
            exact_version = ""
            if "==" in raw:
                exact_version = raw.split("==", 1)[1].split(";", 1)[0].strip()
            items.append({"name": name, "exact_version": exact_version, "raw": raw})
        return items

    def _file_hash(self, path: Path) -> str:
        hasher = hashlib.sha256()
        with path.open("rb") as handle:
            while chunk := handle.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()
