# DNgine Strict SDK And Command Standardization Plan

## Summary
- Reset DNgine into a strict plugin platform with no authoring-contract backwards compatibility.
- Standardize not only page UI and plugin behavior, but also headless/CLI command declaration, translation access, and documentation structure.
- Keep plugin install/import/export/package mechanics unchanged.
- Deliver this in two phases:
  - Phase 1: build the strict engine, SDK, validation, archetypes, command contract, and docs structure
  - Phase 2: migrate existing plugins to the new standard one by one

## Key Changes
### 1. Hard Reset of the Plugin Contract
- Introduce `dngine.sdk` as the only supported plugin authoring surface.
- Retire raw `QtPlugin` authoring as a standard path.
- Legacy plugins remain discoverable for audit and migration visibility, but are explicitly non-standard and do not count as compliant.
- Validation states become:
  - `sdk_valid`
  - `sdk_invalid`
  - `legacy_contract`
  - `advanced_contract`

### 2. Strict SDK Surface
- Create `dngine/sdk/` as the official author API.
- Expose only approved concepts:
  - plugin bases
  - page/section specs
  - field specs
  - action specs
  - task specs
  - command specs
  - result specs
  - translation helpers
  - context-menu helpers
- Keep `dngine.core` internal and undocumented for normal plugin authors.

### 3. Standard Plugin Bases
- Add strict bases:
  - `StandardPlugin`
  - `TaskPlugin`
  - `BatchFilePlugin`
  - `TableToolPlugin`
  - `HeadlessOnlyPlugin`
  - `AdvancedPagePlugin`
- Base classes own:
  - theme/language refresh
  - direction handling
  - shell progress/status/activity-log integration
  - standard action lifecycle
  - standard summary/output states
  - standard empty/loading/error states
- All standard plugins implement declarative hooks, not raw widget assembly.

### 4. Expandable Archetype And Section System
- Build pages from ordered standard sections instead of hand-written layouts.
- Core section types:
  - header
  - settings card
  - actions row
  - file list
  - preview pane
  - table pane
  - details pane
  - summary/output pane
- Standard archetypes:
  - `SimpleFormPage`
  - `FileBatchPage`
  - `FileBatchPreviewPage`
  - `TableDetailsPage`
  - `DashboardPage`
  - `UtilityPage`
- Archetypes must be expandable and linear:
  - support one or many fields
  - support one or many tables
  - support multiple panels where needed
- `AdvancedPagePlugin` exists only for cases that truly cannot fit section-based composition.

### 5. Declarative UI, Task, And Result Model
- Standard plugins declare:
  - `PageSpec`
  - `SectionSpec`
  - `FieldSpec`
  - `ActionSpec`
  - `TaskSpec`
  - `ResultSpec`
- Standard field families:
  - text
  - multiline text
  - choice
  - toggle
  - numeric
  - path
  - file list
  - table
  - preview
- Standard result surfaces:
  - summary
  - output text
  - details text
  - details table
  - preview
- Standard actions:
  - primary
  - secondary
  - row
  - context

### 6. CLI And Headless Command Standardization
- Make command declaration a first-class part of the SDK, not an optional ad hoc plugin method.
- Every plugin must explicitly declare one of:
  - no command surface
  - one or more CLI/headless commands
  - command aliases if needed for compatibility during migration
- Add `CommandSpec` to the SDK with:
  - command id
  - title
  - description
  - input schema/argument mapping
  - worker function
  - result serializer/adapter
  - optional workflow exposure
- Standard plugins declare commands alongside page/task specs so GUI and CLI are part of the same contract.
- Replace scattered manual headless registration with SDK-owned command registration.
- Command behavior standards:
  - structured inputs only
  - structured outputs only
  - shell-owned logging/progress through standard context
  - no GUI-state dependence in command handlers
- Headless-only tools use `HeadlessOnlyPlugin`; mixed GUI/headless tools declare both page spec and command spec in one place.

### 7. Shared Translation And Direction Contract
- Standardize on one global translation/direction helper exposed by the SDK.
- Replace plugin-local `_pt` / `_tr` wrappers with one blessed helper surface, for example:
  - `tr(...)`
  - `bind_tr(...)`
  - direction-aware helper access through the same SDK namespace
- Base classes own:
  - language-change reapplication
  - direction refresh for RTL/LTR layout
  - text lookup fallback behavior
- Plugin authors should define keys and defaults, not language refresh plumbing.
- All standard plugins must use sidecar locale files for primary text.

### 8. Shared Task And Menu Abstractions
- Add an SDK task runner above `services.run_task(...)`.
- Standard task definitions include:
  - task id
  - ready/running/success/error text keys
  - payload builder
  - worker function
  - result adapter
