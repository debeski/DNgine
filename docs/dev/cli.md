# CLI And Command Contract

Commands are now part of the standard plugin contract.

## Rules

- every plugin explicitly declares whether it has a command surface
- command handlers accept structured keyword arguments
- command handlers return structured results
- command handlers do not depend on GUI state
- logging and progress go through the standard command context

## Standard Surface

- declare commands through SDK `CommandSpec`
- register commands through SDK-owned registration helpers
- expose headless-only tools through `HeadlessOnlyPlugin`
- expose mixed GUI and CLI tools through one shared plugin contract
