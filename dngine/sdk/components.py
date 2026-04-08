from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


Rule = dict[str, object] | Callable[[object], bool] | None


@dataclass(frozen=True)
class Text:
    label: str = ""
    placeholder: str = ""
    default: str = ""
    help_text: str = ""
    read_only: bool = False
    on_change: Callable[[object, str], None] | None = None
    visible_when: Rule = None
    enabled_when: Rule = None


@dataclass(frozen=True)
class MultiLine:
    label: str = ""
    placeholder: str = ""
    default: str = ""
    help_text: str = ""
    read_only: bool = False
    on_change: Callable[[object, str], None] | None = None
    visible_when: Rule = None
    enabled_when: Rule = None


@dataclass(frozen=True)
class Choice:
    label: str = ""
    options: tuple[tuple[object, str], ...] | list[tuple[object, str]] | dict[object, str] = ()
    default: object = ""
    help_text: str = ""
    on_change: Callable[[object, str], None] | None = None
    visible_when: Rule = None
    enabled_when: Rule = None


@dataclass(frozen=True)
class Toggle:
    label: str = ""
    default: bool = False
    help_text: str = ""
    on_change: Callable[[object, str], None] | None = None
    visible_when: Rule = None
    enabled_when: Rule = None


@dataclass(frozen=True)
class Numeric:
    label: str = ""
    default: float | int = 0
    min_value: float | int | None = None
    max_value: float | int | None = None
    help_text: str = ""
    on_change: Callable[[object, str], None] | None = None
    visible_when: Rule = None
    enabled_when: Rule = None


@dataclass(frozen=True)
class Path:
    label: str = ""
    placeholder: str = ""
    default: str = ""
    help_text: str = ""
    read_only: bool = False
    mode: str = "any"
    allowed_extensions: tuple[str, ...] = ()
    on_change: Callable[[object, str], None] | None = None
    visible_when: Rule = None
    enabled_when: Rule = None


@dataclass(frozen=True)
class FileList:
    extensions: tuple[str, ...] = ()
    mode: str = "file"
    add_label: str = "Add Files"
    clear_label: str = "Clear"
    remove_label: str = "Remove from list"
    dialog_title: str = "Select Files"
    file_filter: str = ""
    allow_duplicates: bool = False
    display_adapter: Callable[[str], str] | None = None
    on_change: Callable[[object, str], None] | None = None
    visible_when: Rule = None
    enabled_when: Rule = None
    stretch: int = 1


@dataclass(frozen=True)
class Preview:
    builder: Callable[[object], object] | None = None
    empty_text: str = "No preview available."
    dependencies: tuple[str, ...] = ()
    semantic_class: str = "preview_class"
    visible_when: Rule = None
    enabled_when: Rule = None
    stretch: int = 2


@dataclass(frozen=True)
class Info:
    title: str = ""
    body: str = ""
    semantic_class: str = ""
    visible_when: Rule = None
    enabled_when: Rule = None
    stretch: int = 0


@dataclass(frozen=True)
class Table:
    title: str = ""
    headers: tuple[str, ...] | list[str] = ()
    rows: tuple[tuple[object, ...], ...] | list[list[object]] = ()
    semantic_class: str = "output_class"
    visible_when: Rule = None
    enabled_when: Rule = None
    stretch: int = 1


@dataclass(frozen=True)
class Output:
    ready_text: str = "Ready."
    placeholder: str = "Output will appear here."
    semantic_class: str = "output_class"
    stretch: int = 1


@dataclass(frozen=True)
class TextPanel:
    title: str = ""
    default: str = ""
    placeholder: str = ""
    semantic_class: str = "output_class"
    read_only: bool = True
    visible_when: Rule = None
    enabled_when: Rule = None
    stretch: int = 1


@dataclass(frozen=True)
class Action:
    label: str = "Run"
    kind: str = "primary"
    tooltip: str = ""
    enabled: bool = True
    auto_run: bool = False
    on_trigger: Callable[[object], None] | None = None
    worker: Callable | None = None
    payload_builder: Callable[[object], dict[str, object] | None] | None = None
    before_run: Callable[[object], None] | None = None
    on_result: Callable[[object, object], None] | None = None
    on_error: Callable[[object, object], None] | None = None
    on_finished: Callable[[object], None] | None = None
    running_text: str = ""
    success_text: str = ""
    error_text: str = ""
    disable_actions: tuple[str, ...] = ()
    visible_when: Rule = None
    enabled_when: Rule = None


@dataclass(frozen=True)
class MetricDonut:
    title: str = ""
    accent: str = ""
    remainder: str = ""
    caption: str = ""
    visible_when: Rule = None
    enabled_when: Rule = None


@dataclass(frozen=True)
class InfoCard:
    title: str = ""
    rows: tuple[tuple[str, object], ...] | list[tuple[str, object]] = ()
    visible_when: Rule = None
    enabled_when: Rule = None
    stretch: int = 1


@dataclass(frozen=True)
class Row:
    fields: dict[str, object] = field(default_factory=dict)
    visible_when: Rule = None
    enabled_when: Rule = None
    stretch: int = 0


@dataclass(frozen=True)
class TimerTask:
    interval_ms: int = 1000
    on_tick: Callable[[object], None] | None = None
    enabled_when: Rule = None
