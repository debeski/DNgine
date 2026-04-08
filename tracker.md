# DNgine Project TODO Tracker

This file is now the working migration tracker. We will update it as each step lands.

## Current Verified Snapshot

- Date baseline: `2026-04-07`
- Total shipped/internal plugin classes currently discovered: `33`
- On strict SDK ordinary contracts (`StandardPlugin` or `DeclarativePlugin`): `14`
- On the approved declarative authoring standard: `9`
- On strict SDK but still pre-declarative/intermediate ordinary shapes: `5`
- On explicit `AdvancedPagePlugin`: `5`
- Still on legacy `QtPlugin`: `14`
- Current approved ordinary-plugin standard:
  - prefer `DeclarativePlugin` for ordinary tools
  - ordinary plugins should follow the `image_tagger` / `pdf_suite` / `document_bridge` pattern:
    one task function, one payload builder, declarative page dict, and shared SDK helpers for result/error/open/browse/runtime state work
  - keep the full plugin around `~200` lines including task logic when the shared SDK surface is a good fit
  - if a reusable element is missing, add it to the shared SDK surface instead of building one-off plugin-local glue
  - plugin imports should come from `dngine.sdk` wherever the behavior is part of the supported authoring surface
- Declarative pilot now landed and approved:
  - `image_tagger`
- Declarative pages already landed on the new standard:
  - `image_tagger`
  - `about_info`
  - `pdf_suite`
  - `doc_bridge` (`document_bridge`)
  - `hash_checker`
  - `sys_audit` (`system_audit`)
  - `privacy_shred` (`privacy_shredder`)
  - `color_picker`
  - `dev_lab`
- Verified strict-SDK/controllerless plugins overall:
  - `image_tagger`
  - `about_info`
  - `img_trans` (`image_transformer`)
  - `smart_exif` (`smart_exif_editor`)
  - `smart_bg` (`smart_background_remover`)
  - `doc_bridge` (`document_bridge`)
  - `color_picker`
  - `pdf_suite`
  - `hash_checker`
  - `privacy_shred`
  - `cleaner` (`data_cleaner`)
  - `cross_joiner`
  - `sys_audit` (`system_audit`)
  - `dev_lab`
- Verified advanced-contract plugins:
  - these are explicit custom-page exceptions, not zero-boilerplate `StandardPlugin` migrations
  - `dash_hub`:
    live dashboard cards, charts, responsive layout shifts, and shell-style status composition
  - `clip_snip`:
    custom clipboard table model, proxy filtering, stacked preview flows, dialogs, and context actions
  - `command_center`:
    multi-tab settings studio with custom pickers, sliders, quick-access previews, and shell-level behavior controls
  - `plugin_manager`:
    package catalog, plugin inventory, trust/enable/hide toggles, import/export flows, and plugin-state actions
  - `workflow_studio`:
    workflow editor, step table editing, command reference table, and run-output console
- Current SDK runtime already covers:
  - declarative page-dict compilation through `DeclarativePlugin`
  - page-local state
  - field/state sync
  - visibility rules
  - enable rules
  - file-list behaviors
  - preview bindings
  - task bindings
  - state reactions
  - runtime helpers like `set_output(...)`, `set_summary(...)`, `set_field_value(...)`, `add_file_paths(...)`
  - shared ordinary-plugin task helpers:
    - `build_runtime_payload(...)`
    - `before_task_run(...)`
    - `handle_task_success(...)`
    - `handle_task_error(...)`
    - `set_runtime_values(...)`
  - shared plugin-facing media helpers exported through `dngine.sdk`
  - shared plugin-facing document helpers exported through `dngine.sdk`
  - display-oriented declarative `Info` and `Table` components for informational system and utility pages
  - composite `table_details_pane` rendering and table/details helper methods in the page runtime
  - `file_list` + `table_details_pane` split layouts for controllerless review pages
  - controllerless debounced preview refresh flows driven by state reactions plus plugin-owned runtime helpers
  - action-targeted enable/visibility rules, file-list extension filtering, and rule reapplication on file-list mutations in the shared runtime
  - declarative direct-action handlers for non-task buttons like browse/open-result actions
  - declarative input/file-list `on_change` reactions for mode-driven placeholder, path-mode, extension, and summary updates
  - shared runtime file dialog helpers for choose-open / choose-save / choose-directory flows
  - declarative `Path` mode support so ordinary plugins can declare file vs directory intent without `configure_page(...)`
  - reusable display/layout primitives:
    `Info`, `InfoCard`, `Table`, `MetricDonut`, `Row`, `TextPanel`
  - timer-driven declarative polling via `TimerTask`

