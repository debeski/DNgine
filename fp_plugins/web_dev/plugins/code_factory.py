from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
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
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from dngine.core.page_style import apply_page_chrome, apply_semantic_class
from dngine.core.plugin_api import QtPlugin, bind_tr, safe_tr
from dngine.core.table_utils import configure_resizable_table
from dngine.core.widgets import PathLineEdit, ScrollSafeComboBox
from dngine.sdk import MenuActionSpec, show_context_menu


QComboBox = ScrollSafeComboBox

SMART_EXCLUDED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".idea",
    ".vscode",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".nox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "env",
    "node_modules",
    "target",
    "venv",
}

BINARY_SUFFIXES = {
    ".7z",
    ".a",
    ".avi",
    ".bin",
    ".bmp",
    ".class",
    ".dll",
    ".doc",
    ".docx",
    ".exe",
    ".gif",
    ".gz",
    ".heic",
    ".ico",
    ".jar",
    ".jpeg",
    ".jpg",
    ".mkv",
    ".mov",
    ".mp3",
    ".mp4",
    ".o",
    ".otf",
    ".pdf",
    ".png",
    ".pyc",
    ".so",
    ".tar",
    ".ttf",
    ".wav",
    ".woff",
    ".woff2",
    ".xls",
    ".xlsx",
    ".zip",
}

STATUS_ORDER = ("ALL", "PLANNED", "APPLIED", "UNDONE", "SKIPPED", "ERROR")

OPERATION_ORDER = (
    "trim_trailing_ws",
    "compress_blank_lines",
    "indent_mode",
    "ensure_eof_newline",
    "eol_mode",
    "purge_todos",
    "strip_block_comments",
    "strip_line_comments",
    "mask_secrets",
    "neutralize_paths",
    "scrub_ips",
    "brace_internalizer",
    "full_minify",
)

OPERATION_LABELS = {
    "trim_trailing_ws": ("operation.trim", "Trim trailing whitespace"),
    "compress_blank_lines": ("operation.blank", "Compress blank lines"),
    "indent_mode": ("operation.indent", "Standardize indentation"),
    "ensure_eof_newline": ("operation.eof", "Normalize end-of-file newline"),
    "eol_mode": ("operation.eol", "Convert line endings"),
    "purge_todos": ("operation.todo", "Purge TODO and FIXME comments"),
    "strip_block_comments": ("operation.block", "Strip block comments"),
    "strip_line_comments": ("operation.line", "Strip line comments"),
    "mask_secrets": ("operation.secrets", "Mask sensitive strings"),
    "neutralize_paths": ("operation.paths", "Neutralize absolute paths"),
    "scrub_ips": ("operation.ips", "Scrub IP addresses"),
    "brace_internalizer": ("operation.brace", "Move opening braces inline"),
    "full_minify": ("operation.minify", "Full minify"),
    "file_scan": ("operation.file_scan", "File scan"),
    "apply": ("operation.apply", "Apply changes"),
    "undo": ("operation.undo", "Undo last run"),
}

STATUS_LABELS = {
    "PLANNED": ("status.planned", "Planned"),
    "APPLIED": ("status.applied", "Applied"),
    "UNDONE": ("status.undone", "Undone"),
    "SKIPPED": ("status.skipped", "Skipped"),
    "ERROR": ("status.error", "Error"),
}

MASK_RULES = (
    {
        "id": "mask.generic",
        "summary": ("change.mask.generic", "Masked a sensitive assignment."),
        "pattern": re.compile(
            r"""(?ix)
            (
                \b(?:password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|
                secret[_-]?key|client[_-]?secret|auth[_-]?token|private[_-]?key|
                db[_-]?password|connection[_-]?string)\b
                \s*[:=]\s*
                ["']?
            )
            ([^"'\s]{4,})
            (["']?)
            """
        ),
        "replace": lambda match: f"{match.group(1)}[REDACTED]{match.group(3)}",
    },
    {
        "id": "mask.bearer",
        "summary": ("change.mask.bearer", "Masked a bearer token."),
        "pattern": re.compile(r"(?i)\b(Bearer\s+)([A-Za-z0-9\-._~+/]+=*)"),
        "replace": lambda match: f"{match.group(1)}[REDACTED]",
    },
    {
        "id": "mask.aws",
        "summary": ("change.mask.aws", "Masked an AWS access key."),
        "pattern": re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
        "replace": lambda _match: "[REDACTED]",
    },
    {
        "id": "mask.github",
        "summary": ("change.mask.github", "Masked a GitHub token."),
        "pattern": re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,255}\b|\bgithub_pat_[A-Za-z0-9_]{20,255}\b"),
        "replace": lambda _match: "[REDACTED]",
    },
)

WINDOWS_PATH_PATTERN = re.compile(r"(?<![\w/])([A-Za-z]:\\(?:[^\\/:*?\"<>|\r\n]+\\?)+)")
POSIX_PATH_PATTERN = re.compile(r"(?<!https:)(?<!http:)(?<!file:)(?<![\w/])(/(?:Users|home|var|opt|srv|tmp|mnt|Volumes|private)(?:/[^\s\"'<>]+)+)")
IPV4_PATTERN = re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b")
IPV6_PATTERN = re.compile(r"\b(?:[0-9A-Fa-f]{1,4}:){2,7}[0-9A-Fa-f]{1,4}\b")
TODO_PATTERN = re.compile(r"(?i)\b(?:TODO|FIXME)\b")


@dataclass(frozen=True)
class LanguageProfile:
    line_comment_markers: tuple[str, ...] = ()
    block_comment_pairs: tuple[tuple[str, str], ...] = ()
    todo_prefixes: tuple[str, ...] = ()
    brace_language: bool = False
    minify_mode: str = ""


@dataclass(frozen=True)
class LineRecord:
    text: str
    ending: str
    original_line: int


@dataclass(frozen=True)
class ChangeEntry:
    path: str
    relative_path: str
    operation_id: str
    line_number: int | None
    status: str
    summary: str
    before: str
    after: str
    detected_eol: str


@dataclass
class FilePreview:
    path: Path
    relative_path: str
    original_bytes: bytes
    encoding: str
    detected_eol: str
    rows: list[ChangeEntry]
    changed_bytes: bytes

    @property
    def changed(self) -> bool:
        return self.changed_bytes != self.original_bytes


LANGUAGE_PROFILES = {
    ".c": LanguageProfile(("//",), (("/*", "*/"),), ("//", "/*"), True, "compact"),
    ".cc": LanguageProfile(("//",), (("/*", "*/"),), ("//", "/*"), True, "compact"),
    ".cpp": LanguageProfile(("//",), (("/*", "*/"),), ("//", "/*"), True, "compact"),
    ".cs": LanguageProfile(("//",), (("/*", "*/"),), ("//", "/*"), True, "compact"),
    ".css": LanguageProfile((), (("/*", "*/"),), ("/*",), True, "compact"),
    ".go": LanguageProfile(("//",), (("/*", "*/"),), ("//", "/*"), True, "compact"),
    ".h": LanguageProfile(("//",), (("/*", "*/"),), ("//", "/*"), True, "compact"),
    ".hpp": LanguageProfile(("//",), (("/*", "*/"),), ("//", "/*"), True, "compact"),
    ".htm": LanguageProfile((), (("<!--", "-->"),), ("<!--",), False, "html"),
    ".html": LanguageProfile((), (("<!--", "-->"),), ("<!--",), False, "html"),
    ".java": LanguageProfile(("//",), (("/*", "*/"),), ("//", "/*"), True, "compact"),
    ".js": LanguageProfile(("//",), (("/*", "*/"),), ("//", "/*"), True, "compact"),
    ".json": LanguageProfile((), (), (), False, "json"),
    ".jsx": LanguageProfile(("//",), (("/*", "*/"),), ("//", "/*"), True, "compact"),
    ".kt": LanguageProfile(("//",), (("/*", "*/"),), ("//", "/*"), True, "compact"),
    ".kts": LanguageProfile(("//",), (("/*", "*/"),), ("//", "/*"), True, "compact"),
    ".less": LanguageProfile(("//",), (("/*", "*/"),), ("//", "/*"), True, "compact"),
    ".lua": LanguageProfile(("--",), (), ("--",), False, ""),
    ".mjs": LanguageProfile(("//",), (("/*", "*/"),), ("//", "/*"), True, "compact"),
    ".php": LanguageProfile(("//", "#"), (("/*", "*/"),), ("//", "#", "/*"), True, "compact"),
    ".py": LanguageProfile(("#",), (), ("#",), False, ""),
    ".rs": LanguageProfile(("//",), (("/*", "*/"),), ("//", "/*"), True, "compact"),
    ".sass": LanguageProfile(("//",), (("/*", "*/"),), ("//", "/*"), True, "compact"),
    ".scala": LanguageProfile(("//",), (("/*", "*/"),), ("//", "/*"), True, "compact"),
    ".scss": LanguageProfile(("//",), (("/*", "*/"),), ("//", "/*"), True, "compact"),
    ".sh": LanguageProfile(("#",), (), ("#",), False, ""),
    ".sql": LanguageProfile(("--",), (("/*", "*/"),), ("--", "/*"), False, ""),
    ".svg": LanguageProfile((), (("<!--", "-->"),), ("<!--",), False, "html"),
    ".swift": LanguageProfile(("//",), (("/*", "*/"),), ("//", "/*"), True, "compact"),
    ".toml": LanguageProfile(("#",), (), ("#",), False, ""),
    ".ts": LanguageProfile(("//",), (("/*", "*/"),), ("//", "/*"), True, "compact"),
    ".tsx": LanguageProfile(("//",), (("/*", "*/"),), ("//", "/*"), True, "compact"),
    ".vue": LanguageProfile(("//",), (("/*", "*/"), ("<!--", "-->")), ("//", "/*", "<!--"), True, "html"),
    ".xml": LanguageProfile((), (("<!--", "-->"),), ("<!--",), False, "html"),
    ".yaml": LanguageProfile(("#",), (), ("#",), False, ""),
    ".yml": LanguageProfile(("#",), (), ("#",), False, ""),
}

