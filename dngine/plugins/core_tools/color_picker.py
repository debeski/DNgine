from __future__ import annotations

from dngine.sdk import (
    Action,
    DeclarativePlugin,
    MultiLine,
    Preview,
    Text,
    _pt,
    bind_tr,
    copy_to_clipboard,
    solid_color_preview,
    start_screen_picker,
)


DEFAULT_COLOR_HEX = "#D85A8F"


def _status_text(runtime) -> str:
    status_key = str(runtime.value("status_key", "ready") or "ready")
    defaults = {
        "ready": "Ready to sample a color from the screen.",
        "live": "Pick mode is active. Click any pixel on screen, or press Esc to cancel.",
        "picked": "Color captured successfully.",
        "canceled": "Pick mode canceled.",
    }
    return _pt(runtime.tr, f"status.{status_key}", defaults.get(status_key, defaults["ready"]))


def _apply_sampled_color(runtime, color_info: dict[str, object]) -> None:
    hex_val = str(color_info.get("hex", DEFAULT_COLOR_HEX))
    runtime.set_value("selected_hex", hex_val)
    runtime.set_value("status_key", "picked")
    
    runtime.set_field_value("status_text", _status_text(runtime), trigger=False)
    runtime.set_field_value("hex_value", hex_val, trigger=False)
    runtime.set_field_value("rgb_value", str(color_info.get("rgb", "")), trigger=False)
    runtime.set_field_value("hsl_value", str(color_info.get("hsl", "")), trigger=False)


def _handle_pick_canceled(runtime) -> None:
    runtime.set_value("status_key", "canceled")
    runtime.set_field_value("status_text", _status_text(runtime), trigger=False)


def _start_pick(runtime) -> None:
    session = start_screen_picker(
        runtime.page,
        lambda color_info: _apply_sampled_color(runtime, dict(color_info)),
        lambda: _handle_pick_canceled(runtime)
    )
    if session is None:
        runtime.warn(
            _pt(runtime.tr, "warning.title", "Screen capture unavailable"),
            _pt(runtime.tr, "warning.body", "The screen picker could not start on this session."),
        )
        return
    runtime.set_flag("color_picker_session", session)
    runtime.set_value("status_key", "live")
    runtime.set_field_value("status_text", _status_text(runtime), trigger=False)


def _build_color_preview(runtime):
    color_hex = str(runtime.value("selected_hex", DEFAULT_COLOR_HEX) or DEFAULT_COLOR_HEX)
    return solid_color_preview(color_hex, default_hex=DEFAULT_COLOR_HEX)


def _copy_hex(runtime) -> None:
    copy_to_clipboard(str(runtime.value("selected_hex", DEFAULT_COLOR_HEX) or ""))


class ColorPickerPlugin(DeclarativePlugin):
    plugin_id = "color_picker"
    name = "Color Picker"
    description = "Pick a color from anywhere on the screen and inspect its preview, RGB, HEX, and HSL values."
    category = "Media & Images"
    preferred_icon = "palette"

    def declare_page(self, services):
        tr = bind_tr(services, self.plugin_id)
        return {
            "pick_color": Action(
                tr("pick", "Pick from screen"),
                on_trigger=_start_pick,
            ),
            "copy_hex": Action(
                tr("copy.hex", "Copy HEX"),
                kind="secondary",
                on_trigger=_copy_hex,
            ),
            "preview": Preview(
                builder=_build_color_preview,
                dependencies=("selected_hex",),
                empty_text=tr("status.ready", "Ready to sample a color from the screen."),
                stretch=1,
            ),
            "status_text": MultiLine(
                tr("field.status", "Status"),
                read_only=True,
                default=_pt(tr, "status.ready", "Ready to sample a color from the screen."),
            ),
            "hex_value": Text(
                tr("field.hex", "HEX"),
                read_only=True,
                default=DEFAULT_COLOR_HEX,
            ),
            "rgb_value": Text(
                tr("field.rgb", "RGB"),
                read_only=True,
                default="rgb(216, 90, 143)",
            ),
            "hsl_value": Text(
                tr("field.hsl", "HSL"),
                read_only=True,
                default="hsl(335, 63%, 60%)",
            ),
        }
