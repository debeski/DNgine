"""DNgine desktop application."""

from pathlib import Path

__all__ = ["APP_NAME", "DIST_NAME", "__version__"]

APP_NAME = "DNgine"
DIST_NAME = "dngine"

__version__ = Path(__file__).with_name("VERSION").read_text(encoding="utf-8").strip()
