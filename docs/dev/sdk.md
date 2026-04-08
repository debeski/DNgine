# Strict SDK Authoring

`dngine.sdk` is the official public plugin authoring surface.

## Goals

- keep ordinary plugins small, readable, and consistent
- keep plugin imports on `dngine.sdk`, not `dngine.core`
- standardize layout, direction, task execution, and result handling
- let plugin files focus on business logic instead of shell plumbing

## Preferred Standard

For ordinary tools, the default authoring contract is now `DeclarativePlugin`.

- declare the page through a small dict of SDK components
- keep task workers, preview builders, and command declarations in the plugin file
- rely on shared helpers for payload building, run-state updates, success handling, and error handling
- target roughly `~200` lines total per ordinary plugin, including real task logic

`image_tagger` is the current reference plugin for this style.

## Public Contracts

- `DeclarativePlugin`
- `StandardPlugin`
- `TaskPlugin`
- `BatchFilePlugin`
- `TableToolPlugin`
- `HeadlessOnlyPlugin`
- `AdvancedPagePlugin`

## Declarative Components

- `Text`
- `MultiLine`
- `Choice`
- `Toggle`
- `Numeric`
- `Path`
- `FileList`
- `Preview`
- `Info`
- `Table`
- `Action`
- `Output`

These compile into the existing strict SDK runtime, so declarative plugins still get:

- shared page rendering
- visibility and enable rules
- file-list behaviors
- preview bindings
- task bindings
- direction handling
- standardized result panes

`Info` and `Table` are meant for display-heavy pages that still fit the strict shared runtime, such as simple system/about screens that should not stay on `AdvancedPagePlugin` just because they show static copy or a read-only version table.

## Shared Helpers

Use the shared helpers instead of repeating plugin-local task glue:

- `PayloadRequirement`
- `build_runtime_payload(...)`
- `before_task_run(...)`
- `handle_task_success(...)`
- `handle_task_error(...)`

Use SDK media helpers from `dngine.sdk`, not `dngine.core.media_utils`:

- `SUPPORTED_IMAGE_FILTER`
- `pil_to_pixmap(...)`
- `safe_output_extension(...)`
- `apply_tag(...)`
- `transform_image(...)`

## When To Use Each Contract

Use `DeclarativePlugin` when:

- the page is mostly forms, file lists, previews, outputs, and ordinary run actions
- the plugin can be expressed through the shared component set plus runtime helpers

Use `StandardPlugin` with explicit `PageSpec` when:

- the plugin still fits the strict SDK runtime
- but the declarative compiler does not yet cover an important layout or state pattern

Use `AdvancedPagePlugin` when:

- the page is genuinely custom or shell-like
- the plugin needs hand-built widgets and layouts that go beyond the ordinary tool pattern

## Author Policy

- import plugin-authoring helpers from `dngine.sdk`
- keep `dngine.core` imports as an engine-internal exception, not a default pattern
- sidecar locale files remain the preferred translation source
- direct `QMenu(...)`, plugin-local progress bars, and manual command registration are non-standard
- standard plugins should declare intent and logic, not build shell plumbing
