from __future__ import annotations

from collections.abc import Mapping

from dngine.sdk.components import Action, Choice, FileList, Info, InfoCard, MetricDonut, MultiLine, Numeric, Output, Path, Preview, Row, Table, Text, TextPanel, TimerTask, Toggle
from dngine.sdk.specs import (
    ActionHandlerBindingSpec,
    ActionSpec,
    ChoiceOption,
    EnableRule,
    FieldSpec,
    FileListBehaviorSpec,
    PageSpec,
    PreviewBindingSpec,
    ResultSpec,
    SectionSpec,
    StateReactionSpec,
    TaskBindingSpec,
    TaskSpec,
    TimerTaskSpec,
    VisibilityRule,
)


_INPUT_COMPONENTS = (Text, MultiLine, Choice, Toggle, Numeric, Path)


def _evaluate_rule(rule, runtime) -> bool:
    if rule is None:
        return True
    if isinstance(rule, Mapping):
        return all(runtime.value(key) == expected for key, expected in rule.items())
    if callable(rule):
        try:
            return bool(rule(runtime))
        except TypeError:
            try:
                return bool(rule(runtime.snapshot()))
            except Exception:
                return True
        except Exception:
            return True
    return bool(rule)


def _predicate(rule):
    return lambda runtime, _rule=rule: _evaluate_rule(_rule, runtime)


def _choice_options(options) -> tuple[ChoiceOption, ...]:
    if isinstance(options, Mapping):
        items = options.items()
    else:
        items = options or ()
    return tuple(ChoiceOption(value=value, label=label) for value, label in items)


def _field_spec(field_id: str, component) -> FieldSpec:
    if isinstance(component, Text):
        return FieldSpec(
            field_id,
            "text",
            component.label,
            default=component.default,
            placeholder=component.placeholder,
            help_text=component.help_text,
            read_only=component.read_only,
        )
    if isinstance(component, MultiLine):
        return FieldSpec(
            field_id,
            "multiline",
            component.label,
            default=component.default,
            placeholder=component.placeholder,
            help_text=component.help_text,
            read_only=component.read_only,
        )
    if isinstance(component, Choice):
        return FieldSpec(
            field_id,
            "choice",
            component.label,
            default=component.default,
            help_text=component.help_text,
            options=_choice_options(component.options),
        )
    if isinstance(component, Toggle):
        return FieldSpec(
            field_id,
            "toggle",
            component.label,
            default=component.default,
            placeholder=component.label,
            help_text=component.help_text,
        )
    if isinstance(component, Numeric):
        return FieldSpec(
            field_id,
            "numeric",
            component.label,
            default=component.default,
            min_value=component.min_value,
            max_value=component.max_value,
            help_text=component.help_text,
        )
    if isinstance(component, Path):
        return FieldSpec(
            field_id,
            "path",
            component.label,
            default=component.default,
            placeholder=component.placeholder,
            help_text=component.help_text,
            path_mode=component.mode,
            allowed_extensions=tuple(component.allowed_extensions),
            read_only=component.read_only,
        )
    if isinstance(component, MetricDonut):
        return FieldSpec(
            field_id,
            "donut",
            component.title,
            default=component.caption,
            placeholder=component.accent,
            help_text=component.remainder,
        )
    if isinstance(component, InfoCard):
        return FieldSpec(
            field_id,
            "info_card_field",
            component.title,
            table_rows=tuple(component.rows),
        )
    if isinstance(component, TextPanel):
        return FieldSpec(
            field_id,
            "text_panel",
            component.title,
            default=component.default,
            placeholder=component.placeholder,
            semantic_class=component.semantic_class,
            read_only=component.read_only,
        )
    raise TypeError(f"Unsupported input component: {component!r}")


