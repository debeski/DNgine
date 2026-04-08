from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from pathlib import Path

from PIL import Image
from PySide6.QtWidgets import QMessageBox, QTableWidget

from dngine.core.table_utils import configure_resizable_table
from dngine.sdk import (
    ActionSpec,
    ChoiceOption,
    EnableRule,
    FieldSpec,
    FileListBehaviorSpec,
    PageSpec,
    ResultSpec,
    SectionSpec,
    SUPPORTED_IMAGE_FILTER,
    StandardPlugin,
    StateReactionSpec,
    StateSpec,
    TaskBindingSpec,
    TaskSpec,
    _pt,
    bind_tr,
)

WRITEABLE_SUFFIXES = {".jpg", ".jpeg", ".tif", ".tiff"}
EDITABLE_TAGS = {
    "description": 270,
    "artist": 315,
    "copyright": 33432,
    "datetime": 306,
    "datetime_original": 36867,
    "datetime_digitized": 36868,
}
CLEARABLE_TAGS = {
    "description": {EDITABLE_TAGS["description"]},
    "artist": {EDITABLE_TAGS["artist"]},
    "copyright": {EDITABLE_TAGS["copyright"]},
    "datetime": {
        EDITABLE_TAGS["datetime"],
        EDITABLE_TAGS["datetime_original"],
        EDITABLE_TAGS["datetime_digitized"],
    },
}
PRESERVED_STRIP_TAGS = {274, *EDITABLE_TAGS.values()}
GPS_TAG_ID = 34853
CAMERA_TAG_IDS = {
    271,
    272,
    33434,
    33437,
    34850,
    34855,
    37377,
    37378,
    37380,
    37381,
    37382,
    37383,
    37384,
    37385,
    37386,
    37500,
    40961,
    42036,
}


def _undo_root(services) -> Path:
    return Path(services.data_root) / "smart_exif_undo"


def _undo_manifest_path(services) -> Path:
    return _undo_root(services) / "manifest.json"


def _undo_available(services) -> bool:
    return _undo_manifest_path(services).exists()


