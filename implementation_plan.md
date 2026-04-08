# Project-R: DNgine Rebuild — Implementation Plan

## Goal

Rebuild DNgine from scratch as a **framework-first strict plugin engine** where:
- The **SDK owns everything**: layout, rendering, theming, translation, direction, state, tasks, lifecycle
- Plugins **only provide**: their business logic (workers, preview builders) + a **dict mapping** to predefined SDK components
- A plugin's UI is buildable by **a 10-year-old**: declare a dict, write your function, done
- The engine ships **empty** except for system plugins (Dashboard, Settings, About)
- All tool plugins (image tagger, pdf suite, etc.) become downloadable packages — not bundled

---

## Architecture Overview

```
project-r/
├── dngine/
│   ├── __init__.py              # Version only
│   ├── __main__.py              # python -m dngine
│   ├── app.py                   # QApplication bootstrap
│   │
│   ├── sdk/                     # ★ THE public surface — this IS the framework
│   │   ├── __init__.py          # All public exports
│   │   ├── plugin.py            # Plugin base class (one class, that's it)
│   │   ├── components.py        # Text, Choice, Toggle, Numeric, Path,
│   │   │                        # FileList, Table, Preview, Action, Output,
│   │   │                        # Section, Separator, Group
│   │   ├── renderer.py          # Dict → Qt widget tree (auto-layout engine)
│   │   ├── runtime.py           # Per-page state machine + auto-wiring
│   │   ├── theme.py             # Palette system (dark/light × accent colors)
│   │   ├── i18n.py              # Translation + direction helpers
│   │   ├── tasks.py             # Background task runner
│   │   ├── commands.py          # CLI/headless command registration
│   │   └── widgets.py           # Internal Qt widget implementations
│   │                            # (not exposed to plugin authors)
│   │
│   ├── engine/                  # Internal infrastructure
│   │   ├── __init__.py
│   │   ├── shell.py             # Main window (sidebar + content + status)
│   │   ├── sidebar.py           # Navigation sidebar
│   │   ├── loader.py            # Plugin discovery + loading
│   │   ├── services.py          # Service container (lean)
│   │   └── config.py            # App config (JSON)
│   │
│   ├── system/                  # Built-in system plugins
│   │   ├── __init__.py
│   │   ├── dashboard.py         # Home page
│   │   ├── settings.py          # Settings page
│   │   └── about.py             # About page
│   │
│   ├── i18n/                    # Engine-level translations
│   │   ├── en.json
│   │   └── ar.json
│   │
│   └── assets/
│       └── fonts/               # Bundled fonts
│
├── plugins/                     # External plugin install directory (empty)
├── tests/
│   ├── test_sdk.py              # SDK component + rendering tests
│   └── test_engine.py           # Engine boot + plugin loading tests
├── requirements.txt
├── pyproject.toml
└── README.md
```

---

## SDK Component API — The Core Design

### What A Plugin Looks Like

```python
from dngine.sdk import Plugin, Text, Choice, FileList, Preview, Action, Output

def tag_images(ctx, inputs):
    """The actual work — this is the plugin's entire reason to exist."""
    for i, f in enumerate(inputs["files"]):
        ctx.progress((i + 1) / len(inputs["files"]))
        ctx.log(f"Tagging {f}...")
        # ... real image tagging logic ...
    return f"Tagged {len(inputs['files'])} images"

def preview_tag(inputs):
    """Build a preview pixmap from current inputs."""
    path = inputs.get("_selected_file")
    if not path:
        return None
    # ... render tagged preview ...
    return pixmap

class ImageTagger(Plugin):
    id = "image_tagger"
    name = "Image Tagger"
    icon = "tag"
    category = "Media & Images"

    page = {
        "name":        Text("Tag Name", required=True),
        "date_mode":   Choice("Date Source", options=["taken", "today", "custom"]),
        "custom_date": Text("Custom Date", visible_when={"date_mode": "custom"}),
        "files":       FileList(extensions=[".png", ".jpg", ".jpeg", ".bmp", ".webp"]),
        "preview":     Preview(builder=preview_tag),
        "run":         Action("Run Tagger", worker=tag_images, target="output_dir"),
        "output":      Output(),
    }
```

**That's the entire plugin.** 30 lines including the worker. No IDs, no specs, no sections, no bindings, no state declarations.

### Component Catalog

Every component the SDK offers:

| Component | Purpose | Key Parameters |
|---|---|---|
| `Text` | Text input | `label`, `placeholder`, `default`, `required`, `max_length`, `read_only`, `visible_when`, `enabled_when` |
| `MultiLine` | Multiline text area | Same as Text + `rows` |
| `Choice` | Dropdown select | `label`, `options` (list or dict), `default` |
| `Toggle` | Checkbox | `label`, `default=False` |
| `Numeric` | Number input | `label`, `min`, `max`, `step`, `default`, `decimals` |
| `Path` | File/folder path input | `label`, `mode` (file/folder/any), `extensions`, `placeholder` |
| `FileList` | Multi-file input with D&D | `extensions`, `add_label`, `clear_label`, `remove_label` |
| `Table` | Data table display | `columns`, `editable`, `selectable` |
| `Preview` | Image/content preview | `builder(inputs)→pixmap`, `empty_text` |
| `Action` | Button that runs a task | `label`, `worker`, `validate`, `target` (ask for output dir/file), `kind` (primary/secondary) |
| `Output` | Summary + output text | `ready_text`, `placeholder` |
| `Separator` | Visual separator | — |
| `Group` | Group components under a label | `label`, dict of components |

