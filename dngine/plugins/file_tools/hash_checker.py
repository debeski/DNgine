from __future__ import annotations

import hashlib
import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from dngine.core.page_style import apply_page_chrome
from dngine.core.plugin_api import QtPlugin, bind_tr, tr
from dngine.core.widgets import PathLineEdit


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


def calculate_file_hashes_task(context, services, plugin_id: str, file_path: str):
    target = Path(file_path)
    if not target.is_file():
        raise ValueError(tr(services, plugin_id, "error.not_file", "Choose a valid file to analyze."))

    file_size = target.stat().st_size
    md5_hasher = hashlib.md5()
    sha256_hasher = hashlib.sha256()
    chunk_size = 1024 * 1024
    processed = 0

    context.log(tr(services, plugin_id, "log.start", "Calculating hashes for '{file}'...", file=str(target)))
    with target.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            md5_hasher.update(chunk)
            sha256_hasher.update(chunk)
            processed += len(chunk)
            if file_size > 0:
                context.progress(min(processed / float(file_size), 1.0))

    context.progress(1.0)
    md5_value = md5_hasher.hexdigest()
    sha256_value = sha256_hasher.hexdigest()
    context.log(
        tr(
            services,
            plugin_id,
            "log.done",
            "Hashing complete for '{file}'.",
            file=target.name,
        )
    )
    return {
        "file_path": str(target),
        "file_name": target.name,
        "size_bytes": file_size,
        "size_label": _format_file_size(file_size),
        "md5": md5_value,
        "sha256": sha256_value,
    }


class HashCheckerPlugin(QtPlugin):
    plugin_id = "hash_checker"
    name = "Hash Checker"
    description = "Calculate MD5 and SHA-256 for a file, then cross-check a pasted hash against that selected file."
    category = "File Utilities"
    preferred_icon = "fingerprint"

    def create_widget(self, services) -> QWidget:
        return HashCheckerPage(services, self.plugin_id)


