from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QMimeData, QUrl
from PySide6.QtGui import QClipboard, QImage


@dataclass(frozen=True)
class ClipboardEntry:
    entry_id: int
    content: str
    content_type: str
    label: str
    category: str
    pinned: bool
    created_at: str
    html_content: str
    image_path: str
    file_paths_json: str
    metadata_json: str

    @property
    def file_paths(self) -> list[str]:
        try:
            payload = json.loads(self.file_paths_json or "[]")
        except Exception:
            return []
        return [str(item) for item in payload if str(item).strip()]

    @property
    def metadata(self) -> dict:
        try:
            payload = json.loads(self.metadata_json or "{}")
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}


URL_PREFIXES = ("http://", "https://")


def detect_content_type(text: str) -> str:
    stripped = (text or "").strip()
    if not stripped:
        return "text"
    if stripped.startswith(URL_PREFIXES):
        return "url"
    if "\t" in stripped and stripped.count("\t") >= 2:
        return "table"
    if stripped.startswith("<") and ("</html>" in stripped.lower() or "</div>" in stripped.lower()):
        return "rich_text"
    if any(token in stripped for token in ("def ", "class ", "import ", "const ", "let ", "=>", "{", "}")):
        return "code"
    if stripped.startswith("/") or stripped.startswith("\\") or ":/" in stripped or ":\\" in stripped:
        return "file_path"
    return "text"


