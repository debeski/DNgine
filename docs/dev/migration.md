# Legacy Migration Notes

Legacy plugins are intentionally visible as non-standard until migrated.

## Migration Priorities

1. image and media tools
2. simple file and task tools
3. table and review tools
4. larger system pages

## Migration Rules

- move imports to `dngine.sdk`
- replace local translation helpers with the shared SDK helper surface
- replace manual commands with declared `CommandSpec`
- replace manual `QMenu(...)` usage with shared context-menu helpers
- replace handwritten page scaffolding with declarative SDK components when the plugin is an ordinary tool
- fall back to explicit `PageSpec` only when the declarative layer is not yet sufficient

## Current Preferred Target

For ordinary tools, the preferred migration target is now:

1. `DeclarativePlugin`
2. page declared as a small dict of `Text` / `Choice` / `FileList` / `Preview` / `Action` / `Output`
3. shared task helpers from `dngine.sdk`
4. shared public media helpers from `dngine.sdk` instead of `dngine.core.media_utils`

The current reference example is `dngine/plugins/core_tools/image_tagger.py`.

- it keeps the full plugin around the `~200` line mark including task logic
- it uses shared payload/task/result helpers instead of local `_before_run`, `_on_result`, and `_on_error` boilerplate
- it stays on the public SDK surface for both UI and media helpers

## Controllerless Table/Details Pattern

Use `fp_plugins/media_images/plugins/smart_exif_editor.py` as the current strict-SDK example for review-style tools.

- keep the plugin on `StandardPlugin` and declare the full page through `PageSpec`
- place a `file_list` section directly before `table_details_pane` to get the shared split layout
- drive dropped files, add/clear actions, and selection state through `FileListBehaviorSpec`
- use `StateReactionSpec` to refresh table headers, rows, details text, and field placeholders from runtime state
- keep ordinary run/undo flows on `TaskBindingSpec` plus the shared result pane instead of plugin-local task widgets
- use `configure_page(...)` only for lightweight widget tuning that the shared spec surface does not already cover

This remains a valid strict-SDK pattern, but it is no longer the default starting point for simpler tools.
