# UI And UX Standards

DNgine plugins should feel like one product, not a collection of separate apps.

## Standards

- reuse shared page chrome and semantic classes
- use right-click context menus for secondary actions
- support drag and drop where relevant
- keep shell-owned loading, progress, and activity behavior
- keep layouts clear in both English and Arabic
- prefer predictable section ordering over custom page choreography

## Non-Standard Patterns

- direct per-plugin control styling
- manual progress bars for ordinary tasks
- raw `QMenu(...)` in plugin pages
- plugin-local translation wrappers
- manual command registration outside the SDK
