from __future__ import annotations

import os
import shutil
from pathlib import Path

from dngine.core.confirm_dialog import confirm_action
from dngine.sdk import (
    Action,
    CommandSpec,
    DeclarativePlugin,
    FileList,
    Numeric,
    Output,
    _pt,
    bind_tr,
    safe_tr,
)


def _ensure_western(text: str) -> str:
    eastern = "٠١٢٣٤٥٦٧٨٩"
    western = "0123456789"
    return str(text or "").translate(str.maketrans(eastern, western))


def _display_path(path: str) -> str:
    return str(path or "")


def _has_targets(runtime) -> bool:
    return bool(runtime.files("targets"))


def _result_summary(translate, result: dict[str, object]) -> str:
    failed_count = int(result.get("failed_count", 0) or 0)
    skipped_count = int(result.get("skipped_count", 0) or 0)
    if failed_count:
        return safe_tr(
            translate,
            "summary.done.partial",
            "Shredding finished with {deleted} deleted, {skipped} skipped, and {failed} failed items.",
            deleted=result.get("deleted_count", 0),
            skipped=skipped_count,
            failed=failed_count,
        )
    return safe_tr(
        translate,
        "summary.done",
        "Shredding complete. Deleted {deleted} items and skipped {skipped}.",
        deleted=result.get("deleted_count", 0),
        skipped=skipped_count,
    )


def _result_output(translate, result: dict[str, object]) -> str:
    return "\n".join(
        [
            safe_tr(
                translate,
                "output.summary",
                "Targets: {count}\nPasses: {passes}\nDeleted: {deleted}\nSkipped: {skipped}\nFailed: {failed}",
                count=result.get("target_count", 0),
                passes=result.get("passes", 0),
                deleted=result.get("deleted_count", 0),
                skipped=result.get("skipped_count", 0),
                failed=result.get("failed_count", 0),
            ),
            "",
            str(result.get("report_text", "") or ""),
        ]
    ).strip()


def run_shred_task(context, paths: list[str] | list[Path], passes: int, *, translate=None):
    normalized_paths = [Path(path).expanduser() for path in paths]
    total = len(normalized_paths)
    if total <= 0:
        raise ValueError(safe_tr(translate, "dialog.empty.body", "Please add files or folders to shred first."))

    context.log(
        safe_tr(
            translate,
            "log.start",
            "Starting secure shredding of {count} items with {passes} passes...",
            count=_ensure_western(str(total)),
            passes=_ensure_western(str(passes)),
        )
    )

    report_lines: list[str] = []
    deleted_count = 0
    skipped_count = 0
    failed_count = 0

    for index, path in enumerate(normalized_paths, start=1):
        if not path.exists():
            message = safe_tr(translate, "log.not_found", "Skipping non-existent path: {path}", path=str(path))
            context.log(message, "WARNING")
            report_lines.append(message)
            skipped_count += 1
            context.progress(index / float(total))
            continue

        context.log(safe_tr(translate, "log.shredding", "Shredding: {name}", name=path.name))
        try:
            if path.is_file():
                length = path.stat().st_size
                with path.open("wb") as handle:
                    for _ in range(int(passes)):
                        handle.seek(0)
                        if length > 0:
                            handle.write(os.urandom(length))
                        handle.flush()
                        os.fsync(handle.fileno())
                path.unlink()
            elif path.is_dir():
                shutil.rmtree(path)

            message = safe_tr(translate, "log.success", "Permanently deleted: {name}", name=path.name)
            context.log(message)
            report_lines.append(message)
            deleted_count += 1
        except Exception as exc:
            message = safe_tr(
                translate,
                "log.error",
                "Failed to shred {name}: {error}",
                name=path.name,
                error=str(exc),
            )
            context.log(message, "ERROR")
            report_lines.append(message)
            failed_count += 1

        context.progress(index / float(total))

    context.log(safe_tr(translate, "log.done", "Privacy shredding operation complete."))
    return {
        "target_count": total,
        "passes": int(passes),
        "deleted_count": deleted_count,
        "skipped_count": skipped_count,
        "failed_count": failed_count,
        "report_text": "\n".join(report_lines),
    }


def secure_shred_task(context, path: str = "", passes: int = 3, paths: list[str] | None = None, *, translate=None):
    target_paths = list(paths or ())
    if path:
        target_paths.append(path)
    return run_shred_task(context, target_paths, passes, translate=translate)


def _browse_folder(runtime) -> None:
    folder = runtime.choose_directory(
        _pt(runtime.tr, "dialog.select_folder", "Select Folder to Shred")
    )
    if not folder:
        return
    add_paths = getattr(runtime.page, "add_file_paths", None)
    if callable(add_paths):
        add_paths([folder], "targets")


