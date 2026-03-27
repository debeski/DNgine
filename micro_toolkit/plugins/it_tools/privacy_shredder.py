from __future__ import annotations

import os
import shutil
import re
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
    QListWidget,
)

from micro_toolkit.core.plugin_api import QtPlugin


def run_shred_task(context, services, plugin_id: str, paths: list[Path], passes: int):
    def _pt(key: str, default: str, **kwargs) -> str:
        return services.plugin_text(plugin_id, key, default, **kwargs)

    def _ensure_western(text: str) -> str:
        eastern = "٠١٢٣٤٥٦٧٨٩"
        western = "0123456789"
        trans = str.maketrans(eastern, western)
        return text.translate(trans)

    total = len(paths)
    context.log(_pt("log.start", "Starting secure shredding of {count} items with {passes} passes...", count=_ensure_western(str(total)), passes=_ensure_western(str(passes))))
    
    for i, path in enumerate(paths, 1):
        if not path.exists():
            context.log(_pt("log.not_found", "Skipping non-existent path: {path}", path=str(path)), "WARNING")
            continue
            
        context.log(_pt("log.shredding", "Shredding: {name}", name=path.name))
        try:
            if path.is_file():
                length = path.stat().st_size
                with open(path, "wb") as f:
                    for _ in range(passes):
                        f.seek(0)
                        f.write(os.urandom(length))
                        f.flush()
                        os.fsync(f.fileno())
                path.unlink()
            elif path.is_dir():
                shutil.rmtree(path)
            context.log(_pt("log.success", "Permanently deleted: {name}", name=path.name))
        except Exception as e:
            context.log(_pt("log.error", "Failed to shred {name}: {error}", name=path.name, error=str(e)), "ERROR")
            
        context.progress(i / total)

    context.log(_pt("log.done", "Privacy shredding operation complete."))
    return {"shredded_count": _ensure_western(str(total))}


class PrivacyShredderPlugin(QtPlugin):
    plugin_id = "privacy_shred"
    name = "Privacy Shredder"
    description = "Securely wipe files and directories by overwriting them multiple times before deletion."
    category = "IT Utilities"

    def create_widget(self, services) -> QWidget:
        return PrivacyShredderPage(services, self.plugin_id)


