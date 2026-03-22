from __future__ import annotations

import json
from pathlib import Path


class PluginStateManager:
    def __init__(self, state_path: Path):
        self.state_path = Path(state_path)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self._state = self._load()

    def _load(self) -> dict[str, dict]:
        if not self.state_path.exists():
            return {}
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _save(self) -> None:
        self.state_path.write_text(json.dumps(self._state, indent=2), encoding="utf-8")

    def get(self, plugin_id: str) -> dict:
        state = self._state.get(plugin_id, {})
        return {
            "enabled": bool(state.get("enabled", True)),
            "hidden": bool(state.get("hidden", False)),
            "trusted": bool(state.get("trusted", False)),
            "quarantined": bool(state.get("quarantined", False)),
            "risk_level": str(state.get("risk_level", "unknown")),
            "risk_summary": str(state.get("risk_summary", "")),
            "last_error": str(state.get("last_error", "")),
            "failure_count": int(state.get("failure_count", 0)),
        }

    def has(self, plugin_id: str) -> bool:
        return plugin_id in self._state

    def set_enabled(self, plugin_id: str, enabled: bool) -> None:
        current = self.get(plugin_id)
        current["enabled"] = bool(enabled)
        self._state[plugin_id] = current
        self._save()

    def set_hidden(self, plugin_id: str, hidden: bool) -> None:
        current = self.get(plugin_id)
        current["hidden"] = bool(hidden)
        self._state[plugin_id] = current
        self._save()

    def set_trusted(self, plugin_id: str, trusted: bool) -> None:
        current = self.get(plugin_id)
        current["trusted"] = bool(trusted)
        if trusted:
            current["quarantined"] = False
        self._state[plugin_id] = current
        self._save()

    def set_scan_report(self, plugin_id: str, report: dict[str, object]) -> None:
        current = self.get(plugin_id)
        current["risk_level"] = str(report.get("risk_level", "unknown"))
        current["risk_summary"] = str(report.get("summary", ""))
        self._state[plugin_id] = current
        self._save()

    def quarantine(self, plugin_id: str, reason: str) -> None:
        current = self.get(plugin_id)
        current["enabled"] = False
        current["trusted"] = False
        current["quarantined"] = True
        current["last_error"] = str(reason)
        self._state[plugin_id] = current
        self._save()

    def record_failure(self, plugin_id: str, reason: str, *, quarantine_after: int = 3) -> dict:
        current = self.get(plugin_id)
        current["failure_count"] = int(current.get("failure_count", 0)) + 1
        current["last_error"] = str(reason)
        if current["failure_count"] >= max(1, quarantine_after):
            current["enabled"] = False
            current["trusted"] = False
            current["quarantined"] = True
        self._state[plugin_id] = current
        self._save()
        return current

    def clear_failures(self, plugin_id: str) -> None:
        current = self.get(plugin_id)
        current["failure_count"] = 0
        current["last_error"] = ""
        self._state[plugin_id] = current
        self._save()

    def reset(self, plugin_id: str) -> None:
        if plugin_id in self._state:
            del self._state[plugin_id]
            self._save()
