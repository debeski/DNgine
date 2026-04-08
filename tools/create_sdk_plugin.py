from __future__ import annotations

import argparse
from pathlib import Path


PLUGIN_TEMPLATE = """from __future__ import annotations

from dngine.sdk import (
    ActionSpec,
    CommandSpec,
    FieldSpec,
    PageSpec,
    ResultSpec,
    SectionSpec,
    {base_class},
    bind_tr,
)


class {class_name}({base_class}):
    plugin_id = "{plugin_id}"
    name = "{display_name}"
    description = "{description}"
    category = "{category}"

    def declare_page_spec(self, services):
        tr = bind_tr(services, self.plugin_id)
        return PageSpec(
            archetype="{archetype}",
            title=tr("title", "{display_name}"),
            description=tr("description", "{description}"),
            sections=(
                SectionSpec(
                    section_id="settings",
                    kind="settings_card",
                    fields=(
                        FieldSpec("input_value", "text", tr("field.input", "Input"), placeholder=tr("field.input.placeholder", "Enter a value")),
                    ),
                ),
                SectionSpec(
                    section_id="actions",
                    kind="actions_row",
                    actions=(
                        ActionSpec("run", tr("action.run", "Run")),
                    ),
                ),
                SectionSpec(
                    section_id="summary",
                    kind="summary_output_pane",
                    description=tr("summary.ready", "Ready."),
                    stretch=1,
                ),
            ),
            result_spec=ResultSpec(
                summary_placeholder=tr("summary.ready", "Ready."),
                output_placeholder=tr("output.placeholder", "Run output appears here."),
            ),
        )

    def declare_command_specs(self, services):
        return (
            CommandSpec(
                command_id="tool.{plugin_id}.run",
                title="Run {display_name}",
                description="{description}",
                worker=lambda context, input_value="": {{"input_value": input_value, "ok": True}},
            ),
        )
"""

EN_TEMPLATE = """{{
  "plugin.name": "{display_name}",
  "plugin.description": "{description}",
  "plugin.category": "{category}",
  "title": "{display_name}",
  "description": "{description}",
  "field.input": "Input",
  "field.input.placeholder": "Enter a value",
  "action.run": "Run",
  "summary.ready": "Ready.",
  "output.placeholder": "Run output appears here."
}}
"""

AR_TEMPLATE = """{{
  "plugin.name": "{display_name}",
  "plugin.description": "{description}",
  "plugin.category": "{category}",
  "title": "{display_name}",
  "description": "{description}",
  "field.input": "Input",
  "field.input.placeholder": "Enter a value",
  "action.run": "Run",
  "summary.ready": "Ready.",
  "output.placeholder": "Run output appears here."
}}
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a strict DNgine SDK plugin scaffold.")
    parser.add_argument("destination", help="Target directory for the scaffold")
    parser.add_argument("plugin_id", help="Stable plugin id")
    parser.add_argument("--class-name", default="", help="Optional class name override")
    parser.add_argument("--display-name", default="", help="Optional display name override")
    parser.add_argument("--description", default="SDK scaffold plugin.")
    parser.add_argument("--category", default="General")
    parser.add_argument("--base-class", default="TaskPlugin")
    parser.add_argument("--archetype", default="simple_form")
    args = parser.parse_args()

    destination = Path(args.destination).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)

    plugin_id = str(args.plugin_id).strip()
    display_name = str(args.display_name or plugin_id.replace("_", " ").title()).strip()
    class_name = str(args.class_name or "".join(part.title() for part in plugin_id.split("_")) + "Plugin").strip()
    module_path = destination / f"{plugin_id}.py"
    module_path.write_text(
        PLUGIN_TEMPLATE.format(
            plugin_id=plugin_id,
            display_name=display_name,
            class_name=class_name,
            description=str(args.description),
            category=str(args.category),
            base_class=str(args.base_class),
            archetype=str(args.archetype),
        ),
        encoding="utf-8",
    )
    module_path.with_name(f"{plugin_id}.en.json").write_text(
        EN_TEMPLATE.format(
            plugin_id=plugin_id,
            display_name=display_name,
            description=str(args.description),
            category=str(args.category),
        ),
        encoding="utf-8",
    )
    module_path.with_name(f"{plugin_id}.ar.json").write_text(
        AR_TEMPLATE.format(
            plugin_id=plugin_id,
            display_name=display_name,
            description=str(args.description),
            category=str(args.category),
        ),
        encoding="utf-8",
    )
    print(module_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
