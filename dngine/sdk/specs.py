from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass(frozen=True)
class ChoiceOption:
    value: str
    label: str


@dataclass(frozen=True)
class FieldSpec:
    field_id: str
    kind: str
    label: str
    default: object = None
    placeholder: str = ""
    help_text: str = ""
    options: tuple[ChoiceOption, ...] = ()
    min_value: float | int | None = None
    max_value: float | int | None = None
    path_mode: str = "any"
    allowed_extensions: tuple[str, ...] = ()
    semantic_class: str = ""
    read_only: bool = False
    table_headers: tuple[str, ...] = ()
    table_rows: tuple[tuple[object, ...], ...] = ()


@dataclass(frozen=True)
class StateSpec:
    state_id: str
    default: object = None


@dataclass(frozen=True)
class ActionSpec:
    action_id: str
    label: str
    kind: str = "primary"
    task_id: str = ""
    tooltip: str = ""
    enabled: bool = True
    auto_run: bool = False


@dataclass(frozen=True)
class ActionHandlerBindingSpec:
    action_id: str
    handler: Callable[[object], None]


@dataclass(frozen=True)
class ResultSpec:
    summary_placeholder: str = ""
    output_placeholder: str = ""
    details_placeholder: str = ""
    preview_placeholder: str = ""


@dataclass(frozen=True)
class TaskSpec:
    task_id: str
    worker: Callable
    ready_text: str = ""
    running_text: str = ""
    success_text: str = ""
    error_text: str = ""
    payload_builder: Callable[[dict[str, object]], dict[str, object]] | None = None
    result_adapter: Callable[[object], object] | None = None


@dataclass(frozen=True)
class VisibilityRule:
    target_ids: tuple[str, ...]
    predicate: Callable[[object], bool]
    depends_on: tuple[str, ...] = ()


@dataclass(frozen=True)
class EnableRule:
    target_ids: tuple[str, ...]
    predicate: Callable[[object], bool]
    depends_on: tuple[str, ...] = ()


@dataclass(frozen=True)
class FileListBehaviorSpec:
    widget_id: str
    state_id: str
    add_action_id: str = ""
    clear_action_id: str = ""
    selection_state_id: str = ""
    dialog_title: str = ""
    file_filter: str = ""
    remove_action_text: str = ""
    allow_duplicates: bool = False
    display_adapter: Callable[[str], str] | None = None


@dataclass(frozen=True)
class PreviewBindingSpec:
    widget_id: str
    builder: Callable[[object], object]
    dependencies: tuple[str, ...] = ()
    empty_text: str = ""


@dataclass(frozen=True)
class StateReactionSpec:
    depends_on: tuple[str, ...]
    handler: Callable[[object, str], None]


@dataclass(frozen=True)
class TimerTaskSpec:
    timer_id: str
    interval_ms: int
    handler: Callable[[object], None]


@dataclass(frozen=True)
class TaskBindingSpec:
    action_id: str
    task_id: str
    payload_builder: Callable[[object], dict[str, object] | None]
    before_run: Callable[[object], None] | None = None
    on_result: Callable[[object, object], None] | None = None
    on_error: Callable[[object, object], None] | None = None
    on_finished: Callable[[object], None] | None = None
    disable_actions: tuple[str, ...] = ()


@dataclass(frozen=True)
class SectionSpec:
    section_id: str
    kind: str
    title: str = ""
    description: str = ""
    fields: tuple[FieldSpec, ...] = ()
    actions: tuple[ActionSpec, ...] = ()
    semantic_class: str = ""
    stretch: int = 0


@dataclass(frozen=True)
class PageSpec:
    archetype: str
    title: str
    description: str = ""
    sections: tuple[SectionSpec, ...] = ()
    result_spec: ResultSpec = field(default_factory=ResultSpec)
    state: tuple[StateSpec, ...] = ()
    task_specs: tuple[TaskSpec, ...] = ()
    visibility_rules: tuple[VisibilityRule, ...] = ()
    enable_rules: tuple[EnableRule, ...] = ()
    file_behaviors: tuple[FileListBehaviorSpec, ...] = ()
    preview_bindings: tuple[PreviewBindingSpec, ...] = ()
    state_reactions: tuple[StateReactionSpec, ...] = ()
    timer_tasks: tuple[TimerTaskSpec, ...] = ()
    task_bindings: tuple[TaskBindingSpec, ...] = ()
    action_bindings: tuple[ActionHandlerBindingSpec, ...] = ()
