import sys

from dngine.core.cli import build_parser, execute_cli
from dngine.main import launch_gui


def main() -> int:
    if len(sys.argv) == 1:
        return launch_gui()

    parser = build_parser()
    parsed = parser.parse_args()
    if parsed.command in {None, "gui"}:
        return launch_gui(
            initial_plugin_id=getattr(parsed, "plugin_id", None),
            start_minimized=getattr(parsed, "start_minimized", False),
            force_visible=getattr(parsed, "force_visible", False),
        )
    return execute_cli(parsed)


if __name__ == "__main__":
    raise SystemExit(main())
