#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

SKIP_BINARY=0
SKIP_PYTHON_DIST=0
SKIP_DEB=0
PUBLISH_PYPI=0
REPOSITORY=""
REPOSITORY_URL=""
APP_VERSION=""
PACKAGE_ARCH=""

while [ "$#" -gt 0 ]; do
    case "$1" in
        --skip-binary)
            SKIP_BINARY=1
            ;;
        --skip-python-dist)
            SKIP_PYTHON_DIST=1
            ;;
        --skip-deb)
            SKIP_DEB=1
            ;;
        --publish-pypi)
            PUBLISH_PYPI=1
            ;;
        --repository)
            shift
            if [ "$#" -eq 0 ]; then
                echo "--repository requires a value."
                exit 1
            fi
            REPOSITORY="$1"
            ;;
        --repository-url)
            shift
            if [ "$#" -eq 0 ]; then
                echo "--repository-url requires a value."
                exit 1
            fi
            REPOSITORY_URL="$1"
            ;;
        *)
            echo "Unknown argument: $1"
            echo "Supported options: --skip-binary --skip-python-dist --skip-deb --publish-pypi --repository <name> --repository-url <url>"
            exit 1
            ;;
    esac
    shift
done

detect_version() {
    tr -d '\r\n' < dngine/VERSION
}

detect_deb_arch() {
    if command -v dpkg >/dev/null 2>&1; then
        dpkg --print-architecture
        return
    fi
    case "$(uname -m)" in
        x86_64)
            echo "amd64"
            ;;
        aarch64)
            echo "arm64"
            ;;
        armv7l)
            echo "armhf"
            ;;
        *)
            echo "all"
            ;;
    esac
}

build_deb_package() {
    local source_dir="$ROOT_DIR/dist/dngine"
    local staging_root="$ROOT_DIR/build/deb-package"
    local package_root="$staging_root/opt/dngine"
    local bin_root="$staging_root/usr/bin"
    local apps_root="$staging_root/usr/share/applications"
    local pixmaps_root="$staging_root/usr/share/pixmaps"
    local docs_root="$staging_root/usr/share/doc/dngine"
    local icon_source="$ROOT_DIR/app.ico"
    local deb_path="$ROOT_DIR/dist/dngine_${APP_VERSION}_${PACKAGE_ARCH}.deb"
    local installed_size=""

    if [ ! -d "$source_dir" ]; then
        echo "Linux onedir package was not found in dist/dngine."
        echo "Build the binary bundle first or remove --skip-binary."
        exit 1
    fi

    if ! command -v dpkg-deb >/dev/null 2>&1; then
        echo "dpkg-deb is required to build the .deb package."
        exit 1
    fi

    if [ ! -f "$icon_source" ]; then
        icon_source="$ROOT_DIR/dngine/assets/app.ico"
    fi

    echo "Building Debian package..."
    rm -rf "$staging_root"
    mkdir -p "$staging_root/DEBIAN" "$package_root" "$bin_root" "$apps_root" "$pixmaps_root" "$docs_root"
    cp -a "$source_dir"/. "$package_root/"
    cp LICENSE README.md "$docs_root/"
    if [ -f "$icon_source" ]; then
        cp "$icon_source" "$pixmaps_root/dngine.ico"
    fi

    cat > "$bin_root/dngine" <<'EOF'
#!/usr/bin/env sh
exec /opt/dngine/dngine "$@"
EOF
    chmod 755 "$bin_root/dngine"

    cat > "$apps_root/dngine.desktop" <<'EOF'
[Desktop Entry]
Version=1.0
Type=Application
Name=DNgine
Comment=Fast, cross-platform desktop toolkit
Exec=/usr/bin/dngine
Icon=/usr/share/pixmaps/dngine.ico
Terminal=false
Categories=Utility;Office;
StartupNotify=true
EOF
    chmod 644 "$apps_root/dngine.desktop"

    cat > "$staging_root/DEBIAN/postinst" <<'EOF'
#!/usr/bin/env sh
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database /usr/share/applications >/dev/null 2>&1 || true
fi
exit 0
EOF
    chmod 755 "$staging_root/DEBIAN/postinst"

    cat > "$staging_root/DEBIAN/postrm" <<'EOF'
#!/usr/bin/env sh
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database /usr/share/applications >/dev/null 2>&1 || true
fi
exit 0
EOF
    chmod 755 "$staging_root/DEBIAN/postrm"

    installed_size="$(du -sk "$staging_root" | cut -f1)"
    cat > "$staging_root/DEBIAN/control" <<EOF
Package: dngine
Version: $APP_VERSION
Section: utils
Priority: optional
Architecture: $PACKAGE_ARCH
Maintainer: debeski
Installed-Size: $installed_size
Homepage: https://github.com/debeski/dngine
Description: Fast, cross-platform desktop toolkit built with PySide6.
 DNgine is a plugin-driven desktop application with office,
 media, file, IT, and workflow tools in one local-first shell.
EOF

    rm -f "$deb_path"
    if dpkg-deb --help 2>/dev/null | grep -q -- "--root-owner-group"; then
        dpkg-deb --build --root-owner-group "$staging_root" "$deb_path"
    else
        dpkg-deb --build "$staging_root" "$deb_path"
    fi
}