def compile_page_dict(*, page: dict[str, object], title: str, description: str) -> PageSpec:
    sections: list[SectionSpec] = []
    visibility_rules: list[VisibilityRule] = []
    enable_rules: list[EnableRule] = []
    file_behaviors: list[FileListBehaviorSpec] = []
    preview_bindings: list[PreviewBindingSpec] = []
    task_specs: list[TaskSpec] = []
    task_bindings: list[TaskBindingSpec] = []
    action_bindings: list[ActionHandlerBindingSpec] = []
    state_reactions: list[StateReactionSpec] = []
    timer_tasks: list[TimerTaskSpec] = []
    result_spec = ResultSpec()
    output_seen = False

    items = list(page.items())
    index = 0

    while index < len(items):
        key, component = items[index]

        if isinstance(component, _INPUT_COMPONENTS):
            fields: list[FieldSpec] = []
            while index < len(items) and isinstance(items[index][1], _INPUT_COMPONENTS):
                field_id, input_component = items[index]
                fields.append(_field_spec(field_id, input_component))
                if getattr(input_component, "visible_when", None) is not None:
                    target_ids = (field_id,) if isinstance(input_component, Toggle) else (field_id, f"{field_id}.label")
                    visibility_rules.append(VisibilityRule(target_ids=target_ids, predicate=_predicate(input_component.visible_when)))
                if getattr(input_component, "enabled_when", None) is not None:
                    enable_rules.append(EnableRule(target_ids=(field_id,), predicate=_predicate(input_component.enabled_when)))
                if callable(getattr(input_component, "on_change", None)):
                    state_reactions.append(
                        StateReactionSpec(
                            depends_on=(field_id,),
                            handler=input_component.on_change,
                        )
                    )
                index += 1
            sections.append(
                SectionSpec(
                    section_id=f"settings_{len(sections)}",
                    kind="settings_card",
                    fields=tuple(fields),
                )
            )
            continue

        if isinstance(component, TimerTask):
            timer_id = f"{key}.__timer"
            timer_tasks.append(
                TimerTaskSpec(
                    timer_id=timer_id,
                    interval_ms=component.interval_ms,
                    handler=component.on_tick,
                )
            )
            if component.enabled_when is not None:
                enable_rules.append(EnableRule(target_ids=(timer_id,), predicate=_predicate(component.enabled_when)))
            index += 1
            continue

        if isinstance(component, Row):
            row_fields = []
            for child_id, child_component in component.fields.items():
                row_fields.append(_field_spec(child_id, child_component))
                if getattr(child_component, "visible_when", None) is not None:
                    visibility_rules.append(VisibilityRule(target_ids=(child_id,), predicate=_predicate(child_component.visible_when)))
                if getattr(child_component, "enabled_when", None) is not None:
                    enable_rules.append(EnableRule(target_ids=(child_id,), predicate=_predicate(child_component.enabled_when)))
            sections.append(
                SectionSpec(
                    section_id=f"row_{key}",
                    kind="row",
                    fields=tuple(row_fields),
                    stretch=component.stretch,
                )
            )
            if component.visible_when is not None:
                visibility_rules.append(VisibilityRule(target_ids=(f"row_{key}",), predicate=_predicate(component.visible_when)))
            index += 1
            continue

        if isinstance(component, TextPanel):
            sections.append(
                SectionSpec(
                    section_id=f"{key}.__section",
                    kind="text_panel",
                    fields=(FieldSpec(
                        key,
                        "text_panel",
                        component.title,
                        default=component.default,
                        placeholder=component.placeholder,
                        semantic_class=component.semantic_class,
                        read_only=component.read_only,
                    ),),
                    stretch=max(1, int(component.stretch or 1)),
                )
            )
            if component.visible_when is not None:
                visibility_rules.append(VisibilityRule(target_ids=(f"{key}.__section", key), predicate=_predicate(component.visible_when)))
            if component.enabled_when is not None:
                enable_rules.append(EnableRule(target_ids=(f"{key}.__section", key), predicate=_predicate(component.enabled_when)))
            index += 1
            continue

        if isinstance(component, FileList):
            add_action_id = f"{key}.__add"
            clear_action_id = f"{key}.__clear"
            sections.append(
                SectionSpec(
                    section_id=f"{key}.__actions",
                    kind="actions_row",
                    actions=(
                        ActionSpec(add_action_id, component.add_label, kind="secondary"),
                        ActionSpec(clear_action_id, component.clear_label, kind="secondary"),
                    ),
                )
            )
            sections.append(
                SectionSpec(
                    section_id=f"{key}.__section",
                    kind="file_list",
                    fields=(FieldSpec(key, "file_list", "", allowed_extensions=tuple(component.extensions), path_mode=component.mode),),
                    stretch=max(1, int(component.stretch or 1)),
                )
            )
            file_behaviors.append(
                FileListBehaviorSpec(
                    widget_id=key,
                    state_id=key,
                    add_action_id=add_action_id,
                    clear_action_id=clear_action_id,
                    selection_state_id=f"{key}.__selected_row",
                    dialog_title=component.dialog_title,
                    file_filter=component.file_filter,
                    remove_action_text=component.remove_label,
                    allow_duplicates=component.allow_duplicates,
                    display_adapter=component.display_adapter,
                )
            )
            if component.visible_when is not None:
                visibility_rules.append(VisibilityRule(target_ids=(key, add_action_id, clear_action_id), predicate=_predicate(component.visible_when)))
            if component.enabled_when is not None:
                enable_rules.append(EnableRule(target_ids=(key, add_action_id, clear_action_id), predicate=_predicate(component.enabled_when)))
            if callable(component.on_change):
                state_reactions.append(
                    StateReactionSpec(
                        depends_on=(key, f"{key}.__selected_row"),
                        handler=component.on_change,
                    )
                )
            index += 1
            continue

        if isinstance(component, Preview):
            sections.append(
                SectionSpec(
                    section_id=f"{key}.__section",
                    kind="preview_pane",
                    fields=(
                        FieldSpec(
                            key,
                            "preview",
                            "",
                            placeholder=component.empty_text,
                            semantic_class=component.semantic_class,
                        ),
                    ),
                    stretch=max(1, int(component.stretch or 1)),
                )
            )
            preview_bindings.append(
                PreviewBindingSpec(
                    widget_id=key,
                    builder=component.builder,
                    dependencies=tuple(component.dependencies),
                    empty_text=component.empty_text,
                )
            )
            if component.visible_when is not None:
                visibility_rules.append(VisibilityRule(target_ids=(key,), predicate=_predicate(component.visible_when)))
            if component.enabled_when is not None:
                enable_rules.append(EnableRule(target_ids=(key,), predicate=_predicate(component.enabled_when)))
            index += 1
            continue

        if isinstance(component, Info):
            sections.append(
                SectionSpec(
                    section_id=f"{key}.__section",
                    kind="info_card",
                    title=component.title,
                    description=component.body,
                    semantic_class=component.semantic_class,
                    stretch=max(0, int(component.stretch or 0)),
                )
            )
            if component.visible_when is not None:
                visibility_rules.append(VisibilityRule(target_ids=(f"{key}.__section",), predicate=_predicate(component.visible_when)))
            if component.enabled_when is not None:
                enable_rules.append(EnableRule(target_ids=(f"{key}.__section",), predicate=_predicate(component.enabled_when)))
            index += 1
            continue

        if isinstance(component, Table):
            sections.append(
                SectionSpec(
                    section_id=f"{key}.__section",
                    kind="table_card",
                    title=component.title,
                    fields=(
                        FieldSpec(
                            key,
                            "table",
                            "",
                            semantic_class=component.semantic_class,
                            table_headers=tuple(str(header) for header in (component.headers or ())),
                            table_rows=tuple(
                                tuple("" if value is None else value for value in row)
                                for row in (component.rows or ())
                            ),
                        ),
                    ),
                    stretch=max(1, int(component.stretch or 1)),
                )
            )
            if component.visible_when is not None:
                visibility_rules.append(VisibilityRule(target_ids=(f"{key}.__section", key), predicate=_predicate(component.visible_when)))
            if component.enabled_when is not None:
                enable_rules.append(EnableRule(target_ids=(f"{key}.__section", key), predicate=_predicate(component.enabled_when)))
            index += 1
            continue

        if isinstance(component, Row):
            row_fields: list[FieldSpec] = []
            for child_id, child_component in component.fields.items():
                row_fields.append(_field_spec(child_id, child_component))
            sections.append(
                SectionSpec(
                    section_id=key,
                    kind="row",
                    fields=tuple(row_fields),
                )
            )
            index += 1
            continue

        if isinstance(component, Action):
            actions: list[ActionSpec] = []
            pending_rules: list[tuple[str, Action]] = []
            while index < len(items) and isinstance(items[index][1], Action):
                action_id, action_component = items[index]
                actions.append(
                    ActionSpec(
                        action_id=action_id,
                        label=action_component.label,
                        kind=action_component.kind,
                        tooltip=action_component.tooltip,
                        enabled=action_component.enabled,
                        auto_run=action_component.auto_run,
                    )
                )
                pending_rules.append((action_id, action_component))
                if action_component.worker is not None:
                    task_id = f"{action_id}.__task"
                    task_specs.append(
                        TaskSpec(
                            task_id=task_id,
                            worker=action_component.worker,
                            running_text=action_component.running_text,
                            success_text=action_component.success_text,
                            error_text=action_component.error_text,
                        )
                    )
                    task_bindings.append(
                        TaskBindingSpec(
                            action_id=action_id,
                            task_id=task_id,
                            payload_builder=action_component.payload_builder or (lambda runtime: runtime.snapshot()),
                            before_run=action_component.before_run,
                            on_result=action_component.on_result,
                            on_error=action_component.on_error,
                            on_finished=action_component.on_finished,
                            disable_actions=tuple(action_component.disable_actions),
                        )
                    )
                elif callable(action_component.on_trigger):
                    action_bindings.append(
                        ActionHandlerBindingSpec(
                            action_id=action_id,
                            handler=action_component.on_trigger,
                        )
                    )
                index += 1
            sections.append(
                SectionSpec(
                    section_id=f"actions_{len(sections)}",
                    kind="actions_row",
                    actions=tuple(actions),
                )
            )
            for action_id, action_component in pending_rules:
                if action_component.visible_when is not None:
                    visibility_rules.append(VisibilityRule(target_ids=(action_id,), predicate=_predicate(action_component.visible_when)))
                if action_component.enabled_when is not None:
                    enable_rules.append(EnableRule(target_ids=(action_id,), predicate=_predicate(action_component.enabled_when)))
            continue

        if isinstance(component, Output):
            sections.append(
                SectionSpec(
                    section_id="result",
                    kind="summary_output_pane",
                    description=component.ready_text,
                    semantic_class=component.semantic_class,
                    stretch=max(1, int(component.stretch or 1)),
                )
            )
            result_spec = ResultSpec(
                summary_placeholder=component.ready_text,
                output_placeholder=component.placeholder,
                preview_placeholder=result_spec.preview_placeholder,
                details_placeholder=result_spec.details_placeholder,
            )
            output_seen = True
            index += 1
            continue

        raise TypeError(f"Unsupported declarative component for key '{key}': {component!r}")

    if not output_seen:
        result_spec = ResultSpec(
            summary_placeholder="Ready.",
            output_placeholder="Output will appear here.",
            preview_placeholder=result_spec.preview_placeholder,
            details_placeholder=result_spec.details_placeholder,
        )

    return PageSpec(
        archetype="declarative",
        title=title,
        description=description,
        sections=tuple(sections),
        result_spec=result_spec,
        task_specs=tuple(task_specs),
        visibility_rules=tuple(visibility_rules),
        enable_rules=tuple(enable_rules),
        file_behaviors=tuple(file_behaviors),
        preview_bindings=tuple(preview_bindings),
        state_reactions=tuple(state_reactions),
        timer_tasks=tuple(timer_tasks),
        task_bindings=tuple(task_bindings),
        action_bindings=tuple(action_bindings),
    )
