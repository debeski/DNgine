from __future__ import annotations

import platform
from importlib import metadata

import psutil

from dngine import APP_NAME, __version__
from dngine.sdk import DeclarativePlugin, InfoCard, Row, Table, bind_tr


class AboutInfoPlugin(DeclarativePlugin):
    plugin_id = "about_info"
    name = "About Info"
    description = "Project information, support links, runtime versions, and system details."
    category = ""
    standalone = True
    preferred_icon = "info"

    def declare_page(self, services):
        tr = bind_tr(services, self.plugin_id)
        return {
            "overview_top": Row(
                fields={
                    "identity_card": InfoCard(
                        title=tr("identity.heading", "Identity"),
                        rows=(
                            (tr("identity.name", "Project"), tr("identity.name_value", "DeBeski (micro)")),
                            (
                                tr("identity.org", "Organization"),
                                tr("identity.org_value", "Libyan Economic Information and Documentation Center"),
                            ),
                            (tr("identity.year", "Year"), tr("identity.year_value", "2026")),
                        ),
                    ),
                    "license_card": InfoCard(
                        title=tr("license.heading", "License"),
                        rows=((tr("license.label", "Type"), tr("license.body", "NON-COMMERCIAL LICENSE")),),
                    ),
                    "system_card": InfoCard(
                        title=tr("system.heading", "System"),
                        rows=self._system_rows(tr),
                    ),
                },
            ),
            "overview_bottom": Row(
                fields={
                    "project_card": InfoCard(
                        title=tr("project.heading", "Project"),
                        rows=(
                            (
                                tr("project.scope", "Scope"),
                                tr(
                                    "project.body",
                                    "The app shell, plugin discovery, translations, workflows, elevated broker, hotkey helper, and runtime services are all part of the same underlying desktop codebase rather than stitched-on external layers.",
                                ),
                            ),
                        ),
                    ),
                    "support_card": InfoCard(
                        title=tr("support.heading", "Support"),
                        rows=(
                            (
                                tr("support.repo", "Repository"),
                                tr("support.repo_value", "github.com/debeski/micro-Toolkit"),
                            ),
                            (
                                tr("support.issues", "Report issues"),
                                tr("support.issues_value", "github.com/debeski/micro-Toolkit/issues"),
                            ),
                        ),
                    ),
                },
            ),
            "libraries": Table(
                title=tr("libs.heading", "Used Tools and Libraries"),
                headers=(
                    tr("libs.name", "Component"),
                    tr("libs.version", "Version"),
                ),
                rows=self._library_rows(),
                stretch=1,
            ),
        }

    def _library_rows(self) -> list[tuple[str, str]]:
        return [
            (APP_NAME, __version__),
            ("Python", platform.python_version()),
            ("PySide6", self._version("PySide6")),
            ("numpy", self._version("numpy")),
            ("pandas", self._version("pandas")),
            ("openpyxl", self._version("openpyxl")),
            ("python-docx", self._version("python-docx")),
            ("PyPDF2", self._version("PyPDF2")),
            ("Pillow", self._version("Pillow")),
            ("pillow-heif", self._version("pillow-heif")),
            ("cryptography", self._version("cryptography")),
            ("python-dateutil", self._version("python-dateutil")),
            ("psutil", self._version("psutil")),
            ("keyboard", self._version("keyboard")),
            ("Bundled SVG icons", "Bootstrap Icons"),
        ]

    def _system_rows(self, tr) -> tuple[tuple[str, str], ...]:
        cpu = platform.processor() or tr("system.unknown_cpu", "Unknown CPU")
        memory_gb = psutil.virtual_memory().total / (1024 ** 3)
        return (
            (tr("system.platform", "Platform"), platform.platform()),
            (tr("system.cpu", "CPU"), cpu),
            (
                tr("system.memory", "Memory"),
                tr("system.memory_value", "{memory:.1f} GB", memory=memory_gb),
            ),
        )

    @staticmethod
    def _version(package_name: str) -> str:
        try:
            return metadata.version(package_name)
        except metadata.PackageNotFoundError:
            return "Not installed"
