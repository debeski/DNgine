from __future__ import annotations

import os
import sys
from pathlib import Path

from dngine import APP_NAME, DIST_NAME


LEGACY_APP_NAME = "Micro Toolkit"
LEGACY_DIST_NAME = "micro-toolkit"
CONFIG_FILENAME = f"{DIST_NAME}_config.json"
LEGACY_CONFIG_FILENAME = "micro_toolkit_config.json"
DATABASE_FILENAME = f"{DIST_NAME}.db"
LEGACY_DATABASE_FILENAME = "micro_toolkit.db"


def _override_storage_root() -> Path | None:
    for env_name in ("DNGINE_HOME", "MICRO_TOOLKIT_HOME"):
        override = str(os.environ.get(env_name, "")).strip()
        if override:
            return Path(override).expanduser()
    return None


def _platform_storage_root(app_name: str, dist_name: str) -> Path:
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / app_name
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / app_name
    xdg_data_home = str(os.environ.get("XDG_DATA_HOME", "")).strip()
    if xdg_data_home:
        return Path(xdg_data_home).expanduser() / dist_name
    return Path.home() / ".local" / "share" / dist_name


def standard_storage_root() -> Path:
    override = _override_storage_root()
    if override is not None:
        return override

    current_root = _platform_storage_root(APP_NAME, DIST_NAME)
    legacy_root = _platform_storage_root(LEGACY_APP_NAME, LEGACY_DIST_NAME)

    if current_root.exists() or not legacy_root.exists():
        return current_root

    current_root.parent.mkdir(parents=True, exist_ok=True)
    try:
        legacy_root.replace(current_root)
        return current_root
    except OSError:
        return legacy_root


def resolve_runtime_path(root: Path, current_name: str, *legacy_names: str) -> Path:
    current_path = root / current_name
    if current_path.exists():
        return current_path

    for legacy_name in legacy_names:
        legacy_path = root / legacy_name
        if not legacy_path.exists():
            continue
        root.mkdir(parents=True, exist_ok=True)
        try:
            legacy_path.replace(current_path)
            return current_path
        except OSError:
            return legacy_path

    return current_path