SPECIAL_PROFILE_NAMES = {
    "dockerfile": LanguageProfile(("#",), (), ("#",), False, ""),
    ".env": LanguageProfile(("#",), (), ("#",), False, ""),
}


def _pt(translate, key: str, default: str | None = None, **kwargs) -> str:
    return safe_tr(translate, key, default, **kwargs)


def _ensure_western(text: str) -> str:
    eastern = "٠١٢٣٤٥٦٧٨٩"
    western = "0123456789"
    return text.translate(str.maketrans(eastern, western))


def _status_text(status: str, *, translate=None) -> str:
    key, default = STATUS_LABELS.get(status, ("status.unknown", status.title()))
    return _pt(translate, key, default)


def _operation_text(operation_id: str, *, translate=None) -> str:
    key, default = OPERATION_LABELS.get(operation_id, (operation_id, operation_id.replace("_", " ").title()))
    return _pt(translate, key, default)


def _safe_relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except Exception:
        return str(path)


def _preview_text(value: str, *, limit: int = 220) -> str:
    compact = value.replace("\t", "\\t").replace("\r", "\\r").replace("\n", "\\n")
    compact = re.sub(r"\s+", " ", compact).strip()
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 3]}..."


def _profile_for_path(path: Path) -> LanguageProfile | None:
    special = SPECIAL_PROFILE_NAMES.get(path.name.lower())
    if special is not None:
        return special
    return LANGUAGE_PROFILES.get(path.suffix.lower())


def _split_records(text: str) -> list[LineRecord]:
    records: list[LineRecord] = []
    for index, line in enumerate(text.splitlines(keepends=True), start=1):
        ending = ""
        content = line
        if line.endswith("\r\n"):
            ending = "\r\n"
            content = line[:-2]
        elif line.endswith("\n"):
            ending = "\n"
            content = line[:-1]
        records.append(LineRecord(content, ending, index))
    if not records and text == "":
        return []
    if not records:
        return [LineRecord(text, "", 1)]
    if text and not text.endswith(("\n", "\r\n")):
        last = records[-1]
        records[-1] = LineRecord(last.text, "", last.original_line)
    return records


def _detect_eol(records: list[LineRecord]) -> str:
    crlf = sum(1 for record in records if record.ending == "\r\n")
    lf = sum(1 for record in records if record.ending == "\n")
    if crlf and lf:
        return "Mixed"
    if crlf:
        return "CRLF"
    if lf:
        return "LF"
    return "None"


def _default_eol_for_detection(detected_eol: str) -> str:
    return "\r\n" if detected_eol == "CRLF" else "\n"


def _serialize_records(records: list[LineRecord], *, eol_mode: str, detected_eol: str) -> str:
    if not records:
        return ""
    if eol_mode == "keep":
        return "".join(record.text + record.ending for record in records)
    target = "\n" if eol_mode == "lf" else "\r\n"
    pieces = []
    for record in records:
        ending = target if record.ending else ""
        pieces.append(record.text + ending)
    return "".join(pieces)


def _normalize_eof_records(records: list[LineRecord], detected_eol: str) -> list[LineRecord]:
    fallback = _default_eol_for_detection(detected_eol)
    if not records:
        return [LineRecord("", fallback, 1)]
    updated = list(records)
    while len(updated) > 1 and updated[-1].text == "":
        updated.pop()
    last = updated[-1]
    updated[-1] = LineRecord(last.text, last.ending or fallback, last.original_line)
    return updated


def _decode_text_bytes(data: bytes) -> tuple[str, str]:
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig"), "utf-8-sig"
    for encoding in ("utf-8", "latin-1"):
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace"), "utf-8"


def _encode_text(text: str, encoding: str) -> bytes:
    if encoding == "utf-8-sig":
        return text.encode("utf-8-sig")
    return text.encode(encoding, errors="replace")


def _is_binary(path: Path, data: bytes) -> bool:
    if path.suffix.lower() in BINARY_SUFFIXES:
        return True
    if b"\x00" in data[:4096]:
        return True
    sample = data[:4096]
    if not sample:
        return False
    text_like = sum(1 for byte in sample if byte in b"\t\n\r\f\b" or 32 <= byte <= 126)
    return (len(sample) - text_like) / max(1, len(sample)) > 0.30


def _iter_candidate_files(root: Path):
    for current_root, dir_names, file_names in os.walk(root):
        dir_names[:] = sorted(
            name for name in dir_names
            if name not in SMART_EXCLUDED_DIRS
        )
        for file_name in sorted(file_names):
            yield Path(current_root) / file_name


def _line_entry(path: Path, relative_path: str, operation_id: str, status: str, summary: str, before: str, after: str, detected_eol: str, line_number: int | None) -> ChangeEntry:
    return ChangeEntry(
        path=str(path),
        relative_path=relative_path,
        operation_id=operation_id,
        line_number=line_number,
        status=status,
        summary=summary,
        before=_preview_text(before),
        after=_preview_text(after),
        detected_eol=detected_eol,
    )


def _line_number_display(line_number: int | None, *, translate=None) -> str:
    if line_number is None:
        return _pt(translate, "table.line.whole", "Whole file")
    return _ensure_western(str(line_number))


def _selected_operation_ids(settings: dict[str, object]) -> list[str]:
    selected: list[str] = []
    if settings.get("trim_trailing_ws"):
        selected.append("trim_trailing_ws")
    if settings.get("compress_blank_lines"):
        selected.append("compress_blank_lines")
    if settings.get("indent_mode") != "keep":
        selected.append("indent_mode")
    if settings.get("ensure_eof_newline"):
        selected.append("ensure_eof_newline")
    if settings.get("eol_mode") != "keep":
        selected.append("eol_mode")
    if settings.get("purge_todos"):
        selected.append("purge_todos")
    if settings.get("strip_block_comments"):
        selected.append("strip_block_comments")
    if settings.get("strip_line_comments"):
        selected.append("strip_line_comments")
    if settings.get("mask_secrets"):
        selected.append("mask_secrets")
    if settings.get("neutralize_paths"):
        selected.append("neutralize_paths")
    if settings.get("scrub_ips"):
        selected.append("scrub_ips")
    if settings.get("brace_internalizer"):
        selected.append("brace_internalizer")
    if settings.get("full_minify"):
        selected.append("full_minify")
    return selected