class ClipboardStore:
    def __init__(self, db_path: Path, max_history: int = 400):
        self.db_path = Path(db_path)
        self.max_history = max_history
        self.assets_dir = self.db_path.parent / "clipboard_assets"
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self):
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS clipboard_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL,
                    content_hash TEXT UNIQUE NOT NULL,
                    content_type TEXT NOT NULL DEFAULT 'text',
                    label TEXT NOT NULL DEFAULT '',
                    category TEXT NOT NULL DEFAULT '',
                    pinned INTEGER NOT NULL DEFAULT 0,
                    html_content TEXT NOT NULL DEFAULT '',
                    image_path TEXT NOT NULL DEFAULT '',
                    file_paths_json TEXT NOT NULL DEFAULT '[]',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS clipboard_labels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS clipboard_categories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL
                )
                """
            )
            self._ensure_columns(connection)

    def _ensure_columns(self, connection: sqlite3.Connection) -> None:
        existing = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(clipboard_entries)").fetchall()
        }
        wanted = {
            "category": "TEXT NOT NULL DEFAULT ''",
            "pinned": "INTEGER NOT NULL DEFAULT 0",
            "html_content": "TEXT NOT NULL DEFAULT ''",
            "image_path": "TEXT NOT NULL DEFAULT ''",
            "file_paths_json": "TEXT NOT NULL DEFAULT '[]'",
            "metadata_json": "TEXT NOT NULL DEFAULT '{}'",
        }
        for column, definition in wanted.items():
            if column not in existing:
                connection.execute(f"ALTER TABLE clipboard_entries ADD COLUMN {column} {definition}")

    def _entry_hash(
        self,
        *,
        content: str,
        content_type: str,
        html_content: str = "",
        image_path: str = "",
        file_paths: list[str] | None = None,
        metadata: dict | None = None,
    ) -> str:
        image_hash = ""
        if image_path:
            image_file = Path(image_path)
            if image_file.exists():
                image_hash = hashlib.md5(image_file.read_bytes()).hexdigest()
        stable_metadata = self._stable_metadata(metadata or {})
        payload = {
            "content": content.strip(),
            "content_type": content_type,
            "html_content": html_content.strip(),
            "image_hash": image_hash,
            "file_paths": file_paths or [],
            "metadata": stable_metadata,
        }
        serialized = json.dumps(payload, sort_keys=True, ensure_ascii=True)
        return hashlib.md5(serialized.encode("utf-8", errors="replace")).hexdigest()

    @staticmethod
    def _stable_metadata(metadata: dict) -> dict:
        stable: dict[str, object] = {}
        for key in ("kind", "width", "height", "count", "names"):
            if key not in metadata:
                continue
            value = metadata.get(key)
            if key == "names" and isinstance(value, list):
                stable[key] = [str(item) for item in value]
            else:
                stable[key] = value
        return stable

    def add_entry(
        self,
        content: str,
        content_type: str | None = None,
        *,
        html_content: str = "",
        image_path: str = "",
        file_paths: list[str] | None = None,
        metadata: dict | None = None,
    ) -> bool:
        normalized = (content or "").strip()
        if not normalized and not image_path and not (file_paths or []):
            return False
        entry_type = content_type or detect_content_type(normalized)
        metadata_payload = metadata or {}
        content_hash = self._entry_hash(
            content=normalized,
            content_type=entry_type,
            html_content=html_content,
            image_path=image_path,
            file_paths=file_paths,
            metadata=metadata_payload,
        )
        file_paths_json = json.dumps(file_paths or [], ensure_ascii=False)
        metadata_json = json.dumps(metadata_payload, ensure_ascii=False)
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO clipboard_entries
                (content, content_hash, content_type, html_content, image_path, file_paths_json, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    normalized,
                    content_hash,
                    entry_type,
                    html_content or "",
                    image_path or "",
                    file_paths_json,
                    metadata_json,
                ),
            )
            if cursor.rowcount > 0:
                self._trim_history(connection)
                return True

            connection.execute(
                """
                UPDATE clipboard_entries
                SET created_at = CURRENT_TIMESTAMP
                WHERE content_hash = ?
                """,
                (content_hash,),
            )
            return True

    def add_mime_entry(self, mime_data: QMimeData | None) -> bool:
        if mime_data is None:
            return False

        formats = [str(item) for item in mime_data.formats()]
        metadata = {"formats": formats}

        urls = [url for url in mime_data.urls() if isinstance(url, QUrl) and url.isLocalFile()]
        if urls:
            file_paths = [url.toLocalFile() for url in urls if url.toLocalFile()]
            names = [Path(path).name for path in file_paths]
            metadata.update({"kind": "files", "count": len(file_paths), "names": names})
            return self.add_entry(
                "\n".join(file_paths),
                "files",
                file_paths=file_paths,
                metadata=metadata,
            )

        if mime_data.hasImage():
            image = mime_data.imageData()
            if isinstance(image, QImage):
                qimage = image
            elif hasattr(image, "toImage"):
                qimage = image.toImage()
            else:
                qimage = QImage()
            if not qimage.isNull():
                image_path = self._save_image(qimage)
                metadata.update({"kind": "image", "width": qimage.width(), "height": qimage.height()})
                return self.add_entry(
                    f"Image {qimage.width()}x{qimage.height()}",
                    "image",
                    image_path=str(image_path),
                    metadata=metadata,
                )

        html = (mime_data.html() or "").strip()
        text = (mime_data.text() or "").strip()
        if html:
            metadata.update({"kind": "rich_text", "has_html": True})
            return self.add_entry(
                text or "Rich text content",
                "rich_text",
                html_content=html,
                metadata=metadata,
            )

        if text:
            metadata.update({"kind": "text"})
            return self.add_entry(text, metadata=metadata)
        return False

    def _save_image(self, image: QImage) -> Path:
        image_bytes = bytes(image.bits().tobytes())
        image_hash = hashlib.md5(image_bytes).hexdigest()
        target = self.assets_dir / f"{image_hash}.png"
        if not target.exists():
            image.save(str(target), "PNG")
        return target

    def _trim_history(self, connection: sqlite3.Connection) -> None:
        count = connection.execute("SELECT COUNT(*) FROM clipboard_entries WHERE pinned = 0").fetchone()[0]
        overflow = count - self.max_history
        if overflow > 0:
            rows = connection.execute(
                """
                SELECT id, image_path FROM clipboard_entries
                WHERE pinned = 0
                ORDER BY id ASC
                LIMIT ?
                """,
                (overflow,),
            ).fetchall()
            image_paths = [row["image_path"] for row in rows]
            connection.execute(
                """
                DELETE FROM clipboard_entries
                WHERE id IN (
                    SELECT id FROM clipboard_entries
                    WHERE pinned = 0
                    ORDER BY id ASC
                    LIMIT ?
                )
                """,
                (overflow,),
            )
            self._cleanup_unused_assets(connection, image_paths)

    def list_entries(
        self,
        *,
        search: str = "",
        content_type: str = "ALL",
        label: str = "",
        category: str = "",
        pinned_only: bool = False,
    ) -> list[ClipboardEntry]:
        query = """
            SELECT id, content, content_type, label, category, pinned, created_at,
                   html_content, image_path, file_paths_json, metadata_json
            FROM clipboard_entries
        """
        conditions = []
        params = []
        if content_type and content_type != "ALL":
            conditions.append("content_type = ?")
            params.append(content_type)
        if label:
            conditions.append("label = ?")
            params.append(label)
        if category:
            conditions.append("category = ?")
            params.append(category)
        if pinned_only:
            conditions.append("pinned = 1")
        if search:
            conditions.append("(content LIKE ? OR label LIKE ? OR category LIKE ?)")
            params.extend([f"%{search}%"] * 3)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY pinned DESC, datetime(created_at) DESC, id DESC"
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [
            ClipboardEntry(
                entry_id=row["id"],
                content=row["content"],
                content_type=row["content_type"],
                label=row["label"],
                category=row["category"],
                pinned=bool(row["pinned"]),
                created_at=row["created_at"],
                html_content=row["html_content"],
                image_path=row["image_path"],
                file_paths_json=row["file_paths_json"],
                metadata_json=row["metadata_json"],
            )
            for row in rows
        ]

    def get_entry(self, entry_id: int) -> ClipboardEntry | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, content, content_type, label, category, pinned, created_at,
                       html_content, image_path, file_paths_json, metadata_json
                FROM clipboard_entries
                WHERE id = ?
                """,
                (entry_id,),
            ).fetchone()
        if row is None:
            return None
        return ClipboardEntry(
            entry_id=row["id"],
            content=row["content"],
            content_type=row["content_type"],
            label=row["label"],
            category=row["category"],
            pinned=bool(row["pinned"]),
            created_at=row["created_at"],
            html_content=row["html_content"],
            image_path=row["image_path"],
            file_paths_json=row["file_paths_json"],
            metadata_json=row["metadata_json"],
        )

    def restore_entry_to_clipboard(self, entry: ClipboardEntry, clipboard: QClipboard) -> bool:
        if entry.content_type == "files" and entry.file_paths:
            mime = QMimeData()
            mime.setUrls([QUrl.fromLocalFile(path) for path in entry.file_paths])
            mime.setText("\n".join(entry.file_paths))
            clipboard.setMimeData(mime)
            return True

        if entry.content_type == "image" and entry.image_path:
            image = QImage(entry.image_path)
            if not image.isNull():
                clipboard.setImage(image)
                return True

        if entry.html_content:
            mime = QMimeData()
            mime.setHtml(entry.html_content)
            if entry.content:
                mime.setText(entry.content)
            clipboard.setMimeData(mime)
            return True

        if entry.content:
            clipboard.setText(entry.content)
            return True
        return False

    def update_label(self, entry_id: int, label: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE clipboard_entries SET label = ? WHERE id = ?",
                (label.strip(), entry_id),
            )

    def update_category(self, entry_id: int, category: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE clipboard_entries SET category = ? WHERE id = ?",
                (category.strip(), entry_id),
            )

    def update_pinned(self, entry_id: int, pinned: bool) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE clipboard_entries
                SET pinned = ?, created_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (1 if pinned else 0, entry_id),
            )

    def delete_entry(self, entry_id: int) -> None:
        entry = self.get_entry(entry_id)
        if entry is None:
            return
        with self._connect() as connection:
            connection.execute("DELETE FROM clipboard_entries WHERE id = ?", (entry_id,))
            self._cleanup_unused_assets(connection, [entry.image_path])

    def clear_entries(self, preserve_pinned: bool = True) -> None:
        with self._connect() as connection:
            if preserve_pinned:
                rows = connection.execute(
                    "SELECT image_path FROM clipboard_entries WHERE pinned = 0"
                ).fetchall()
                image_paths = [row["image_path"] for row in rows]
                connection.execute("DELETE FROM clipboard_entries WHERE pinned = 0")
                self._cleanup_unused_assets(connection, image_paths)
            else:
                rows = connection.execute("SELECT image_path FROM clipboard_entries").fetchall()
                image_paths = [row["image_path"] for row in rows]
                connection.execute("DELETE FROM clipboard_entries")
                self._cleanup_unused_assets(connection, image_paths)

    def list_labels(self) -> list[str]:
        with self._connect() as connection:
            rows = connection.execute("SELECT name FROM clipboard_labels ORDER BY name").fetchall()
        return [row["name"] for row in rows]

    def add_label(self, label: str) -> None:
        normalized = label.strip()
        if not normalized:
            return
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO clipboard_labels (name) VALUES (?)",
                (normalized,),
            )

    def delete_label(self, label: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM clipboard_labels WHERE name = ?", (label,))
            connection.execute("UPDATE clipboard_entries SET label = '' WHERE label = ?", (label,))

    def list_categories(self) -> list[str]:
        with self._connect() as connection:
            rows = connection.execute("SELECT name FROM clipboard_categories ORDER BY name").fetchall()
        return [row["name"] for row in rows]

    def add_category(self, category: str) -> None:
        normalized = category.strip()
        if not normalized:
            return
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO clipboard_categories (name) VALUES (?)",
                (normalized,),
            )

    def delete_category(self, category: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM clipboard_categories WHERE name = ?", (category,))
            connection.execute("UPDATE clipboard_entries SET category = '' WHERE category = ?", (category,))

    def _remove_asset(self, image_path: str) -> None:
        if not image_path:
            return
        try:
            path = Path(image_path)
            if path.exists():
                path.unlink()
        except Exception:
            pass

    def _cleanup_unused_assets(self, connection: sqlite3.Connection, image_paths: list[str]) -> None:
        for image_path in {path for path in image_paths if path}:
            still_used = connection.execute(
                "SELECT 1 FROM clipboard_entries WHERE image_path = ? LIMIT 1",
                (image_path,),
            ).fetchone()
            if still_used is None:
                self._remove_asset(image_path)
