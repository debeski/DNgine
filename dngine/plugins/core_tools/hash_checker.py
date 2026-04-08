from __future__ import annotations

import hashlib
import os
from pathlib import Path

from dngine.sdk import (
    Action,
    CommandSpec,
    DeclarativePlugin,
    DeclarativePlugin,
    Output,
    Path as PathField,
    PayloadRequirement,
    Text,
    _pt,
    before_task_run,
    bind_tr,
    build_runtime_payload,
    copy_to_clipboard,
    handle_task_error,
    handle_task_success,
    safe_tr,
)


def _format_file_size(size_bytes: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(max(size_bytes, 0))
    unit_index = 0
    while size >= 1024.0 and unit_index < len(units) - 1:
        size /= 1024.0
        unit_index += 1
    if unit_index == 0:
        return f"{int(size)} {units[unit_index]}"
    return f"{size:.2f} {units[unit_index]}"


def _normalize_hash(value: str) -> str:
    return "".join(str(value or "").strip().lower().split())


def _normalize_path(path_text: str) -> str:
    text = str(path_text or "").strip()
    if not text:
        return ""
    try:
        return os.path.normpath(str(Path(text).expanduser().resolve()))
    except Exception:
        return os.path.normpath(text)


def _done_summary(translate, file_name: str) -> str:
    return safe_tr(
        translate,
        "summary.done",
        "Calculated MD5 and SHA-256 for '{file}'.",
        file=file_name,
    )


def _verification_details(
    result: dict[str, object],
    expected_hash: str,
    *,
    translate=None,
) -> dict[str, object]:
    normalized = _normalize_hash(expected_hash)
    if not normalized:
        return {
            "status": "empty",
            "match": False,
            "algorithm": "",
            "message": safe_tr(
                translate,
                "verify.none",
                "Paste an MD5 or SHA-256 value and click Verify Hash to cross-check it against this file.",
            ),
        }

    if len(normalized) not in {32, 64} or any(char not in "0123456789abcdef" for char in normalized):
        return {
            "status": "invalid",
            "match": False,
            "algorithm": "",
            "message": safe_tr(
                translate,
                "verify.invalid",
                "The provided hash is not a valid MD5 or SHA-256 value.",
            ),
        }

    md5_value = str(result.get("md5", "") or "")
    sha256_value = str(result.get("sha256", "") or "")
    if normalized == md5_value:
        return {
            "status": "match",
            "match": True,
            "algorithm": "md5",
            "message": safe_tr(
                translate,
                "verify.match.md5",
                "Match confirmed. The selected file matches the pasted MD5 hash.",
            ),
        }

    if normalized == sha256_value:
        return {
            "status": "match",
            "match": True,
            "algorithm": "sha256",
            "message": safe_tr(
                translate,
                "verify.match.sha256",
                "Match confirmed. The selected file matches the pasted SHA-256 hash.",
            ),
        }

    return {
        "status": "mismatch",
        "match": False,
        "algorithm": "",
        "message": safe_tr(
            translate,
            "verify.mismatch",
            "No match. The pasted hash does not match the selected file.",
        ),
    }


def calculate_file_hashes_task(context, file_path: str, *, translate=None):
    target = Path(file_path).expanduser()
    if not target.is_file():
        raise ValueError(safe_tr(translate, "error.not_file", "Choose a valid file to analyze."))

    file_size = target.stat().st_size
    md5_hasher = hashlib.md5()
    sha256_hasher = hashlib.sha256()
    chunk_size = 1024 * 1024
    processed = 0

    context.log(safe_tr(translate, "log.start", "Calculating hashes for '{file}'...", file=str(target)))
    with target.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            md5_hasher.update(chunk)
            sha256_hasher.update(chunk)
            processed += len(chunk)
            if file_size > 0:
                context.progress(min(processed / float(file_size), 1.0))

    context.progress(1.0)
    context.log(
        safe_tr(
            translate,
            "log.done",
            "Hashing complete for '{file}'.",
            file=target.name,
        )
    )
    return {
        "file_path": str(target.resolve()),
        "file_name": target.name,
        "size_bytes": file_size,
        "size_label": _format_file_size(file_size),
        "md5": md5_hasher.hexdigest(),
        "sha256": sha256_hasher.hexdigest(),
    }


def _hash_result(runtime) -> dict[str, object]:
    value = runtime.value("latest_result", {})
    return dict(value) if isinstance(value, dict) else {}


def _has_source_path(runtime) -> bool:
    return bool(str(runtime.value("source_path", "") or "").strip())


def _has_hash_result(runtime) -> bool:
    return bool(_hash_result(runtime))


def _matches_current_source(runtime) -> bool:
    current_path = _normalize_path(str(runtime.value("source_path", "") or ""))
    latest_path = _normalize_path(str(_hash_result(runtime).get("file_path", "") or ""))
    return bool(current_path and latest_path and current_path == latest_path)


def _render_output_text(runtime, result: dict[str, object], verification_message: str) -> str:
    lines = [
        f"{_pt(runtime.tr, 'output.header.file', 'File')}: {result.get('file_path', '')}",
        f"{_pt(runtime.tr, 'output.header.size', 'Size')}: {result.get('size_label', '')}",
        "",
        f"{_pt(runtime.tr, 'output.header.md5', 'MD5')}: {result.get('md5', '')}",
        f"{_pt(runtime.tr, 'output.header.sha256', 'SHA-256')}: {result.get('sha256', '')}",
        "",
        f"{_pt(runtime.tr, 'output.header.verification', 'Verification')}: {verification_message}",
    ]
    return "\n".join(lines)


def _handle_source_change(runtime, changed_key: str) -> None:
    if changed_key not in {"", "source_path"}:
        return
    result = _hash_result(runtime)
    if not result:
        if changed_key == "":
            runtime.set_summary_placeholder(_pt(runtime.tr, "summary.initial", "Choose a file to calculate its hashes."))
        return
    if _matches_current_source(runtime):
        return
    runtime.set_value("latest_result", {})
    runtime.set_value("last_verification_message", "")
    runtime.set_summary_placeholder(_pt(runtime.tr, "summary.initial", "Choose a file to calculate its hashes."))
    runtime.clear_output()


def _build_run_payload(runtime) -> dict[str, object] | None:
    return build_runtime_payload(
        runtime,
        required=(
            PayloadRequirement(
                "file_path",
                lambda rt: str(rt.value("source_path", "") or "").strip(),
                _pt(runtime.tr, "dialog.missing.file", "Choose a file to analyze."),
                title=_pt(runtime.tr, "dialog.missing.title", "Missing Input"),
            ),
        ),
        extras={
            "translate": lambda rt: rt.tr,
        },
    )


def _before_run(runtime) -> None:
    runtime.clear_output()
    runtime.set_value("latest_result", {})
    runtime.set_value("last_verification_message", "")
    before_task_run(runtime, _pt(runtime.tr, "summary.running", "Calculating file hashes..."))


def _apply_verification(runtime) -> None:
    result = _hash_result(runtime)
    if not result:
        return
    details = _verification_details(
        result,
        str(runtime.value("expected_hash", "") or ""),
        translate=runtime.tr,
    )
    message = str(details["message"] or "")
    runtime.set_value("last_verification_message", message)
    status = str(details.get("status", "") or "")

    runtime.set_summary(message)
    runtime.set_output(_render_output_text(runtime, result, message))

    if status == "match":
        runtime.services.record_run(runtime.plugin_id, "SUCCESS", message)
    elif status in {"invalid", "mismatch"}:
        runtime.services.record_run(runtime.plugin_id, "WARNING", message)


def _handle_hash_result(runtime, payload: object) -> None:
    result = dict(payload) if isinstance(payload, dict) else {}
    runtime.set_value("latest_result", result)

    if runtime.flag("pending_verify", False):
        runtime.set_flag("pending_verify", False)
        _apply_verification(runtime)
        return

    verification_msg = _verification_details(result, "", translate=runtime.tr)["message"]
    handle_task_success(
        runtime,
        payload,
        summary=lambda res: _done_summary(runtime.tr, str(res.get("file_name", "") or "")),
        output=lambda res: _render_output_text(runtime, res, verification_msg),
    )


def _handle_hash_error(runtime, payload: object) -> None:
    runtime.set_flag("pending_verify", False)
    handle_task_error(
        runtime,
        payload,
        summary=_pt(runtime.tr, "summary.failed", "Hash calculation failed."),
        fallback=_pt(runtime.tr, "error.not_file", "Choose a valid file to analyze."),
        log_message=_pt(runtime.tr, "log.failed", "Hash calculation failed."),
    )


def _browse_source(runtime) -> None:
    file_path = runtime.choose_file(
        _pt(runtime.tr, "dialog.browse", "Select File To Analyze"),
        "",
        start_path=str(runtime.services.default_output_path()),
    )
    if file_path:
        runtime.set_field_value("source_path", file_path)


def _verify_hash(runtime) -> None:
    source_path = str(runtime.value("source_path", "") or "").strip()
    expected_hash = str(runtime.value("expected_hash", "") or "").strip()
    if not source_path:
        runtime.warn(
            _pt(runtime.tr, "dialog.missing.title", "Missing Input"),
            _pt(runtime.tr, "dialog.missing.file", "Choose a file to analyze."),
        )
        return
    if not expected_hash:
        runtime.warn(
            _pt(runtime.tr, "dialog.missing.title", "Missing Input"),
            _pt(runtime.tr, "dialog.missing.hash", "Paste an MD5 or SHA-256 value to verify."),
        )
        return
    if _matches_current_source(runtime) and _has_hash_result(runtime):
        _apply_verification(runtime)
        return
    runtime.set_flag("pending_verify", True)
    run_action = runtime.page.generated_actions.get("run")
    if run_action is not None:
        run_action.click()


def _copy_hash(runtime, algorithm: str) -> None:
    result = _hash_result(runtime)
    value = str(result.get(algorithm, "") or "")
    if not value:
        return
    copy_to_clipboard(value)
    label = "MD5" if algorithm == "md5" else "SHA-256"
    runtime.set_summary(_pt(runtime.tr, "copy.done", "Copied {algorithm} to the clipboard.", algorithm=label))


def _hash_checker_command_worker(context, file_path: str, expected_hash: str = "", *, translate=None):
    result = calculate_file_hashes_task(context, file_path, translate=translate)
    details = _verification_details(result, expected_hash, translate=translate)
    return {
        **result,
        "verification_status": details["status"],
        "verification_match": details["match"],
        "verification_algorithm": details["algorithm"],
        "verification_message": details["message"],
    }


class HashCheckerPlugin(DeclarativePlugin):
    plugin_id = "hash_checker"
    name = "Hash Checker"
    description = "Calculate MD5 and SHA-256 for a file, then cross-check a pasted hash against that selected file."
    category = "Files & Storage"
    preferred_icon = "fingerprint"

    def declare_page(self, services):
        tr = bind_tr(services, self.plugin_id)
        return {
            "source_path": PathField(
                tr("output.header.file", "File"),
                placeholder=tr("file.placeholder", "Select a file to analyze..."),
                mode="file",
                on_change=_handle_source_change,
            ),
            "expected_hash": Text(
                tr("hash.label", "Hash"),
                placeholder=tr("hash.placeholder", "Paste an MD5 or SHA-256 value to verify..."),
            ),
            "browse_source": Action(
                tr("browse", "Browse"),
                kind="secondary",
                on_trigger=_browse_source,
            ),
            "run": Action(
                tr("run.button", "Calculate Hashes"),
                worker=calculate_file_hashes_task,
                payload_builder=_build_run_payload,
                before_run=_before_run,
                on_result=_handle_hash_result,
                on_error=_handle_hash_error,
                running_text=tr("summary.running", "Calculating file hashes..."),
                success_text=tr("summary.done", "Calculated MD5 and SHA-256."),
                error_text=tr("error.not_file", "Choose a valid file to analyze."),
                enabled_when=_has_source_path,
                disable_actions=("run", "verify"),
            ),
            "verify": Action(
                tr("verify.button", "Verify Hash"),
                kind="secondary",
                on_trigger=_verify_hash,
                enabled_when=_has_source_path,
            ),
            "copy_md5": Action(
                tr("copy.md5", "Copy MD5"),
                kind="secondary",
                on_trigger=lambda runtime: _copy_hash(runtime, "md5"),
                enabled_when=_has_hash_result,
            ),
            "copy_sha256": Action(
                tr("copy.sha256", "Copy SHA-256"),
                kind="secondary",
                on_trigger=lambda runtime: _copy_hash(runtime, "sha256"),
                enabled_when=_has_hash_result,
            ),
            "result": Output(
                ready_text=tr("summary.initial", "Choose a file to calculate its hashes."),
                placeholder=tr("output.placeholder", "MD5, SHA-256, and verification details will appear here."),
            ),
        }

    def declare_command_specs(self, services):
        tr = bind_tr(services, self.plugin_id)
        return (
            CommandSpec(
                command_id="tool.hash_checker.calculate",
                title=tr("run.button", "Calculate Hashes"),
                description=tr(
                    "plugin.description",
                    "Calculate MD5 and SHA-256 for a file, then cross-check a pasted hash against that selected file.",
                ),
                worker=lambda context, file_path, expected_hash="": _hash_checker_command_worker(
                    context,
                    file_path,
                    expected_hash,
                    translate=tr,
                ),
                input_adapter=lambda payload, svc=services: {
                    "file_path": str(payload.get("file_path", "")),
                    "expected_hash": str(payload.get("expected_hash", "")),
                },
            ),
        )
