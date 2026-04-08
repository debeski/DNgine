#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "build_macos.sh should be run on macOS."
    exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 is required to build DNgine."
    exit 1
fi

if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate

echo "Installing build dependencies..."
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller

echo "Cleaning previous build artifacts..."
rm -rf build dist dngine.egg-info

echo "Building signed first-party packages..."
python tools/build_fp_plugins.py

echo "Generating builtin plugin manifest..."
python tools/gen_builtin_manifest.py

echo "Building macOS app bundle..."
python -m PyInstaller --noconfirm --clean dngine.spec

deactivate
echo "Build complete: dist/DNgine.app"
echo "Launcher: dist/DNgine.app"
