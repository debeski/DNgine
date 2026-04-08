from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from dngine.sdk.i18n import _pt


@dataclass(frozen=True)
class PayloadRequirement:
    payload_key: str
    resolver: Callable[[object], object]
    message: str
    title: str = "Missing Input"
    is_missing: Callable[[object], bool] | None = None


def build_runtime_payload(
    runtime,
    *,
    required: tuple[PayloadRequirement, ...] = (),
    choose_directory: tuple[str, str] | None = None,
    extras: dict[str, object | Callable[[object], object]] | None = None,
) -> dict[str, object] | None:
    payload: dict[str, object] = {}

    for requirement in required:
        value = requirement.resolver(runtime)
        missing = requirement.is_missing(value) if callable(requirement.is_missing) else not value
        if missing:
            runtime.warn(requirement.title, requirement.message)
            return None
        payload[requirement.payload_key] = value

    if choose_directory is not None:
        payload_key, title = choose_directory
        selected = runtime.choose_directory(title)
        if not selected:
            return None
        payload[payload_key] = selected

    for key, value in (extras or {}).items():
        payload[key] = value(runtime) if callable(value) else value

    return payload


def before_task_run(runtime, summary: str, *, clear_output: bool = True) -> None:
    if clear_output:
        runtime.clear_output()
    runtime.set_summary(summary)


def set_runtime_values(runtime, /, **values) -> None:
    for key, value in values.items():
        runtime.set_value(key, value)


def error_message(runtime, payload: object, *, fallback: str) -> str:
    if isinstance(payload, dict):
        return str(payload.get("message") or fallback)
    return str(payload or fallback)


def handle_task_success(
    runtime,
    payload: object,
    *,
    summary: str | Callable[[dict[str, object]], str],
    output: str | Callable[[dict[str, object]], str],
    run_detail: str | Callable[[dict[str, object]], str] | None = None,
) -> None:
    result = dict(payload) if isinstance(payload, dict) else {"result": payload}
    runtime.set_summary(summary(result) if callable(summary) else str(summary))
    runtime.set_output(output(result) if callable(output) else str(output))
    if run_detail is not None:
        detail_text = run_detail(result) if callable(run_detail) else str(run_detail)
        runtime.services.record_run(runtime.plugin_id, "SUCCESS", detail_text)


def handle_task_error(
    runtime,
    payload: object,
    *,
    summary: str,
    fallback: str,
    log_message: str | Callable[[str], str] | None = None,
) -> None:
    message = error_message(runtime, payload, fallback=fallback)
    runtime.set_summary(summary)
    runtime.set_output(message)
    runtime.services.record_run(runtime.plugin_id, "ERROR", message[:500])
    if log_message is not None:
        rendered = log_message(message) if callable(log_message) else str(log_message)
        runtime.services.log(rendered, "ERROR")


def translated(message_key: str, default: str, **kwargs):
    return lambda runtime: _pt(runtime.tr, message_key, default, **kwargs)


def copy_to_clipboard(text: str) -> None:
    from PySide6.QtWidgets import QApplication
    clipboard = QApplication.clipboard()
    if clipboard is not None:
        clipboard.setText(str(text or ""))


def start_screen_picker(parent_widget, on_picked: Callable, on_canceled: Callable) -> object | None:
    from dngine.core.screen_picker import ScreenColorPickerSession

    def _handle(color):
        hex_val = color.name().upper() if color.isValid() else "#000000"
        rgb_val = f"rgb({color.red()}, {color.green()}, {color.blue()})"
        hue = color.hslHue()
        sat = round(color.hslSaturationF() * 100)
        light = round(color.lightnessF() * 100)
        hue_text = "0" if hue < 0 else str(hue)
        hsl_val = f"hsl({hue_text}, {sat}%, {light}%)"
        on_picked({"hex": hex_val, "rgb": rgb_val, "hsl": hsl_val, "isValid": color.isValid()})

    session = ScreenColorPickerSession(parent_widget)
    session.color_picked.connect(_handle)
    session.canceled.connect(on_canceled)
    if session.start():
        return session
    return None
