from __future__ import annotations

import abc
from dataclasses import dataclass

from PySide6.QtWidgets import QWidget


@dataclass(frozen=True)
class PluginMetadata:
    plugin_id: str
    name: str
    description: str
    category: str
    version: str = "0.1.0"
    standalone: bool = False
    allow_name_override: bool = False
    allow_icon_override: bool = False
    preferred_icon: str = ""


class QtPlugin(abc.ABC):
    plugin_id = ""
    name = "Unnamed Tool"
    description = ""
    category = "General"
    version = "0.1.0"
    standalone = False
    allow_name_override = True
    allow_icon_override = True
    preferred_icon = ""
    translations: dict[str, dict[str, str]] = {}

    @classmethod
    def metadata(cls) -> PluginMetadata:
        return PluginMetadata(
            plugin_id=cls.plugin_id,
            name=cls.name,
            description=cls.description,
            category=cls.category,
            version=cls.version,
            standalone=cls.standalone,
            allow_name_override=cls.allow_name_override,
            allow_icon_override=cls.allow_icon_override,
            preferred_icon=getattr(cls, "preferred_icon", getattr(cls, "preferred_qt_icon", "")),
        )

    def register_commands(self, registry, services) -> None:
        return None

    def register_elevated_capabilities(self, registry, runtime) -> None:
        return None

    @abc.abstractmethod
    def create_widget(self, services) -> QWidget:
        raise NotImplementedError
