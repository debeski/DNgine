from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path


class SessionManager:
    """Tracks tool execution history in the application database."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tool_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    details TEXT
                )
                """
            )

    def log_run(self, tool_id: str, status: str, details: str = "") -> None:
        try:
            with self._connect() as connection:
                connection.execute(
                    "INSERT INTO sessions (tool_id, status, timestamp, details) VALUES (?, ?, ?, ?)",
                    (tool_id, status, time.time(), details),
                )
        except Exception as exc:
            print(f"Database logging failed: {exc}")

    def get_history(self, limit: int = 50):
        try:
            with self._connect() as connection:
                cursor = connection.execute(
                    "SELECT id, tool_id, status, timestamp, details FROM sessions ORDER BY timestamp DESC LIMIT ?",
                    (limit,),
                )
                return cursor.fetchall()
        except Exception:
            return []

    def get_summary(self, *, days: int = 7, top_limit: int = 6) -> dict[str, object]:
        window_start = time.time() - max(1, days) * 86400
        try:
            with self._connect() as connection:
                total_runs = connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
                unique_tools = connection.execute("SELECT COUNT(DISTINCT tool_id) FROM sessions").fetchone()[0]
                status_rows = connection.execute(
                    "SELECT status, COUNT(*) FROM sessions GROUP BY status ORDER BY COUNT(*) DESC"
                ).fetchall()
                top_tool_rows = connection.execute(
                    """
                    SELECT tool_id, COUNT(*) AS run_count
                    FROM sessions
                    GROUP BY tool_id
                    ORDER BY run_count DESC, tool_id ASC
                    LIMIT ?
                    """,
                    (max(1, top_limit),),
                ).fetchall()
                daily_rows = connection.execute(
                    """
                    SELECT date(timestamp, 'unixepoch', 'localtime') AS run_day, COUNT(*) AS run_count
                    FROM sessions
                    WHERE timestamp >= ?
                    GROUP BY run_day
                    ORDER BY run_day ASC
                    """,
                    (window_start,),
                ).fetchall()
        except Exception:
            return {
                "total_runs": 0,
                "unique_tools": 0,
                "status_counts": {},
                "top_tools": [],
                "daily_runs": [],
            }

        daily_lookup = {str(day): int(count) for day, count in daily_rows}
        daily_runs = []
        start_day = datetime.now().date() - timedelta(days=max(1, days) - 1)
        for offset in range(max(1, days)):
            current_day = start_day + timedelta(days=offset)
            key = current_day.isoformat()
            daily_runs.append({"day": key, "count": daily_lookup.get(key, 0)})

        return {
            "total_runs": int(total_runs),
            "unique_tools": int(unique_tools),
            "status_counts": {str(status): int(count) for status, count in status_rows},
            "top_tools": [
                {"tool_id": str(tool_id), "count": int(run_count)}
                for tool_id, run_count in top_tool_rows
            ],
            "daily_runs": daily_runs,
        }
