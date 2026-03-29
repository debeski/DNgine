from __future__ import annotations

import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dngine.core.icon_registry import ASSETS_ROOT, used_icon_asset_paths


def main() -> int:
    destination = ROOT / "build" / "used-icons"
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True, exist_ok=True)

    exported = 0
    for source in used_icon_asset_paths():
        relative = source.relative_to(ASSETS_ROOT)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        exported += 1

    print(f"Exported {exported} icons to {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