## SDK Usable Surface

- Declarative components already usable for plugin authors:
  - inputs and values:
    `Text`, `MultiLine`, `Choice`, `Toggle`, `Numeric`, `Path`
  - review and output surfaces:
    `FileList`, `Preview`, `Table`, `Output`
  - display and layout:
    `Info`, `InfoCard`, `MetricDonut`, `Row`, `TextPanel`
  - actions and orchestration:
    `Action`, `TimerTask`
- Shared helpers already usable from `dngine.sdk`:
  - task helpers:
    `build_runtime_payload(...)`, `before_task_run(...)`, `handle_task_success(...)`, `handle_task_error(...)`, `set_runtime_values(...)`
  - runtime helpers:
    `copy_to_clipboard(...)`, `start_screen_picker(...)`
  - shared plugin-facing helper surfaces:
    media helpers and document helpers exported through `dngine.sdk`
- Shared declarative/runtime behaviors already available:
  - direct `on_trigger` actions for non-task buttons
  - `on_change` reactions for fields and file lists
  - path intent via `Path(mode="file" | "directory")`
  - file-list auto add/clear wiring and extension filtering
  - preview binding refresh
  - row-based composition with shared card chrome
  - timer-driven polling pages without controller classes
- Current migration rule:
  - when a plugin needs a generic pattern, component, or helper, promote it into the SDK once and reuse it everywhere
  - `dev_lab` proved this path with shared `TextPanel` support instead of page-specific widget code
- Current acceptance coverage already verifies:
  - plugin contract classification
  - declarative plugin contract classification
  - standard page rendering
  - standard command registration
  - controller-style `StandardPlugin` classes are rejected unless they move to `AdvancedPagePlugin`
  - `image_tagger` without `_controller`
  - `image_tagger` on `DeclarativePlugin`
  - `image_tagger` auto-generated file-list add/clear actions through the declarative compiler
  - `about_info` on `DeclarativePlugin`
  - `about_info` on the strict SDK runtime with shared display cards and a shared static table
  - `img_trans` without `_controller`
  - `img_trans` handoff, enable rules, and aspect sync
  - `smart_exif` without `_controller`
  - `smart_exif` table/details split rendering, state reactions, and action enablement
  - `smart_bg` without `_controller`
  - `smart_bg` preview rendering, action enablement, and conditional custom-color visibility on the shared runtime
  - `doc_bridge` without `_controller`
  - `doc_bridge` on `DeclarativePlugin`
  - `doc_bridge` strict SDK command declaration plus declarative mode-driven field visibility, path constraints, and shared browse/open action wiring
  - `color_picker` without `_controller`
  - `color_picker` preview rendering and runtime-driven state updates from the picker session
  - `pdf_suite` without `_controller`
  - `pdf_suite` on `DeclarativePlugin`
  - `pdf_suite` strict SDK command declaration, file-list behavior, and output-path action enablement
  - `hash_checker` without `_controller`
  - `hash_checker` on `DeclarativePlugin`
  - `hash_checker` strict SDK command declaration plus runtime-driven calculate/verify flows
  - `privacy_shred` without `_controller`
  - `privacy_shred` on `DeclarativePlugin`
  - `privacy_shred` strict SDK command declaration, queue behavior, and confirmation-gated wipe flows
  - `color_picker` mapped completely to Declarative without explicit setup
  - `color_picker` overlay extracted to SDK as `start_screen_picker` allowing removal of PySide deps
  - `cleaner` without `_controller`
  - `cleaner` strict SDK command declaration plus workbook-cleaning runtime flow
  - `cross_joiner` without `_controller`
  - `cross_joiner` strict SDK command declaration plus workbook-join runtime flow
  - `sys_audit` on `DeclarativePlugin`
  - `sys_audit` strict SDK command declaration plus declarative live-dashboard cards, donuts, and table population
  - `dev_lab` on `DeclarativePlugin`
  - `dev_lab` strict SDK timer polling, shared `TextPanel` rendering, and controllerless snapshot copy flow
  - remaining audited system pages intentionally stay on explicit custom `AdvancedPagePlugin` contracts:
    - `dash_hub`
    - `clip_snip`
    - `command_center`
    - `plugin_manager`
    - `workflow_studio`
  - focused verification:
    - `./venv/bin/python -m unittest tests.test_sdk_contracts`
    - `./venv/bin/python -m unittest tests.test_media_plugins`
    - `./venv/bin/python -m unittest tests.test_signed_packages`