### Auto-Layout Algorithm

The renderer scans the page dict in order and groups components automatically:

1. **Consecutive inputs** (Text, Choice, Toggle, Numeric, Path) → grouped into a **settings card** (QFrame + QFormLayout)
2. **FileList** → rendered as a full-width droppable list with auto-generated Add/Clear buttons
3. **FileList followed by Preview** → auto-split horizontally (QSplitter)
4. **FileList followed by Table** → auto-split horizontally
5. **Preview alone** → centered preview pane
6. **Action** → button row
7. **Output** → summary label + output text area in a card
8. **Group** → sub-card with its own label and nested layout
9. **Separator** → horizontal line

### Auto-Wiring

The engine automatically handles:

| Concern | How |
|---|---|
| **State** | Every dict key becomes a state entry. Inputs sync bidirectionally. |
| **Visibility** | `visible_when={"field": "value"}` → auto-rule. Lambda for complex. |
| **Enable** | `enabled_when={"field": True}` → auto-rule. |
| **File list** | Add/Clear/Remove/Drag-drop/Extension filter — all automatic. |
| **Preview** | `builder(inputs)` called on any input change. Debounced. |
| **Action** | Validates required fields → shows target dialog → runs worker on thread → pipes result to Output. |
| **Theme** | All widgets use palette. Reapplies on change. |
| **Direction** | RTL/LTR auto-applied. Reapplies on language change. |
| **Translation** | Plugin provides sidecar JSONs. Labels auto-translated. |

### The `inputs` Dict (Runtime View)

Workers and preview builders receive a flat dict:

```python
{
    "name": "My Tag",              # from Text
    "date_mode": "custom",         # from Choice
    "custom_date": "2026-01-01",   # from Text
    "files": ["/path/a.png", ...], # from FileList
    "_selected_file": "/path/a.png",  # auto-added: currently selected file in FileList
    "_selected_row": 0,            # auto-added: selected row index
}
```

Special `_` prefixed keys are auto-injected by the runtime for convenience.

### The `ctx` Object (Task Context)

Workers receive a context for progress/logging:

```python
ctx.progress(0.5)         # 0.0–1.0, drives shell progress bar
ctx.log("Processing...")  # goes to activity log
ctx.cancelled             # bool, check for cancellation
```

---

## Engine Infrastructure

### Shell (`engine/shell.py`)

Minimal, clean main window:

```
┌──────────┬──────────────────────────────────────────┐
│          │ [Search]              [⚙] [❓]           │
│ Sidebar  ├──────────────────────────────────────────┤
│          │ Plugin Name                              │
│ Dashboard│ Plugin description                       │
│ ─────────├──────────────────────────────────────────┤
│ Tools    │                                          │
│  (empty) │   Plugin Page Content                    │
│ ─────────│   (rendered from plugin.page dict)       │
│ System   │                                          │
│  Settings│                                          │
│  About   │                                          │
│          ├──────────────────────────────────────────┤
│          │ [status message]               [▊▊▊▊░░] │
└──────────┴──────────────────────────────────────────┘
```

- **Sidebar**: tree with groups (System, installed plugin categories)
- **Header**: plugin name + description (auto-populated from plugin metadata)
- **Content**: QStackedWidget with rendered plugin pages
- **Status bar**: status text + progress bar + activity log toggle

### Services (`engine/services.py`)

Lean container — only what's needed:

```python
class Services:
    config: AppConfig
    theme: ThemeManager
    i18n: TranslationManager
    logger: AppLogger
    thread_pool: QThreadPool
    plugins: PluginLoader
```

No clipboard managers, no elevated brokers, no backup managers, no hotkey helpers, no tray managers, no workflow managers. Those are plugin concerns if needed later.

### Config (`engine/config.py`)

Simple JSON config:

```python
class AppConfig:
    def get(key, default=None) -> object
    def set(key, value) -> None
    def save() -> None
```

Stores: language, theme color, dark mode, font, plugin states, window geometry.

### Plugin Loader (`engine/loader.py`)

Discovers plugins from:
1. `dngine/system/` — system plugins (always loaded)
2. `plugins/` — installed external plugins

Each plugin is a Python module with a class that extends `Plugin`. Discovery is by scanning for `Plugin` subclasses.

---

## System Plugins

### Dashboard (`system/dashboard.py`)

Uses `SystemPlugin` (extends Plugin with custom page building for complex layouts):
- Welcome message
- Installed plugin list with categories
- Recent activity (last 10 runs)

### Settings (`system/settings.py`)

