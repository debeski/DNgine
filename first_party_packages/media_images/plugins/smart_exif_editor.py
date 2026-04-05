from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from pathlib import Path

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from dngine.core.media_utils import SUPPORTED_IMAGE_FILTER
from dngine.core.page_style import apply_page_chrome, apply_semantic_class
from dngine.core.plugin_api import QtPlugin, bind_tr, safe_tr
from dngine.core.table_utils import configure_resizable_table
from dngine.core.widgets import DroppableListWidget, ScrollSafeComboBox


QComboBox = ScrollSafeComboBox

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


def _pt(translate, key: str, default: str | None = None, **kwargs) -> str:
    return safe_tr(translate, key, default, **kwargs)


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


def _metadata_snapshot(path: str) -> dict[str, str]:
    with Image.open(path) as image:
        exif = image.getexif()
        return {
            "path": path,
            "description": _stringify(exif.get(EDITABLE_TAGS["description"])),
            "artist": _stringify(exif.get(EDITABLE_TAGS["artist"])),
            "copyright": _stringify(exif.get(EDITABLE_TAGS["copyright"])),
            "datetime": _stringify(exif.get(EDITABLE_TAGS["datetime_original"]) or exif.get(EDITABLE_TAGS["datetime"])),
            "has_gps": "yes" if GPS_TAG_ID in exif else "no",
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


class SmartExifEditorPlugin(QtPlugin):
    plugin_id = "smart_exif"
    name = "SMART EXIF Editor"
    description = "Batch edit practical EXIF tags, strip sensitive metadata, and optionally undo the last in-place update."
    category = "Media & Images"

    def create_widget(self, services) -> QWidget:
        return SmartExifEditorPage(services, self.plugin_id)


class SmartExifEditorPage(QWidget):
    def __init__(self, services, plugin_id: str):
        super().__init__()
        self.services = services
        self.plugin_id = plugin_id
        self.tr = bind_tr(services, plugin_id)
        self.files: list[str] = []
        self._build_ui()
        self._apply_texts()
        self.services.i18n.language_changed.connect(self._handle_language_change)
        self.services.theme_manager.theme_changed.connect(self._handle_theme_change)

    def _pt(self, key: str, default: str | None = None, **kwargs) -> str:
        return _pt(self.tr, key, default, **kwargs)

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 28, 28, 28)
        outer.setSpacing(16)

        self.title_label = QLabel()
        outer.addWidget(self.title_label)

        self.description_label = QLabel()
        self.description_label.setWordWrap(True)
        outer.addWidget(self.description_label)

        self.settings_card = QFrame()
        settings_layout = QGridLayout(self.settings_card)
        settings_layout.setContentsMargins(16, 14, 16, 14)
        settings_layout.setHorizontalSpacing(12)
        settings_layout.setVerticalSpacing(10)

        self.mode_label = QLabel()
        settings_layout.addWidget(self.mode_label, 0, 0)
        self.mode_combo = QComboBox()
        self.mode_combo.currentIndexChanged.connect(self._refresh_metadata_view)
        settings_layout.addWidget(self.mode_combo, 0, 1)

        self.description_field_label = QLabel()
        settings_layout.addWidget(self.description_field_label, 1, 0)
        self.description_input = QLineEdit()
        self.description_input.textChanged.connect(self._refresh_metadata_view)
        self.clear_description_checkbox = QCheckBox()
        self.clear_description_checkbox.toggled.connect(self._refresh_metadata_view)
        description_row = QHBoxLayout()
        description_row.addWidget(self.description_input, 1)
        description_row.addWidget(self.clear_description_checkbox, 0)
        settings_layout.addLayout(description_row, 1, 1)

        self.artist_label = QLabel()
        settings_layout.addWidget(self.artist_label, 2, 0)
        self.artist_input = QLineEdit()
        self.artist_input.textChanged.connect(self._refresh_metadata_view)
        self.clear_artist_checkbox = QCheckBox()
        self.clear_artist_checkbox.toggled.connect(self._refresh_metadata_view)
        artist_row = QHBoxLayout()
        artist_row.addWidget(self.artist_input, 1)
        artist_row.addWidget(self.clear_artist_checkbox, 0)
        settings_layout.addLayout(artist_row, 2, 1)

        self.copyright_label = QLabel()
        settings_layout.addWidget(self.copyright_label, 3, 0)
        self.copyright_input = QLineEdit()
        self.copyright_input.textChanged.connect(self._refresh_metadata_view)
        self.clear_copyright_checkbox = QCheckBox()
        self.clear_copyright_checkbox.toggled.connect(self._refresh_metadata_view)
        copyright_row = QHBoxLayout()
        copyright_row.addWidget(self.copyright_input, 1)
        copyright_row.addWidget(self.clear_copyright_checkbox, 0)
        settings_layout.addLayout(copyright_row, 3, 1)

        self.datetime_label = QLabel()
        settings_layout.addWidget(self.datetime_label, 4, 0)
        self.datetime_input = QLineEdit()
        self.datetime_input.textChanged.connect(self._refresh_metadata_view)
        self.clear_datetime_checkbox = QCheckBox()
        self.clear_datetime_checkbox.toggled.connect(self._refresh_metadata_view)
        datetime_row = QHBoxLayout()
        datetime_row.addWidget(self.datetime_input, 1)
        datetime_row.addWidget(self.clear_datetime_checkbox, 0)
        settings_layout.addLayout(datetime_row, 4, 1)

        options_row = QHBoxLayout()
        self.clear_gps_checkbox = QCheckBox()
        self.clear_gps_checkbox.toggled.connect(self._refresh_metadata_view)
        self.clear_camera_checkbox = QCheckBox()
        self.clear_camera_checkbox.toggled.connect(self._refresh_metadata_view)
        self.strip_non_essential_checkbox = QCheckBox()
        self.strip_non_essential_checkbox.toggled.connect(self._refresh_metadata_view)
        options_row.addWidget(self.clear_gps_checkbox)
        options_row.addWidget(self.clear_camera_checkbox)
        options_row.addWidget(self.strip_non_essential_checkbox)
        options_row.addStretch(1)
        settings_layout.addLayout(options_row, 5, 1)

        self.files_label = QLabel()
        settings_layout.addWidget(self.files_label, 6, 0)
        files_row = QHBoxLayout()
        self.add_button = QPushButton()
        self.add_button.clicked.connect(self._add_files)
        self.clear_button = QPushButton()
        self.clear_button.clicked.connect(self._clear_files)
        files_row.addWidget(self.add_button)
        files_row.addWidget(self.clear_button)
        files_row.addStretch(1)
        settings_layout.addLayout(files_row, 6, 1)

        outer.addWidget(self.settings_card)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(splitter, 1)

        left_panel = QWidget()
        apply_semantic_class(left_panel, "transparent_class")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)
        self.file_list = DroppableListWidget(mode="file", allowed_extensions=[".jpg", ".jpeg", ".tif", ".tiff"])
        self.file_list.remove_requested.connect(self._remove_file_at)
        self.file_list.currentRowChanged.connect(self._refresh_metadata_view)
        self.file_list.files_dropped.connect(self._handle_files_dropped)
        left_layout.addWidget(self.file_list, 1)
        splitter.addWidget(left_panel)

        right_panel = QWidget()
        apply_semantic_class(right_panel, "transparent_class")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)

        self.metadata_table = QTableWidget(0, 3)
        self.metadata_table.verticalHeader().setVisible(False)
        self.metadata_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.metadata_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        configure_resizable_table(
            self.metadata_table,
            stretch_columns={1, 2},
            resize_to_contents_columns={0},
            default_widths={0: 120, 1: 220, 2: 220},
        )
        right_layout.addWidget(self.metadata_table, 1)

        self.details_output = QPlainTextEdit()
        self.details_output.setReadOnly(True)
        apply_semantic_class(self.details_output, "output_class")
        right_layout.addWidget(self.details_output, 1)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        controls = QHBoxLayout()
        self.run_button = QPushButton()
        self.run_button.clicked.connect(self._run)
        self.undo_button = QPushButton()
        self.undo_button.clicked.connect(self._run_undo)
        controls.addWidget(self.run_button, 0, Qt.AlignmentFlag.AlignLeft)
        controls.addWidget(self.undo_button, 0, Qt.AlignmentFlag.AlignLeft)
        controls.addStretch(1)
        outer.addLayout(controls)

        self.summary_output = QPlainTextEdit()
        self.summary_output.setReadOnly(True)
        apply_semantic_class(self.summary_output, "output_class")
        outer.addWidget(self.summary_output, 1)

    def _set_combo_items(self, combo: QComboBox, items: list[tuple[str, str]]) -> None:
        current_value = str(combo.currentData() or combo.currentText() or "")
        combo.blockSignals(True)
        combo.clear()
        for value, label in items:
            combo.addItem(label, value)
        index = combo.findData(current_value)
        combo.setCurrentIndex(max(0, index))
        combo.blockSignals(False)

    def _mode_value(self) -> str:
        return str(self.mode_combo.currentData() or self.mode_combo.currentText() or "copy")

    def _options_payload(self) -> dict[str, object]:
        return {
            "description": self.description_input.text().strip(),
            "artist": self.artist_input.text().strip(),
            "copyright": self.copyright_input.text().strip(),
            "date_time": self.datetime_input.text().strip(),
            "clear_description": self.clear_description_checkbox.isChecked(),
            "clear_artist": self.clear_artist_checkbox.isChecked(),
            "clear_copyright": self.clear_copyright_checkbox.isChecked(),
            "clear_datetime": self.clear_datetime_checkbox.isChecked(),
            "clear_gps": self.clear_gps_checkbox.isChecked(),
            "clear_camera": self.clear_camera_checkbox.isChecked(),
            "strip_non_essential": self.strip_non_essential_checkbox.isChecked(),
        }

    def _handle_language_change(self) -> None:
        self._apply_texts()
        self._refresh_file_list()
        self._refresh_metadata_view()

    def _apply_texts(self) -> None:
        self.title_label.setText(self._pt("title", "SMART EXIF Editor"))
        self.description_label.setText(
            self._pt(
                "description",
                "Batch edit practical EXIF fields, strip sensitive metadata, and keep an undo path for the last in-place run.",
            )
        )
        self.mode_label.setText(self._pt("label.mode", "Write Mode"))
        self.description_field_label.setText(self._pt("label.description", "Description"))
        self.artist_label.setText(self._pt("label.artist", "Artist"))
        self.copyright_label.setText(self._pt("label.copyright", "Copyright"))
        self.datetime_label.setText(self._pt("label.datetime", "Date / Time"))
        self.clear_description_checkbox.setText(self._pt("option.clear_field", "Clear"))
        self.clear_artist_checkbox.setText(self._pt("option.clear_field", "Clear"))
        self.clear_copyright_checkbox.setText(self._pt("option.clear_field", "Clear"))
        self.clear_datetime_checkbox.setText(self._pt("option.clear_field", "Clear"))
        self.description_input.setPlaceholderText(self._pt("placeholder.description", "Current value appears here"))
        self.artist_input.setPlaceholderText(self._pt("placeholder.artist", "Current value appears here"))
        self.copyright_input.setPlaceholderText(self._pt("placeholder.copyright", "Current value appears here"))
        self.datetime_input.setPlaceholderText(self._pt("placeholder.datetime", "Current value appears here"))
        self.clear_gps_checkbox.setText(self._pt("option.clear_gps", "Clear GPS"))
        self.clear_camera_checkbox.setText(self._pt("option.clear_camera", "Clear camera / vendor tags"))
        self.strip_non_essential_checkbox.setText(self._pt("option.strip", "Strip non-essential metadata"))
        self.files_label.setText(self._pt("label.files", "Files"))
        self.file_list.set_remove_action_text(self._pt("list.remove", "Remove from list"))
        self._set_combo_items(
            self.mode_combo,
            [
                ("copy", self._pt("mode.copy", "Write copies")),
                ("in_place", self._pt("mode.in_place", "Edit in place")),
            ],
        )
        self.add_button.setText(self._pt("add", "Add Images"))
        self.clear_button.setText(self._pt("clear", "Clear All"))
        self.run_button.setText(self._pt("run", "Run SMART EXIF"))
        self.undo_button.setText(self._pt("undo", "Undo Last In-Place Run"))
        self.undo_button.setEnabled(_undo_available(self.services))
        self.metadata_table.setHorizontalHeaderLabels(
            [
                self._pt("table.field", "Field"),
                self._pt("table.current", "Current"),
                self._pt("table.pending", "Pending"),
            ]
        )
        self.summary_output.setPlaceholderText(self._pt("summary.placeholder", "SMART EXIF activity will appear here."))
        self._apply_theme_styles()
        self._refresh_metadata_view()

    def _apply_theme_styles(self) -> None:
        palette = self.services.theme_manager.current_palette()
        apply_page_chrome(
            palette,
            title_label=self.title_label,
            description_label=self.description_label,
            cards=(self.settings_card,),
            title_size=26,
            title_weight=700,
            card_radius=14,
        )

    def _handle_theme_change(self, _mode: str) -> None:
        self._apply_theme_styles()

    def _add_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            self._pt("dialog.select_images", "Select Images"),
            str(self.services.default_output_path()),
            SUPPORTED_IMAGE_FILTER,
        )
        if files:
            self._append_files(files)

    def _append_files(self, paths: list[str]) -> None:
        first_new_index: int | None = None
        for path in paths:
            if path not in self.files and _supported_for_write(path):
                if first_new_index is None:
                    first_new_index = len(self.files)
                self.files.append(path)
        self._refresh_file_list()
        if first_new_index is not None:
            self.file_list.setCurrentRow(first_new_index)
        elif self.files and self.file_list.currentRow() < 0:
            self.file_list.setCurrentRow(0)

    def _clear_files(self) -> None:
        self.files = []
        self.file_list.clear()
        self.metadata_table.setRowCount(0)
        self.details_output.clear()
        self._apply_snapshot_placeholders(None)

    def _refresh_file_list(self) -> None:
        self.file_list.clear()
        self.file_list.addItems([os.path.basename(path) for path in self.files])

    def _handle_files_dropped(self, paths: list[str]) -> None:
        self._append_files(paths)

    def _remove_file_at(self, row: int) -> None:
        if row < 0 or row >= len(self.files):
            return
        del self.files[row]
        self._refresh_file_list()
        if not self.files:
            self.metadata_table.setRowCount(0)
            self.details_output.setPlainText(self._pt("details.empty", "Select an image to inspect its current metadata and pending changes."))
            self._apply_snapshot_placeholders(None)
            return
        next_row = min(row, len(self.files) - 1)
        self.file_list.setCurrentRow(next_row)

    def _apply_snapshot_placeholders(self, snapshot: dict[str, str] | None) -> None:
        fields = (
            ("description", self.description_input, "placeholder.description"),
            ("artist", self.artist_input, "placeholder.artist"),
            ("copyright", self.copyright_input, "placeholder.copyright"),
            ("datetime", self.datetime_input, "placeholder.datetime"),
        )
        for field_key, widget, placeholder_key in fields:
            value = ""
            if snapshot is not None:
                value = str(snapshot.get(field_key, "")).strip()
            widget.setPlaceholderText(
                value or self._pt(placeholder_key, "Current value appears here")
            )

    def _pending_display(self, field_key: str, current_value: str) -> str:
        options = self._options_payload()
        if field_key in {"description", "artist", "copyright", "datetime"} and bool(options.get(f"clear_{field_key}", False)):
            return self._pt("table.pending_clear", "(clear)")
        if field_key == "datetime":
            return _parse_datetime_text(str(options.get("date_time", ""))) or current_value
        pending = str(options.get(field_key, "")).strip()
        return pending or current_value

    def _refresh_metadata_view(self) -> None:
        row = self.file_list.currentRow()
        if row < 0 or row >= len(self.files):
            self.metadata_table.setRowCount(0)
            self._apply_snapshot_placeholders(None)
            self.details_output.setPlainText(self._pt("details.empty", "Select an image to inspect its current metadata and pending changes."))
            return
        path = self.files[row]
        try:
            snapshot = _metadata_snapshot(path)
        except Exception as exc:
            self._apply_snapshot_placeholders(None)
            self.details_output.setPlainText(self._pt("details.error", "Metadata preview failed: {message}", message=str(exc)))
            return
        self._apply_snapshot_placeholders(snapshot)

        rows = [
            ("description", self._pt("table.description", "Description"), snapshot["description"]),
            ("artist", self._pt("table.artist", "Artist"), snapshot["artist"]),
            ("copyright", self._pt("table.copyright", "Copyright"), snapshot["copyright"]),
            ("datetime", self._pt("table.datetime", "Date / Time"), snapshot["datetime"]),
            ("has_gps", self._pt("table.gps", "GPS Present"), snapshot["has_gps"]),
        ]
        self.metadata_table.setRowCount(len(rows))
        for row_index, (field_key, label, current_value) in enumerate(rows):
            pending_value = self._pending_display(field_key, current_value) if field_key != "has_gps" else ("no" if self.clear_gps_checkbox.isChecked() else current_value)
            for column, value in enumerate((label, current_value or self._pt("details.none", "(empty)"), pending_value or self._pt("details.none", "(empty)"))):
                item = QTableWidgetItem(str(value))
                item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                self.metadata_table.setItem(row_index, column, item)
        details = [
            f"{self._pt('details.path', 'File')}: {path}",
            f"{self._pt('details.mode', 'Write mode')}: {self.mode_combo.currentText()}",
            f"{self._pt('details.clear_description', 'Clear description')}: {self._pt('details.yes', 'Yes') if self.clear_description_checkbox.isChecked() else self._pt('details.no', 'No')}",
            f"{self._pt('details.clear_artist', 'Clear artist')}: {self._pt('details.yes', 'Yes') if self.clear_artist_checkbox.isChecked() else self._pt('details.no', 'No')}",
            f"{self._pt('details.clear_copyright', 'Clear copyright')}: {self._pt('details.yes', 'Yes') if self.clear_copyright_checkbox.isChecked() else self._pt('details.no', 'No')}",
            f"{self._pt('details.clear_datetime', 'Clear date / time')}: {self._pt('details.yes', 'Yes') if self.clear_datetime_checkbox.isChecked() else self._pt('details.no', 'No')}",
            f"{self._pt('details.gps', 'Clear GPS')}: {self._pt('details.yes', 'Yes') if self.clear_gps_checkbox.isChecked() else self._pt('details.no', 'No')}",
            f"{self._pt('details.camera', 'Clear camera tags')}: {self._pt('details.yes', 'Yes') if self.clear_camera_checkbox.isChecked() else self._pt('details.no', 'No')}",
            f"{self._pt('details.strip', 'Strip non-essential')}: {self._pt('details.yes', 'Yes') if self.strip_non_essential_checkbox.isChecked() else self._pt('details.no', 'No')}",
        ]
        self.details_output.setPlainText("\n".join(details))

    def _run(self) -> None:
        if not self.files:
            QMessageBox.warning(
                self,
                self._pt("error.missing_input.title", "Missing Input"),
                self._pt("error.missing_files", "Add at least one supported image first."),
            )
            return
        write_mode = self._mode_value()
        output_dir: str | None = None
        if write_mode == "copy":
            output_dir = QFileDialog.getExistingDirectory(
                self,
                self._pt("dialog.select_output", "Select Output Folder"),
                str(self.services.default_output_path()),
            )
            if not output_dir:
                return
        else:
            confirmed = QMessageBox.question(
                self,
                self._pt("dialog.in_place.title", "Edit files in place?"),
                self._pt(
                    "dialog.in_place.body",
                    "This will update the original files directly. DNgine will keep a last-run undo snapshot. Continue?",
                ),
            )
            if confirmed != QMessageBox.StandardButton.Yes:
                return

        self.run_button.setEnabled(False)
        self.summary_output.clear()
        self.services.run_task(
            lambda context: run_smart_exif_task(
                context,
                self.services,
                self.plugin_id,
                list(self.files),
                write_mode,
                self._options_payload(),
                output_dir,
            ),
            on_result=self._handle_result,
            on_error=self._handle_error,
            on_finished=self._finish_run,
        )

    def _handle_result(self, payload: object) -> None:
        result = dict(payload)
        skipped_lines = "\n".join(f"- {entry}" for entry in result.get("skipped", []))
        summary = self._pt(
            "summary.done",
            "SMART EXIF editing complete.\nFiles updated: {count}\nSkipped: {skipped}\nMode: {mode}",
            count=result["count"],
            skipped=result["skipped_count"],
            mode=result["write_mode"],
        )
        if result.get("output_dir"):
            summary = f"{summary}\n{self._pt('summary.output', 'Output folder')}: {result['output_dir']}"
        if skipped_lines:
            summary = f"{summary}\n\n{self._pt('summary.skipped', 'Skipped files:')}\n{skipped_lines}"
        self.summary_output.setPlainText(summary)
        self.undo_button.setEnabled(bool(result.get("undo_available")))
        self._refresh_metadata_view()
        self.services.record_run(self.plugin_id, "SUCCESS", self._pt("run.success", "Updated {count} image metadata entries", count=result["count"]))

    def _handle_error(self, payload: object) -> None:
        message = payload.get("message", self._pt("error.unknown", "Unknown SMART EXIF error")) if isinstance(payload, dict) else str(payload)
        self.summary_output.setPlainText(message)
        self.services.record_run(self.plugin_id, "ERROR", message[:500])
        self.services.log(self._pt("log.failed", "SMART EXIF editing failed."), "ERROR")

    def _finish_run(self) -> None:
        self.run_button.setEnabled(True)
        self.undo_button.setEnabled(_undo_available(self.services))

    def _run_undo(self) -> None:
        if not _undo_available(self.services):
            QMessageBox.information(
                self,
                self._pt("undo.none.title", "No undo snapshot"),
                self._pt("undo.none.body", "There is no SMART EXIF in-place undo snapshot to restore."),
            )
            return
        self.undo_button.setEnabled(False)
        self.services.run_task(
            lambda context: undo_smart_exif_task(context, self.services, self.plugin_id),
            on_result=self._handle_undo_result,
            on_error=self._handle_error,
            on_finished=self._finish_run,
        )

    def _handle_undo_result(self, payload: object) -> None:
        result = dict(payload)
        errors = "\n".join(f"- {entry}" for entry in result.get("errors", []))
        summary = self._pt(
            "undo.done",
            "SMART EXIF undo restored {count} files.",
            count=result["restored_count"],
        )
        if errors:
            summary = f"{summary}\n\n{self._pt('undo.errors', 'Files still failing:')}\n{errors}"
        self.summary_output.setPlainText(summary)
        self.undo_button.setEnabled(bool(result.get("undo_available")))
        self._refresh_metadata_view()
