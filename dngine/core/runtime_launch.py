from __future__ import annotations

import os
import sys
from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def pythonpath_env() -> dict[str, str] | None:
    if getattr(sys, "frozen", False):
        return None
    env = os.environ.copy()
    root = str(project_root())
    existing = str(env.get("PYTHONPATH") or "").strip()
    if not existing:
        env["PYTHONPATH"] = root
        return env
    parts = [part for part in existing.split(os.pathsep) if part]
    if root not in parts:
        parts.insert(0, root)
        env["PYTHONPATH"] = os.pathsep.join(parts)
    return env


def gui_executable() -> str:
    if not getattr(sys, "frozen", False):
        return sys.executable
    executable = Path(sys.executable).resolve()
    if sys.platform == "darwin" and executable.name == "dngine-helper":
        candidate = executable.with_name("dngine")
        if candidate.exists():
            return str(candidate)
    return sys.executable


def bundled_background_helper_path() -> Path | None:
    if sys.platform != "darwin" or not getattr(sys, "frozen", False):
        return None
    # Bundled macOS background services should not reuse the GUI launcher,
    # or LaunchServices may surface an extra Dock tile for the helper process.
    candidate = Path(sys.executable).resolve().with_name("dngine-helper")
    return candidate if candidate.exists() else None


def build_background_subcommand_args(subcommand: str, *args: str) -> list[str]:
    helper_path = bundled_background_helper_path()
    if helper_path is not None:
        return [str(helper_path), subcommand, *args]
    if getattr(sys, "frozen", False):
        return [sys.executable, subcommand, *args]
    return [sys.executable, "-m", "dngine", subcommand, *args]