- The shell remains owner of:
  - spinner
  - progress bar
  - status text
  - activity log
- Add one global context-menu system:
  - `show_context_menu(...)`
  - `attach_list_context_menu(...)`
  - `attach_table_context_menu(...)`
- Direct `QMenu(...)` becomes non-standard outside SDK internals.

### 9. Validation, Audit, And Policy Enforcement
- Expand validation so it checks structural SDK compliance, not just style hygiene.
- Audit rules must flag:
  - legacy plugin contract usage
  - direct `QMenu(...)`
  - plugin-local `_pt` / `_tr`
  - manual command registration outside the SDK contract
  - plugin-local progress bars for ordinary tasks
  - raw styling of standard controls
  - manual page scaffolding outside SDK/advanced contract
- First-party policy:
  - no new non-SDK plugins
  - no new non-SDK command definitions
  - migrated plugins must pass strict audit before completion

### 10. Documentation Restructure
- Move expanded documentation into a structured `./docs/` tree.
- Keep root [README.md](/home/debeski/depy/tools/DNgine/README.md) as the project entrypoint that links into `./docs/`.
- Move version history into root [CHANGELOG.md](/home/debeski/depy/tools/DNgine/CHANGELOG.md).
- Documentation structure should include:
  - app usage docs
  - plugin authoring docs
  - SDK reference docs
  - CLI/headless command docs
  - migration guides
  - UI/UX standards and semantic-class rules
- Remove raw `QtPlugin` guidance from author docs and replace it with SDK-only examples.
- Provide canonical examples for:
  - simple form task plugin
  - file batch preview plugin
  - table/details plugin
  - advanced custom plugin
  - headless-only plugin
  - GUI + CLI dual-surface plugin

### 11. Two-Phase Delivery
- Phase 1: engine groundwork
  - build `dngine.sdk`
  - add section/archetype system
  - add command spec system
  - add global translation/direction helper surface
  - add shared task/menu abstractions
  - add validation/audit rules
  - restructure docs into `./docs/` and move history to `CHANGELOG.md`
- Phase 2: plugin migration
  - migrate first-party plugins one by one
  - bring both GUI and headless command surfaces to SDK standard
  - start with image/media tools, then simple task tools, then larger table/system tools
  - any unmigrated plugin remains intentionally non-standard until converted

## Public APIs / Interfaces
- New public namespace: `dngine.sdk`
- New plugin contracts:
  - `StandardPlugin`
  - `TaskPlugin`
  - `BatchFilePlugin`
  - `TableToolPlugin`
  - `HeadlessOnlyPlugin`
  - `AdvancedPagePlugin`
- New declarative specs:
  - `PageSpec`
  - `SectionSpec`
  - `FieldSpec`
  - `ActionSpec`
  - `TaskSpec`
  - `CommandSpec`
  - `ResultSpec`
- New shared helpers:
  - global `tr` / `bind_tr` and direction-aware access from the SDK
  - `show_context_menu(...)`
  - `attach_list_context_menu(...)`
  - `attach_table_context_menu(...)`
- New documentation layout:
  - `README.md` as entrypoint
  - `docs/` as structured docs home
  - `CHANGELOG.md` as version history

## Test Plan
- SDK tests:
  - archetypes render correct standard sections
  - section composition supports variable field/table/preview counts
  - translation and RTL/LTR direction reapply automatically
  - task specs drive shell progress/logging consistently
  - command specs register and execute consistently
- Validation tests:
  - SDK plugins pass strict validation
  - legacy plugins classify as `legacy_contract`
  - advanced plugins classify as `advanced_contract`
  - banned direct patterns are flagged
- Command tests:
  - GUI/headless dual-surface plugins declare commands from the same contract
  - headless-only plugins run without GUI state
  - command outputs serialize in a standard format
- Migration tests:
  - migrated plugins render and run correctly
  - migrated plugins no longer use legacy authoring or command-registration patterns
- Docs/tests for scaffolding:
  - scaffolded SDK plugin passes validation out of the box
  - scaffolded GUI and CLI examples match the documented contract

## Assumptions And Defaults
- No backwards compatibility is preserved at the plugin authoring-contract level.
- Breaking old plugins is acceptable because it exposes non-standard code for migration.
- Archetypes are expandable ordered compositions of standard sections, not rigid templates.
- `AdvancedPagePlugin` is a narrow explicit exception path, not a general alternative.
- CLI/headless command declaration is part of the standard plugin contract, not an afterthought.
- Root `README.md` remains concise and points to structured `docs/`; root `CHANGELOG.md` becomes the canonical version-history file.
