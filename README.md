# DNgine

[![PyPI version](https://img.shields.io/pypi/v/dngine.svg)](https://pypi.org/project/dngine/)

DNgine is a fast, cross-platform, multilingual, plugin-driven desktop companion for day-to-day office and home use. It is built with `PySide6` and designed to feel like a native desktop application: quick to open, responsive while working, tray-friendly, and flexible enough to grow through drop-in plugins.

## Documentation

- Start here: [docs/README.md](./docs/README.md)
- App usage docs: [docs/app/README.md](./docs/app/README.md)
- SDK and plugin authoring docs: [docs/dev/sdk.md](./docs/dev/sdk.md)
- CLI and command docs: [docs/dev/cli.md](./docs/dev/cli.md)
- Migration notes: [docs/dev/migration.md](./docs/dev/migration.md)
- UI and UX standards: [docs/design/ui-ux-standards.md](./docs/design/ui-ux-standards.md)
- Release history: [CHANGELOG.md](./CHANGELOG.md)

## Overview

DNgine brings practical desktop utilities into one cohesive shell:

- file utilities
- spreadsheet and office helpers
- IT and system tools
- clipboard history and quick access
- media and image tools
- workflows and CLI automation
- signed first-party package installs
- custom plugin loading

The app is intentionally desktop-first. It is not a browser wrapper, and it is not built around always-online services. It is meant to stay light, quick, and usable throughout the day.

## Highlights

- Native desktop UX built on `PySide6`
- Lazy plugin discovery and lazy page creation for fast startup
- English and Arabic support with RTL-aware layout direction
- Five curated theme colors with a dark-mode toggle
- Global top-bar search with live results and direct page/section navigation
- Live preview for language, direction, density, and UI scaling
- Shell-owned top-bar visual refresh spinner, busy cursor, and status-bar task progress
- Standardized per-user runtime storage across Windows, macOS, and Linux
- Tray integration for all-day companion use
- Integrated `Clip-Monitor` clipboard capture that stays active while DNgine is hidden in the tray without spawning a second app instance
- Dashboard shell with a workspace pulse panel, usage snapshots, and recent activity
- Settings support for default output path and default startup page selection
- Workflow engine and CLI command surface
- Core-only base bundle plus installable signed first-party tool packages
- In-app first-party package catalog with install, update, remove, and local signed import flows
- Archive-first custom plugin packaging and sharing
- Custom plugin dependency sidecars with install/repair flow in Plugins
- Plugin-local translations through sidecar locale files plus shared `bind_tr(...)`, `tr(...)`, and `safe_tr(...)` helpers
- Public `dngine.sdk` authoring surface with declarative `DeclarativePlugin` pages, shared task helpers, and shared media helpers for ordinary plugins
- Shared `apply_page_chrome(...)` and semantic UI classes for low-boilerplate plugin pages
- Four-level shell surface model with shared card/control/console/preview styling
- Opt-in plugin display name and icon customization
- Headless tool commands for workflows and automation
- Capability-based elevated broker for future admin/root operations
- Dedicated elevated hotkey helper for Linux global shortcuts
- Developer inspector system page gated behind developer mode
- Multi-format clipboard history with pinned snippets, labels, and categories

## Installation

You can download the pre-built binaries from the GitHub Releases page or build from source.

### Pre-built Packages

- **Windows**: Download the `.exe` installer from the Releases page and run it to install DNgine.
- **macOS**: Download the `.app` bundle from the Releases page. You can run it directly as a portable application from any directory (e.g. your Downloads or Applications folder).
- **Linux**: Download and install the `.deb` package from the Releases page.

### Building from Source

#### Requirements

- Python 3.10+
- the base runtime packages listed in [requirements.txt](./requirements.txt)
- optional first-party package dependencies are installed from signed package sidecars when those packages are installed

#### Linux Note

On some X11 systems, Qt 6.5+ may require:

```bash
sudo apt-get install -y libxcb-cursor0
```

#### Setup

PowerShell on Windows:

```powershell
git clone https://github.com/debeski/dngine.git
cd dngine
py -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

If PowerShell blocks activation, you can use the venv interpreter directly instead:

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

macOS / Linux:

```bash
git clone https://github.com/debeski/dngine.git
cd dngine
python3 -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt
```

Packaged builds should also regenerate the first-party package catalog and builtin manifest before running `PyInstaller`:

```bash
python tools/build_fp_plugins.py
python tools/gen_builtin_manifest.py
```

## Running the App

### From Pre-built Packages

- **Windows / Linux**: Launch DNgine from your system's application menu.
- **macOS**: Double-click the `DNgine.app` to launch it. If macOS blocks the app because it's from an unidentified developer, `Right-click` (or `Control-click`) the app and select **Open**.

### From Source

Launch the desktop app:

```bash
python -m dngine
```

On Windows PowerShell, if you prefer calling the venv interpreter directly:

```powershell
.\venv\Scripts\python.exe -m dngine
```

On macOS / Linux, the equivalent direct venv command is:

```bash
./venv/bin/python -m dngine
```

Launch directly into GUI mode:

```bash
python -m dngine gui
```

Open a specific plugin on startup:

```bash
python -m dngine gui --plugin-id clip_snip
```

## CLI Examples

List plugins:

```bash
python -m dngine plugins list
```

List registered workflow and tool commands:

```bash
python -m dngine commands list
```

Run a headless tool command:

```bash
python -m dngine commands run tool.doc_bridge.md_to_docx --args '{"markdown_path": "notes.md"}'
```

Refresh the bundled first-party package catalog:

```bash
python -m dngine packages refresh
```

Install the `Web Dev` first-party package:

```bash
python -m dngine packages install web_dev
```

Run the `Web Scraper` headlessly after the `web_dev` package is installed:

```bash
python -m dngine commands run tool.web_scraper.run --args '{"url": "https://example.com/articles", "item_selector": "article", "title_selector": "h2", "link_selector": "a[href]", "text_selector": "p", "max_pages": 1}'
```

Run a saved workflow:

```bash
python -m dngine workflows run my_workflow
```

## Included Tools

### Shipped System Pages

- Dashboard
- Clip Snip
- Command Center
- Workflow Studio
- About Info
- Dev Lab (`Developer mode`)

### Shipped Core 7

#### Files & Storage

- Hash Checker

#### Office & Docs

- PDF Core Engine
- Document Bridge (`Markdown -> DOCX` and `DOCX -> Markdown`)

#### Network & Security

- Privacy Data Shredder
- System Overview

#### Media & Images

- Image Tagger
- Color Picker

### Signed First-Party Packages

#### Media & Images

- Image Transformer
- SMART Background Remover
- SMART EXIF Editor

#### Files & Storage

- Batch File Renamer
- Deep File Searcher
- Smart File Organizer
- Disk Space Visualizer

#### Office & Docs

- Data Cleaner
- Data Cross Joiner

#### Data & Analysis

- Chart Builder
- Data Link Auditor
- Deep Scan Auditor
- Folder Mapper
- Sequence Auditor

#### Network & Security

- Network Port Scanner
- Wi-Fi Profiles

#### Web Dev

- Code Factory
- Code Exploit Scanner
- Web Scraper

## Tool Notes

The core 8 ship inside the base app. Everything else above is distributed as a signed first-party package that can be installed from `Settings -> Plugins` or the `packages.*` CLI commands.

### Dashboard

- Acts as the app landing page
- Shows a welcome header, greeting, date, usage snapshots, and recent activity
- Includes a workspace pulse panel for output, backups, workflows, shortcuts, and useful next actions

### Clip Snip

- Captures plain text, code, URLs, file lists, rich text / HTML, and images
- Restores entries back to the system clipboard in their original supported format
- Supports labels, categories, pinned snippets, quick history access, persistent local storage, and an integrated background `Clip-Monitor`
- Pinned entries stay above normal history and are not removed when non-pinned history is trimmed
- Supports entry editing, text transforms, merge-and-copy, and sequential paste queue workflows for selected items
- When `Clip-Monitor` is enabled, clipboard capture continues while DNgine is hidden in the tray, and the quick panel stays owned by the main app instead of a second clipboard app instance

### Folder Mapper

- Maps a full folder tree into an Excel workbook with file metadata, paths, permissions, and dates
- Useful as an inventory/export view before file operations or audits

### Deep-Scan Auditor

- Folder mode accepts multiple folders at once
- Folder duplicate matching can use `Name`, `Size`, `Created Date`, and optional `Hash`
- Excel mode accepts multiple workbook files
- Each workbook can define its own one-or-more target column names, comma-separated

### Sequence Auditor

- Audits folder listings or workbook columns for missing numbered items
- Exports a workbook that includes missing entries plus surrounding context rows

### Data-Link Auditor

- Audits filenames referenced in an Excel workbook against one or more source folders
- Can optionally move confirmed matches into a destination structure while exporting missing-value and missing-file reports

### Hash Checker

- Calculates `MD5` and `SHA-256` for a selected file
- Verifies a pasted checksum against the selected file and lets you copy either generated hash back to the clipboard

### Web Scraper

- Distributed through the signed `web_dev` first-party package
- Scrapes public static HTML pages only; it is not intended for login flows or JavaScript-rendered sites
- Uses CSS selectors for items, titles, links, text, and optional pagination
- Shows extracted rows in-app first with table filtering, detail previews, and right-click copy/open/export actions
- Can optionally export visible results as `JSON` or `CSV`

### Code Exploit Scanner

- Scans folders for exposed secrets, risky filenames, and exploit indicators across common text-based source and config files
- Masks matched secrets in previews, flags risky files for manual review, and writes a review report beside the scanned folder when suspicious findings are detected

### System Overview

- Replaces the earlier hardware audit view
- Shows live CPU, memory, and disk visualization plus current runtime and system details

### Wi-Fi Profiles

- Lists saved Wi-Fi profiles and current network information when the platform backend allows it
- Passwords are masked by default and can be revealed or copied on demand

### Color Picker

- Picks colors from anywhere on the screen
- Shows a preview plus `HEX`, `RGB`, and `HSL`
- Uses a virtual multi-screen picker surface so all connected displays can be sampled

### Inspector

- Hidden unless `Developer mode` is enabled
- Lets you inspect live widgets, object names, hierarchy, palette roles, and stylesheet state
- Can temporarily unlock static app text so labels become highlightable and copyable
- While inspect mode is active, use right-click navigation to move around the app and left-click to select the target widget
- Useful for debugging layout, theming, and shell paint issues without external Qt tooling

## Shell Navigation

- `Ctrl+K` focuses the global top-bar search
- Search matches app pages plus key `Command Center` sections such as `Plugins`, `Quick Access`, and `Shortcuts`
- Results appear live in a dropdown, follow the current RTL/LTR direction, and open directly into the selected page or section
- Standard page loading, theme refresh, and language refresh work through the same shell-owned spinner/progress system

## Architecture

### Package Layout

```text
dngine/
  __main__.py
  app.py
  main.py
  assets/
  core/
  i18n/
  plugins/
fp_plugins/
tools/
build_linux.sh
build_macos.sh
build_windows.sh
build_windows.bat
dngine.spec
```

### Runtime Layout

- [dngine](/home/debeski/depy/tools/dngine/dngine) contains code, assets, built-in plugins, and locale files.
- [fp_plugins](/home/debeski/Desktop/depy/tools/DNgine/fp_plugins) contains the source for signed first-party plugin packages that are built into downloadable archives.
- Runtime state lives in a per-user storage root, not in the project directory.
- Windows uses `%LOCALAPPDATA%\\DNgine`
- macOS uses `~/Library/Application Support/DNgine`
- Linux uses `$XDG_DATA_HOME/dngine` or `~/.local/share/dngine`
- Inside that root, `data/` contains config, database, plugin state, workflows, custom plugins, installed signed packages, the package catalog cache, and package download cache.
- Installed signed first-party packages live under `<storage_root>/data/signed_plugins/`.
- Cached package catalog data lives under `<storage_root>/data/package_catalog/`.
- Cached package archives live under `<storage_root>/data/package_cache/`.
- Inside that root, `output/` is the default export/output folder for generated files.
- `DNGINE_HOME` can override the storage root for development or portable testing.
- `MICRO_TOOLKIT_HOME` is still accepted as a backward-compatible override.
- Existing `DNgine` / `dngine` storage folders are migrated forward on first run when possible.

### Plugin Engine

The plugin engine is built around:

- AST-based metadata discovery
- lazy module import
- lazy widget creation
- plugin-local `en/ar` sidecar locales
- plugin-local sidecar dependencies
- optional headless command registration
- optional elevated capability registration
- signed first-party package installation and verification
- import/export of custom plugin bundles
- manifest-verified builtin plugin discovery in packaged builds
- signed-plugin verification plus custom plugin trust review and quarantine state

That means a plugin can contribute:

- metadata
- a `QWidget` page
- locale bundles
- CLI/workflow commands
- narrow elevated capabilities when truly needed
- independent dependencies

without changing the core shell.

In packaged `onedir` builds, bundled first-party plugins are verified against `builtin_plugin_manifest.json` before they are treated as builtin. Extra or modified files dropped into the shipped plugin folder do not automatically become first-class app plugins.

### Plugin Safety Model

Builtin, signed, and custom plugins do not all follow the same trust path.

DNgine now applies several safety measures:

- packaged builtin plugins are identified through a build-generated manifest
- signed first-party packages must pass signature verification against the bundled signer trust store
- signed packages are trusted by default after verification but still participate in failure quarantine
- imported plugins start disabled and untrusted
- manually dropped custom plugins are still discovered as untrusted
- custom plugins stay out of the sidebar until explicitly trusted
- static safety scans inspect plugin Python files for risky imports and calls
- critical-risk imports are blocked during import and remain quarantined
- repeated load or command-registration failures cause automatic quarantine
- trust, risk, failure, and quarantine state are visible in `Settings -> Plugins`

Important limit:

- this is not a full OS sandbox

Trusted plugins still run Python code in the app process. The review and quarantine system reduces accidental breakage and raises the bar against obviously unsafe plugins, but users should still only install plugins they trust.

### Plugin Origins

DNgine is designed around three plugin origins:

- `builtin`: shipped with the app and verified by the build manifest
- `signed`: signer-verified first-party or third-party package installs
- `custom`: local or imported plugins that go through review and trust controls

Current shipping model:

- `builtin` contains system pages plus the curated core 8 tool set
- `signed` carries the rest of the first-party tools as installable packages grouped by category
- `custom` remains the flexible local/imported path for development and user-created extensions

The first-party package groups are also the in-app category labels for non-system tools:

- `Files & Storage`
- `Office & Docs`
- `Network & Security`
- `Web Dev`
- `Media & Images`
- `Data & Analysis`

## Multilingual and RTL Support

The shell supports English and Arabic, and plugins can ship their own translations alongside the plugin file.

Example:

```text
my_plugin.py
my_plugin.en.json
my_plugin.ar.json
```

The shell handles:

- current language
- layout direction
- RTL-aware app chrome
- plugin metadata localization
- shared translator helpers through `bind_tr(...)`, `tr(...)`, and `safe_tr(...)`
- global Cairo-based font stack with fallbacks

Recommended widget usage:

```python
from dngine.core.plugin_api import bind_tr

tr = bind_tr(services, "my_plugin")
title = QLabel(tr("ui.title", "My Plugin"))
```

Recommended helper/task usage:

```python
from dngine.core.plugin_api import safe_tr, tr

context.log(tr(services, "my_plugin", "log.start", "Starting task..."))
message = safe_tr(translate, "error.failed", "Task failed.")
```

## Performance Model

DNgine is designed to stay responsive:

- plugin metadata is discovered before modules are imported
- pages are only created when opened
- opened pages stay cached
- heavy work is expected to run in background tasks
- headless command functions are separated from UI code where possible

## Elevated Access Model

DNgine now has two separate elevated helpers, each with a narrow purpose:

### 1. Hotkey Helper

The hotkey helper exists only for global shortcut capture on Linux sessions where the keyboard backend requires elevated input access. It is intentionally narrow and should not be reused for general elevated work.

### 2. Elevated Broker

The elevated broker is the general capability-based elevation layer for future tool/plugin needs.

Important design rules:

- the main app stays non-elevated
- plugins do not get arbitrary root/admin command execution
- elevated actions must be registered as named capabilities
- each capability should do one narrow job
- capabilities should accept structured payloads and return structured results

Examples of good broker capability shapes:

- `filesystem.stat_path`
- `filesystem.secure_delete`
- `system.read_protected_info`
- `network.bind_elevated_port`

Examples of bad designs to avoid:

- “run any shell command”
- “execute this Python string”
- one giant admin capability that does many unrelated things

### Broker Namespace Commands

List capabilities:

```bash
python -m dngine broker elevated capabilities
```

Start the broker explicitly:

```bash
python -m dngine broker elevated start
```

Run one capability:

```bash
python -m dngine broker elevated run system.identity --payload '{}'
```

Stop the broker:

```bash
python -m dngine broker elevated stop
```

## First-Party Package Management

Signed first-party packages can be managed from `Settings -> Plugins` or from the CLI.

Available package commands:

- `python -m dngine packages list`
- `python -m dngine packages refresh`
- `python -m dngine packages install <package_id>`
- `python -m dngine packages remove <package_id>`
- `python -m dngine packages updates`

Manual `.zip` import in `Settings -> Plugins` now recognizes signed first-party archives and installs them into the signed package area instead of treating them as custom plugins.

## Custom Plugin Development

This section is the main guide for writing DNgine plugins.

### Where Custom Plugins Live

You have three supported options:

1. Import a plugin package archive through `Settings -> Plugins`
2. Import a loose plugin file or plugin folder through `Settings -> Plugins` for development workflows
3. Place them inside the writable custom plugin area under:

```text
<storage_root>/data/plugins/<your_plugin_package>/
```

Example:

```text
<storage_root>/data/plugins/my_tools/
  my_plugin.py
  my_plugin.en.json
  my_plugin.ar.json
  helpers.py
```

Recommended sharing path:

- use the zip-based plugin package flow in `Settings -> Plugins`
- keep loose file/folder imports for development and manual testing
- keep manual folder drop-ins for power-user workflows, not casual sharing

### Minimal Plugin Shape

```python
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from dngine.core.plugin_api import QtPlugin


class MyPlugin(QtPlugin):
    plugin_id = "my_plugin"
    name = "My Plugin"
    description = "Example plugin."
    category = "General"
    version = "1.0.0"

    def create_widget(self, services) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("Hello from DNgine"))
        return page
```

### What to Import

Use:

- `from dngine.core.plugin_api import QtPlugin, bind_tr`
- `from dngine.core.plugin_api import tr` for helper/task code that already has `services` and `plugin_id`
- `from dngine.core.plugin_api import safe_tr` when a background/helper path accepts an optional translation callable
- `from dngine.core.page_style import apply_page_chrome` for standard page title/description/card styling
- `from dngine.core.page_style import apply_semantic_class` only for approved special surfaces such as console, preview, chart, or hero variants
- `from dngine.core.command_runtime import HeadlessTaskContext` for headless command work
- `from dngine.core.app_utils import ...` for shared helpers where appropriate
- `services.run_task(...)` for background work with automatic shell progress
- `services.request_elevated(...)` only when a capability-based elevated operation is truly required
- `register_elevated_capabilities(...)` only for narrow, explicit elevated operations
- `allow_name_override` and `allow_icon_override` when the plugin should permit user-side display customization
- `preferred_icon` when the plugin wants a default app icon without shipping a custom `.ico`

Avoid:

- imports from non-existent folders
- top-level heavy imports if they are only needed when the user actually runs the tool
- defining per-plugin `_pt` / `_tr` wrappers when `bind_tr(...)`, `tr(...)`, and `safe_tr(...)` already cover page and task translation needs
- raw per-page styling for standard controls when shared page/style helpers already cover the layout
- plugin-local inline progress bars for ordinary tasks; the shell owns routine loading/progress affordances
- doing large file/network/CPU work directly on the UI thread

### Zero-Boilerplate Page Pattern

For a standard content page, the preferred pattern is:

```python
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from dngine.core.page_style import apply_page_chrome
from dngine.core.plugin_api import QtPlugin, bind_tr


class MyPlugin(QtPlugin):
    plugin_id = "my_plugin"
    name = "My Plugin"
    description = "Example plugin page."
    category = "General"

    def create_widget(self, services) -> QWidget:
        tr = bind_tr(services, self.plugin_id)
        palette = services.theme_manager.current_palette()

        page = QWidget()
        layout = QVBoxLayout(page)

        title_label = QLabel(tr("title", "My Plugin"))
        description_label = QLabel(tr("description", "Example plugin page."))
        card = QFrame()

        layout.addWidget(title_label)
        layout.addWidget(description_label)
        layout.addWidget(card)

        apply_page_chrome(
            palette,
            title_label=title_label,
            description_label=description_label,
            cards=(card,),
        )
        return page
```

Standard controls inside that card inherit the shared global control styling automatically. Reserve `apply_semantic_class(...)` for genuinely special surfaces such as console outputs, previews, charts, or hero-style cards.

### How Custom Plugin Review Works

When a plugin package, loose plugin file, or plugin folder is imported through `Settings -> Plugins`, or even when it is copied manually into `<storage_root>/data/plugins`, the app treats it as a custom plugin with review state.

This review flow does not apply to packaged first-party plugins that were verified through the builtin manifest during app startup.

Default behavior:

- `trusted = false`
- `enabled = false`
- `hidden = false`
- the plugin is not loaded into the main shell

Review flow:

1. Open `Settings -> Plugins`
2. Inspect the plugin `Risk` and `Status` columns
3. Review the plugin code and sidecar files yourself
4. Mark the plugin as `Trusted` only if you accept running that code
5. Enable it if you want it available in the main app

Risk behavior:

- `low`: no obvious risky patterns were found by the static scan
- `medium` or `high`: the app asks for confirmation before trust is applied
- `critical`: import is blocked or the plugin remains quarantined and disabled
- direct elevation patterns such as `sudo`, `pkexec`, `runas`, or similar self-elevation code are treated as high risk
- the broker-based `register_elevated_capabilities(...)` path is the approved exception and is not itself a risk marker

Current protective scope:

- static AST scanning
- explicit trust review
- disabled-by-default custom imports
- load-time failure containment
- automatic quarantine after repeated failures

Current non-goals:

- full sandboxing
- arbitrary-code trust bypass
- generic elevated execution

### Translations

Preferred pattern:

```text
my_plugin.py
my_plugin.en.json
my_plugin.ar.json
```

Example `my_plugin.en.json`:

```json
{
  "plugin.name": "My Plugin",
  "plugin.description": "Example plugin.",
  "plugin.category": "General",
  "ui.title": "My Plugin",
  "ui.run": "Run"
}
```

Example usage inside the widget:

```python
from dngine.core.plugin_api import bind_tr

tr = bind_tr(services, "my_plugin")
title = QLabel(tr("ui.title", "My Plugin"))
```

You can also keep a tiny inline `translations = {...}` fallback in the plugin class, but sidecar files are the preferred pattern.

### Dependency Sidecars

Custom plugins can optionally declare extra Python package requirements with a dependency sidecar next to the plugin file.

Preferred naming:

```text
my_plugin.py
my_plugin.deps
```

Accepted fallback:

```text
my_plugin.py
my_plugin.deps.txt
```

The dependency file follows normal `requirements.txt` style lines.

Example:

```text
requests==2.32.3
beautifulsoup4>=4.12
```

Behavior:

- dependency sidecars are preserved in plugin package export/import
- imported custom plugins still start disabled and untrusted
- once reviewed and trusted, use `Settings -> Plugins` and right-click the plugin row to:
- `Install dependencies`
- `Repair dependencies`
- `Clear dependencies`
- dependencies install into app-managed writable storage under the per-user runtime root, not into the bundled app folder

### Display Name and Icon Customization

Plugins can opt into user-side display customization from `Settings -> Plugins`.

Available metadata flags:

- `allow_name_override = True`
- `allow_icon_override = True`
- `preferred_icon = "analytics"`

Example:

```python
class MyPlugin(QtPlugin):
    plugin_id = "my_plugin"
    name = "My Plugin"
    description = "Example plugin."
    category = "General"
    allow_name_override = True
    allow_icon_override = True
    preferred_icon = "search"
```

How it works:

- if allowed, the user can override the display name without changing the plugin code
- if allowed, the user can choose an icon from the app icon library
- if no override is set, the shell falls back to plugin-provided icons or Qt defaults
- if a plugin sets either flag to `False`, the UI keeps that aspect locked

Current icon sources are used in this order:

1. user override from settings
2. sidecar plugin icon such as `my_plugin.ico` or `plugin.ico`
3. plugin `preferred_icon`
4. shell fallback icon by tool/category

### Headless Commands

If your tool should work in workflows and CLI, register commands:

```python
from dngine.core.command_runtime import HeadlessTaskContext


def run_my_task(context, source_path: str):
    context.log(f"Processing {source_path}")
    context.progress(0.5)
    return {"source_path": source_path, "ok": True}


class MyPlugin(QtPlugin):
    plugin_id = "my_plugin"
    name = "My Plugin"

    def register_commands(self, registry, services) -> None:
        registry.register(
            "tool.my_plugin.run",
            "Run My Plugin",
            "Run the plugin headlessly.",
            lambda source_path: run_my_task(
                HeadlessTaskContext(services, command_id="tool.my_plugin.run"),
                source_path,
            ),
        )
```

Guidance:

- keep the command function separate from widget code
- accept structured keyword arguments
- return structured dict/list/scalar results
- make the command usable without GUI state

### Background Work

If the plugin has a GUI and the task is expensive, use `services.run_task(...)`:

```python
self.services.run_task(
    lambda context: run_my_task(context, file_path),
    on_result=self._handle_result,
    on_error=self._handle_error,
    on_finished=self._finish_run,
)
```

Notes:

- call `context.progress(...)` inside the worker when you have real measurable progress
- the shared status-bar progress bar is updated automatically for ordinary plugin tasks
- the top-bar spinner and busy cursor remain shell-owned, so routine plugins usually do not need inline progress widgets
- `on_progress` is still available when a page truly needs extra local behavior in addition to the shared shell progress

### Elevated Broker Capabilities

If a plugin really needs elevated access, do not shell out to `sudo`, `pkexec`, or platform elevation tools directly from the plugin page.

Instead:

1. Register a narrow capability
2. Request it through `services.request_elevated(...)`

Example capability registration:

```python
from pathlib import Path


def stat_sensitive_path(context, payload: dict[str, object]):
    target = Path(str(payload["path"])).expanduser().resolve()
    context.log(f"Checking {target}")
    stat_result = target.stat()
    return {"path": str(target), "size": stat_result.st_size}


class MyPlugin(QtPlugin):
    plugin_id = "my_plugin"
    name = "My Plugin"

    def register_elevated_capabilities(self, registry, runtime) -> None:
        registry.register(
            "my_plugin.stat_sensitive_path",
            "Stat Sensitive Path",
            "Return metadata for a path that may require elevated access.",
            stat_sensitive_path,
            provider=self.plugin_id,
        )
```

Example usage from the normal app process:

```python
result = services.request_elevated(
    "my_plugin.stat_sensitive_path",
    {"path": "/some/protected/location"},
)
```

Broker guidance:

- keep handlers deterministic and narrow
- accept JSON-serializable payloads
- return JSON-serializable results
- keep handlers separate from Qt widgets
- avoid generic command execution capabilities
- avoid mixing many unrelated actions into one capability

### What to Avoid

Avoid these patterns in plugins:

- heavy imports at module top level unless they are truly cheap
- storing mutable runtime data beside the plugin code
- building giant all-in-one widget classes with task logic embedded everywhere
- hardcoding translated strings into the widget when plugin locale files are available
- blocking the UI thread with file scans, pandas work, image processing, or network operations
- using the hotkey helper for anything except global hotkeys
- treating the elevated broker like a generic admin shell

### Recommended Plugin Structure

For anything beyond a tiny tool, use:

```text
<storage_root>/data/plugins/my_tools/
  my_plugin.py
  my_plugin.en.json
  my_plugin.ar.json
  my_plugin_helpers.py
```

Recommended split:

- plugin class for metadata and widget creation
- helper functions for data processing
- command functions for workflows/CLI
- elevated capability handlers only when absolutely required

## Build and Packaging

DNgine uses `PyInstaller` in `onedir` mode.

The build scripts regenerate the builtin plugin manifest before packaging so shipped first-party plugins can be verified at runtime in packaged builds.

Why `onedir`:

- better fit for Qt applications
- more reliable than `onefile`
- easier data/plugin packaging
- easier debugging and post-build inspection

### Linux

```bash
./build_linux.sh
```

Outputs:

```text
dist/dngine/dngine
dist/dngine_<version>_<arch>.deb
```

### macOS

```bash
./build_macos.sh
```

Launcher:

```text
dist/DNgine.app
```

### Windows Native

Run on Windows:

```bat
build_windows.bat
```

Launcher:

```text
dist\dngine\dngine.exe
```

### Windows Cross-Build from Linux

Optional Docker-based build:

```bash
./build_windows.sh
```

This is convenient, but native Windows builds are still the more reliable option for final release packaging.

## Product Goals

DNgine is meant to feel:

- fast enough to keep open all day
- light enough to revisit often
- native enough to not feel like a web wrapper
- practical enough to help with everyday office and home workflows

It is not a monolithic enterprise suite. It is a personal productivity and utility companion designed to stay useful, responsive, and extensible.

## Version History

Version history now lives in [CHANGELOG.md](./CHANGELOG.md).
