from __future__ import annotations

import os
import re
from pathlib import Path

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from dngine.core.page_style import apply_page_chrome, muted_text_style, section_title_style
from dngine.core.plugin_api import QtPlugin, bind_tr, tr
from dngine.core.widgets import PathLineEdit


SKIP_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".pdf", ".zip", ".gz", ".7z",
    ".exe", ".dll", ".so", ".bin", ".woff", ".woff2", ".ttf", ".mp3", ".mp4",
    ".mov", ".avi", ".mkv", ".class", ".jar", ".pyc", ".o", ".a",
}
MAX_PREVIEW_LENGTH = 180

DETECTION_RULES = (
    {
        "name": "AWS Access Key",
        "pattern": re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
        "secret_group": 0,
    },
    {
        "name": "GitHub Token",
        "pattern": re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,255}\b|\bgithub_pat_[A-Za-z0-9_]{20,255}\b"),
        "secret_group": 0,
    },
    {
        "name": "GitLab Token",
        "pattern": re.compile(r"\bglpat-[A-Za-z0-9\-_]{20,255}\b"),
        "secret_group": 0,
    },
    {
        "name": "Slack Token",
        "pattern": re.compile(r"\bxox(?:a|b|p|r|s)-[A-Za-z0-9-]{10,200}\b"),
        "secret_group": 0,
    },
    {
        "name": "Stripe Live Key",
        "pattern": re.compile(r"\b(?:sk|rk)_live_[A-Za-z0-9]{16,255}\b"),
        "secret_group": 0,
    },
    {
        "name": "Google API Key",
        "pattern": re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b"),
        "secret_group": 0,
    },
    {
        "name": "Azure Storage Connection String",
        "pattern": re.compile(r"\bDefaultEndpointsProtocol=https;AccountName=[^;]+;AccountKey=[^;]+;EndpointSuffix=[^;\s]+", re.IGNORECASE),
        "secret_group": 0,
    },
    {
        "name": "JWT",
        "pattern": re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9._-]{8,}\.[A-Za-z0-9._-]{8,}\b"),
        "secret_group": 0,
    },
    {
        "name": "Private Key Block",
        "pattern": re.compile(r"-----BEGIN (?:RSA |DSA |EC |OPENSSH |PGP )?PRIVATE KEY-----"),
        "secret_group": 0,
    },
    {
        "name": "Bearer Token",
        "pattern": re.compile(r"\bBearer\s+([A-Za-z0-9\-._~+/]+=*)", re.IGNORECASE),
        "secret_group": 1,
    },
    {
        "name": "Basic Auth URL",
        "pattern": re.compile(r"\b[a-z][a-z0-9+\-.]{1,20}://[^/\s:@]{1,64}:([^/\s@]{3,})@[^/\s]+\b", re.IGNORECASE),
        "secret_group": 1,
    },
    {
        "name": "Generic Secret Assignment",
        "pattern": re.compile(
            r"""(?ix)
            \b(?:password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|secret[_-]?key|
               client[_-]?secret|auth[_-]?token|private[_-]?key|db[_-]?password|
               connection[_-]?string)\b
            \s*[:=]\s*
            ["']?([A-Za-z0-9/_+=.@\-]{12,})["']?
            """
        ),
        "secret_group": 1,
    },
)

RISKY_FILENAME_PATTERNS = (
    ("review.reason.env", re.compile(r"(?i)^\.env(?:\..+)?$")),
    ("review.reason.registry", re.compile(r"(?i)^\.npmrc$")),
    ("review.reason.registry", re.compile(r"(?i)^\.pypirc$")),
    ("review.reason.netrc", re.compile(r"(?i)^\.netrc$")),
    ("review.reason.ssh", re.compile(r"(?i)^id_(?:rsa|dsa|ecdsa|ed25519)$")),
    ("review.reason.service_account", re.compile(r"(?i).*(?:service-account|service_account|sa-key|sa_key).*\.(?:json|ya?ml|ini|conf|txt)$")),
    ("review.reason.secret_inventory", re.compile(r"(?i).*(?:secret|secrets|credential|credentials).*\.(?:json|ya?ml|ini|conf|txt|env)$")),
)

RISKY_SUFFIX_KEYS = {
    ".pem": "review.reason.pem",
    ".key": "review.reason.key",
    ".p12": "review.reason.pkcs12",
    ".pfx": "review.reason.pkcs12",
    ".jks": "review.reason.keystore",
    ".kdbx": "review.reason.keystore",
    ".keystore": "review.reason.keystore",
    ".ovpn": "review.reason.vpn",
}