def _build_run_payload(runtime) -> dict[str, object] | None:
    targets = runtime.files("targets")
    if not targets:
        runtime.warn(
            _pt(runtime.tr, "dialog.empty.title", "Queue Empty"),
            _pt(runtime.tr, "dialog.empty.body", "Please add files or folders to shred first."),
        )
        return None
    if not confirm_action(
        runtime.page,
        title=_pt(runtime.tr, "dialog.confirm.title", "Final Warning"),
        body=_pt(
            runtime.tr,
            "dialog.confirm.body",
            "Are you absolutely sure? This will IRREVERSIBLY destroy {count} items. This cannot be undone.",
            count=str(len(targets)),
        ),
        confirm_text=_pt(runtime.tr, "dialog.confirm.confirm", "Wipe Now"),
        cancel_text=_pt(runtime.tr, "dialog.confirm.cancel", "Cancel"),
    ):
        return None
    return {
        "paths": list(targets),
        "passes": int(runtime.value("passes", 3) or 3),
    }


def _before_run(runtime) -> None:
    runtime.set_flag("clear_after_run", False)
    runtime.clear_output()
    runtime.set_summary(_pt(runtime.tr, "summary.running", "Securely wiping selected files and folders..."))


def _handle_result(runtime, payload: object) -> None:
    result = dict(payload) if isinstance(payload, dict) else {}
    runtime.set_flag("clear_after_run", True)
    runtime.set_summary(_result_summary(runtime.tr, result))
    runtime.set_output(_result_output(runtime.tr, result))
    runtime.services.record_run(runtime.plugin_id, "SUCCESS", _result_summary(runtime.tr, result))


def _handle_error(runtime, payload: object) -> None:
    if isinstance(payload, dict):
        message = str(payload.get("message") or _pt(runtime.tr, "error.unknown", "Unknown shred error"))
    else:
        message = str(payload or _pt(runtime.tr, "error.unknown", "Unknown shred error"))
    runtime.set_summary(message)
    runtime.set_output(message)
    runtime.services.record_run(runtime.plugin_id, "ERROR", message[:500])


def _finish_run(runtime) -> None:
    if runtime.flag("clear_after_run", False):
        clear_button = runtime.page.generated_actions.get("targets.__clear")
        if clear_button is not None:
            clear_button.click()
        runtime.set_flag("clear_after_run", False)


class PrivacyShredderPlugin(DeclarativePlugin):
    plugin_id = "privacy_shred"
    name = "Privacy Shredder"
    description = "Securely wipe files and directories by overwriting them multiple times before deletion."
    category = "Network & Security"

    def declare_page(self, services):
        tr = bind_tr(services, self.plugin_id)
        return {
            "add_folder": Action(
                tr("button.add_folder", "Add Folder"),
                kind="secondary",
                on_trigger=lambda runtime: _browse_folder(runtime),
            ),
            "targets": FileList(
                extensions=(),
                mode="any",
                add_label=tr("button.add_files", "Add Files"),
                clear_label=tr("button.clear", "Clear Queue"),
                dialog_title=tr("dialog.select_files", "Select Files to Shred"),
                remove_label=tr("queue.remove", "Remove from queue"),
                display_adapter=_display_path,
            ),
            "passes": Numeric(
                tr("passes.label", "Overwriting Passes:"),
                default=3,
                min_value=1,
                max_value=35,
            ),
            "run": Action(
                tr("button.run", "Wipe Selected Data"),
                enabled=False,
                worker=lambda context, paths, passes: run_shred_task(
                    context, paths, passes, translate=tr
                ),
                payload_builder=_build_run_payload,
                before_run=_before_run,
                on_result=_handle_result,
                on_error=_handle_error,
                on_finished=_finish_run,
                running_text=tr("summary.running", "Securely wiping selected files and folders..."),
                success_text=tr("summary.done", "Privacy shredding operation complete."),
                error_text=tr("error.unknown", "Unknown shred error"),
                disable_actions=("run", "add_folder", "targets.__add", "targets.__clear"),
                enabled_when=lambda runtime: _has_targets(runtime),
            ),
            "result": Output(
                ready_text=tr("summary.initial", "Add files or folders to begin shredding."),
                placeholder=tr("output.placeholder", "Operation logs will appear here..."),
            ),
        }

    def declare_command_specs(self, services):
        tr = bind_tr(services, self.plugin_id)
        return (
            CommandSpec(
                command_id="tool.privacy_shred.run",
                title=tr("button.run", "Wipe Selected Data"),
                description=tr(
                    "plugin.description",
                    "Securely wipe files and directories by overwriting them multiple times before deletion.",
                ),
                worker=lambda context, paths, passes=3: run_shred_task(
                    context,
                    paths,
                    int(passes),
                    translate=tr,
                ),
                input_adapter=lambda payload: {
                    "paths": list(payload.get("paths", []))
                    or ([payload.get("path")] if payload.get("path") else []),
                    "passes": int(payload.get("passes", 3)),
                },
                aliases=("tool.shredder.run",),
            ),
        )


