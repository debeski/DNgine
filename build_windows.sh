#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 is required to prepare the build environment."
    exit 1
fi

if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate

echo "Installing local build dependencies..."
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller

if ! command -v docker >/dev/null 2>&1; then
    echo "Docker is required for the Linux-to-Windows cross-build."
    echo "For the most reliable Windows package, use build_windows.bat on Windows."
    deactivate
    exit 1
fi

echo "Cleaning previous build artifacts..."
rm -rf build dist dngine.egg-info

echo "Building signed first-party packages..."
python tools/build_first_party_packages.py

echo "Generating builtin plugin manifest..."
python tools/generate_builtin_plugin_manifest.py

echo "Building Windows onedir package through Docker..."
docker run --rm \
    --user "$(id -u):$(id -g)" \
    -v "$ROOT_DIR:/src" \
    -w /src \
    batonogov/pyinstaller-windows \
    bash -lc "pip install --upgrade pip && pip install -r requirements.txt pyinstaller && pyinstaller --noconfirm --clean dngine.spec"

deactivate
echo "Build complete: dist/dngine/"
echo "Launcher: dist/dngine/dngine.exe"