## Immediate Active Queue

- [x] Finish the SDK table/details migration path by proving it through `smart_exif_editor`
- [x] Add/expand SDK acceptance tests for table/details style plugins
- [x] Migrate `smart_exif_editor` to controllerless `StandardPlugin`
- [x] Migrate `smart_background_remover` to controllerless `StandardPlugin`
- [x] Add an audit gate so controller-style "standard" plugins are rejected unless explicitly marked `AdvancedPagePlugin`
- [x] Prove the new declarative plugin standard through `image_tagger`
- [x] Prove the display-oriented declarative system/info page path through `about_info`
- [x] Roll the declarative plugin standard to the next ordinary migrated tool if the current pilot remains satisfactory

## Contract Cleanup Strategy

- [ ] Default target for ordinary task/file/table tools: `DeclarativePlugin`
- [ ] Use explicit `StandardPlugin` + `PageSpec` only when the plugin still fits the strict SDK runtime but needs patterns the declarative compiler does not yet expose
- [ ] Default target for genuinely complex shell-owned pages: explicit `AdvancedPagePlugin`
- [ ] Remove raw legacy ambiguity by making each remaining `QtPlugin` become either `DeclarativePlugin`, explicit `StandardPlugin`, or `AdvancedPagePlugin`

## Internal Plugins

### System Pages

- [ ] Migrate `dash_hub`
- [x] Reclassify or migrate `clip_snip`
- [x] Reclassify or migrate `command_center`
- [x] Reclassify or migrate `plugin_manager`
- [x] Reclassify or migrate `workflow_studio`
- [x] Migrate `about_info`
- [x] Migrate `dev_lab`

### Built-in Core Tools

- [x] Migrate `image_tagger`
- [x] Migrate `pdf_suite`
- [x] Migrate `document_bridge`
- [x] Migrate `hash_checker`
- [x] Migrate `system_audit`
- [x] Migrate `privacy_shredder`
- [x] Migrate `color_picker`

## First-Party Packages

### Media & Images

- [ ] Migrate `img_trans`
- [ ] Migrate `smart_exif`
- [ ] Migrate `smart_bg`

### Files & Storage

- [ ] Migrate `batch_renamer`
- [ ] Migrate `deep_searcher`
- [ ] Migrate `smart_org`
- [ ] Migrate `usage_analyzer`

### Office & Docs

- [ ] Migrate `cross_joiner`
- [ ] Migrate `cleaner`

### Data & Analysis

- [ ] Migrate `chart_builder`
- [ ] Migrate `data_link_auditor`
- [ ] Migrate `deep_scan_auditor`
- [ ] Migrate `folder_mapper`
- [ ] Migrate `sequence_auditor`

### Network & Security

- [ ] Migrate `net_scan`
- [ ] Migrate `wifi_profiles`

### Web Dev

- [ ] Migrate `code_factory`
- [ ] Migrate `cred_scanner`
- [ ] Migrate `web_scraper`

## Cross-Cutting Audits

- [ ] Sidecar dependency audit for packaged first-party plugins still missing `.deps` manifests:
  - `img_trans`
  - `batch_renamer`
  - `deep_searcher`
  - `smart_org`
  - `net_scan`
  - `wifi_profiles`
  - `code_factory`
  - `cred_scanner`
- [ ] Internal/builtin sidecar policy audit:
  - decide whether builtin plugins should gain explicit `.deps` sidecars or a documented exemption
- [ ] Command contract audit:
  - move legacy/manual command registration onto `declare_command_specs(...)`
  - `document_bridge` migrated onto `declare_command_specs(...)`
  - `pdf_suite` migrated onto `declare_command_specs(...)`
  - `cleaner` migrated onto `declare_command_specs(...)`
  - `cross_joiner` migrated onto `declare_command_specs(...)`
  - `system_audit` migrated onto `declare_command_specs(...)`
  - continue with `web_scraper`
- [ ] Context-menu audit:
  - replace direct `QMenu(...)` usage with shared context-menu abstractions
  - no currently confirmed direct plugin-local `QMenu(...)` usage in builtin or first-party plugin pages from the latest focused scan
