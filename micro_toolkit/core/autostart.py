from __future__ import annotations

import os
import plistlib
import shlex
import sys
from pathlib import Path

from micro_toolkit.core.clip_monitor import build_clip_monitor_launch_args, build_gui_launch_args


class AutostartManager:
    def __init__(self, app_name: str = "Micro Toolkit"):
        self.app_name = app_name

    def is_enabled(self) -> bool:
        if os.name == "nt":
            return self._is_registry_enabled()
        return self._target_path().exists()

    def set_enabled(self, enabled: bool, *, start_minimized: bool = False) -> Path | None:
        if os.name == "nt":
            self._set_registry_enabled(enabled, self.app_name, self._launch_command(start_minimized=start_minimized))
            self._cleanup_legacy_nt_autostart()
            return None

        target = self._target_path(component="app")
        if enabled:
            target.parent.mkdir(parents=True, exist_ok=True)
            self._write_launcher(target, self._launch_command(start_minimized=start_minimized), self._launch_args(start_minimized=start_minimized), label="com.debeski.microtoolkit")
        elif target.exists():
            target.unlink()
        return target

    def is_clip_monitor_enabled(self) -> bool:
        if os.name == "nt":
            return self._is_registry_enabled(name=f"{self.app_name} Clip Monitor")
        return self._target_path(component="clip_monitor").exists()

    def set_clip_monitor_enabled(self, enabled: bool) -> Path | None:
        if os.name == "nt":
            self._set_registry_enabled(enabled, f"{self.app_name} Clip Monitor", self._clip_monitor_launch_command())
            return None

        target = self._target_path(component="clip_monitor")
        if enabled:
            target.parent.mkdir(parents=True, exist_ok=True)
            self._write_launcher(
                target,
                self._clip_monitor_launch_command(),
                self._clip_monitor_launch_args(),
                label="com.debeski.microtoolkit.clipmonitor",
            )
        elif target.exists():
            target.unlink()
        return target

    def _target_path(self, *, component: str = "app") -> Path:
        home = Path.home()
        if sys.platform.startswith("linux"):
            filename = "micro-toolkit.desktop" if component == "app" else "micro-toolkit-clip-monitor.desktop"
            return home / ".config" / "autostart" / filename
        if sys.platform == "darwin":
            filename = "com.debeski.microtoolkit.plist" if component == "app" else "com.debeski.microtoolkit.clipmonitor.plist"
            return home / "Library" / "LaunchAgents" / filename
        if os.name == "nt":
            # Legacy path for cleanup
            appdata = Path(os.environ.get("APPDATA", home))
            return appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "micro-toolkit.cmd"
        return home / ".micro-toolkit-startup"

    def _is_registry_enabled(self, name: str | None = None) -> bool:
        import winreg

        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_READ,
            ) as key:
                winreg.QueryValueEx(key, name or self.app_name)
                return True
        except OSError:
            return False

    def _set_registry_enabled(self, enabled: bool, name: str, command: str) -> None:
        import winreg

        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        if enabled:
            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_WRITE) as key:
                winreg.SetValueEx(key, name, 0, winreg.REG_SZ, command)
        else:
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_WRITE) as key:
                    winreg.DeleteValue(key, name)
            except OSError:
                pass

    def _cleanup_legacy_nt_autostart(self) -> None:
        if os.name != "nt":
            return
        legacy = self._target_path()
        if legacy.exists():
            try:
                legacy.unlink()
            except OSError:
                pass

    def _write_launcher(self, target: Path, command: str, launch_args: list[str], *, label: str) -> None:
        if sys.platform.startswith("linux"):
            target.write_text(
                "\n".join(
                    [
                        "[Desktop Entry]",
                        "Type=Application",
                        f"Name={self.app_name}",
                        f"Exec={command}",
                        "Terminal=false",
                        "X-GNOME-Autostart-enabled=true",
                    ]
                ),
                encoding="utf-8",
            )
            return
        if sys.platform == "darwin":
            payload = {
                "Label": label,
                "ProgramArguments": launch_args,
                "RunAtLoad": True,
                "LimitLoadToSessionType": ["Aqua"],
                "ProcessType": "Interactive",
                "WorkingDirectory": str(Path.home()),
            }
            with target.open("wb") as handle:
                plistlib.dump(payload, handle)
            return
        # NT handled via Registry now
        target.write_text(command + "\n", encoding="utf-8")

    def _launch_args(self, *, start_minimized: bool) -> list[str]:
        if sys.platform == "darwin":
            mac_bundle_path = self._mac_bundle_path()
            if mac_bundle_path is not None:
                args = ["/usr/bin/open", str(mac_bundle_path), "--args"]
                args.append("gui")
                if start_minimized:
                    args.append("--start-minimized")
                return args
        return build_gui_launch_args(start_minimized=start_minimized)

    def _launch_command(self, *, start_minimized: bool) -> str:
        return " ".join(shlex.quote(part) for part in self._launch_args(start_minimized=start_minimized))

    def _clip_monitor_launch_args(self) -> list[str]:
        if sys.platform == "darwin":
            mac_bundle_path = self._mac_bundle_path()
            if mac_bundle_path is not None:
                return ["/usr/bin/open", str(mac_bundle_path), "--args", "clip-monitor"]
        return build_clip_monitor_launch_args()

    def _clip_monitor_launch_command(self) -> str:
        return " ".join(shlex.quote(part) for part in self._clip_monitor_launch_args())

    def _mac_bundle_path(self) -> Path | None:
        if sys.platform != "darwin" or not getattr(sys, "frozen", False):
            return None
        executable_path = Path(sys.executable).resolve()
        for parent in executable_path.parents:
            if parent.suffix == ".app":
                return parent
        return None
