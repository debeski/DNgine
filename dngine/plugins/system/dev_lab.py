from __future__ import annotations

import json
import time

from dngine.sdk import (
    Action,
    DeclarativePlugin,
    InfoCard,
    Row,
    TextPanel,
    TimerTask,
    Toggle,
    bind_tr,
    copy_to_clipboard,
)


def _snapshot_json(snapshot: dict[str, object]) -> str:
    if not snapshot:
        return ""
    return json.dumps(snapshot, indent=2, ensure_ascii=False)


def _bool_text(tr, value: object) -> str:
    return tr("bool.yes", "Yes") if bool(value) else tr("bool.no", "No")


def _status_rows(runtime, *, enabled: bool, inspecting: bool, text_unlock: bool) -> list[tuple[str, object]]:
    tr = runtime.tr
    if not enabled:
        state_text = tr("status.locked", "Developer mode is off. Enable it from Command Center to use Dev Lab.")
    elif inspecting:
        state_text = tr(
            "status.live",
            "Inspect mode is active. Hover the app, left-click to capture a widget, and use right-click navigation if you need to move to another page first. Press Esc to cancel.",
        )
    elif text_unlock:
        state_text = tr(
            "status.text_unlock",
            "Inspector text unlock is active. Static app text can now be highlighted and copied where supported.",
        )
    else:
        state_text = tr("status.ready", "Inspector is ready. Start inspect mode to capture a widget.")

    rows: list[tuple[str, object]] = [
        (tr("status.access", "Developer Mode"), _bool_text(tr, enabled)),
        (tr("status.inspecting", "Inspecting"), _bool_text(tr, inspecting)),
        (tr("status.unlock", "Text Unlock"), _bool_text(tr, text_unlock)),
        (tr("status.message", "Status"), state_text),
    ]
    if float(runtime.value("copy_feedback_until", 0.0) or 0.0) > time.monotonic():
        rows.append((tr("status.clipboard", "Clipboard"), tr("copy.done", "Copied")))
    return rows


def _selection_rows(runtime, snapshot: dict[str, object]) -> list[tuple[str, object]]:
    tr = runtime.tr
    if not snapshot:
        return [
            (tr("selection.state", "Selection"), tr("summary.empty", "No widget selected yet.")),
        ]
    return [
        (tr("selection.class_name", "Class"), str(snapshot.get("class_name") or "QWidget")),
        (tr("selection.object_name", "Object Name"), str(snapshot.get("object_name") or "--")),
        (tr("selection.window_title", "Window Title"), str(snapshot.get("window_title") or "--")),
        (tr("selection.geometry", "Geometry"), str(snapshot.get("geometry") or "--")),
        (tr("selection.children", "Child Count"), str(snapshot.get("child_count") or 0)),
        (tr("selection.visible", "Visible"), _bool_text(tr, snapshot.get("visible"))),
        (tr("selection.enabled", "Enabled"), _bool_text(tr, snapshot.get("enabled"))),
    ]


def _sync_dev_lab(runtime) -> None:
    inspector = runtime.services.ui_inspector
    enabled = bool(runtime.services.developer_mode_enabled())
    inspecting = bool(inspector.inspect_mode())
    text_unlock = bool(inspector.text_unlock_enabled())
    snapshot = dict(inspector.last_snapshot() or {})
    chain_text = "\n".join(str(item) for item in (snapshot.get("parent_chain") or ()))
    details_text = _snapshot_json(snapshot)

    runtime.set_value("developer_enabled", enabled)
    runtime.set_value("inspect_mode", inspecting)
    runtime.set_value("snapshot_json", details_text)
    runtime.set_field_value("text_unlock", text_unlock, trigger=False)
    runtime.set_field_value("status_card", _status_rows(runtime, enabled=enabled, inspecting=inspecting, text_unlock=text_unlock), trigger=False)
    runtime.set_field_value("selection_card", _selection_rows(runtime, snapshot), trigger=False)
    runtime.set_field_value("parent_chain_panel", chain_text, trigger=False)
    runtime.set_field_value("details_panel", details_text, trigger=False)


def _set_text_unlock(runtime, _changed_key: str) -> None:
    if not runtime.services.developer_mode_enabled():
        return
    runtime.services.ui_inspector.set_text_unlock_enabled(bool(runtime.value("text_unlock", False)))


def _start_inspecting(runtime) -> None:
    if runtime.services.developer_mode_enabled():
        runtime.services.ui_inspector.set_inspect_mode(True)
        _sync_dev_lab(runtime)


def _stop_inspecting(runtime) -> None:
    runtime.services.ui_inspector.set_inspect_mode(False)
    _sync_dev_lab(runtime)


def _copy_snapshot(runtime) -> None:
    payload = str(runtime.value("snapshot_json", "") or "").strip()
    if not payload:
        return
    copy_to_clipboard(payload)
    runtime.set_value("copy_feedback_until", time.monotonic() + 1.4)
    _sync_dev_lab(runtime)


class DevLabPlugin(DeclarativePlugin):
    plugin_id = "dev_lab"
    name = "Dev Lab"
    description = "Developer inspection tools for exploring live Qt widgets, layout structure, and styles."
    category = ""
    standalone = True
    allow_name_override = False
    allow_icon_override = False
    preferred_icon = "inspect"

    def declare_page(self, services):
        tr = bind_tr(services, self.plugin_id)
        return {
            "text_unlock": Toggle(
                tr("text_unlock", "Unlock static text selection across the app"),
                default=False,
                on_change=_set_text_unlock,
                enabled_when=lambda runtime: bool(runtime.value("developer_enabled", runtime.services.developer_mode_enabled())),
            ),
            "status_row": Row(
                fields={
                    "status_card": InfoCard(title=tr("tools.title", "Tools")),
                    "selection_card": InfoCard(title=tr("details.title", "Widget Details")),
                }
            ),
            "inspect_start": Action(
                tr("inspect.start", "Start inspecting"),
                on_trigger=_start_inspecting,
                enabled_when=lambda runtime: bool(runtime.value("developer_enabled", runtime.services.developer_mode_enabled())),
                visible_when=lambda runtime: not bool(runtime.value("inspect_mode", False)),
            ),
            "inspect_stop": Action(
                tr("inspect.stop", "Stop inspecting"),
                on_trigger=_stop_inspecting,
                enabled_when=lambda runtime: bool(runtime.value("developer_enabled", runtime.services.developer_mode_enabled())),
                visible_when=lambda runtime: bool(runtime.value("inspect_mode", False)),
            ),
            "copy_snapshot": Action(
                tr("copy", "Copy snapshot"),
                kind="secondary",
                on_trigger=_copy_snapshot,
                enabled_when=lambda runtime: bool(str(runtime.value("snapshot_json", "") or "").strip()),
            ),
            "sync_state": Action(
                "sync_state",
                kind="secondary",
                on_trigger=_sync_dev_lab,
                auto_run=True,
                visible_when=lambda runtime: False,
            ),
            "details_row": Row(
                fields={
                    "parent_chain_panel": TextPanel(
                        title=tr("path.title", "Parent Chain"),
                        placeholder=tr("path.placeholder", "Parent widgets will appear here."),
                    ),
                    "details_panel": TextPanel(
                        title=tr("details.title", "Widget Details"),
                        placeholder=tr("details.placeholder", "Widget snapshot JSON will appear here."),
                    ),
                }
            ),
            "poller": TimerTask(interval_ms=250, on_tick=_sync_dev_lab),
        }