def _ensure_western(text: str) -> str:
    eastern = "٠١٢٣٤٥٦٧٨٩"
    western = "0123456789"
    trans = str.maketrans(eastern, western)
    return text.translate(trans)


def _mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    visible = min(4, max(1, len(value) // 6))
    hidden = max(4, len(value) - (visible * 2))
    return f"{value[:visible]}{'*' * hidden}{value[-visible:]}"


def _truncate_preview(value: str) -> str:
    compact = re.sub(r"\s+", " ", value).strip()
    if len(compact) <= MAX_PREVIEW_LENGTH:
        return compact
    return f"{compact[: MAX_PREVIEW_LENGTH - 3]}..."


def _build_masked_preview(line: str, match: re.Match[str], secret_group: int) -> str:
    preview = line.rstrip("\n")
    group_index = secret_group if secret_group <= (match.lastindex or 0) else 0
    start, end = match.span(group_index)
    if start < 0 or end < 0:
        start, end = match.span(0)
    secret_text = preview[start:end]
    preview = f"{preview[:start]}{_mask_secret(secret_text)}{preview[end:]}"
    return _truncate_preview(preview)


def _entry_signal_count(entry: dict[str, object]) -> int:
    return len(entry["matches"]) + len(entry["review_reasons"])


def _entry_disposition_key(entry: dict[str, object]) -> str:
    return "disposition.match" if entry["matches"] else "disposition.review"


def _entry_scan_key(entry: dict[str, object]) -> str:
    scan_note = str(entry.get("scan_note") or "")
    if scan_note == "unreadable":
        return "scan.status.unreadable"
    if scan_note == "skipped":
        return "scan.status.skipped"
    return "scan.status.scanned"


def _review_reasons_for_file(services, plugin_id: str, file_path: Path) -> list[str]:
    reasons: list[str] = []
    file_name = file_path.name
    suffix = file_path.suffix.lower()
    for key, pattern in RISKY_FILENAME_PATTERNS:
        if pattern.match(file_name):
            reason = tr(services, plugin_id, key, key)
            if reason not in reasons:
                reasons.append(reason)
    suffix_key = RISKY_SUFFIX_KEYS.get(suffix)
    if suffix_key:
        reason = tr(services, plugin_id, suffix_key, suffix_key)
        if reason not in reasons:
            reasons.append(reason)
    return reasons


def _new_review_entry(target_dir: str, path: str) -> dict[str, object]:
    return {
        "path": path,
        "relative_path": os.path.relpath(path, target_dir),
        "matches": [],
        "review_reasons": [],
        "scan_note": "",
    }


def _write_report(report_path: str, target_dir: str, review_entries: list[dict[str, object]], scanned_files: int, indicator_count: int, services, plugin_id: str) -> None:
    with open(report_path, "w", encoding="utf-8") as handle:
        handle.write(f"{tr(services, plugin_id, 'report.header.title', 'Code Exploit Scanner Report')}\n")
        handle.write(f"{tr(services, plugin_id, 'report.header.target', 'Target')}: {target_dir}\n")
        handle.write(f"{tr(services, plugin_id, 'report.header.scanned', 'Files scanned')}: {_ensure_western(str(scanned_files))}\n")
        handle.write(f"{tr(services, plugin_id, 'report.header.review', 'Risky files')}: {_ensure_western(str(len(review_entries)))}\n")
        handle.write(f"{tr(services, plugin_id, 'report.header.matches', 'Exploit indicators')}: {_ensure_western(str(indicator_count))}\n")

        for entry in review_entries:
            handle.write("\n")
            handle.write(f"=== {entry['relative_path']} ===\n")
            handle.write(f"{tr(services, plugin_id, 'details.path', 'Path')}: {entry['path']}\n")
            handle.write(
                f"{tr(services, plugin_id, 'details.status', 'Status')}: "
                f"{tr(services, plugin_id, _entry_disposition_key(entry), 'Review')}\n"
            )
            handle.write(
                f"{tr(services, plugin_id, 'details.scan', 'Content scan')}: "
                f"{tr(services, plugin_id, _entry_scan_key(entry), 'Text scanned')}\n"
            )
            if entry["review_reasons"]:
                handle.write(f"{tr(services, plugin_id, 'details.review_reasons', 'Filename review reasons')}:\n")
                for reason in entry["review_reasons"]:
                    handle.write(f"- {reason}\n")
            if entry["matches"]:
                handle.write(f"{tr(services, plugin_id, 'details.matches', 'Matched indicators')}:\n")
                for match_info in entry["matches"]:
                    handle.write(
                        f"- {match_info['rule_name']} | "
                        f"{tr(services, plugin_id, 'details.line', 'Line')} {_ensure_western(str(match_info['line_number']))} | "
                        f"{match_info['snippet']}\n"
                    )


def run_credential_scan(context, services, plugin_id: str, target_dir: str):
    file_list: list[str] = []
    for root, _, files in os.walk(target_dir):
        for file_name in files:
            file_list.append(os.path.join(root, file_name))

    if not file_list:
        raise ValueError(tr(services, plugin_id, "error.no_files", "No files found in the selected folder."))

    context.log(tr(services, plugin_id, "log.start", "Scanning {count} files for exploit indicators...", count=_ensure_western(str(len(file_list)))))
    matches: list[dict[str, object]] = []
    review_map: dict[str, dict[str, object]] = {}
    scanned_text_files = 0

    for index, path in enumerate(file_list, start=1):
        context.progress(index / float(len(file_list)))
        file_path = Path(path)
        review_reasons = _review_reasons_for_file(services, plugin_id, file_path)
        if review_reasons:
            entry = review_map.setdefault(path, _new_review_entry(target_dir, path))
            for reason in review_reasons:
                if reason not in entry["review_reasons"]:
                    entry["review_reasons"].append(reason)

        if file_path.suffix.lower() in SKIP_SUFFIXES:
            if path in review_map:
                review_map[path]["scan_note"] = "skipped"
            continue

        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                scanned_text_files += 1
                for line_number, line in enumerate(handle, start=1):
                    for rule in DETECTION_RULES:
                        match = rule["pattern"].search(line)
                        if not match:
                            continue
                        entry = review_map.setdefault(path, _new_review_entry(target_dir, path))
                        match_info = {
                            "path": path,
                            "relative_path": entry["relative_path"],
                            "rule_name": rule["name"],
                            "line_number": line_number,
                            "snippet": _build_masked_preview(line, match, int(rule["secret_group"])),
                        }
                        matches.append(match_info)
                        entry["matches"].append(match_info)
        except Exception:
            if path in review_map and not review_map[path]["scan_note"]:
                review_map[path]["scan_note"] = "unreadable"
            continue

    report_path = None
    review_entries = sorted(
        review_map.values(),
        key=lambda entry: (-len(entry["matches"]), -len(entry["review_reasons"]), str(entry["relative_path"]).lower()),
    )

    if review_entries:
        report_filename = tr(services, plugin_id, "report.filename", "Code_Exploit_Report.txt")
        report_path = os.path.join(target_dir, report_filename)
        _write_report(report_path, target_dir, review_entries, len(file_list), len(matches), services, plugin_id)

        matches_count = _ensure_western(str(len(matches)))
        review_count = _ensure_western(str(len(review_entries)))
        context.log(
            tr(
                services,
                plugin_id,
                "log.matches",
                "Flagged {files} risky files with {count} total exploit indicators.",
                files=review_count,
                count=matches_count,
            )
        )
        context.log(tr(services, plugin_id, "log.save", "Saved report to {path}", path=report_path))
    else:
        context.log(tr(services, plugin_id, "log.clean", "No exploit indicators or risky files detected."))

    return {
        "target_dir": target_dir,
        "matches": matches,
        "review_files": review_entries,
        "report_path": report_path,
        "scanned_files": len(file_list),
        "text_files_scanned": scanned_text_files,
    }


class CredentialScannerPlugin(QtPlugin):
    plugin_id = "cred_scanner"
    name = "Code Exploit Scanner"
    description = "Sweep a folder for exposed secrets, risky files, and exploit indicators, then write a review report when anything looks suspicious."
    category = "IT Utilities"
    preferred_icon = "shield"

    def create_widget(self, services) -> QWidget:
        return CredentialScannerPage(services, self.plugin_id)


class CredentialScannerPage(QWidget):
    def __init__(self, services, plugin_id: str):
        super().__init__()
        self.services = services
        self.plugin_id = plugin_id
        self.tr = bind_tr(services, plugin_id)
        self._latest_report_path = None
        self._last_result: dict[str, object] | None = None
        self._review_entries: list[dict[str, object]] = []
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

        path_row = QHBoxLayout()
        path_row.setSpacing(10)
        self.path_input = PathLineEdit(mode="directory")
        path_row.addWidget(self.path_input, 1)

        self.browse_button = QPushButton()
        self.browse_button.clicked.connect(self._browse_folder)
        path_row.addWidget(self.browse_button)
        self.main_layout.addLayout(path_row)

        controls = QHBoxLayout()
        controls.setSpacing(12)
        self.run_button = QPushButton()
        self.run_button.clicked.connect(self._run)
        controls.addWidget(self.run_button, 0, Qt.AlignmentFlag.AlignLeft)

        self.open_report_button = QPushButton()
        self.open_report_button.setEnabled(False)
        self.open_report_button.clicked.connect(self._open_report)
        controls.addWidget(self.open_report_button, 0, Qt.AlignmentFlag.AlignLeft)

        self.main_layout.addLayout(controls)

        self.summary_card = QFrame()
        summary_layout = QVBoxLayout(self.summary_card)
        summary_layout.setContentsMargins(16, 14, 16, 14)
        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        summary_layout.addWidget(self.summary_label)
        self.main_layout.addWidget(self.summary_card)

        self.review_card = QFrame()
        review_layout = QVBoxLayout(self.review_card)
        review_layout.setContentsMargins(16, 14, 16, 14)
        review_layout.setSpacing(10)
        self.review_heading = QLabel()
        review_layout.addWidget(self.review_heading)

        self.review_table = QTableWidget(0, 4)
        self.review_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.review_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.review_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.review_table.setAlternatingRowColors(True)
        self.review_table.verticalHeader().setVisible(False)
        self.review_table.itemSelectionChanged.connect(self._handle_selection_changed)
        header = self.review_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        review_layout.addWidget(self.review_table, 1)
        self.main_layout.addWidget(self.review_card, 1)

        self.details_card = QFrame()
        details_layout = QVBoxLayout(self.details_card)
        details_layout.setContentsMargins(16, 14, 16, 14)
        details_layout.setSpacing(10)
        self.details_heading = QLabel()
        details_layout.addWidget(self.details_heading)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        details_layout.addWidget(self.output, 1)
        self.main_layout.addWidget(self.details_card, 1)

        self.open_file_button = QPushButton()
        self.open_file_button.setEnabled(False)
        self.open_file_button.clicked.connect(self._open_selected_file)
        controls.addWidget(self.open_file_button, 0, Qt.AlignmentFlag.AlignLeft)

        self.open_folder_button = QPushButton()
        self.open_folder_button.setEnabled(False)
        self.open_folder_button.clicked.connect(self._open_selected_folder)
        controls.addWidget(self.open_folder_button, 0, Qt.AlignmentFlag.AlignLeft)

        self._refresh()

    def _refresh(self) -> None:
        self.title_label.setText(self.tr("title", "Code Exploit Scanner"))
        self.desc_label.setText(self.tr("description", "A broader static sweep for exposed secrets, risky filenames, and exploit indicators. It masks previews, skips obvious binary formats, and writes a review report beside the scanned folder."))
        self.path_input.setPlaceholderText(self.tr("path.placeholder", "Select a folder to scan..."))
        self.browse_button.setText(self.tr("browse", "Browse"))
        self.run_button.setText(self.tr("run.button", "Scan Folder"))
        self.open_report_button.setText(self.tr("report.button", "Open Report"))
        self.open_file_button.setText(self.tr("open.file.button", "Open Selected File"))
        self.open_folder_button.setText(self.tr("open.folder.button", "Open Containing Folder"))
        self.review_heading.setText(self.tr("review.heading", "Risky File Review"))
        self.details_heading.setText(self.tr("details.heading", "Signal Details"))
        self.review_table.setHorizontalHeaderLabels(
            [
                self.tr("table.file", "File"),
                self.tr("table.signals", "Signals"),
                self.tr("table.matches", "Matches"),
                self.tr("table.scan", "Content Scan"),
            ]
        )
        self.output.setPlaceholderText(self.tr("output.placeholder", "Select a flagged file to inspect its signals."))
        if self._last_result is None:
            self.summary_label.setText(self.tr("summary.initial", "Choose a folder to start a security sweep."))
            self.output.setPlainText(self.tr("details.empty", "Select a flagged file to inspect its indicators."))
            self.review_table.setRowCount(0)
        else:
            self._render_result()
        self._apply_theme_styles()

    def _apply_theme_styles(self) -> None:
        palette = self.services.theme_manager.current_palette()
        apply_page_chrome(
            palette,
            title_label=self.title_label,
            description_label=self.desc_label,
            cards=(self.summary_card, self.review_card, self.details_card),
            summary_label=self.summary_label,
        )
        self.review_heading.setStyleSheet(section_title_style(palette, size=16, weight=700))
        self.details_heading.setStyleSheet(section_title_style(palette, size=16, weight=700))
        self.output.setStyleSheet(muted_text_style(palette, size=13))

    def _handle_theme_change(self, _mode: str) -> None:
        self._apply_theme_styles()

    def _browse_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            self.tr("dialog.browse", "Select Folder To Scan"),
            str(self.services.default_output_path()),
        )
        if folder:
            self.path_input.setText(folder)

    def _run(self) -> None:
        target_dir = self.path_input.text().strip()
        if not target_dir:
            QMessageBox.warning(
                self, 
                self.tr("dialog.missing.title", "Missing Input"), 
                self.tr("dialog.missing.body", "Choose a folder to scan.")
            )
            return

        self.run_button.setEnabled(False)
        self.open_report_button.setEnabled(False)
        self.open_file_button.setEnabled(False)
        self.open_folder_button.setEnabled(False)
        self._latest_report_path = None
        self._last_result = None
        self._review_entries = []
        self.review_table.setRowCount(0)
        self.output.setPlainText(self.tr("summary.running", "Scanning folder..."))
        self.summary_label.setText(self.tr("summary.running", "Scanning folder..."))

        self.services.run_task(
            lambda context: run_credential_scan(context, self.services, self.plugin_id, target_dir),
            on_result=self._handle_result,
            on_error=self._handle_error,
            on_finished=self._finish_run,
            status_text=self.tr("summary.running", "Scanning folder..."),
        )

    def _handle_result(self, payload: object) -> None:
        result = dict(payload)
        self._latest_report_path = result["report_path"]
        self._last_result = result
        self._review_entries = list(result.get("review_files", []))
        matches_count_str = _ensure_western(str(len(result["matches"])))
        scanned_count_str = _ensure_western(str(result["scanned_files"]))
        review_count_str = _ensure_western(str(len(self._review_entries)))

        if self._review_entries:
            self._render_result()
            self.summary_label.setText(
                self.tr(
                    "summary.done",
                    "Scanned {count} files, queued {review} risky files, and found {matches} exploit indicators.",
                    count=scanned_count_str,
                    review=review_count_str,
                    matches=matches_count_str,
                )
            )
            self.open_report_button.setEnabled(bool(self._latest_report_path))
            self.services.record_run(
                self.plugin_id,
                "WARNING",
                self.tr(
                    "run.warning",
                    "Flagged {review} risky files and {matches} exploit indicators in {dir}",
                    review=review_count_str,
                    matches=matches_count_str,
                    dir=result["target_dir"],
                ),
            )
        else:
            self.review_table.setRowCount(0)
            self.output.setPlainText(self.tr("details.clean", "No risky files or exploit indicators were detected."))
            self.summary_label.setText(self.tr("summary.clean", "Scanned {count} files with no matches.", count=scanned_count_str))
            self.services.record_run(
                self.plugin_id,
                "SUCCESS",
                self.tr("run.clean", "Clean exploit scan for {dir}", dir=result["target_dir"], count=scanned_count_str),
            )
        self._refresh_selection_buttons()

    def _handle_error(self, payload: object) -> None:
        message = payload.get("message", "Unknown scanner error") if isinstance(payload, dict) else str(payload)
        self.output.setPlainText(message)
        self.summary_label.setText(message)
        self.services.record_run(self.plugin_id, "ERROR", message[:500])
        self.services.log(self.tr("log.failed", "Code exploit scan failed."), "ERROR")

    def _finish_run(self) -> None:
        self.run_button.setEnabled(True)

    def _render_result(self) -> None:
        result = self._last_result or {}
        scanned_count_str = _ensure_western(str(result.get("scanned_files", 0)))
        review_count_str = _ensure_western(str(len(self._review_entries)))
        matches_count_str = _ensure_western(str(len(result.get("matches", []))))
        if self._review_entries:
            self.summary_label.setText(
                self.tr(
                    "summary.done",
                    "Scanned {count} files, queued {review} risky files, and found {matches} exploit indicators.",
                    count=scanned_count_str,
                    review=review_count_str,
                    matches=matches_count_str,
                )
            )
        else:
            self.summary_label.setText(
                self.tr("summary.clean", "Scanned {count} files with no risky findings.", count=scanned_count_str)
            )
        selected_path = self._selected_path()
        self._populate_review_table(selected_path)
        if self.review_table.rowCount() and self.review_table.currentRow() < 0:
            self.review_table.selectRow(0)
        if self.review_table.rowCount() == 0:
            self.output.setPlainText(self.tr("details.clean", "No risky files or exploit indicators were detected."))
        else:
            self._update_details_panel()
        self._refresh_selection_buttons()

    def _populate_review_table(self, selected_path: str | None = None) -> None:
        self.review_table.setRowCount(0)
        for row, entry in enumerate(self._review_entries):
            self.review_table.insertRow(row)
            file_item = QTableWidgetItem(str(entry["relative_path"]))
            file_item.setData(Qt.ItemDataRole.UserRole, entry["path"])
            self.review_table.setItem(row, 0, file_item)
            self.review_table.setItem(row, 1, QTableWidgetItem(_ensure_western(str(_entry_signal_count(entry)))))
            self.review_table.setItem(row, 2, QTableWidgetItem(_ensure_western(str(len(entry["matches"])))))
            self.review_table.setItem(row, 3, QTableWidgetItem(self.tr(_entry_scan_key(entry), "Text scanned")))

        if selected_path:
            for row in range(self.review_table.rowCount()):
                item = self.review_table.item(row, 0)
                if item and item.data(Qt.ItemDataRole.UserRole) == selected_path:
                    self.review_table.selectRow(row)
                    break

    def _selected_path(self) -> str | None:
        item = self.review_table.item(self.review_table.currentRow(), 0)
        if item is None:
            return None
        path = item.data(Qt.ItemDataRole.UserRole)
        return str(path) if path else None

    def _selected_entry(self) -> dict[str, object] | None:
        selected_path = self._selected_path()
        if not selected_path:
            return None
        for entry in self._review_entries:
            if entry["path"] == selected_path:
                return entry
        return None

    def _handle_selection_changed(self) -> None:
        self._update_details_panel()
        self._refresh_selection_buttons()

    def _update_details_panel(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            self.output.setPlainText(self.tr("details.empty", "Select a flagged file to inspect its indicators."))
            return

        lines = [
            f"{self.tr('details.path', 'Path')}: {entry['path']}",
            f"{self.tr('details.status', 'Status')}: {self.tr(_entry_disposition_key(entry), 'Review')}",
            f"{self.tr('details.scan', 'Content scan')}: {self.tr(_entry_scan_key(entry), 'Text scanned')}",
        ]

        if entry["review_reasons"]:
            lines.append("")
            lines.append(f"{self.tr('details.review_reasons', 'Filename review reasons')}:")
            for reason in entry["review_reasons"]:
                lines.append(f"- {reason}")

        if entry["matches"]:
            lines.append("")
            lines.append(f"{self.tr('details.matches', 'Matched indicators')}:")
            for match_info in entry["matches"][:12]:
                lines.append(
                    f"- {match_info['rule_name']} | {self.tr('details.line', 'Line')} "
                    f"{_ensure_western(str(match_info['line_number']))} | {match_info['snippet']}"
                )
            remaining = len(entry["matches"]) - 12
            if remaining > 0:
                lines.append(
                    self.tr(
                        "details.more",
                        "... and {count} more matches in the report.",
                        count=_ensure_western(str(remaining)),
                    )
                )

        self.output.setPlainText("\n".join(lines))

    def _refresh_selection_buttons(self) -> None:
        has_selection = self._selected_entry() is not None
        self.open_file_button.setEnabled(has_selection)
        self.open_folder_button.setEnabled(has_selection)

    def _open_report(self) -> None:
        if self._latest_report_path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._latest_report_path))

    def _open_selected_file(self) -> None:
        entry = self._selected_entry()
        if entry is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(entry["path"])))

    def _open_selected_folder(self) -> None:
        entry = self._selected_entry()
        if entry is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(str(entry["path"])).parent)))