if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 is required to build DNgine."
    exit 1
fi

if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate

APP_VERSION="$(detect_version)"
PACKAGE_ARCH="$(detect_deb_arch)"

echo "Installing build dependencies..."
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller build twine

echo "Cleaning previous build artifacts..."
rm -rf build dist dngine.egg-info

echo "Building signed first-party packages..."
python tools/build_first_party_packages.py

echo "Generating builtin plugin manifest..."
python tools/generate_builtin_plugin_manifest.py

if [ "$SKIP_BINARY" -eq 0 ]; then
    echo "Building Linux onedir package..."
    python -m PyInstaller --noconfirm --clean dngine.spec
fi

if [ "$SKIP_DEB" -eq 0 ]; then
    build_deb_package
fi

if [ "$SKIP_PYTHON_DIST" -eq 0 ]; then
    echo "Building Python distributions..."
    python -m build --sdist --wheel
fi

if [ "$PUBLISH_PYPI" -eq 1 ]; then
    if [ "$SKIP_PYTHON_DIST" -eq 1 ]; then
        echo "Cannot publish to PyPI when --skip-python-dist is set."
        exit 1
    fi

    PYPI_UPLOAD_TOKEN="${PYPI_TOKEN:-${TWINE_PASSWORD:-}}"
    if [ -z "$PYPI_UPLOAD_TOKEN" ]; then
        echo "Publishing requested, but PYPI_TOKEN or TWINE_PASSWORD is not set."
        exit 1
    fi

    export TWINE_USERNAME="${TWINE_USERNAME:-__token__}"
    export TWINE_PASSWORD="$PYPI_UPLOAD_TOKEN"

    shopt -s nullglob
    DIST_FILES=(dist/*.whl dist/*.tar.gz)
    shopt -u nullglob
    if [ "${#DIST_FILES[@]}" -eq 0 ]; then
        echo "No wheel or source distribution was found in dist/ for upload."
        exit 1
    fi

    TWINE_COMMAND=(python -m twine upload)
    if [ -n "$REPOSITORY_URL" ]; then
        TWINE_COMMAND+=(--repository-url "$REPOSITORY_URL")
    elif [ -n "$REPOSITORY" ]; then
        TWINE_COMMAND+=(--repository "$REPOSITORY")
    fi

    echo "Uploading Python distributions..."
    "${TWINE_COMMAND[@]}" "${DIST_FILES[@]}"
fi

deactivate
echo "Build complete."
if [ "$SKIP_BINARY" -eq 0 ]; then
    echo "Linux launcher: dist/dngine/dngine"
fi
if [ "$SKIP_DEB" -eq 0 ]; then
    echo "Debian package: dist/dngine_${APP_VERSION}_${PACKAGE_ARCH}.deb"
fi
if [ "$SKIP_PYTHON_DIST" -eq 0 ]; then
    echo "Python distributions:"
    ls -1 dist/*.whl dist/*.tar.gz 2>/dev/null || true
fi