System plugin with custom page:
- Theme color picker (5 accent colors)
- Dark/Light mode toggle
- Language selector (English/Arabic)
- Font family selector
- Output directory path

### About (`system/about.py`)

System plugin:
- App name + version
- Credits
- License

---

## Theme System (`sdk/theme.py`)

Simplified from current — no qt-material dependency, pure palette + stylesheet:

```python
@dataclass
class Palette:
    mode: str       # "dark" | "light"
    bg: str         # window background
    surface: str    # card background
    input_bg: str   # input background
    border: str     # borders
    text: str       # primary text
    muted: str      # secondary text
    accent: str     # accent color
    accent_hover: str
    danger: str
```

- 5 accent color families (same as current: pink, blue, orange, green, red)
- Dark/light variants auto-computed
- One stylesheet generation function that styles ALL widgets
- No per-widget manual styling. Ever.

---

## Translation System (`sdk/i18n.py`)

Carried over (it's already clean):
- Engine translations in `dngine/i18n/{lang}.json`
- Plugin translations in sidecar `{plugin_file}.{lang}.json`
- `tr(key, default, **kwargs)` helper
- RTL/LTR auto-direction
- Language change signal → re-renders all labels

---

## User Review Required

> [!IMPORTANT]
> **Scope Reduction**: The new engine deliberately drops these features from the current DNgine. They can be added back as plugins or engine extensions later:
> - Clipboard manager (Clip Snip)
> - Workflow studio
> - Command center (complex search/command palette)
> - System tray + clip monitor
> - Elevated broker
> - Backup manager
> - Plugin signing/security
> - Plugin packaging/import/export
> - Dev lab / UI inspector
> - Keyboard shortcuts manager
> - Hotkey helper
> - Embedded terminal

> [!WARNING]
> **qt-material removal**: The current engine uses `qt-material` for base styling. The new engine will use **pure Fusion style + custom stylesheet** from palette values. This gives us full control and eliminates the dependency, but the visual starting point will be different. The end result will look polished but not identical to the current material look.

> [!IMPORTANT]
> **System plugins**: Dashboard, Settings, and About will use `SystemPlugin` which allows custom widget building (similar to current `AdvancedPagePlugin`). They're shell-owned pages that need more layout freedom than a standard dict mapping provides.

---

## Open Questions

1. **Plugin `id`**: Should it be the class attribute `id = "image_tagger"` or derived from the module/file name? Class attribute is more explicit.

2. **First run**: What should the Dashboard show when no plugins are installed? Just a welcome message + pointer to where to get plugins?

3. **Plugin install mechanism**: For the initial build, should external plugins be simple Python files dropped into `plugins/`? Or do you want the package/zip install flow from day one?

4. **Font bundling**: Carry over Amiri + Cairo + DejaVu, or start with system fonts only?

5. **Any system plugin beyond Dashboard/Settings/About** that you want in the initial build?

---

## Execution Plan

### Phase 1: Skeleton + Theme + Translation (~Foundation)
- Create `project-r/` directory structure
- `pyproject.toml`, `requirements.txt` (PySide6 only)
- `dngine/__init__.py` (version), `__main__.py`, `app.py`
- `sdk/theme.py` — palette + stylesheet generation
- `sdk/i18n.py` — translation manager + direction
- `engine/config.py` — JSON config
- `engine/services.py` — lean service container
- Engine translations (`i18n/en.json`, `i18n/ar.json`)
- **Deliverable**: App boots, shows an empty window with theme applied

### Phase 2: SDK Components + Renderer + Runtime (~The Framework)
- `sdk/components.py` — all component classes
- `sdk/widgets.py` — internal Qt widget implementations
- `sdk/renderer.py` — dict → Qt page (auto-layout)
- `sdk/runtime.py` — state machine + auto-wiring
- `sdk/tasks.py` — background task runner
- `sdk/plugin.py` — Plugin base class
- **Deliverable**: A plugin defined as a dict renders into a working interactive page

### Phase 3: Shell + Navigation + System Plugins (~The App)
- `engine/shell.py` — main window
- `engine/sidebar.py` — navigation
- `engine/loader.py` — plugin discovery
- `system/dashboard.py`, `system/settings.py`, `system/about.py`
- **Deliverable**: Full working app with sidebar, system plugins, theme/language switching

### Phase 4: Polish + Tests (~Ship)
- Tests for SDK rendering, runtime wiring, plugin loading
- README documentation
- Visual polish pass on theming
- **Deliverable**: Verified, documented, ready for plugin development

---

## Verification Plan

### Automated Tests
- `test_sdk.py`: Components render correct widgets, auto-layout groups inputs into cards, FileList+Preview auto-splits, visibility/enable rules fire, Action runs worker, Output receives result
- `test_engine.py`: App boots, plugins discovered from `plugins/`, system plugins load, theme applies, language switches

### Manual Verification
- Boot the app → see Dashboard
- Switch theme colors → all widgets update
- Switch to Arabic → RTL layout + translated labels
- Navigate to Settings → change preferences → persist after restart
- Drop a test plugin file into `plugins/` → appears in sidebar → page renders → action runs worker → output shows result