def _stringify(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8", errors="ignore").strip("\x00")
        except Exception:
            return ""
    return str(value)


def _parse_datetime_text(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).strftime("%Y:%m:%d %H:%M:%S")
    except Exception:
        pass
    try:
        from dateutil import parser as date_parser

        return date_parser.parse(text).strftime("%Y:%m:%d %H:%M:%S")
    except Exception:
        return ""


def _supported_for_write(path: str) -> bool:
    return Path(path).suffix.lower() in WRITEABLE_SUFFIXES


def _metadata_snapshot(path: str) -> dict[str, object]:
    with Image.open(path) as image:
        exif = image.getexif()
        return {
            "path": path,
            "description": _stringify(exif.get(EDITABLE_TAGS["description"])),
            "artist": _stringify(exif.get(EDITABLE_TAGS["artist"])),
            "copyright": _stringify(exif.get(EDITABLE_TAGS["copyright"])),
            "datetime": _stringify(exif.get(EDITABLE_TAGS["datetime_original"]) or exif.get(EDITABLE_TAGS["datetime"])),
            "has_gps": GPS_TAG_ID in exif,
        }


def _editable_updates(options: dict[str, object]) -> dict[int, str]:
    date_text = _parse_datetime_text(str(options.get("date_time", "")))
    updates: dict[int, str] = {}
    if str(options.get("description", "")).strip() and not bool(options.get("clear_description", False)):
        updates[EDITABLE_TAGS["description"]] = str(options["description"]).strip()
    if str(options.get("artist", "")).strip() and not bool(options.get("clear_artist", False)):
        updates[EDITABLE_TAGS["artist"]] = str(options["artist"]).strip()
    if str(options.get("copyright", "")).strip() and not bool(options.get("clear_copyright", False)):
        updates[EDITABLE_TAGS["copyright"]] = str(options["copyright"]).strip()
    if date_text and not bool(options.get("clear_datetime", False)):
        updates[EDITABLE_TAGS["datetime"]] = date_text
        updates[EDITABLE_TAGS["datetime_original"]] = date_text
        updates[EDITABLE_TAGS["datetime_digitized"]] = date_text
    return updates


def _cleared_tag_ids(options: dict[str, object]) -> set[int]:
    cleared: set[int] = set()
    for field_key, tag_ids in CLEARABLE_TAGS.items():
        if bool(options.get(f"clear_{field_key}", False)):
            cleared.update(tag_ids)
    return cleared


def _apply_exif_options(path: str, target_path: str, options: dict[str, object]) -> tuple[bool, str]:
    if not _supported_for_write(path):
        return False, "Unsupported format for safe EXIF writing."

    with Image.open(path) as image:
        source = image.copy()
        exif = source.getexif()
        updates = _editable_updates(options)
        cleared_tag_ids = _cleared_tag_ids(options)

        if bool(options.get("strip_non_essential", False)):
            for tag_id in list(exif.keys()):
                if tag_id not in PRESERVED_STRIP_TAGS:
                    try:
                        del exif[tag_id]
                    except Exception:
                        continue

        if bool(options.get("clear_gps", False)) and GPS_TAG_ID in exif:
            del exif[GPS_TAG_ID]

        if bool(options.get("clear_camera", False)):
            for tag_id in CAMERA_TAG_IDS:
                if tag_id in exif:
                    del exif[tag_id]

        for tag_id in cleared_tag_ids:
            if tag_id in exif:
                del exif[tag_id]

        for tag_id, value in updates.items():
            exif[tag_id] = value

        try:
            source.save(target_path, exif=exif.tobytes())
        except Exception as exc:
            return False, str(exc)
    return True, ""


def run_smart_exif_task(
    context,
    services,
    plugin_id: str,
    files: list[str],
    write_mode: str,
    options: dict[str, object],
    output_dir: str | None = None,
):
    _ = plugin_id
    mode = str(write_mode or "copy").strip().lower()
    if mode == "copy" and not output_dir:
        raise ValueError("Output folder is required for copy mode.")

    manifest_entries: list[dict[str, object]] = []
    backup_root = _undo_root(services) / "backups"
    if mode == "in_place":
        shutil.rmtree(_undo_root(services), ignore_errors=True)
        backup_root.mkdir(parents=True, exist_ok=True)
    elif output_dir:
        os.makedirs(output_dir, exist_ok=True)

    written_files: list[str] = []
    skipped: list[str] = []
    for index, file_path in enumerate(files, start=1):
        context.progress(index / float(max(1, len(files))))
        context.log(_pt(lambda key, default=None, **kwargs: services.plugin_text("smart_exif", key, default, **kwargs), "log.processing", "Updating metadata for {file}...", file=os.path.basename(file_path)))
        target_path = file_path
        if mode == "copy":
            target_path = os.path.join(str(output_dir), f"smart_exif_{Path(file_path).name}")
        else:
            backup_name = f"{index:04d}.bin"
            backup_path = backup_root / backup_name
            backup_path.write_bytes(Path(file_path).read_bytes())

        ok, message = _apply_exif_options(file_path, target_path, options)
        if not ok:
            skipped.append(f"{os.path.basename(file_path)}: {message}")
            if mode == "in_place":
                backup_candidate = backup_root / f"{index:04d}.bin"
                backup_candidate.unlink(missing_ok=True)
            context.log(_pt(lambda key, default=None, **kwargs: services.plugin_text("smart_exif", key, default, **kwargs), "log.skipped", "Skipped {file}: {reason}", file=os.path.basename(file_path), reason=message), "WARNING")
            continue

        written_files.append(target_path)
        if mode == "in_place":
            manifest_entries.append({"path": file_path, "backup": f"{index:04d}.bin"})

    if mode == "in_place":
        manifest_path = _undo_manifest_path(services)
        if manifest_entries:
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            manifest_path.write_text(json.dumps({"files": manifest_entries}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        else:
            shutil.rmtree(_undo_root(services), ignore_errors=True)

    context.log(
        _pt(
            lambda key, default=None, **kwargs: services.plugin_text("smart_exif", key, default, **kwargs),
            "log.done",
            "SMART EXIF editing finished. Updated {count} files and skipped {skipped}.",
            count=len(written_files),
            skipped=len(skipped),
        )
    )
    return {
        "count": len(written_files),
        "skipped_count": len(skipped),
        "files": written_files,
        "skipped": skipped,
        "output_dir": output_dir or "",
        "write_mode": mode,
        "undo_available": mode == "in_place" and bool(manifest_entries),
    }


def undo_smart_exif_task(context, services, plugin_id: str):
    _ = plugin_id
    manifest_path = _undo_manifest_path(services)
    if not manifest_path.exists():
        raise ValueError("No SMART EXIF undo snapshot is available.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    restored = 0
    errors: list[str] = []
    for index, entry in enumerate(manifest.get("files", []), start=1):
        context.progress(index / float(max(1, len(manifest.get("files", [])))))
        target_path = Path(str(entry.get("path", "")))
        backup_name = str(entry.get("backup", "")).strip()
        backup_path = _undo_root(services) / "backups" / backup_name
        try:
            target_path.write_bytes(backup_path.read_bytes())
            restored += 1
        except Exception as exc:
            errors.append(f"{target_path.name}: {exc}")
    if not errors:
        shutil.rmtree(_undo_root(services), ignore_errors=True)
    return {
        "restored_count": restored,
        "error_count": len(errors),
        "errors": errors,
        "undo_available": bool(errors),
    }


def _options_payload(runtime) -> dict[str, object]:
    return {
        "description": str(runtime.value("description", "") or "").strip(),
        "artist": str(runtime.value("artist", "") or "").strip(),
        "copyright": str(runtime.value("copyright", "") or "").strip(),
        "date_time": str(runtime.value("date_time", "") or "").strip(),
        "clear_description": bool(runtime.value("clear_description", False)),
        "clear_artist": bool(runtime.value("clear_artist", False)),
        "clear_copyright": bool(runtime.value("clear_copyright", False)),
        "clear_datetime": bool(runtime.value("clear_datetime", False)),
        "clear_gps": bool(runtime.value("clear_gps", False)),
        "clear_camera": bool(runtime.value("clear_camera", False)),
        "strip_non_essential": bool(runtime.value("strip_non_essential", False)),
    }


def _bool_text(runtime, value: bool) -> str:
    return _pt(runtime.tr, "details.yes", "Yes") if value else _pt(runtime.tr, "details.no", "No")


def _mode_text(runtime, value: str | None = None) -> str:
    mode = str(value or runtime.value("write_mode", "copy") or "copy").strip().lower()
    defaults = {
        "copy": "Write copies",
        "in_place": "Edit in place",
    }
    return _pt(runtime.tr, f"mode.{mode}", defaults.get(mode, mode))


def _display_value(runtime, value: object) -> str:
    text = str(value or "").strip()
    return text or _pt(runtime.tr, "details.none", "(empty)")


def _apply_snapshot_placeholders(runtime, snapshot: dict[str, object] | None) -> None:
    fields = (
        ("description", "description", "placeholder.description"),
        ("artist", "artist", "placeholder.artist"),
        ("copyright", "copyright", "placeholder.copyright"),
        ("datetime", "date_time", "placeholder.datetime"),
    )
    for snapshot_key, field_id, placeholder_key in fields:
        value = ""
        if snapshot is not None:
            value = str(snapshot.get(snapshot_key, "") or "").strip()
        runtime.set_placeholder(field_id, value or _pt(runtime.tr, placeholder_key, "Current value appears here"))


def _pending_display(runtime, field_key: str, current_value: str) -> str:
    options = _options_payload(runtime)
    if field_key in {"description", "artist", "copyright"} and bool(options.get(f"clear_{field_key}", False)):
        return _pt(runtime.tr, "table.pending_clear", "(clear)")
    if field_key == "datetime":
        if bool(options.get("clear_datetime", False)):
            return _pt(runtime.tr, "table.pending_clear", "(clear)")
        return _parse_datetime_text(str(options.get("date_time", ""))) or current_value
    pending = str(options.get(field_key, "") or "").strip()
    return pending or current_value


def _refresh_metadata_projection(runtime, _changed_key: str) -> None:
    runtime.set_table_headers(
        "metadata_table",
        [
            _pt(runtime.tr, "table.field", "Field"),
            _pt(runtime.tr, "table.current", "Current"),
            _pt(runtime.tr, "table.pending", "Pending"),
        ],
    )

    path = runtime.selected_file("files")
    if not path:
        runtime.set_table_rows("metadata_table", [])
        _apply_snapshot_placeholders(runtime, None)
        runtime.set_details_text(
            "metadata_details",
            _pt(runtime.tr, "details.empty", "Select an image to inspect its current metadata and pending changes."),
        )
        return

    try:
        snapshot = _metadata_snapshot(path)
    except Exception as exc:
        runtime.set_table_rows("metadata_table", [])
        _apply_snapshot_placeholders(runtime, None)
        runtime.set_details_text(
            "metadata_details",
            _pt(runtime.tr, "details.error", "Metadata preview failed: {message}", message=str(exc)),
        )
        return

    _apply_snapshot_placeholders(runtime, snapshot)

    current_gps = bool(snapshot.get("has_gps", False))
    rows = [
        [
            _pt(runtime.tr, "table.description", "Description"),
            _display_value(runtime, snapshot.get("description")),
            _display_value(runtime, _pending_display(runtime, "description", str(snapshot.get("description", "") or ""))),
        ],
        [
            _pt(runtime.tr, "table.artist", "Artist"),
            _display_value(runtime, snapshot.get("artist")),
            _display_value(runtime, _pending_display(runtime, "artist", str(snapshot.get("artist", "") or ""))),
        ],
        [
            _pt(runtime.tr, "table.copyright", "Copyright"),
            _display_value(runtime, snapshot.get("copyright")),
            _display_value(runtime, _pending_display(runtime, "copyright", str(snapshot.get("copyright", "") or ""))),
        ],
        [
            _pt(runtime.tr, "table.datetime", "Date / Time"),
            _display_value(runtime, snapshot.get("datetime")),
            _display_value(runtime, _pending_display(runtime, "datetime", str(snapshot.get("datetime", "") or ""))),
        ],
        [
            _pt(runtime.tr, "table.gps", "GPS Present"),
            _bool_text(runtime, current_gps),
            _bool_text(runtime, False if runtime.value("clear_gps", False) else current_gps),
        ],
    ]
    runtime.set_table_rows("metadata_table", rows)

    details = [
        f"{_pt(runtime.tr, 'details.path', 'File')}: {path}",
        f"{_pt(runtime.tr, 'details.mode', 'Write mode')}: {_mode_text(runtime)}",
        f"{_pt(runtime.tr, 'details.clear_description', 'Clear description')}: {_bool_text(runtime, bool(runtime.value('clear_description', False)))}",
        f"{_pt(runtime.tr, 'details.clear_artist', 'Clear artist')}: {_bool_text(runtime, bool(runtime.value('clear_artist', False)))}",
        f"{_pt(runtime.tr, 'details.clear_copyright', 'Clear copyright')}: {_bool_text(runtime, bool(runtime.value('clear_copyright', False)))}",
        f"{_pt(runtime.tr, 'details.clear_datetime', 'Clear date / time')}: {_bool_text(runtime, bool(runtime.value('clear_datetime', False)))}",
        f"{_pt(runtime.tr, 'details.gps', 'Clear GPS')}: {_bool_text(runtime, bool(runtime.value('clear_gps', False)))}",
        f"{_pt(runtime.tr, 'details.camera', 'Clear camera tags')}: {_bool_text(runtime, bool(runtime.value('clear_camera', False)))}",
        f"{_pt(runtime.tr, 'details.strip', 'Strip non-essential')}: {_bool_text(runtime, bool(runtime.value('strip_non_essential', False)))}",
    ]
    runtime.set_details_text("metadata_details", "\n".join(details))


def _build_run_payload(runtime) -> dict[str, object] | None:
    files = runtime.files("files")
    if not files:
        runtime.warn(
            _pt(runtime.tr, "error.missing_input.title", "Missing Input"),
            _pt(runtime.tr, "error.missing_files", "Add at least one supported image first."),
        )
        return None

    write_mode = str(runtime.value("write_mode", "copy") or "copy").strip().lower()
    output_dir: str | None = None
    if write_mode == "copy":
        output_dir = runtime.choose_directory(_pt(runtime.tr, "dialog.select_output", "Select Output Folder"))
        if not output_dir:
            return None
    else:
        confirmed = QMessageBox.question(
            runtime.page,
            _pt(runtime.tr, "dialog.in_place.title", "Edit files in place?"),
            _pt(
                runtime.tr,
                "dialog.in_place.body",
                "This will update the original files directly. DNgine will keep a last-run undo snapshot. Continue?",
            ),
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return None

    return {
        "services": runtime.services,
        "plugin_id": runtime.plugin_id,
        "files": files,
        "write_mode": write_mode,
        "options": _options_payload(runtime),
        "output_dir": output_dir,
    }


def _before_run(runtime) -> None:
    runtime.clear_output()
    runtime.set_summary(_pt(runtime.tr, "summary.running", "Running SMART EXIF..."))


def _handle_run_result(runtime, payload: object) -> None:
    result = dict(payload)
    skipped_lines = "\n".join(f"- {entry}" for entry in result.get("skipped", []))
    output = _pt(
        runtime.tr,
        "summary.done",
        "SMART EXIF editing complete.\nFiles updated: {count}\nSkipped: {skipped}\nMode: {mode}",
        count=result["count"],
        skipped=result["skipped_count"],
        mode=_mode_text(runtime, str(result.get("write_mode", "copy"))),
    )
    if result.get("output_dir"):
        output = f"{output}\n{_pt(runtime.tr, 'summary.output', 'Output folder')}: {result['output_dir']}"
    if skipped_lines:
        output = f"{output}\n\n{_pt(runtime.tr, 'summary.skipped', 'Skipped files:')}\n{skipped_lines}"

    runtime.set_summary(_pt(runtime.tr, "summary.complete", "SMART EXIF editing complete."))
    runtime.set_output(output)
    runtime.set_value("undo_ready", bool(result.get("undo_available")))
    _refresh_metadata_projection(runtime, "")
    runtime.services.record_run(
        runtime.plugin_id,
        "SUCCESS",
        _pt(runtime.tr, "run.success", "Updated {count} image metadata entries", count=result["count"]),
    )


def _handle_task_error(runtime, payload: object) -> None:
    if isinstance(payload, dict):
        message = str(payload.get("message") or _pt(runtime.tr, "error.unknown", "Unknown SMART EXIF error"))
    else:
        message = str(payload or _pt(runtime.tr, "error.unknown", "Unknown SMART EXIF error"))
    runtime.set_summary(_pt(runtime.tr, "summary.failed", "SMART EXIF editing failed."))
    runtime.set_output(message)
    runtime.set_value("undo_ready", _undo_available(runtime.services))
    runtime.services.record_run(runtime.plugin_id, "ERROR", message[:500])
    runtime.services.log(_pt(runtime.tr, "log.failed", "SMART EXIF editing failed."), "ERROR")


def _finish_task(runtime) -> None:
    runtime.set_value("undo_ready", _undo_available(runtime.services))


def _build_undo_payload(runtime) -> dict[str, object] | None:
    if not _undo_available(runtime.services):
        runtime.set_value("undo_ready", False)
        QMessageBox.information(
            runtime.page,
            _pt(runtime.tr, "undo.none.title", "No undo snapshot"),
            _pt(runtime.tr, "undo.none.body", "There is no SMART EXIF in-place undo snapshot to restore."),
        )
        return None
    return {
        "services": runtime.services,
        "plugin_id": runtime.plugin_id,
    }


def _before_undo(runtime) -> None:
    runtime.clear_output()
    runtime.set_summary(_pt(runtime.tr, "undo.running", "Restoring the last SMART EXIF undo snapshot..."))


def _handle_undo_result(runtime, payload: object) -> None:
    result = dict(payload)
    errors = "\n".join(f"- {entry}" for entry in result.get("errors", []))
    output = _pt(
        runtime.tr,
        "undo.done",
        "SMART EXIF undo restored {count} files.",
        count=result["restored_count"],
    )
    if errors:
        output = f"{output}\n\n{_pt(runtime.tr, 'undo.errors', 'Files still failing:')}\n{errors}"

    runtime.set_summary(_pt(runtime.tr, "undo.complete", "SMART EXIF undo complete."))
    runtime.set_output(output)
    runtime.set_value("undo_ready", bool(result.get("undo_available")))
    _refresh_metadata_projection(runtime, "")
    runtime.services.record_run(
        runtime.plugin_id,
        "SUCCESS",
        _pt(runtime.tr, "undo.success", "Restored {count} image files", count=result["restored_count"]),
    )


class SmartExifEditorPlugin(StandardPlugin):
    plugin_id = "smart_exif"
    name = "SMART EXIF Editor"
    description = "Batch edit practical EXIF tags, strip sensitive metadata, and optionally undo the last in-place update."
    category = "Media & Images"

    def declare_page_spec(self, services):
        tr = bind_tr(services, self.plugin_id)
        writable_extensions = tuple(sorted(WRITEABLE_SUFFIXES))
        reaction_dependencies = (
            "files",
            "selected_file_row",
            "write_mode",
            "description",
            "artist",
            "copyright",
            "date_time",
            "clear_description",
            "clear_artist",
            "clear_copyright",
            "clear_datetime",
            "clear_gps",
            "clear_camera",
            "strip_non_essential",
        )
        return PageSpec(
            archetype="file_table_details",
            title=tr("title", "SMART EXIF Editor"),
            description=tr(
                "description",
                "Batch edit practical EXIF fields, strip sensitive metadata, and keep an undo path for the last in-place run.",
            ),
            sections=(
                SectionSpec(
                    section_id="settings",
                    kind="settings_card",
                    fields=(
                        FieldSpec(
                            "write_mode",
                            "choice",
                            tr("label.mode", "Write Mode"),
                            default="copy",
                            options=(
                                ChoiceOption("copy", tr("mode.copy", "Write copies")),
                                ChoiceOption("in_place", tr("mode.in_place", "Edit in place")),
                            ),
                        ),
                        FieldSpec("description", "text", tr("label.description", "Description"), placeholder=tr("placeholder.description", "Current value appears here")),
                        FieldSpec("clear_description", "toggle", tr("label.clear_description", "Clear Description"), placeholder=tr("option.clear_field", "Clear")),
                        FieldSpec("artist", "text", tr("label.artist", "Artist"), placeholder=tr("placeholder.artist", "Current value appears here")),
                        FieldSpec("clear_artist", "toggle", tr("label.clear_artist", "Clear Artist"), placeholder=tr("option.clear_field", "Clear")),
                        FieldSpec("copyright", "text", tr("label.copyright", "Copyright"), placeholder=tr("placeholder.copyright", "Current value appears here")),
                        FieldSpec("clear_copyright", "toggle", tr("label.clear_copyright", "Clear Copyright"), placeholder=tr("option.clear_field", "Clear")),
                        FieldSpec("date_time", "text", tr("label.datetime", "Date / Time"), placeholder=tr("placeholder.datetime", "Current value appears here")),
                        FieldSpec("clear_datetime", "toggle", tr("label.clear_datetime", "Clear Date / Time"), placeholder=tr("option.clear_field", "Clear")),
                        FieldSpec("clear_gps", "toggle", tr("label.gps", "GPS"), placeholder=tr("option.clear_gps", "Clear GPS")),
                        FieldSpec("clear_camera", "toggle", tr("label.camera", "Camera Tags"), placeholder=tr("option.clear_camera", "Clear camera / vendor tags")),
                        FieldSpec("strip_non_essential", "toggle", tr("label.cleanup", "Metadata Cleanup"), placeholder=tr("option.strip", "Strip non-essential metadata")),
                    ),
                ),
                SectionSpec(
                    section_id="file_actions",
                    kind="actions_row",
                    actions=(
                        ActionSpec("add_files", tr("add", "Add Images"), kind="secondary"),
                        ActionSpec("clear_files", tr("clear", "Clear All"), kind="secondary"),
                    ),
                ),
                SectionSpec(
                    section_id="files_panel",
                    kind="file_list",
                    fields=(FieldSpec("files", "file_list", tr("label.files", "Files"), allowed_extensions=writable_extensions),),
                    stretch=1,
                ),
                SectionSpec(
                    section_id="inspection",
                    kind="table_details_pane",
                    fields=(
                        FieldSpec("metadata_table", "table", "", semantic_class="output_class"),
                        FieldSpec(
                            "metadata_details",
                            "multiline",
                            "",
                            placeholder=tr("details.empty", "Select an image to inspect its current metadata and pending changes."),
                            semantic_class="output_class",
                        ),
                    ),
                    stretch=2,
                ),
                SectionSpec(
                    section_id="run_actions",
                    kind="actions_row",
                    actions=(
                        ActionSpec("run", tr("run", "Run SMART EXIF")),
                        ActionSpec("undo_run", tr("undo", "Undo Last In-Place Run"), kind="secondary"),
                    ),
                ),
                SectionSpec(
                    section_id="result",
                    kind="summary_output_pane",
                    description=tr("summary.ready", "Choose images and configure the metadata update to begin."),
                    semantic_class="output_class",
                    stretch=1,
                ),
            ),
            result_spec=ResultSpec(
                summary_placeholder=tr("summary.ready", "Choose images and configure the metadata update to begin."),
                output_placeholder=tr("summary.placeholder", "SMART EXIF activity will appear here."),
                details_placeholder=tr("details.empty", "Select an image to inspect its current metadata and pending changes."),
            ),
            state=(
                StateSpec("files", []),
                StateSpec("selected_file_row", -1),
                StateSpec("undo_ready", _undo_available(services)),
            ),
            task_specs=(
                TaskSpec(
                    task_id="run_smart_exif",
                    worker=run_smart_exif_task,
                    running_text=tr("summary.running", "Running SMART EXIF..."),
                    success_text=tr("summary.complete", "SMART EXIF editing complete."),
                    error_text=tr("summary.failed", "SMART EXIF editing failed."),
                ),
                TaskSpec(
                    task_id="undo_smart_exif",
                    worker=undo_smart_exif_task,
                    running_text=tr("undo.running", "Restoring the last SMART EXIF undo snapshot..."),
                    success_text=tr("undo.complete", "SMART EXIF undo complete."),
                    error_text=tr("summary.failed", "SMART EXIF editing failed."),
                ),
            ),
            enable_rules=(
                EnableRule(("clear_files", "run"), predicate=lambda runtime: bool(runtime.files("files")), depends_on=("files",)),
                EnableRule(("undo_run",), predicate=lambda runtime: bool(runtime.value("undo_ready", False)), depends_on=("undo_ready",)),
            ),
            file_behaviors=(
                FileListBehaviorSpec(
                    widget_id="files",
                    state_id="files",
                    add_action_id="add_files",
                    clear_action_id="clear_files",
                    selection_state_id="selected_file_row",
                    dialog_title=tr("dialog.select_images", "Select Images"),
                    file_filter=SUPPORTED_IMAGE_FILTER,
                    remove_action_text=tr("list.remove", "Remove from list"),
                ),
            ),
            state_reactions=(
                StateReactionSpec(
                    depends_on=reaction_dependencies,
                    handler=_refresh_metadata_projection,
                ),
            ),
            task_bindings=(
                TaskBindingSpec(
                    action_id="run",
                    task_id="run_smart_exif",
                    payload_builder=_build_run_payload,
                    before_run=_before_run,
                    on_result=_handle_run_result,
                    on_error=_handle_task_error,
                    on_finished=_finish_task,
                    disable_actions=("run", "undo_run"),
                ),
                TaskBindingSpec(
                    action_id="undo_run",
                    task_id="undo_smart_exif",
                    payload_builder=_build_undo_payload,
                    before_run=_before_undo,
                    on_result=_handle_undo_result,
                    on_error=_handle_task_error,
                    on_finished=_finish_task,
                    disable_actions=("run", "undo_run"),
                ),
            ),
        )

    def configure_page(self, page, services) -> None:
        super().configure_page(page, services)
        metadata_table = page.generated_widgets.get("metadata_table")
        if isinstance(metadata_table, QTableWidget):
            metadata_table.verticalHeader().setVisible(False)
            metadata_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            metadata_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
            configure_resizable_table(
                metadata_table,
                stretch_columns={1, 2},
                resize_to_contents_columns={0},
                default_widths={0: 120, 1: 220, 2: 220},
            )
