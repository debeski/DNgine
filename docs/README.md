# DNgine Docs

This directory is the structured documentation home for DNgine.

## Sections

- [App usage](./app/README.md)
- [Developer docs](./dev/README.md)
- [UI and UX standards](./design/ui-ux-standards.md)
- [Changelog](../CHANGELOG.md)

## Current Direction

DNgine is moving toward a strict plugin SDK:

- plugin authors should use `dngine.sdk`
- page layout, task flow, CLI commands, translation, and menus are owned by the shell
- legacy plugins are intentionally non-standard until migrated