- [ ] Translation/layout audit:
  - keep all migrations on SDK translation helpers and shared RTL/LTR handling
- [ ] Shared layout audit:
  - keep migrations on SDK declarative components first, then explicit SDK page specs when needed, plus shared semantic classes and shell-owned task/progress behavior
- [ ] Package metadata audit:
  - keep package manifests, builtin manifest, and first-party catalog aligned as plugins migrate

## Tests

- [x] Keep extending `tests/test_sdk_contracts.py` as each migration lands
- [x] Keep package-specific tests green while migrating:
  - `tests.test_media_plugins`
  - `tests.test_sdk_contracts`
  - `tests.test_signed_packages`
  - other impacted suites as touched

## Docs Follow-Up

- [x] Update `docs/dev/sdk.md` to document the declarative plugin standard, shared helpers, and public SDK surface
- [x] Update `docs/dev/migration.md` with the controllerless migration pattern once the next milestone lands
- [x] Update root `README.md` when the current migration milestone is complete
- [x] Fix package coverage in docs:
  - root `README.md` now includes `Media & Images` and `Data & Analysis` in the first-party package overview
- [ ] Leave `CHANGELOG.md` untouched for now

## Future Agent Handoff & Working Rules

- Start by reading this file, then `./.agents/rules/code-123.md`, then the relevant plugin and SDK files for the active migration target.
- Treat `dngine.sdk` as the public plugin-authoring surface and `dngine.core` as internal engine infrastructure unless the task is explicitly about engine internals.
- Prefer converting ordinary plugins to `DeclarativePlugin`; use explicit `StandardPlugin` only when the plugin still fits the strict SDK runtime but the declarative layer is not enough, and use `AdvancedPagePlugin` only when the page is genuinely too complex for the strict SDK path.
- Ordinary plugins should match the approved declarative shape used by `image_tagger`, `pdf_suite`, and `document_bridge`: keep the page as a compact dict, keep task/result wiring on shared SDK helpers, and keep plugin code near `~200` lines unless the tool is genuinely more advanced.
- Do not leave ordinary plugins on explicit `PageSpec`, `configure_page(...)`, manual `generated_actions[...]` signal wiring, plugin-local file dialogs, or bespoke result/error glue if the behavior can be moved into shared `dngine.sdk` primitives first.
- If a needed ordinary-plugin behavior is missing from the SDK, add it to shared/global `dngine.sdk` logic before finishing the plugin migration, then consume it from the plugin instead of implementing a one-off local workaround.
- Do not preserve legacy plugin-authoring or backwards-compatibility patterns by default. The goal is to migrate them, not wrap them.
- Keep translations and dependency declarations in sidecar files for plugins, and use the shared SDK translation, direction, task, and media helpers for all new strings, commands, fields, layout behavior, and ordinary plugin workflows.
- Reuse predefined app classes, declarative SDK components, strict shared layouts, shared semantic classes, shared task/progress behavior, drag-and-drop support, and shared context-menu abstractions instead of handwritten plugin-local scaffolding, custom styles, direct `QMenu(...)`, or plugin-local loading widgets for ordinary tasks.
- Prefer rich in-app tables, filters, previews, and charts over export-first workflows; exports should stay optional when the product shape allows it.
- Preserve the modular, dynamic architecture across shell, services, and plugins, and keep the GUI simple, responsive, and consistent across English/Arabic plus Windows/macOS/Linux.
- Keep the `System` pages visually and behaviorally aligned with the rest of the shell unless the task explicitly calls for a broader shell redesign.
- Update shared/global element classes when a style or behavior change should apply across the app, unless the user explicitly wants a local exception.
- Do not remove or rewrite unrelated lines of code while migrating a plugin.
- Keep `tracker.md` updated after each meaningful step so the next agent can resume from current reality instead of stale assumptions.
- Update `README.md` and the relevant files under `docs/` when a migration milestone materially changes the public or developer-facing story.
- All standard plugins should declare their CLI/headless command surfaces through the shared SDK command contract instead of ad hoc manual registration.
- Keep plugin imports on `dngine.sdk` whenever the SDK exposes the needed helper; do not reach into `dngine.core` from ordinary plugin code unless there is no public SDK surface yet.
- Leave `CHANGELOG.md` untouched for now despite the broader standing rule, unless the user explicitly asks to resume release-history updates.
- Before closing a step, run the smallest relevant verification possible and record the outcome in this tracker if it changes project status.