def _find_token_outside_quotes(text: str, tokens: tuple[str, ...], start: int = 0) -> tuple[int | None, str | None]:
    quote = ""
    escaped = False
    index = start
    while index < len(text):
        char = text[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\" and quote in {"'", '"', "`"}:
                escaped = True
            elif char == quote:
                quote = ""
            index += 1
            continue
        if char in {"'", '"', "`"}:
            quote = char
            index += 1
            continue
        for token in tokens:
            if text.startswith(token, index):
                return index, token
        index += 1
    return None, None


def _indent_columns(leading: str, width: int) -> int:
    columns = 0
    for char in leading:
        if char == "\t":
            columns += width
        else:
            columns += 1
    return columns


def _convert_indent_prefix(prefix: str, mode: str, width: int) -> str:
    columns = _indent_columns(prefix, width)
    if mode == "spaces":
        return " " * columns
    tabs = columns // width
    spaces = columns % width
    return ("\t" * tabs) + (" " * spaces)


def _trim_trailing_whitespace(records: list[LineRecord], rows: list[ChangeEntry], path: Path, relative_path: str, detected_eol: str, *, translate=None) -> list[LineRecord]:
    updated: list[LineRecord] = []
    for record in records:
        stripped = record.text.rstrip(" \t")
        if stripped != record.text:
            rows.append(
                _line_entry(
                    path,
                    relative_path,
                    "trim_trailing_ws",
                    "PLANNED",
                    _pt(translate, "change.trim", "Removed trailing whitespace."),
                    record.text,
                    stripped,
                    detected_eol,
                    record.original_line,
                )
            )
        updated.append(LineRecord(stripped, record.ending, record.original_line))
    return updated


def _compress_blank_lines(records: list[LineRecord], rows: list[ChangeEntry], path: Path, relative_path: str, detected_eol: str, *, translate=None) -> list[LineRecord]:
    updated: list[LineRecord] = []
    previous_blank = False
    for record in records:
        current_blank = record.text.strip() == ""
        if current_blank and previous_blank:
            rows.append(
                _line_entry(
                    path,
                    relative_path,
                    "compress_blank_lines",
                    "PLANNED",
                    _pt(translate, "change.blank", "Removed an extra blank line."),
                    record.text,
                    "",
                    detected_eol,
                    record.original_line,
                )
            )
            continue
        updated.append(record)
        previous_blank = current_blank
    return updated


def _standardize_indentation(records: list[LineRecord], rows: list[ChangeEntry], path: Path, relative_path: str, detected_eol: str, mode: str, width: int, *, translate=None) -> list[LineRecord]:
    if mode == "keep":
        return records
    updated: list[LineRecord] = []
    for record in records:
        prefix_match = re.match(r"^[ \t]+", record.text)
        if prefix_match is None:
            updated.append(record)
            continue
        prefix = prefix_match.group(0)
        replacement = _convert_indent_prefix(prefix, mode, width)
        if replacement == prefix:
            updated.append(record)
            continue
        new_text = replacement + record.text[len(prefix):]
        rows.append(
            _line_entry(
                path,
                relative_path,
                "indent_mode",
                "PLANNED",
                _pt(
                    translate,
                    "change.indent",
                    "Standardized indentation to {mode}.",
                    mode=_pt(translate, f"indent.mode.{mode}", mode.title()),
                ),
                record.text,
                new_text,
                detected_eol,
                record.original_line,
            )
        )
        updated.append(LineRecord(new_text, record.ending, record.original_line))
    return updated


def _purge_todos(records: list[LineRecord], rows: list[ChangeEntry], path: Path, relative_path: str, detected_eol: str, profile: LanguageProfile | None, *, translate=None) -> list[LineRecord]:
    prefixes = tuple(profile.todo_prefixes) if profile is not None else ()
    if not prefixes:
        rows.append(
            _line_entry(
                path,
                relative_path,
                "purge_todos",
                "SKIPPED",
                _pt(translate, "skip.todo.unsupported", "TODO purge is not available for this file type."),
                "",
                "",
                detected_eol,
                None,
            )
        )
        return records
    updated: list[LineRecord] = []
    for record in records:
        stripped = record.text.lstrip()
        if TODO_PATTERN.search(stripped) and any(stripped.startswith(prefix) for prefix in prefixes):
            rows.append(
                _line_entry(
                    path,
                    relative_path,
                    "purge_todos",
                    "PLANNED",
                    _pt(translate, "change.todo", "Removed a TODO or FIXME comment line."),
                    record.text,
                    "",
                    detected_eol,
                    record.original_line,
                )
            )
            continue
        updated.append(record)
    return updated


def _strip_line_comments(records: list[LineRecord], rows: list[ChangeEntry], path: Path, relative_path: str, detected_eol: str, profile: LanguageProfile | None, *, translate=None) -> list[LineRecord]:
    markers = tuple(profile.line_comment_markers) if profile is not None else ()
    if not markers:
        rows.append(
            _line_entry(
                path,
                relative_path,
                "strip_line_comments",
                "SKIPPED",
                _pt(translate, "skip.line.unsupported", "Line comment stripping is not available for this file type."),
                "",
                "",
                detected_eol,
                None,
            )
        )
        return records
    updated: list[LineRecord] = []
    for record in records:
        index, marker = _find_token_outside_quotes(record.text, markers)
        if index is None or marker is None:
            updated.append(record)
            continue
        new_text = record.text[:index].rstrip()
        if new_text == record.text:
            updated.append(record)
            continue
        rows.append(
            _line_entry(
                path,
                relative_path,
                "strip_line_comments",
                "PLANNED",
                _pt(translate, "change.line", "Removed a line comment."),
                record.text,
                new_text,
                detected_eol,
                record.original_line,
            )
        )
        updated.append(LineRecord(new_text, record.ending, record.original_line))
    return updated


def _strip_block_comments(records: list[LineRecord], rows: list[ChangeEntry], path: Path, relative_path: str, detected_eol: str, profile: LanguageProfile | None, *, translate=None) -> list[LineRecord]:
    pairs = tuple(profile.block_comment_pairs) if profile is not None else ()
    if not pairs:
        rows.append(
            _line_entry(
                path,
                relative_path,
                "strip_block_comments",
                "SKIPPED",
                _pt(translate, "skip.block.unsupported", "Block comment stripping is not available for this file type."),
                "",
                "",
                detected_eol,
                None,
            )
        )
        return records

    start_to_end = {start: end for start, end in pairs}
    start_tokens = tuple(start_to_end.keys())
    updated: list[LineRecord] = []
    in_block = False
    end_token = ""
    comment_start_line: int | None = None
    comment_before = ""

    for record in records:
        text = record.text
        output = []
        index = 0
        while index < len(text):
            if in_block:
                end_index = text.find(end_token, index)
                if end_index < 0:
                    index = len(text)
                    continue
                index = end_index + len(end_token)
                in_block = False
                rows.append(
                    _line_entry(
                        path,
                        relative_path,
                        "strip_block_comments",
                        "PLANNED",
                        _pt(translate, "change.block", "Removed a block comment."),
                        comment_before,
                        "",
                        detected_eol,
                        comment_start_line,
                    )
                )
                comment_before = ""
                comment_start_line = None
                continue
            start_index, token = _find_token_outside_quotes(text, start_tokens, index)
            if start_index is None or token is None:
                output.append(text[index:])
                break
            output.append(text[index:start_index])
            comment_start_line = comment_start_line or record.original_line
            end_token = start_to_end[token]
            comment_before = text[start_index:]
            end_index = text.find(end_token, start_index + len(token))
            if end_index >= 0:
                index = end_index + len(end_token)
                rows.append(
                    _line_entry(
                        path,
                        relative_path,
                        "strip_block_comments",
                        "PLANNED",
                        _pt(translate, "change.block", "Removed a block comment."),
                        comment_before,
                        "",
                        detected_eol,
                        comment_start_line,
                    )
                )
                comment_before = ""
                comment_start_line = None
                continue
            in_block = True
            index = len(text)
        updated.append(LineRecord("".join(output), record.ending, record.original_line))

    if in_block:
        rows.append(
            _line_entry(
                path,
                relative_path,
                "strip_block_comments",
                "PLANNED",
                _pt(translate, "change.block.unterminated", "Removed an unterminated block comment."),
                comment_before,
                "",
                detected_eol,
                comment_start_line,
            )
        )
    return updated


def _apply_regex_substitutions(text: str, rules: tuple[dict[str, object], ...], rows: list[ChangeEntry], path: Path, relative_path: str, detected_eol: str, line_number: int, *, translate=None) -> str:
    updated = text
    for rule in rules:
        pattern = rule["pattern"]

        def _replace(match: re.Match[str]) -> str:
            replaced = rule["replace"](match)
            if replaced == match.group(0):
                return replaced
            key, default = rule["summary"]
            rows.append(
                _line_entry(
                    path,
                    relative_path,
                    "mask_secrets",
                    "PLANNED",
                    _pt(translate, key, default),
                    match.group(0),
                    replaced,
                    detected_eol,
                    line_number,
                )
            )
            return replaced

        updated = pattern.sub(_replace, updated)
    return updated


def _mask_secrets(records: list[LineRecord], rows: list[ChangeEntry], path: Path, relative_path: str, detected_eol: str, *, translate=None) -> list[LineRecord]:
    updated: list[LineRecord] = []
    for record in records:
        new_text = _apply_regex_substitutions(
            record.text,
            MASK_RULES,
            rows,
            path,
            relative_path,
            detected_eol,
            record.original_line,
            translate=translate,
        )
        updated.append(LineRecord(new_text, record.ending, record.original_line))
    return updated


def _substitute_simple(pattern: re.Pattern[str], replacement: str, operation_id: str, summary_key: str, summary_default: str, records: list[LineRecord], rows: list[ChangeEntry], path: Path, relative_path: str, detected_eol: str, *, translate=None) -> list[LineRecord]:
    updated: list[LineRecord] = []
    for record in records:
        matches = list(pattern.finditer(record.text))
        new_text = pattern.sub(replacement, record.text)
        if matches and new_text != record.text:
            for match in matches:
                rows.append(
                    _line_entry(
                        path,
                        relative_path,
                        operation_id,
                        "PLANNED",
                        _pt(translate, summary_key, summary_default),
                        match.group(0),
                        replacement,
                        detected_eol,
                        record.original_line,
                    )
                )
        updated.append(LineRecord(new_text, record.ending, record.original_line))
    return updated


def _neutralize_paths(records: list[LineRecord], rows: list[ChangeEntry], path: Path, relative_path: str, detected_eol: str, *, translate=None) -> list[LineRecord]:
    updated = _substitute_simple(
        WINDOWS_PATH_PATTERN,
        "<ABSOLUTE_PATH>",
        "neutralize_paths",
        "change.paths",
        "Neutralized an absolute file path.",
        records,
        rows,
        path,
        relative_path,
        detected_eol,
        translate=translate,
    )
    return _substitute_simple(
        POSIX_PATH_PATTERN,
        "<ABSOLUTE_PATH>",
        "neutralize_paths",
        "change.paths",
        "Neutralized an absolute file path.",
        updated,
        rows,
        path,
        relative_path,
        detected_eol,
        translate=translate,
    )


def _scrub_ips(records: list[LineRecord], rows: list[ChangeEntry], path: Path, relative_path: str, detected_eol: str, *, translate=None) -> list[LineRecord]:
    updated = _substitute_simple(
        IPV4_PATTERN,
        "[REDACTED_IP]",
        "scrub_ips",
        "change.ips",
        "Scrubbed an IP address.",
        records,
        rows,
        path,
        relative_path,
        detected_eol,
        translate=translate,
    )
    return _substitute_simple(
        IPV6_PATTERN,
        "[REDACTED_IP]",
        "scrub_ips",
        "change.ips",
        "Scrubbed an IP address.",
        updated,
        rows,
        path,
        relative_path,
        detected_eol,
        translate=translate,
    )


def _brace_internalizer(records: list[LineRecord], rows: list[ChangeEntry], path: Path, relative_path: str, detected_eol: str, profile: LanguageProfile | None, *, translate=None) -> list[LineRecord]:
    if profile is None or not profile.brace_language:
        rows.append(
            _line_entry(
                path,
                relative_path,
                "brace_internalizer",
                "SKIPPED",
                _pt(translate, "skip.brace.unsupported", "Brace internalizer is not available for this file type."),
                "",
                "",
                detected_eol,
                None,
            )
        )
        return records
    updated = list(records)
    index = 1
    while index < len(updated):
        current = updated[index]
        previous = updated[index - 1]
        if current.text.strip() != "{" or previous.text.strip() == "":
            index += 1
            continue
        merged_text = previous.text.rstrip() + " {"
        rows.append(
            _line_entry(
                path,
                relative_path,
                "brace_internalizer",
                "PLANNED",
                _pt(translate, "change.brace", "Moved an opening brace onto the previous line."),
                current.text,
                merged_text,
                detected_eol,
                current.original_line,
            )
        )
        updated[index - 1] = LineRecord(merged_text, current.ending or previous.ending, previous.original_line)
        del updated[index]
    return updated


def _minify_text(text: str, mode: str) -> str:
    if mode == "json":
        payload = json.loads(text or "null")
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if mode == "html":
        text = re.sub(r">\s+<", "><", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s*([{}();,:])\s*", r"\1", text)
    return text.strip()


def _full_minify(records: list[LineRecord], rows: list[ChangeEntry], path: Path, relative_path: str, detected_eol: str, profile: LanguageProfile | None, *, translate=None) -> list[LineRecord]:
    if profile is None or not profile.minify_mode:
        rows.append(
            _line_entry(
                path,
                relative_path,
                "full_minify",
                "SKIPPED",
                _pt(translate, "skip.minify.unsupported", "Full minify is not available for this file type."),
                "",
                "",
                detected_eol,
                None,
            )
        )
        return records
    before = _serialize_records(records, eol_mode="keep", detected_eol=detected_eol)
    try:
        after = _minify_text(before, profile.minify_mode)
    except Exception:
        rows.append(
            _line_entry(
                path,
                relative_path,
                "full_minify",
                "ERROR",
                _pt(translate, "error.minify.invalid", "Full minify could not parse this file safely."),
                "",
                "",
                detected_eol,
                None,
            )
        )
        return records
    if after == before:
        return records
    rows.append(
        _line_entry(
            path,
            relative_path,
            "full_minify",
            "PLANNED",
            _pt(translate, "change.minify", "Minified the file into a compact form."),
            before,
            after,
            detected_eol,
            None,
        )
    )
    return _split_records(after)


def _build_file_preview(path: Path, root: Path, settings: dict[str, object], *, translate=None) -> tuple[FilePreview | None, int]:
    relative_path = _safe_relative(path, root)
    try:
        data = path.read_bytes()
    except Exception as exc:
        row = _line_entry(
            path,
            relative_path,
            "file_scan",
            "ERROR",
            _pt(translate, "error.read.file", "Could not read the file: {error}", error=str(exc)),
            "",
            "",
            "None",
            None,
        )
        return FilePreview(path, relative_path, b"", "utf-8", "None", [row], b""), 0
    if _is_binary(path, data):
        row = _line_entry(
            path,
            relative_path,
            "file_scan",
            "SKIPPED",
            _pt(translate, "skip.binary", "Skipped a binary or non-text file."),
            "",
            "",
            "None",
            None,
        )
        return FilePreview(path, relative_path, data, "utf-8", "None", [row], data), 0

    text, encoding = _decode_text_bytes(data)
    records = _split_records(text)
    detected_eol = _detect_eol(records)
    rows: list[ChangeEntry] = []
    profile = _profile_for_path(path)

    if settings.get("trim_trailing_ws"):
        records = _trim_trailing_whitespace(records, rows, path, relative_path, detected_eol, translate=translate)
    if settings.get("indent_mode") != "keep":
        records = _standardize_indentation(
            records,
            rows,
            path,
            relative_path,
            detected_eol,
            str(settings.get("indent_mode") or "keep"),
            int(settings.get("indent_width") or 4),
            translate=translate,
        )
    if settings.get("purge_todos"):
        records = _purge_todos(records, rows, path, relative_path, detected_eol, profile, translate=translate)
    if settings.get("strip_block_comments"):
        records = _strip_block_comments(records, rows, path, relative_path, detected_eol, profile, translate=translate)
    if settings.get("strip_line_comments"):
        records = _strip_line_comments(records, rows, path, relative_path, detected_eol, profile, translate=translate)
    if settings.get("mask_secrets"):
        records = _mask_secrets(records, rows, path, relative_path, detected_eol, translate=translate)
    if settings.get("neutralize_paths"):
        records = _neutralize_paths(records, rows, path, relative_path, detected_eol, translate=translate)
    if settings.get("scrub_ips"):
        records = _scrub_ips(records, rows, path, relative_path, detected_eol, translate=translate)
    if settings.get("brace_internalizer"):
        records = _brace_internalizer(records, rows, path, relative_path, detected_eol, profile, translate=translate)
    if settings.get("compress_blank_lines"):
        records = _compress_blank_lines(records, rows, path, relative_path, detected_eol, translate=translate)
    if settings.get("full_minify"):
        records = _full_minify(records, rows, path, relative_path, detected_eol, profile, translate=translate)

    base_text = _serialize_records(records, eol_mode="keep", detected_eol=detected_eol)
    finalized_records = _normalize_eof_records(records, detected_eol) if settings.get("ensure_eof_newline") else list(records)
    eof_text = _serialize_records(finalized_records, eol_mode="keep", detected_eol=detected_eol)
    new_text = _serialize_records(finalized_records, eol_mode=str(settings.get("eol_mode") or "keep"), detected_eol=detected_eol)
    new_bytes = _encode_text(new_text, encoding)
    if settings.get("ensure_eof_newline") and eof_text != base_text:
        rows.append(
            _line_entry(
                path,
                relative_path,
                "ensure_eof_newline",
                "PLANNED",
                _pt(translate, "change.eof", "Normalized the file to end with exactly one newline."),
                base_text[-80:] if base_text else "",
                eof_text[-80:] if eof_text else "",
                detected_eol,
                None,
            )
        )
    if settings.get("eol_mode") != "keep" and new_text != eof_text:
        rows.append(
            _line_entry(
                path,
                relative_path,
                "eol_mode",
                "PLANNED",
                _pt(
                    translate,
                    "change.eol",
                    "Converted line endings from {before} to {after}.",
                    before=detected_eol,
                    after=str(settings.get("eol_mode", "keep")).upper(),
                ),
                detected_eol,
                str(settings.get("eol_mode", "keep")).upper(),
                detected_eol,
                None,
            )
        )
    return FilePreview(path, relative_path, data, encoding, detected_eol, rows, new_bytes), 1


def _serialize_rows(rows: list[ChangeEntry], *, translate=None, status_override: str | None = None) -> list[dict[str, object]]:
    payload: list[dict[str, object]] = []
    for row in rows:
        status_code = status_override if row.status == "PLANNED" and status_override else row.status
        payload.append(
            {
                "path": row.path,
                "relative_path": row.relative_path,
                "operation_id": row.operation_id,
                "operation_label": _operation_text(row.operation_id, translate=translate),
                "line_number": row.line_number,
                "line_display": _line_number_display(row.line_number, translate=translate),
                "status": status_code,
                "status_label": _status_text(status_code, translate=translate),
                "summary": row.summary,
                "before": row.before,
                "after": row.after,
                "detected_eol": row.detected_eol,
            }
        )
    return payload


def _summary_payload(previews: list[FilePreview], scanned_files: int, text_files: int) -> dict[str, object]:
    eol_counts = {"LF": 0, "CRLF": 0, "Mixed": 0, "None": 0}
    skipped_paths: set[str] = set()
    changed_paths: set[str] = set()
    error_paths: set[str] = set()
    total_rows = 0
    for preview in previews:
        eol_counts.setdefault(preview.detected_eol, 0)
        eol_counts[preview.detected_eol] += 1
        total_rows += len(preview.rows)
        if preview.changed:
            changed_paths.add(str(preview.path))
        for row in preview.rows:
            if row.status == "SKIPPED":
                skipped_paths.add(str(preview.path))
            if row.status == "ERROR":
                error_paths.add(str(preview.path))
    return {
        "scanned_files": scanned_files,
        "text_files": text_files,
        "changed_files": len(changed_paths),
        "skipped_files": len(skipped_paths),
        "error_files": len(error_paths),
        "result_rows": total_rows,
        "eol_counts": eol_counts,
    }


def _compute_preview(context, target_dir: Path, settings: dict[str, object], *, translate=None) -> dict[str, object]:
    previews: list[FilePreview] = []
    files = list(_iter_candidate_files(target_dir))
    if not files:
        raise ValueError(_pt(translate, "error.no_files", "No files were found in the selected folder."))
    text_files = 0
    context.log(_pt(translate, "log.preview.start", "Scanning {count} files for Code Factory preview...", count=_ensure_western(str(len(files)))))
    for index, file_path in enumerate(files, start=1):
        preview, text_increment = _build_file_preview(file_path, target_dir, settings, translate=translate)
        text_files += text_increment
        if preview is not None:
            previews.append(preview)
        context.progress(index / float(len(files)))
    summary = _summary_payload(previews, len(files), text_files)
    context.log(
        _pt(
            translate,
            "log.preview.done",
            "Previewed {rows} result rows across {files} changed files.",
            rows=_ensure_western(str(summary["result_rows"])),
            files=_ensure_western(str(summary["changed_files"])),
        )
    )
    return {
        "previews": previews,
        "summary": summary,
    }


def _undo_root(services) -> Path:
    return services.data_root / "code_factory_undo"


def _undo_manifest_path(services) -> Path:
    return _undo_root(services) / "manifest.json"


def _undo_available(services) -> bool:
    return _undo_manifest_path(services).exists()


def run_code_factory_preview(context, services, plugin_id: str, target_dir: str, settings: dict[str, object]):
    _ = plugin_id
    preview_data = _compute_preview(context, Path(target_dir), settings, translate=lambda key, default, **kwargs: services.plugin_text("code_factory", key, default, **kwargs))
    rows: list[dict[str, object]] = []
    for preview in preview_data["previews"]:
        rows.extend(_serialize_rows(preview.rows, translate=lambda key, default, **kwargs: services.plugin_text("code_factory", key, default, **kwargs)))
    return {
        "action": "preview",
        "target_dir": target_dir,
        "rows": rows,
        "summary": preview_data["summary"],
        "undo_available": _undo_available(services),
    }


def _write_snapshot(services, previews: list[FilePreview]) -> Path:
    root = _undo_root(services)
    shutil.rmtree(root, ignore_errors=True)
    backup_root = root / "backups"
    backup_root.mkdir(parents=True, exist_ok=True)
    return backup_root


def run_code_factory_apply(context, services, plugin_id: str, target_dir: str, settings: dict[str, object]):
    _ = plugin_id
    translate = lambda key, default, **kwargs: services.plugin_text("code_factory", key, default, **kwargs)
    preview_data = _compute_preview(context, Path(target_dir), settings, translate=translate)
    previews: list[FilePreview] = preview_data["previews"]
    changed_previews = [preview for preview in previews if preview.changed]
    if not changed_previews:
        return {
            "action": "apply",
            "target_dir": target_dir,
            "rows": [row for preview in previews for row in _serialize_rows(preview.rows, translate=translate)],
            "summary": preview_data["summary"],
            "undo_available": _undo_available(services),
        }

    backup_root = _write_snapshot(services, changed_previews)
    manifest_entries: list[dict[str, object]] = []
    rows: list[dict[str, object]] = []
    success_count = 0
    for index, preview in enumerate(previews, start=1):
        if not preview.changed:
            rows.extend(_serialize_rows(preview.rows, translate=translate))
            continue
        backup_name = f"{index:04d}.bin"
        backup_path = backup_root / backup_name
        backup_path.write_bytes(preview.original_bytes)
        try:
            preview.path.write_bytes(preview.changed_bytes)
            try:
                mode = preview.path.stat().st_mode
            except Exception:
                mode = None
            manifest_entries.append(
                {
                    "path": str(preview.path),
                    "backup": backup_name,
                    "mode": mode,
                }
            )
            success_count += 1
            rows.extend(_serialize_rows(preview.rows, translate=translate, status_override="APPLIED"))
        except Exception as exc:
            rows.append(
                {
                    "path": str(preview.path),
                    "relative_path": preview.relative_path,
                    "operation_id": "apply",
                    "operation_label": _operation_text("apply", translate=translate),
                    "line_number": None,
                    "line_display": _line_number_display(None, translate=translate),
                    "status": "ERROR",
                    "status_label": _status_text("ERROR", translate=translate),
                    "summary": _pt(translate, "error.apply.file", "Failed to write updated file: {error}", error=str(exc)),
                    "before": "",
                    "after": "",
                    "detected_eol": preview.detected_eol,
                }
            )
        context.progress(index / float(len(previews)))

    manifest_path = _undo_manifest_path(services)
    if manifest_entries:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps({"files": manifest_entries}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    else:
        shutil.rmtree(_undo_root(services), ignore_errors=True)

    summary = _summary_payload(previews, preview_data["summary"]["scanned_files"], preview_data["summary"]["text_files"])
    summary["changed_files"] = success_count
    context.log(
        _pt(
            translate,
            "log.apply.done",
            "Applied Code Factory changes to {count} files.",
            count=_ensure_western(str(success_count)),
        )
    )
    return {
        "action": "apply",
        "target_dir": target_dir,
        "rows": rows,
        "summary": summary,
        "undo_available": bool(manifest_entries),
    }


def run_code_factory_undo(context, services, plugin_id: str):
    _ = plugin_id
    translate = lambda key, default, **kwargs: services.plugin_text("code_factory", key, default, **kwargs)
    manifest_path = _undo_manifest_path(services)
    if not manifest_path.exists():
        raise ValueError(_pt(translate, "error.undo.none", "No undo snapshot is available."))
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(_pt(translate, "error.undo.read", "Undo snapshot could not be read: {error}", error=str(exc))) from exc

    files = manifest.get("files", [])
    rows: list[dict[str, object]] = []
    for index, entry in enumerate(files, start=1):
        target = Path(str(entry.get("path", "")))
        backup_name = str(entry.get("backup", "")).strip()
        backup_path = _undo_root(services) / "backups" / backup_name
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(backup_path.read_bytes())
            mode = entry.get("mode")
            if isinstance(mode, int):
                os.chmod(target, mode)
            rows.append(
                {
                    "path": str(target),
                    "relative_path": target.name,
                    "operation_id": "undo",
                    "operation_label": _operation_text("undo", translate=translate),
                    "line_number": None,
                    "line_display": _line_number_display(None, translate=translate),
                    "status": "UNDONE",
                    "status_label": _status_text("UNDONE", translate=translate),
                    "summary": _pt(translate, "undo.file", "Restored the original file."),
                    "before": "",
                    "after": "",
                    "detected_eol": "None",
                }
            )
        except Exception as exc:
            rows.append(
                {
                    "path": str(target),
                    "relative_path": target.name,
                    "operation_id": "undo",
                    "operation_label": _operation_text("undo", translate=translate),
                    "line_number": None,
                    "line_display": _line_number_display(None, translate=translate),
                    "status": "ERROR",
                    "status_label": _status_text("ERROR", translate=translate),
                    "summary": _pt(translate, "error.undo.file", "Failed to restore original file: {error}", error=str(exc)),
                    "before": "",
                    "after": "",
                    "detected_eol": "None",
                }
            )
        context.progress(index / float(max(1, len(files))))

    if all(row["status"] == "UNDONE" for row in rows):
        shutil.rmtree(_undo_root(services), ignore_errors=True)

    context.log(
        _pt(
            translate,
            "log.undo.done",
            "Undo finished for {count} files.",
            count=_ensure_western(str(sum(1 for row in rows if row["status"] == "UNDONE"))),
        )
    )
    return {
        "action": "undo",
        "rows": rows,
        "summary": {
            "scanned_files": len(files),
            "text_files": len(files),
            "changed_files": sum(1 for row in rows if row["status"] == "UNDONE"),
            "skipped_files": 0,
            "error_files": sum(1 for row in rows if row["status"] == "ERROR"),
            "result_rows": len(rows),
            "eol_counts": {"LF": 0, "CRLF": 0, "Mixed": 0, "None": 0},
        },
        "undo_available": not all(row["status"] == "UNDONE" for row in rows),
    }


class CodeFactoryPlugin(QtPlugin):
    plugin_id = "code_factory"
    name = "Code Factory"
    description = "Preview, apply, and undo code cleanup, comment stripping, sanitization, and packing operations across a project folder."
    category = "Web Dev"
    preferred_icon = "code"

    def create_widget(self, services) -> QWidget:
        return CodeFactoryPage(services, self.plugin_id)


class CodeFactoryPage(QWidget):
    def __init__(self, services, plugin_id: str):
        super().__init__()
        self.services = services
        self.plugin_id = plugin_id
        self.tr = bind_tr(services, plugin_id)
        self._rows: list[dict[str, object]] = []
        self._last_preview_signature = ""
        self._last_preview_summary: dict[str, object] | None = None
        self._preview_active = False
        self._build_ui()
        self._apply_texts()
        self._update_undo_button_state()
        self.services.i18n.language_changed.connect(self._apply_texts)
        self.services.theme_manager.theme_changed.connect(self._handle_theme_change)

    def _pt(self, key: str, default: str | None = None, **kwargs) -> str:
        return self.tr(key, default, **kwargs)

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 28, 28, 28)
        outer.setSpacing(16)

        self.title_label = QLabel()
        outer.addWidget(self.title_label)

        self.description_label = QLabel()
        self.description_label.setWordWrap(True)
        outer.addWidget(self.description_label)

        path_row = QHBoxLayout()
        path_row.setSpacing(10)
        self.path_input = PathLineEdit(mode="directory")
        self.path_input.textChanged.connect(self._invalidate_preview)
        self.path_input.path_dropped.connect(self._invalidate_preview)
        path_row.addWidget(self.path_input, 1)
        self.browse_button = QPushButton()
        self.browse_button.clicked.connect(self._browse_folder)
        path_row.addWidget(self.browse_button)
        outer.addLayout(path_row)

        self.options_card = QFrame()
        options_layout = QVBoxLayout(self.options_card)
        options_layout.setContentsMargins(16, 16, 16, 16)
        options_layout.setSpacing(12)

        self.options_intro = QLabel()
        self.options_intro.setWordWrap(True)
        options_layout.addWidget(self.options_intro)

        cards_grid = QGridLayout()
        cards_grid.setHorizontalSpacing(12)
        cards_grid.setVerticalSpacing(12)
        options_layout.addLayout(cards_grid)

        self.cleanup_card = self._create_group_card()
        cleanup_layout = self.cleanup_card.layout()
        self.cleanup_title = QLabel()
        cleanup_layout.addWidget(self.cleanup_title)
        self.cleanup_desc = QLabel()
        self.cleanup_desc.setWordWrap(True)
        cleanup_layout.addWidget(self.cleanup_desc)
        self.trim_checkbox = self._create_option_checkbox(cleanup_layout, checked=True)
        self.blank_checkbox = self._create_option_checkbox(cleanup_layout, checked=True)
        indent_row = QHBoxLayout()
        self.indent_label = QLabel()
        indent_row.addWidget(self.indent_label)
        self.indent_mode_combo = QComboBox()
        self.indent_mode_combo.currentIndexChanged.connect(self._invalidate_preview)
        indent_row.addWidget(self.indent_mode_combo, 1)
        self.indent_width = QSpinBox()
        self.indent_width.setRange(2, 8)
        self.indent_width.setValue(4)
        self.indent_width.valueChanged.connect(self._invalidate_preview)
        indent_row.addWidget(self.indent_width)
        cleanup_layout.addLayout(indent_row)
        self.eof_checkbox = self._create_option_checkbox(cleanup_layout, checked=True)
        eol_row = QHBoxLayout()
        self.eol_label = QLabel()
        eol_row.addWidget(self.eol_label)
        self.eol_combo = QComboBox()
        self.eol_combo.currentIndexChanged.connect(self._invalidate_preview)
        eol_row.addWidget(self.eol_combo, 1)
        cleanup_layout.addLayout(eol_row)
        cards_grid.addWidget(self.cleanup_card, 0, 0)

        self.comments_card = self._create_group_card()
        comments_layout = self.comments_card.layout()
        self.comments_title = QLabel()
        comments_layout.addWidget(self.comments_title)
        self.comments_desc = QLabel()
        self.comments_desc.setWordWrap(True)
        comments_layout.addWidget(self.comments_desc)
        self.todo_checkbox = self._create_option_checkbox(comments_layout)
        self.block_checkbox = self._create_option_checkbox(comments_layout)
        self.line_checkbox = self._create_option_checkbox(comments_layout)
        cards_grid.addWidget(self.comments_card, 0, 1)

        self.sanitize_card = self._create_group_card()
        sanitize_layout = self.sanitize_card.layout()
        self.sanitize_title = QLabel()
        sanitize_layout.addWidget(self.sanitize_title)
        self.sanitize_desc = QLabel()
        self.sanitize_desc.setWordWrap(True)
        sanitize_layout.addWidget(self.sanitize_desc)
        self.mask_checkbox = self._create_option_checkbox(sanitize_layout)
        self.paths_checkbox = self._create_option_checkbox(sanitize_layout)
        self.ips_checkbox = self._create_option_checkbox(sanitize_layout)
        cards_grid.addWidget(self.sanitize_card, 1, 0)

        self.pack_card = self._create_group_card()
        pack_layout = self.pack_card.layout()
        self.pack_title = QLabel()
        pack_layout.addWidget(self.pack_title)
        self.pack_desc = QLabel()
        self.pack_desc.setWordWrap(True)
        pack_layout.addWidget(self.pack_desc)
        self.brace_checkbox = self._create_option_checkbox(pack_layout)
        self.minify_checkbox = self._create_option_checkbox(pack_layout)
        self.pack_note = QLabel()
        self.pack_note.setWordWrap(True)
        pack_layout.addWidget(self.pack_note)
        cards_grid.addWidget(self.pack_card, 1, 1)

        outer.addWidget(self.options_card)

        actions_row = QHBoxLayout()
        actions_row.setSpacing(10)
        self.preview_button = QPushButton()
        apply_semantic_class(self.preview_button, "button_class")
        self.preview_button.clicked.connect(self._run_preview)
        actions_row.addWidget(self.preview_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.cancel_button = QPushButton()
        apply_semantic_class(self.cancel_button, "inline_button_class")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self._cancel_preview)
        actions_row.addWidget(self.cancel_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.apply_button = QPushButton()
        apply_semantic_class(self.apply_button, "button_class")
        self.apply_button.setEnabled(False)
        self.apply_button.clicked.connect(self._run_apply)
        actions_row.addWidget(self.apply_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.undo_button = QPushButton()
        apply_semantic_class(self.undo_button, "inline_button_class")
        self.undo_button.clicked.connect(self._run_undo)
        actions_row.addWidget(self.undo_button, 0, Qt.AlignmentFlag.AlignLeft)
        actions_row.addStretch(1)
        outer.addLayout(actions_row)

        self.summary_card = QFrame()
        summary_layout = QVBoxLayout(self.summary_card)
        summary_layout.setContentsMargins(16, 14, 16, 14)
        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        summary_layout.addWidget(self.summary_label)
        outer.addWidget(self.summary_card)

        filters_row = QHBoxLayout()
        filters_row.setSpacing(10)
        self.search_input = QLineEdit()
        self.search_input.textChanged.connect(self._apply_filters)
        filters_row.addWidget(self.search_input, 1)
        self.operation_filter = QComboBox()
        self.operation_filter.currentIndexChanged.connect(self._apply_filters)
        filters_row.addWidget(self.operation_filter)
        self.status_filter = QComboBox()
        self.status_filter.currentIndexChanged.connect(self._apply_filters)
        filters_row.addWidget(self.status_filter)
        outer.addLayout(filters_row)

        self.results_splitter = QSplitter(Qt.Orientation.Vertical)

        self.table = QTableWidget(0, 5)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.itemSelectionChanged.connect(self._render_selected_details)
        configure_resizable_table(
            self.table,
            stretch_columns={0, 4},
            resize_to_contents_columns={1, 2, 3},
            default_widths={0: 260, 4: 440},
        )
        self.results_splitter.addWidget(self.table)

        self.details_output = QPlainTextEdit()
        self.details_output.setReadOnly(True)
        apply_semantic_class(self.details_output, "output_class")
        self.results_splitter.addWidget(self.details_output)
        self.results_splitter.setStretchFactor(0, 3)
        self.results_splitter.setStretchFactor(1, 2)
        outer.addWidget(self.results_splitter, 1)

        for widget in (
            self.trim_checkbox,
            self.blank_checkbox,
            self.eof_checkbox,
            self.todo_checkbox,
            self.block_checkbox,
            self.line_checkbox,
            self.mask_checkbox,
            self.paths_checkbox,
            self.ips_checkbox,
            self.brace_checkbox,
            self.minify_checkbox,
        ):
            widget.toggled.connect(self._invalidate_preview)

    def _create_group_card(self) -> QFrame:
        card = QFrame()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)
        return card

    def _create_option_checkbox(self, parent_layout: QVBoxLayout, *, checked: bool = False) -> QCheckBox:
        checkbox = QCheckBox()
        checkbox.setChecked(checked)
        parent_layout.addWidget(checkbox)
        return checkbox

    def _apply_texts(self) -> None:
        self.setLayoutDirection(self.services.i18n.layout_direction())
        align = Qt.AlignmentFlag.AlignRight if self.services.i18n.is_rtl() else Qt.AlignmentFlag.AlignLeft
        for widget in (self.path_input, self.search_input, self.details_output):
            widget.setLayoutDirection(self.services.i18n.layout_direction())
        self.title_label.setText(self._pt("title", "Code Factory"))
        self.description_label.setText(
            self._pt(
                "description",
                "Preview, apply, and undo grouped code cleanup, comment stripping, safe-to-share masking, and pack operations across a project folder.",
            )
        )
        self.path_input.setPlaceholderText(self._pt("path.placeholder", "Select or drop a project folder..."))
        self.browse_button.setText(self._pt("browse", "Browse"))
        self.options_intro.setText(self._pt("options.intro", "Choose exactly which operations to preview or apply. Riskier pack options stay off by default."))

        self.cleanup_title.setText(self._pt("group.cleanup.title", "Cleanup"))
        self.cleanup_desc.setText(self._pt("group.cleanup.desc", "Whitespace, indentation, EOF newline, and line ending normalization."))
        self.trim_checkbox.setText(self._pt("option.trim.label", "Trim trailing whitespace"))
        self.trim_checkbox.setToolTip(self._pt("option.trim.desc", "Remove spaces and tabs at the end of lines."))
        self.blank_checkbox.setText(self._pt("option.blank.label", "Compress repeated blank lines"))
        self.blank_checkbox.setToolTip(self._pt("option.blank.desc", "Keep only one blank line inside each empty-line run."))
        self.indent_label.setText(self._pt("option.indent.label", "Indentation"))
        self.eof_checkbox.setText(self._pt("option.eof.label", "Ensure exactly one newline at end of file"))
        self.eof_checkbox.setToolTip(self._pt("option.eof.desc", "Normalize the file to end with a single trailing newline."))
        self.eol_label.setText(self._pt("option.eol.label", "Line endings"))

        self.comments_title.setText(self._pt("group.comments.title", "Comments"))
        self.comments_desc.setText(self._pt("group.comments.desc", "Grammar-aware comment cleanup for supported file types only."))
        self.todo_checkbox.setText(self._pt("option.todo.label", "Remove TODO and FIXME comment lines"))
        self.todo_checkbox.setToolTip(self._pt("option.todo.desc", "Delete comment-only lines that contain TODO or FIXME markers."))
        self.block_checkbox.setText(self._pt("option.block.label", "Strip block comments"))
        self.block_checkbox.setToolTip(self._pt("option.block.desc", "Remove multi-line comment blocks for supported syntaxes."))
        self.line_checkbox.setText(self._pt("option.line.label", "Strip line comments"))
        self.line_checkbox.setToolTip(self._pt("option.line.desc", "Remove inline and whole-line comments for supported syntaxes."))

        self.sanitize_title.setText(self._pt("group.sanitize.title", "Safe-to-Share"))
        self.sanitize_desc.setText(self._pt("group.sanitize.desc", "Mask secrets and scrub local paths or IP addresses before sharing code."))
        self.mask_checkbox.setText(self._pt("option.mask.label", "Mask sensitive strings"))
        self.mask_checkbox.setToolTip(self._pt("option.mask.desc", "Replace obvious tokens, secrets, and password-like assignments with redacted values."))
        self.paths_checkbox.setText(self._pt("option.paths.label", "Neutralize absolute paths"))
        self.paths_checkbox.setToolTip(self._pt("option.paths.desc", "Replace local absolute paths with a generic placeholder."))
        self.ips_checkbox.setText(self._pt("option.ips.label", "Scrub IPv4 and IPv6 addresses"))
        self.ips_checkbox.setToolTip(self._pt("option.ips.desc", "Mask hard-coded IP addresses before sharing the code."))

        self.pack_title.setText(self._pt("group.pack.title", "Pack"))
        self.pack_desc.setText(self._pt("group.pack.desc", "More aggressive vertical-space and size reduction for supported formats."))
        self.brace_checkbox.setText(self._pt("option.brace.label", "Move opening braces onto the previous line"))
        self.brace_checkbox.setToolTip(self._pt("option.brace.desc", "Collapse lone opening-brace lines into the statement above them."))
        self.minify_checkbox.setText(self._pt("option.minify.label", "Full minify into a compact single-line result"))
        self.minify_checkbox.setToolTip(self._pt("option.minify.desc", "Use a conservative format-specific minify pass on supported file types."))
        self.pack_note.setText(self._pt("group.pack.note", "Pack options are intentionally off by default because they are the most behavior-sensitive operations."))

        self.preview_button.setText(self._pt("button.preview", "Preview Changes"))
        self.cancel_button.setText(self._pt("button.cancel", "Cancel Preview"))
        self.apply_button.setText(self._pt("button.apply", "Apply"))
        self.undo_button.setText(self._pt("button.undo", "Undo Last Run"))
        self.search_input.setPlaceholderText(self._pt("filter.search", "Filter results..."))

        current_indent = self.indent_mode_combo.currentData()
        self.indent_mode_combo.blockSignals(True)
        self.indent_mode_combo.clear()
        self.indent_mode_combo.addItem(self._pt("indent.mode.keep", "No change"), "keep")
        self.indent_mode_combo.addItem(self._pt("indent.mode.spaces", "Convert to spaces"), "spaces")
        self.indent_mode_combo.addItem(self._pt("indent.mode.tabs", "Convert to tabs"), "tabs")
        self._restore_combo_data(self.indent_mode_combo, current_indent or "keep")
        self.indent_mode_combo.blockSignals(False)

        current_eol = self.eol_combo.currentData()
        self.eol_combo.blockSignals(True)
        self.eol_combo.clear()
        self.eol_combo.addItem(self._pt("eol.keep", "Keep detected"), "keep")
        self.eol_combo.addItem(self._pt("eol.lf", "Convert to LF"), "lf")
        self.eol_combo.addItem(self._pt("eol.crlf", "Convert to CRLF"), "crlf")
        self._restore_combo_data(self.eol_combo, current_eol or "keep")
        self.eol_combo.blockSignals(False)

        current_op = self.operation_filter.currentData()
        self.operation_filter.blockSignals(True)
        self.operation_filter.clear()
        self.operation_filter.addItem(self._pt("filter.operation.all", "All operations"), "ALL")
        for operation_id in OPERATION_ORDER:
            self.operation_filter.addItem(_operation_text(operation_id, translate=self.tr), operation_id)
        self._restore_combo_data(self.operation_filter, current_op or "ALL")
        self.operation_filter.blockSignals(False)

        current_status = self.status_filter.currentData()
        self.status_filter.blockSignals(True)
        self.status_filter.clear()
        self.status_filter.addItem(self._pt("filter.status.all", "All statuses"), "ALL")
        for status_code in STATUS_ORDER[1:]:
            self.status_filter.addItem(_status_text(status_code, translate=self.tr), status_code)
        self._restore_combo_data(self.status_filter, current_status or "ALL")
        self.status_filter.blockSignals(False)

        self.table.setHorizontalHeaderLabels(
            [
                self._pt("table.file", "File"),
                self._pt("table.operation", "Operation"),
                self._pt("table.line", "Line"),
                self._pt("table.status", "Status"),
                self._pt("table.summary", "Summary"),
            ]
        )
        self.details_output.setPlaceholderText(self._pt("details.placeholder", "Select a result row to inspect the before/after preview and file metadata."))
        if not self._rows and not self._preview_active:
            self.summary_label.setText(self._pt("summary.ready", "Choose a project folder and preview the operations you want to run."))
            self.details_output.setPlainText(self._pt("details.empty", "Select a result row to inspect its details."))
        else:
            self._render_summary(self._last_preview_summary or {}, undo_available=self.undo_button.isEnabled())
            if self._rows:
                self._populate_table()
                self._render_selected_details()
            else:
                self.table.setRowCount(0)
                self.details_output.setPlainText(self._pt("details.clean", "No matching changes were generated for the selected folder and operations."))
        self._apply_theme_styles()
        self.title_label.setAlignment(align)
        self.description_label.setAlignment(align)
        self.summary_label.setAlignment(align)

    def _restore_combo_data(self, combo: QComboBox, target) -> None:
        for index in range(combo.count()):
            if combo.itemData(index) == target:
                combo.setCurrentIndex(index)
                return
        if combo.count():
            combo.setCurrentIndex(0)

    def _apply_theme_styles(self) -> None:
        palette = self.services.theme_manager.current_palette()
        apply_page_chrome(
            palette,
            title_label=self.title_label,
            description_label=self.description_label,
            cards=(
                self.options_card,
                self.cleanup_card,
                self.comments_card,
                self.sanitize_card,
                self.pack_card,
                self.summary_card,
            ),
            summary_label=self.summary_label,
        )

    def _handle_theme_change(self, _mode: str) -> None:
        self._apply_theme_styles()

    def _browse_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            self._pt("dialog.browse", "Select Folder"),
            self.path_input.text().strip() or str(self.services.default_output_path()),
        )
        if folder:
            self.path_input.setText(folder)

    def _settings(self) -> dict[str, object]:
        return {
            "trim_trailing_ws": self.trim_checkbox.isChecked(),
            "compress_blank_lines": self.blank_checkbox.isChecked(),
            "indent_mode": self.indent_mode_combo.currentData() or "keep",
            "indent_width": self.indent_width.value(),
            "ensure_eof_newline": self.eof_checkbox.isChecked(),
            "eol_mode": self.eol_combo.currentData() or "keep",
            "purge_todos": self.todo_checkbox.isChecked(),
            "strip_block_comments": self.block_checkbox.isChecked(),
            "strip_line_comments": self.line_checkbox.isChecked(),
            "mask_secrets": self.mask_checkbox.isChecked(),
            "neutralize_paths": self.paths_checkbox.isChecked(),
            "scrub_ips": self.ips_checkbox.isChecked(),
            "brace_internalizer": self.brace_checkbox.isChecked(),
            "full_minify": self.minify_checkbox.isChecked(),
        }

    def _target_dir(self) -> Path | None:
        raw = self.path_input.text().strip()
        if not raw:
            return None
        path = Path(raw)
        if not path.is_dir():
            return None
        return path

    def _settings_signature(self) -> str:
        target_dir = str(self._target_dir() or "")
        return json.dumps({"dir": target_dir, "settings": self._settings()}, sort_keys=True)

    def _can_apply_current_preview(self) -> bool:
        return bool(self._last_preview_signature and any(row.get("status") == "PLANNED" for row in self._rows))

    def _clear_preview_state(self) -> None:
        self._rows = []
        self._preview_active = False
        self._last_preview_signature = ""
        self._last_preview_summary = None
        self.table.setRowCount(0)
        self.table.clearSelection()
        self._set_busy(False)
        self._render_summary({}, undo_available=_undo_available(self.services))
        self.details_output.setPlainText(self._pt("details.empty", "Select a result row to inspect its details."))

    def _invalidate_preview(self, *_args) -> None:
        self._last_preview_signature = ""
        self.apply_button.setEnabled(False)

    def _cancel_preview(self) -> None:
        self._clear_preview_state()

    def _validate_run(self) -> tuple[Path | None, dict[str, object] | None]:
        target_dir = self._target_dir()
        if target_dir is None:
            QMessageBox.warning(self, self._pt("dialog.missing.title", "Missing Input"), self._pt("dialog.missing.folder", "Choose a valid folder first."))
            return None, None
        settings = self._settings()
        if not _selected_operation_ids(settings):
            QMessageBox.warning(self, self._pt("dialog.missing.title", "Missing Input"), self._pt("dialog.missing.ops", "Select at least one operation to preview or apply."))
            return None, None
        return target_dir, settings

    def _set_busy(self, busy: bool) -> None:
        for widget in (
            self.trim_checkbox,
            self.blank_checkbox,
            self.indent_mode_combo,
            self.indent_width,
            self.eof_checkbox,
            self.eol_combo,
            self.todo_checkbox,
            self.block_checkbox,
            self.line_checkbox,
            self.mask_checkbox,
            self.paths_checkbox,
            self.ips_checkbox,
            self.brace_checkbox,
            self.minify_checkbox,
        ):
            widget.setEnabled(not busy)
        self.preview_button.setEnabled(not busy)
        self.cancel_button.setEnabled(not busy and self._preview_active)
        self.browse_button.setEnabled(not busy)
        self.path_input.setEnabled(not busy)
        self.undo_button.setEnabled(not busy and _undo_available(self.services))
        if busy:
            self.apply_button.setEnabled(False)
        else:
            self.apply_button.setEnabled(self._can_apply_current_preview())

    def _run_preview(self) -> None:
        target_dir, settings = self._validate_run()
        if target_dir is None or settings is None:
            return
        self._set_busy(True)
        self.summary_label.setText(self._pt("summary.preview.running", "Building preview..."))
        self.table.setRowCount(0)
        self._rows = []
        self.details_output.setPlainText("")
        self.services.run_task(
            lambda context: run_code_factory_preview(context, self.services, self.plugin_id, str(target_dir), settings),
            on_result=self._handle_preview_result,
            on_error=self._handle_task_error,
            on_finished=lambda: self._finish_action("preview"),
            status_text=self._pt("summary.preview.running", "Building preview..."),
        )

    def _run_apply(self) -> None:
        target_dir, settings = self._validate_run()
        if target_dir is None or settings is None:
            return
        if self._last_preview_signature != self._settings_signature():
            QMessageBox.information(self, self._pt("dialog.preview.title", "Preview Required"), self._pt("dialog.preview.body", "Run Preview Changes first so the apply step uses the latest folder and options."))
            return
        confirm = QMessageBox.question(
            self,
            self._pt("dialog.apply.title", "Apply Changes"),
            self._pt("dialog.apply.body", "Apply the previewed Code Factory changes to the original files?"),
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self._set_busy(True)
        self.summary_label.setText(self._pt("summary.apply.running", "Applying changes..."))
        self.services.run_task(
            lambda context: run_code_factory_apply(context, self.services, self.plugin_id, str(target_dir), settings),
            on_result=self._handle_apply_result,
            on_error=self._handle_task_error,
            on_finished=lambda: self._finish_action("apply"),
            status_text=self._pt("summary.apply.running", "Applying changes..."),
        )

    def _run_undo(self) -> None:
        if not _undo_available(self.services):
            QMessageBox.information(self, self._pt("dialog.undo.title", "Undo Unavailable"), self._pt("dialog.undo.none", "No undo snapshot is currently available."))
            return
        confirm = QMessageBox.question(
            self,
            self._pt("dialog.undo.title", "Undo Last Run"),
            self._pt("dialog.undo.body", "Restore the most recent Code Factory apply session?"),
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self._set_busy(True)
        self.summary_label.setText(self._pt("summary.undo.running", "Restoring the last run..."))
        self.services.run_task(
            lambda context: run_code_factory_undo(context, self.services, self.plugin_id),
            on_result=self._handle_undo_result,
            on_error=self._handle_task_error,
            on_finished=lambda: self._finish_action("undo"),
            status_text=self._pt("summary.undo.running", "Restoring the last run..."),
        )

    def _handle_preview_result(self, payload: object) -> None:
        result = dict(payload)
        self._rows = list(result.get("rows", []))
        self._preview_active = True
        self._last_preview_summary = dict(result.get("summary", {}))
        self._last_preview_signature = self._settings_signature()
        self._populate_table()
        self._render_summary(self._last_preview_summary, undo_available=bool(result.get("undo_available")))
        self.cancel_button.setEnabled(True)
        if self._rows:
            self._select_first_visible_row()
        else:
            self.details_output.setPlainText(self._pt("details.clean", "No matching changes were generated for the selected folder and operations."))
        has_planned = any(row.get("status") == "PLANNED" for row in self._rows)
        self.apply_button.setEnabled(has_planned)
        if has_planned:
            self.services.record_run(self.plugin_id, "SUCCESS", self._pt("run.preview", "Previewed Code Factory changes for {path}", path=result.get("target_dir", "")))
        else:
            self.services.record_run(self.plugin_id, "WARNING", self._pt("run.preview.none", "Preview completed with no editable changes."))

    def _handle_apply_result(self, payload: object) -> None:
        result = dict(payload)
        self._rows = list(result.get("rows", []))
        self._preview_active = False
        self._last_preview_summary = dict(result.get("summary", {}))
        self._last_preview_signature = ""
        self._populate_table()
        self._render_summary(self._last_preview_summary, undo_available=bool(result.get("undo_available")))
        if self._rows:
            self._select_first_visible_row()
        changed_files = int(self._last_preview_summary.get("changed_files", 0))
        status = "SUCCESS" if changed_files > 0 else "WARNING"
        self.services.record_run(
            self.plugin_id,
            status,
            self._pt("run.apply", "Applied Code Factory changes to {count} files.", count=_ensure_western(str(changed_files))),
        )
        self._update_undo_button_state()

    def _handle_undo_result(self, payload: object) -> None:
        result = dict(payload)
        self._rows = list(result.get("rows", []))
        self._preview_active = False
        self._last_preview_summary = dict(result.get("summary", {}))
        self._last_preview_signature = ""
        self._populate_table()
        self._render_summary(self._last_preview_summary, undo_available=bool(result.get("undo_available")))
        if self._rows:
            self._select_first_visible_row()
        restored = int(self._last_preview_summary.get("changed_files", 0))
        status = "SUCCESS" if restored > 0 else "WARNING"
        self.services.record_run(
            self.plugin_id,
            status,
            self._pt("run.undo", "Restored {count} files from the last Code Factory snapshot.", count=_ensure_western(str(restored))),
        )
        self._update_undo_button_state()

    def _handle_task_error(self, payload: object) -> None:
        self._preview_active = False
        message = payload.get("message", self._pt("error.unknown", "Unknown Code Factory error.")) if isinstance(payload, dict) else str(payload)
        self.summary_label.setText(message)
        self.details_output.setPlainText(message)
        self.services.record_run(self.plugin_id, "ERROR", message[:500])
        self.apply_button.setEnabled(False)
        self.cancel_button.setEnabled(False)

    def _finish_action(self, action: str) -> None:
        self._set_busy(False)
        if action != "preview":
            self.apply_button.setEnabled(False)

    def _update_undo_button_state(self) -> None:
        self.undo_button.setEnabled(_undo_available(self.services))

    def _populate_table(self) -> None:
        self.table.setRowCount(0)
        for row_index, row in enumerate(self._rows):
            self.table.insertRow(row_index)
            file_item = QTableWidgetItem(str(row.get("relative_path", "")))
            file_item.setData(Qt.ItemDataRole.UserRole, row_index)
            self.table.setItem(row_index, 0, file_item)
            self.table.setItem(row_index, 1, QTableWidgetItem(str(row.get("operation_label", ""))))
            self.table.setItem(row_index, 2, QTableWidgetItem(str(row.get("line_display", ""))))
            self.table.setItem(row_index, 3, QTableWidgetItem(str(row.get("status_label", ""))))
            self.table.setItem(row_index, 4, QTableWidgetItem(str(row.get("summary", ""))))
        self._apply_filters()
        self._select_first_visible_row()

    def _render_summary(self, summary: dict[str, object], *, undo_available: bool) -> None:
        if not summary:
            self.summary_label.setText(self._pt("summary.ready", "Choose a project folder and preview the operations you want to run."))
            return
        eol_counts = summary.get("eol_counts", {})
        lf = _ensure_western(str(eol_counts.get("LF", 0)))
        crlf = _ensure_western(str(eol_counts.get("CRLF", 0)))
        mixed = _ensure_western(str(eol_counts.get("Mixed", 0)))
        scanned = _ensure_western(str(summary.get("scanned_files", 0)))
        text_files = _ensure_western(str(summary.get("text_files", 0)))
        changed = _ensure_western(str(summary.get("changed_files", 0)))
        skipped = _ensure_western(str(summary.get("skipped_files", 0)))
        rows = _ensure_western(str(summary.get("result_rows", 0)))
        undo_text = self._pt("summary.undo.ready", "Undo is ready.") if undo_available else self._pt("summary.undo.empty", "Undo is not available yet.")
        self.summary_label.setText(
            self._pt(
                "summary.metrics",
                "Scanned {scanned} files ({text} text). Changed {changed} files, listed {rows} result rows, and skipped {skipped} files where needed. Line endings detected: LF {lf}, CRLF {crlf}, Mixed {mixed}. {undo}",
                scanned=scanned,
                text=text_files,
                changed=changed,
                rows=rows,
                skipped=skipped,
                lf=lf,
                crlf=crlf,
                mixed=mixed,
                undo=undo_text,
            )
        )

    def _apply_filters(self) -> None:
        needle = self.search_input.text().strip().lower()
        operation_id = self.operation_filter.currentData() or "ALL"
        status_code = self.status_filter.currentData() or "ALL"
        for row_index, row in enumerate(self._rows):
            matches_text = True
            if needle:
                haystack = " ".join(
                    [
                        str(row.get("relative_path", "")),
                        str(row.get("operation_label", "")),
                        str(row.get("summary", "")),
                        str(row.get("before", "")),
                        str(row.get("after", "")),
                    ]
                ).lower()
                matches_text = needle in haystack
            matches_operation = operation_id == "ALL" or row.get("operation_id") == operation_id
            matches_status = status_code == "ALL" or row.get("status") == status_code
            self.table.setRowHidden(row_index, not (matches_text and matches_operation and matches_status))
        self._select_first_visible_row()
        self._render_selected_details()

    def _select_first_visible_row(self) -> None:
        current_row = self.table.currentRow()
        if current_row >= 0 and not self.table.isRowHidden(current_row):
            return
        for row_index in range(self.table.rowCount()):
            if not self.table.isRowHidden(row_index):
                self.table.selectRow(row_index)
                return
        self.table.clearSelection()

    def _selected_row(self) -> dict[str, object] | None:
        current = self.table.item(self.table.currentRow(), 0)
        if current is None:
            return None
        row_index = current.data(Qt.ItemDataRole.UserRole)
        if row_index is None:
            return None
        try:
            return self._rows[int(row_index)]
        except Exception:
            return None

    def _render_selected_details(self) -> None:
        row = self._selected_row()
        if row is None:
            self.details_output.setPlainText(self._pt("details.empty", "Select a result row to inspect its details."))
            return
        details = [
            f"{self._pt('details.file', 'File')}: {row.get('path', '')}",
            f"{self._pt('details.operation', 'Operation')}: {row.get('operation_label', '')}",
            f"{self._pt('details.status', 'Status')}: {row.get('status_label', '')}",
            f"{self._pt('details.eol', 'Detected line endings')}: {row.get('detected_eol', 'None')}",
            f"{self._pt('details.summary', 'Summary')}: {row.get('summary', '')}",
            "",
            f"{self._pt('details.before', 'Before')}:",
            str(row.get("before", "")) or self._pt("details.none", "No preview available."),
            "",
            f"{self._pt('details.after', 'After')}:",
            str(row.get("after", "")) or self._pt("details.none", "No preview available."),
        ]
        self.details_output.setPlainText("\n".join(details))

    def _show_context_menu(self, position) -> None:
        item = self.table.itemAt(position)
        if item is not None:
            self.table.setCurrentItem(item)
        row = self._selected_row()
        if row is None:
            return
        target_path = Path(str(row.get("path", "")))
        items = [
            MenuActionSpec(
                label=self._pt("context.open_file", "Open File"),
                callback=lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(target_path))),
            ),
            MenuActionSpec(
                label=self._pt("context.open_folder", "Open Containing Folder"),
                callback=lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(target_path.parent))),
            ),
            MenuActionSpec(
                label=self._pt("context.copy_before", "Copy Before Preview"),
                callback=lambda: QGuiApplication.clipboard().setText(str(row.get("before", ""))),
                enabled=bool(row.get("before")),
            ),
            MenuActionSpec(
                label=self._pt("context.copy_after", "Copy After Preview"),
                callback=lambda: QGuiApplication.clipboard().setText(str(row.get("after", ""))),
                enabled=bool(row.get("after")),
            ),
        ]
        show_context_menu(self, self.table.viewport().mapToGlobal(position), items)