class HashCheckerPage(QWidget):
    def __init__(self, services, plugin_id: str):
        super().__init__()
        self.services = services
        self.plugin_id = plugin_id
        self.tr = bind_tr(services, plugin_id)
        self._latest_result: dict[str, str | int] | None = None
        self._last_verification_message: str | None = None
        self._pending_verification = False
        self._build_ui()
        self.services.i18n.language_changed.connect(self._refresh)
        self.services.theme_manager.theme_changed.connect(self._handle_theme_change)

    def _build_ui(self) -> None:
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(28, 28, 28, 28)
        self.main_layout.setSpacing(16)

        self.title_label = QLabel()
        self.main_layout.addWidget(self.title_label)

        self.desc_label = QLabel()
        self.desc_label.setWordWrap(True)
        self.main_layout.addWidget(self.desc_label)

        file_row = QHBoxLayout()
        file_row.setSpacing(10)
        self.file_input = PathLineEdit(mode="file")
        self.file_input.textChanged.connect(self._handle_file_changed)
        file_row.addWidget(self.file_input, 1)
        self.browse_button = QPushButton()
        self.browse_button.clicked.connect(self._browse_file)
        file_row.addWidget(self.browse_button)
        self.main_layout.addLayout(file_row)

        hash_row = QHBoxLayout()
        hash_row.setSpacing(10)
        self.hash_label = QLabel()
        self.hash_label.setFixedWidth(90)
        hash_row.addWidget(self.hash_label)
        self.hash_input = QLineEdit()
        hash_row.addWidget(self.hash_input, 1)
        self.main_layout.addLayout(hash_row)

        controls = QHBoxLayout()
        controls.setSpacing(12)
        self.run_button = QPushButton()
        self.run_button.clicked.connect(self._run)
        controls.addWidget(self.run_button, 0, Qt.AlignmentFlag.AlignLeft)

        self.verify_button = QPushButton()
        self.verify_button.clicked.connect(self._verify)
        controls.addWidget(self.verify_button, 0, Qt.AlignmentFlag.AlignLeft)

        self.copy_md5_button = QPushButton()
        self.copy_md5_button.setEnabled(False)
        self.copy_md5_button.clicked.connect(lambda: self._copy_hash("md5"))
        controls.addWidget(self.copy_md5_button, 0, Qt.AlignmentFlag.AlignLeft)

        self.copy_sha_button = QPushButton()
        self.copy_sha_button.setEnabled(False)
        self.copy_sha_button.clicked.connect(lambda: self._copy_hash("sha256"))
        controls.addWidget(self.copy_sha_button, 0, Qt.AlignmentFlag.AlignLeft)

        self.main_layout.addLayout(controls)

        self.summary_card = QFrame()
        summary_layout = QVBoxLayout(self.summary_card)
        summary_layout.setContentsMargins(16, 14, 16, 14)
        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        summary_layout.addWidget(self.summary_label)
        self.main_layout.addWidget(self.summary_card)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.main_layout.addWidget(self.output, 1)

        self._refresh()

    def _refresh(self) -> None:
        self.title_label.setText(self.tr("title", "Hash Checker"))
        self.desc_label.setText(
            self.tr(
                "description",
                "Calculate MD5 and SHA-256 for a file, then verify a pasted hash against the same selected file.",
            )
        )
        self.file_input.setPlaceholderText(self.tr("file.placeholder", "Select a file to analyze..."))
        self.browse_button.setText(self.tr("browse", "Browse"))
        self.hash_label.setText(self.tr("hash.label", "Hash"))
        self.hash_input.setPlaceholderText(
            self.tr("hash.placeholder", "Paste an MD5 or SHA-256 value to verify...")
        )
        self.run_button.setText(self.tr("run.button", "Calculate Hashes"))
        self.verify_button.setText(self.tr("verify.button", "Verify Hash"))
        self.copy_md5_button.setText(self.tr("copy.md5", "Copy MD5"))
        self.copy_sha_button.setText(self.tr("copy.sha256", "Copy SHA-256"))
        if self._latest_result:
            self._render_output()
        else:
            self.summary_label.setText(self.tr("summary.initial", "Choose a file to calculate its hashes."))
            self.output.setPlaceholderText(
                self.tr("output.placeholder", "MD5, SHA-256, and verification details will appear here.")
            )
        self._apply_theme_styles()

    def _apply_theme_styles(self) -> None:
        palette = self.services.theme_manager.current_palette()
        apply_page_chrome(
            palette,
            title_label=self.title_label,
            description_label=self.desc_label,
            cards=(self.summary_card,),
            summary_label=self.summary_label,
        )

    def _handle_theme_change(self, _mode: str) -> None:
        self._apply_theme_styles()

    def _handle_file_changed(self, value: str) -> None:
        latest_path = str((self._latest_result or {}).get("file_path", ""))
        if os.path.normpath(value.strip()) == os.path.normpath(latest_path):
            return
        self._latest_result = None
        self._last_verification_message = None
        self._pending_verification = False
        self.copy_md5_button.setEnabled(False)
        self.copy_sha_button.setEnabled(False)
        self.summary_label.setText(self.tr("summary.initial", "Choose a file to calculate its hashes."))
        self.output.clear()

    def _browse_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("dialog.browse", "Select File To Analyze"),
            str(self.services.default_output_path()),
        )
        if file_path:
            self.file_input.setText(file_path)

    def _run(self) -> None:
        target_path = self.file_input.text().strip()
        if not target_path:
            QMessageBox.warning(
                self,
                self.tr("dialog.missing.title", "Missing Input"),
                self.tr("dialog.missing.file", "Choose a file to analyze."),
            )
            return

        self._start_hash_run()

    def _verify(self) -> None:
        target_path = self.file_input.text().strip()
        expected_hash = self.hash_input.text().strip()
        if not target_path:
            QMessageBox.warning(
                self,
                self.tr("dialog.missing.title", "Missing Input"),
                self.tr("dialog.missing.file", "Choose a file to analyze."),
            )
            return
        if not expected_hash:
            QMessageBox.warning(
                self,
                self.tr("dialog.missing.title", "Missing Input"),
                self.tr("dialog.missing.hash", "Paste an MD5 or SHA-256 value to verify."),
            )
            return

        latest_path = str((self._latest_result or {}).get("file_path", ""))
        if self._latest_result and os.path.normpath(target_path) == os.path.normpath(latest_path):
            self._apply_verification()
            return

        self._pending_verification = True
        self._start_hash_run()

    def _start_hash_run(self) -> None:
        target_path = self.file_input.text().strip()
        self.run_button.setEnabled(False)
        self.verify_button.setEnabled(False)
        self.copy_md5_button.setEnabled(False)
        self.copy_sha_button.setEnabled(False)
        self._last_verification_message = None
        self.summary_label.setText(self.tr("summary.running", "Calculating file hashes..."))
        self.output.clear()
        self.services.run_task(
            lambda context: calculate_file_hashes_task(context, self.services, self.plugin_id, target_path),
            on_result=self._handle_result,
            on_error=self._handle_error,
            on_finished=self._finish_run,
        )

    def _handle_result(self, payload: object) -> None:
        self._latest_result = dict(payload)
        self.copy_md5_button.setEnabled(True)
        self.copy_sha_button.setEnabled(True)
        if self._pending_verification:
            self._pending_verification = False
            self._apply_verification()
            return

        self.summary_label.setText(
            self.tr(
                "summary.done",
                "Calculated MD5 and SHA-256 for '{file}'.",
                file=str(self._latest_result.get("file_name", "")),
            )
        )
        self._render_output()
        self.services.record_run(
            self.plugin_id,
            "SUCCESS",
            self.tr(
                "summary.done",
                "Calculated MD5 and SHA-256 for '{file}'.",
                file=str(self._latest_result.get("file_name", "")),
            ),
        )

    def _handle_error(self, payload: object) -> None:
        self._pending_verification = False
        message = payload.get("message", "Unknown hash error") if isinstance(payload, dict) else str(payload)
        self.summary_label.setText(message)
        self.output.setPlainText(message)
        self.services.record_run(self.plugin_id, "ERROR", message[:500])
        self.services.log(self.tr("log.failed", "Hash calculation failed."), "ERROR")

    def _finish_run(self) -> None:
        self.run_button.setEnabled(True)
        self.verify_button.setEnabled(True)

    def _render_output(self, verification_message: str | None = None) -> None:
        if not self._latest_result:
            self.output.clear()
            return

        verification_text = verification_message or self._last_verification_message or self.tr(
            "verify.none",
            "Paste an MD5 or SHA-256 value and click Verify Hash to cross-check it against this file.",
        )
        lines = [
            f"{self.tr('output.header.file', 'File')}: {self._latest_result['file_path']}",
            f"{self.tr('output.header.size', 'Size')}: {self._latest_result['size_label']}",
            "",
            f"{self.tr('output.header.md5', 'MD5')}: {self._latest_result['md5']}",
            f"{self.tr('output.header.sha256', 'SHA-256')}: {self._latest_result['sha256']}",
            "",
            f"{self.tr('output.header.verification', 'Verification')}: {verification_text}",
        ]
        self.output.setPlainText("\n".join(lines))

    def _apply_verification(self) -> None:
        if not self._latest_result:
            return

        expected_hash = _normalize_hash(self.hash_input.text())
        if not expected_hash:
            message = self.tr("verify.none", "Paste an MD5 or SHA-256 value and click Verify Hash to cross-check it against this file.")
            self._last_verification_message = message
            self.summary_label.setText(message)
            self._render_output(message)
            return

        if len(expected_hash) not in {32, 64} or any(char not in "0123456789abcdef" for char in expected_hash):
            message = self.tr("verify.invalid", "The provided hash is not a valid MD5 or SHA-256 value.")
            self._last_verification_message = message
            self.summary_label.setText(message)
            self._render_output(message)
            self.services.record_run(self.plugin_id, "WARNING", message)
            return

        md5_value = str(self._latest_result["md5"])
        sha256_value = str(self._latest_result["sha256"])
        if expected_hash == md5_value:
            message = self.tr(
                "verify.match.md5",
                "Match confirmed. The selected file matches the pasted MD5 hash.",
            )
            self._last_verification_message = message
            self.summary_label.setText(message)
            self._render_output(message)
            self.services.record_run(self.plugin_id, "SUCCESS", message)
            return

        if expected_hash == sha256_value:
            message = self.tr(
                "verify.match.sha256",
                "Match confirmed. The selected file matches the pasted SHA-256 hash.",
            )
            self._last_verification_message = message
            self.summary_label.setText(message)
            self._render_output(message)
            self.services.record_run(self.plugin_id, "SUCCESS", message)
            return

        message = self.tr(
            "verify.mismatch",
            "No match. The pasted hash does not match the selected file.",
        )
        self._last_verification_message = message
        self.summary_label.setText(message)
        self._render_output(message)
        self.services.record_run(self.plugin_id, "WARNING", message)

    def _copy_hash(self, algorithm: str) -> None:
        if not self._latest_result:
            return
        value = str(self._latest_result.get(algorithm, ""))
        if not value:
            return
        QApplication.clipboard().setText(value)
        message = self.tr("copy.done", "Copied {algorithm} to the clipboard.", algorithm=algorithm.upper())
        self.summary_label.setText(message)
        self._render_output(self._last_verification_message)