class PrivacyShredderPage(QWidget):
    def __init__(self, services, plugin_id: str):
        super().__init__()
        self.services = services
        self.plugin_id = plugin_id
        self._paths: list[Path] = []
        self._build_ui()
        self.services.i18n.language_changed.connect(self._refresh)

    def _pt(self, key: str, default: str, **kwargs) -> str:
        return self.services.plugin_text(self.plugin_id, key, default, **kwargs)

    def _build_ui(self) -> None:
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(28, 28, 28, 28)
        self.main_layout.setSpacing(16)

        self.title_label = QLabel()
        self.title_label.setStyleSheet("font-size: 26px; font-weight: 700; color: #b71c1c;")
        self.main_layout.addWidget(self.title_label)

        self.desc_label = QLabel()
        self.desc_label.setWordWrap(True)
        self.desc_label.setStyleSheet("font-size: 14px; color: #43535c;")
        self.main_layout.addWidget(self.desc_label)

        list_header = QHBoxLayout()
        self.queue_label = QLabel()
        self.queue_label.setStyleSheet("font-weight: 600; color: #10232c;")
        list_header.addWidget(self.queue_label)
        list_header.addStretch()
        
        self.add_file_btn = QPushButton()
        self.add_file_btn.clicked.connect(self._add_files)
        list_header.addWidget(self.add_file_btn)
        
        self.add_dir_btn = QPushButton()
        self.add_dir_btn.clicked.connect(self._add_dir)
        list_header.addWidget(self.add_dir_btn)
        
        self.clear_btn = QPushButton()
        self.clear_btn.clicked.connect(self._clear_queue)
        list_header.addWidget(self.clear_btn)
        self.main_layout.addLayout(list_header)

        self.path_list = QListWidget()
        self.main_layout.addWidget(self.path_list, 1)

        pass_row = QHBoxLayout()
        self.passes_label_widget = QLabel()
        pass_row.addWidget(self.passes_label_widget)
        self.passes_input = QSpinBox()
        self.passes_input.setRange(1, 35)
        self.passes_input.setValue(3)
        pass_row.addWidget(self.passes_input)
        pass_row.addStretch()
        self.main_layout.addLayout(pass_row)

        controls = QHBoxLayout()
        self.run_button = QPushButton()
        self.run_button.setStyleSheet("background-color: #d32f2f; color: white; font-weight: bold; padding: 8px 16px;")
        self.run_button.clicked.connect(self._run)
        controls.addWidget(self.run_button)

        self.main_layout.addLayout(controls)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.main_layout.addWidget(self.output, 1)
        
        self._refresh()

    def _refresh(self) -> None:
        self.title_label.setText(self._pt("title", "Privacy Shredder"))
        self.desc_label.setText(self._pt("description", "Permanently destroy sensitive files. Warning: Data deleted this way cannot be recovered even with specialized forensics software."))
        self.queue_label.setText(self._pt("queue.label", "Shredding Queue"))
        self.add_file_btn.setText(self._pt("button.add_files", "Add Files"))
        self.add_dir_btn.setText(self._pt("button.add_folder", "Add Folder"))
        self.clear_btn.setText(self._pt("button.clear", "Clear"))
        self.passes_label_widget.setText(self._pt("passes.label", "Overwriting Passes:"))
        self.run_button.setText(self._pt("button.run", "Wipe Selected Data"))
        self.output.setPlaceholderText(self._pt("output.placeholder", "Operation logs will appear here..."))

    def _add_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, self._pt("dialog.select_files", "Select Files to Shred"))
        if files:
            for f in files:
                p = Path(f)
                if p not in self._paths:
                    self._paths.append(p)
                    self.path_list.addItem(str(p))

    def _add_dir(self) -> None:
        dir_path = QFileDialog.getExistingDirectory(self, self._pt("dialog.select_folder", "Select Folder to Shred"))
        if dir_path:
            p = Path(dir_path)
            if p not in self._paths:
                self._paths.append(p)
                self.path_list.addItem(str(p))

    def _clear_queue(self) -> None:
        self._paths.clear()
        self.path_list.clear()

    def _run(self) -> None:
        if not self._paths:
            QMessageBox.information(self, self._pt("dialog.empty.title", "Queue Empty"), self._pt("dialog.empty.body", "Please add files or folders to shred first."))
            return

        confirm = QMessageBox.critical(
            self,
            self._pt("dialog.confirm.title", "Final Warning"),
            self._pt("dialog.confirm.body", "Are you absolutely sure? This will IRREVERSIBLY destroy {count} items. This cannot be undone.", count=str(len(self._paths))),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        self.run_button.setEnabled(False)
        self.add_file_btn.setEnabled(False)
        self.add_dir_btn.setEnabled(False)
        self.clear_btn.setEnabled(False)
        self.output.setPlainText("")
        
        passes = self.passes_input.value()
        
        self.services.run_task(
            lambda context: run_shred_task(context, self.services, self.plugin_id, self._paths, passes),
            on_result=self._handle_result,
            on_error=self._handle_error,
            on_finished=self._finish_run,
            status_text=self._pt("log.start", "Starting secure shredding..."),
        )

    def _handle_result(self, payload: object) -> None:
        self._clear_queue()
        self.services.record_run(self.plugin_id, "SUCCESS", self._pt("log.done", "Privacy shredding operation complete."))

    def _handle_error(self, payload: object) -> None:
        message = payload.get("message", "Unknown shred error") if isinstance(payload, dict) else str(payload)
        self.output.appendPlainText(f"\nERROR: {message}")
        self.services.record_run(self.plugin_id, "ERROR", message[:500])

    def _finish_run(self) -> None:
        self.run_button.setEnabled(True)
        self.add_file_btn.setEnabled(True)
        self.add_dir_btn.setEnabled(True)
        self.clear_btn.setEnabled(True)
