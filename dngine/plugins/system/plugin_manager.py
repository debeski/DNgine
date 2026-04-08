from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from dngine.core.confirm_dialog import confirm_action
from dngine.core.icon_registry import icon_choices, icon_from_name
from dngine.core.page_style import apply_page_chrome, apply_semantic_class, muted_text_style, section_title_style
from dngine.core.plugin_api import bind_tr
from dngine.core.widgets import adaptive_grid_columns, visible_parent_width, width_breakpoint
from dngine.sdk import AdvancedPagePlugin, MenuActionSpec, show_context_menu


class IconPickerDialog(QDialog):
    def __init__(self, parent: QWidget, options: list[tuple[str, str, object]], current_value: str = ""):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setModal(True)
        self._selected_icon = str(current_value or "").strip()
        self._options = options
        self._build_ui()
        self._populate()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        self.grid = QListWidget()
        self.grid.setViewMode(QListWidget.ViewMode.IconMode)
        self.grid.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.grid.setMovement(QListWidget.Movement.Static)
        self.grid.setWrapping(True)
        self.grid.setUniformItemSizes(True)
        self.grid.setSpacing(8)
        self.grid.setIconSize(QSize(22, 22))
        self.grid.setGridSize(QSize(86, 62))
        self.grid.setWordWrap(True)
        self.grid.itemClicked.connect(self._choose_item)
        self.grid.itemDoubleClicked.connect(self._choose_item)
        layout.addWidget(self.grid)

        actions = QHBoxLayout()
        actions.setSpacing(6)
        clear_button = QPushButton("Default")
        clear_button.clicked.connect(self._clear_selection)
        actions.addWidget(clear_button)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.reject)
        actions.addWidget(close_button)
        layout.addLayout(actions)
        self.resize(420, 320)

    def _populate(self) -> None:
        default_item = QListWidgetItem("Default")
        default_item.setData(Qt.ItemDataRole.UserRole, "")
        self.grid.addItem(default_item)
        if not self._selected_icon:
            self.grid.setCurrentItem(default_item)

        for icon_id, label, icon in self._options:
            item = QListWidgetItem(icon, label)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item.setData(Qt.ItemDataRole.UserRole, icon_id)
            self.grid.addItem(item)
            if icon_id == self._selected_icon:
                self.grid.setCurrentItem(item)

    def _choose_item(self, item: QListWidgetItem) -> None:
        self._selected_icon = str(item.data(Qt.ItemDataRole.UserRole) or "").strip()
        self.accept()

    def _clear_selection(self) -> None:
        self._selected_icon = ""
        self.accept()

    def selected_icon(self) -> str:
        return self._selected_icon


class PluginManagerPlugin(AdvancedPagePlugin):
    plugin_id = "plugin_manager"
    name = "Plugin Manager"
    description = "Install, inspect, trust, enable, hide, import, and export plugins and signed packages."
    category = ""
    standalone = True
    preferred_icon = "plugin"
    translations = {
        "en": {
            "plugin.name": "Plugin Manager",
            "plugin.description": "Install, inspect, trust, enable, hide, import, and export plugins and signed packages.",
        },
        "ar": {
            "plugin.name": "مدير الإضافات",
            "plugin.description": "ثبّت الإضافات والحزم الموقعة وافحصها ووثّقها وفعّلها وأخفها واستوردها وصدّرها.",
        },
    }

    def build_advanced_widget(self, services) -> QWidget:
        return PluginManagerPage(services)


class PluginManagerPage(QWidget):
    plugin_id = "plugin_manager"

    def __init__(self, services):
        super().__init__()
        self.setObjectName("PluginManagerPage")
        self.services = services
        self.i18n = services.i18n
        self._page_tr = bind_tr(services, self.plugin_id)
        self.tr = bind_tr(services, "command_center")
        self.plugin_row_map: dict[str, int] = {}
        self._building_plugin_table = False
        self._plugins_table_width_sync_pending = False
        self._responsive_bucket = ""
        self._responsive_refresh_pending = False
        self._build_ui()
        self._populate_values()
        self._apply_texts()
        self.i18n.language_changed.connect(self._apply_texts)
        self.services.theme_manager.theme_changed.connect(self._handle_theme_change)
        self.services.plugin_visuals_changed.connect(lambda _plugin_id: self._populate_plugin_table())

    @staticmethod
    def _configure_note_label(label: QLabel) -> None:
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)

    def _confirm_risky(self, title: str, body: str) -> bool:
        return confirm_action(
            self,
            title=title,
            body=body,
            confirm_text=self.tr("confirm.continue", "Continue"),
            cancel_text=self.tr("confirm.cancel", "Cancel"),
        )

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 28, 28, 28)
        outer.setSpacing(16)

        self.title_label = QLabel()
        outer.addWidget(self.title_label)

        self.description_label = QLabel()
        self._configure_note_label(self.description_label)
        outer.addWidget(self.description_label)

        self.packages_card = QFrame()
        packages_layout = QVBoxLayout(self.packages_card)
        packages_layout.setContentsMargins(18, 16, 18, 16)
        packages_layout.setSpacing(12)

        self.packages_note = QLabel()
        self._configure_note_label(self.packages_note)
        packages_layout.addWidget(self.packages_note)

        self.packages_table = QTableWidget(0, 6)
        self.packages_table.setAlternatingRowColors(True)
        self.packages_table.verticalHeader().setVisible(False)
        self.packages_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.packages_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.packages_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.packages_table.customContextMenuRequested.connect(self._show_packages_context_menu)
        self.packages_table.itemSelectionChanged.connect(self._sync_package_action_buttons)
        self.packages_table.horizontalHeader().setStretchLastSection(True)
        self.packages_table.setColumnWidth(0, 220)
        self.packages_table.setColumnWidth(1, 170)
        self.packages_table.setColumnWidth(2, 120)
        self.packages_table.setColumnWidth(3, 110)
        self.packages_table.setColumnWidth(4, 210)
        packages_layout.addWidget(self.packages_table)

        self.packages_actions_layout = QGridLayout()
        self.packages_actions_layout.setHorizontalSpacing(8)
        self.packages_actions_layout.setVerticalSpacing(8)
        self.refresh_package_catalog_button = self._make_action_button("sync", self._refresh_package_catalog)
        self.install_package_button = self._make_action_button("download", self._install_selected_package)
        self.remove_package_button = self._make_action_button("delete", self._remove_selected_package)
        self.import_signed_package_button = self._make_action_button("open", self._import_signed_package)
        self._package_action_buttons = [
            self.refresh_package_catalog_button,
            self.install_package_button,
            self.remove_package_button,
            self.import_signed_package_button,
        ]
        packages_layout.addLayout(self.packages_actions_layout)
        outer.addWidget(self.packages_card)

        self.plugins_card = QFrame()
        plugins_layout = QVBoxLayout(self.plugins_card)
        plugins_layout.setContentsMargins(18, 16, 18, 16)
        plugins_layout.setSpacing(12)

        self.plugins_note = QLabel()
        self._configure_note_label(self.plugins_note)
        plugins_layout.addWidget(self.plugins_note)

        self.plugins_table = QTableWidget(0, 11)
        self.plugins_table.setAlternatingRowColors(True)
        self.plugins_table.verticalHeader().setVisible(False)
        self.plugins_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.plugins_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.plugins_table.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustToContents)
        self.plugins_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.plugins_table.customContextMenuRequested.connect(self._show_plugins_context_menu)
        self.plugins_table.itemChanged.connect(self._handle_plugin_item_changed)
        header = self.plugins_table.horizontalHeader()
        header.setSectionsMovable(False)
        header.setStretchLastSection(False)
        header.setMinimumSectionSize(44)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(10, QHeaderView.ResizeMode.Stretch)
        header.sectionResized.connect(self._schedule_plugins_table_width_sync)
        self.plugins_table.setColumnWidth(0, 88)
        self.plugins_table.setColumnWidth(1, 88)
        self.plugins_table.setColumnWidth(2, 220)
        self.plugins_table.setColumnWidth(3, 140)
        self.plugins_table.setColumnWidth(4, 92)
        self.plugins_table.setColumnWidth(5, 86)
        self.plugins_table.setColumnWidth(6, 82)
        self.plugins_table.setColumnWidth(7, 82)
        self.plugins_table.setColumnWidth(8, 86)
        self.plugins_table.setColumnWidth(9, 140)
        plugins_layout.addWidget(self.plugins_table, 1)

        self.plugins_actions_layout = QGridLayout()
        self.plugins_actions_layout.setHorizontalSpacing(8)
        self.plugins_actions_layout.setVerticalSpacing(8)
        self.import_package_button = self._make_action_button("download", self._import_plugin_package)
        self.import_file_button = self._make_action_button("open", self._import_plugin_file)
        self.import_folder_button = self._make_action_button("folder-open", self._import_plugin_folder)
        self.export_selected_button = self._make_action_button("save", self._export_selected_plugins)
        self.export_all_button = self._make_action_button("database", self._export_all_plugins)
        self.reset_plugins_button = self._make_action_button("repeat", self._reset_plugin_defaults)
        self.refresh_plugins_button = self._make_action_button("sync", self._populate_plugin_table)
        self._plugin_action_buttons = [
            self.import_package_button,
            self.import_file_button,
            self.import_folder_button,
            self.export_selected_button,
            self.export_all_button,
            self.reset_plugins_button,
            self.refresh_plugins_button,
        ]
        self._developer_plugin_action_buttons = [
            self.import_file_button,
            self.import_folder_button,
        ]
        plugins_layout.addLayout(self.plugins_actions_layout)
        outer.addWidget(self.plugins_card, 1)

    def _make_action_button(self, icon_name: str, handler) -> QToolButton:
        button = QToolButton()
        apply_semantic_class(button, "button_class")
        button.setAutoRaise(False)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        button.setIcon(icon_from_name(icon_name, self) or self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon))
        button.setIconSize(QSize(16, 16))
        button.setMinimumHeight(36)
        button.clicked.connect(handler)
        return button

    def _populate_values(self) -> None:
        self._populate_packages_table()
        self._populate_plugin_table()
        self._sync_developer_plugin_actions()
        self._apply_responsive_layout(force=True)

    def _populate_packages_table(self) -> None:
        entries = self.services.plugin_package_manager.list_catalog_packages()
        self._package_rows = {}
        self.packages_table.setRowCount(len(entries))
        self.packages_table.setHorizontalHeaderLabels(
            [
                self.tr("packages.name", "Package"),
                self.tr("packages.category", "Category"),
                self.tr("packages.version", "Version"),
                self.tr("packages.status", "Status"),
                self.tr("packages.plugins", "Plugins"),
                self.tr("packages.signer", "Signer"),
            ]
        )
        for row_index, entry in enumerate(entries):
            package_id = str(entry.get("package_id", "")).strip()
            self._package_rows[package_id] = dict(entry)

            name_item = QTableWidgetItem(str(entry.get("display_name") or package_id))
            name_item.setData(Qt.ItemDataRole.UserRole, package_id)
            name_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            self.packages_table.setItem(row_index, 0, name_item)

            category_item = QTableWidgetItem(str(entry.get("category_label", "")))
            category_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            self.packages_table.setItem(row_index, 1, category_item)

            version_text = str(entry.get("installed_version") or entry.get("package_version") or "")
            version_item = QTableWidgetItem(version_text)
            version_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            self.packages_table.setItem(row_index, 2, version_item)

            status_item = QTableWidgetItem(self._package_status_text(entry))
            status_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            self.packages_table.setItem(row_index, 3, status_item)

            plugins_text = ", ".join(str(item) for item in entry.get("group_plugin_ids", entry.get("plugin_ids", [])))
            plugins_item = QTableWidgetItem(plugins_text)
            plugins_item.setToolTip(plugins_text)
            plugins_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            self.packages_table.setItem(row_index, 4, plugins_item)

            signer_item = QTableWidgetItem(str(entry.get("signer", "")))
            signer_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            self.packages_table.setItem(row_index, 5, signer_item)
        self.packages_table.resizeColumnToContents(0)
        self.packages_table.resizeColumnToContents(2)
        self.packages_table.resizeColumnToContents(3)
        self.packages_table.resizeColumnToContents(5)
        self._sync_package_action_buttons()

    def _package_status_text(self, entry: dict[str, object]) -> str:
        if bool(entry.get("installed")) and bool(entry.get("update_available")):
            return self.tr("packages.status.update", "Installed · Update Available")
        if bool(entry.get("installed")):
            return self.tr("packages.status.installed", "Installed")
        return self.tr("packages.status.available", "Available")

    def _selected_package_entry(self) -> dict[str, object] | None:
        items = self.packages_table.selectedItems()
        if not items:
            return None
        row = items[0].row()
        name_item = self.packages_table.item(row, 0)
        if name_item is None:
            return None
        package_id = str(name_item.data(Qt.ItemDataRole.UserRole) or "").strip()
        if not package_id:
            return None
        return dict(self._package_rows.get(package_id, {}))

    def _sync_package_action_buttons(self) -> None:
        entry = self._selected_package_entry()
        has_selection = entry is not None
        is_installed = bool(entry and entry.get("installed"))
        self.install_package_button.setEnabled(has_selection)
        self.remove_package_button.setEnabled(has_selection and is_installed)

    def _show_packages_context_menu(self, position) -> None:
        index = self.packages_table.indexAt(position)
        if not index.isValid():
            return
        self.packages_table.selectRow(index.row())
        entry = self._selected_package_entry()
        if entry is None:
            return
        items = [
            MenuActionSpec(
                label=self.tr("packages.refresh", "Refresh Catalog"),
                callback=self._refresh_package_catalog,
            ),
            MenuActionSpec(
                label=self.tr(
                    "packages.install_update" if bool(entry.get("installed")) else "packages.install",
                    "Update Package" if bool(entry.get("installed")) else "Install Package",
                ),
                callback=self._install_selected_package,
            ),
        ]
        if bool(entry.get("installed")):
            items.append(
                MenuActionSpec(
                    label=self.tr("packages.remove", "Remove Package"),
                    callback=self._remove_selected_package,
                )
            )
        items.append(
            MenuActionSpec(
                label=self.tr("packages.import_local", "Import Signed Package..."),
                callback=self._import_signed_package,
            )
        )
        show_context_menu(self, self.packages_table.viewport().mapToGlobal(position), items)

    def _refresh_package_catalog(self) -> None:
        window = self.services.main_window
        if window is not None:
            window.begin_loading(self.tr("loading.packages_refresh", "Refreshing package catalog..."))

        def _on_result(payload: object) -> None:
            result = dict(payload) if isinstance(payload, dict) else {}
            self._populate_packages_table()
            QMessageBox.information(
                self,
                self.tr("packages.refreshed.title", "Catalog refreshed"),
                self.tr(
                    "packages.refreshed.body",
                    "Loaded {count} first-party packages from the catalog.",
                    count=str(result.get("count", 0)),
                ),
            )

        def _on_error(payload: object) -> None:
            message = payload.get("message", self.tr("packages.failed.body", "The package operation failed.")) if isinstance(payload, dict) else str(payload)
            QMessageBox.critical(self, self.tr("packages.failed.title", "Package operation failed"), message)

        def _on_finished() -> None:
            if window is not None:
                window.end_loading()
            self._populate_packages_table()

        self.services.run_task(
            lambda _context: self.services.plugin_package_manager.refresh_catalog(),
            on_result=_on_result,
            on_error=_on_error,
            on_finished=_on_finished,
            status_text=self.tr("loading.packages_refresh", "Refreshing package catalog..."),
        )

    def _install_selected_package(self) -> None:
        entry = self._selected_package_entry()
        if entry is None:
            QMessageBox.information(
                self,
                self.tr("packages.selection.title", "Select a package"),
                self.tr("packages.selection.body", "Select one package from the table first."),
            )
            return
        package_id = str(entry.get("package_id", "")).strip()
        package_name = str(entry.get("display_name", package_id))
        window = self.services.main_window
        if window is not None:
            window.begin_loading(self.tr("loading.packages_install", "Installing package..."))

        def _on_result(payload: object) -> None:
            result = dict(payload) if isinstance(payload, dict) else {}
            installed_name = str(result.get("display_name", package_name))
            self.services.log(
                self.tr(
                    "loading.packages_reload",
                    "Installing {package}: reloading plugins...",
                    package=installed_name,
                )
            )
            self.services.reload_plugins()
            self._populate_packages_table()
            self._populate_plugin_table()
            dependency_errors = [
                str(item.get("plugin_name") or item.get("plugin_id") or "").strip()
                for item in result.get("dependency_errors", [])
                if isinstance(item, dict)
            ]
            dependency_errors = [name for name in dependency_errors if name]
            if dependency_errors:
                QMessageBox.warning(
                    self,
                    self.tr("packages.installed.partial_title", "Package installed with warnings"),
                    self.tr(
                        "packages.installed.partial_body",
                        "Installed {package} with {count} plugin(s), but dependency setup still needs attention for: {failures}.",
                        package=installed_name,
                        count=str(len(result.get("plugin_ids", []))),
                        failures=", ".join(dependency_errors),
                    ),
                )
                self.services.logger.set_status(
                    self.tr(
                        "packages.installed.partial_status",
                        "{package} installed with dependency warnings.",
                        package=installed_name,
                    )
                )
                return
            QMessageBox.information(
                self,
                self.tr("packages.installed.title", "Package installed"),
                self.tr(
                    "packages.installed.body",
                    "Installed {package} with {count} plugin(s).",
                    package=installed_name,
                    count=str(len(result.get("plugin_ids", []))),
                ),
            )
            self.services.logger.set_status(
                self.tr(
                    "packages.installed.status",
                    "{package} installed.",
                    package=installed_name,
                )
            )

        def _on_error(payload: object) -> None:
            message = payload.get("message", self.tr("packages.failed.body", "The package operation failed.")) if isinstance(payload, dict) else str(payload)
            QMessageBox.critical(self, self.tr("packages.failed.title", "Package operation failed"), message)

        def _on_finished() -> None:
            if window is not None:
                window.end_loading()
            self._populate_packages_table()
            self._populate_plugin_table()

        self.services.run_task(
            lambda context: self.services._install_catalog_package(package_id, context=context),
            on_result=_on_result,
            on_error=_on_error,
            on_finished=_on_finished,
            status_text=self.tr("loading.packages_install", "Installing package..."),
        )

    def _remove_selected_package(self) -> None:
        entry = self._selected_package_entry()
        if entry is None:
            QMessageBox.information(
                self,
                self.tr("packages.selection.title", "Select a package"),
                self.tr("packages.selection.body", "Select one package from the table first."),
            )
            return
        if not bool(entry.get("installed")):
            return
        package_id = str(entry.get("package_id", "")).strip()
        package_name = str(entry.get("display_name", package_id))
        confirmed = confirm_action(
            self,
            title=self.tr("packages.remove_confirm.title", "Remove package?"),
            body=self.tr(
                "packages.remove_confirm.body",
                "Remove the installed signed package {package} and its managed dependency runtimes?",
                package=package_name,
            ),
            confirm_text=self.tr("packages.remove", "Remove Package"),
            cancel_text=self.tr("confirm.cancel", "Cancel"),
        )
        if not confirmed:
            return
        try:
            result = self.services._remove_signed_package(package_id)
        except Exception as exc:
            QMessageBox.critical(self, self.tr("packages.failed.title", "Package operation failed"), str(exc))
            return
        self.services.reload_plugins()
        self._populate_packages_table()
        self._populate_plugin_table()
        QMessageBox.information(
            self,
            self.tr("packages.removed.title", "Package removed"),
            self.tr(
                "packages.removed.body",
                "Removed {package} and {count} plugin(s).",
                package=package_name,
                count=str(len(result.get("plugin_ids", []))),
            ),
        )

    def _import_signed_package(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("packages.import_local", "Import Signed Package..."),
            str(Path.home()),
            self.tr("plugins.import_package.filter", "Plugin Package (*.zip)"),
        )
        if not file_path:
            return
        try:
            plugin_ids = self.services.plugin_package_manager.import_plugin_package(Path(file_path))
        except Exception as exc:
            QMessageBox.critical(self, self.tr("packages.failed.title", "Package operation failed"), str(exc))
            return
        self.services.reload_plugins()
        self._populate_packages_table()
        self._populate_plugin_table()
        self._show_plugin_import_result(plugin_ids)

    def _row_action_widget(self, spec, *, selected: bool) -> QWidget:
        container = QWidget()
        container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        apply_semantic_class(container, "transparent_class")
        layout = QHBoxLayout(container)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(2)

        export_check = QCheckBox()
        apply_semantic_class(export_check, "transparent_class")
        export_check.setChecked(selected)
        export_check.setToolTip(self.tr("plugins.export", "Select for export"))
        export_check.setEnabled(spec.source_type == "custom")
        layout.addWidget(export_check)
        return container

    def _sanitized_plugin_icon_override(self, spec) -> str:
        override = str(self.services.plugin_icon_override(spec) or "").strip()
        if not override:
            return ""
        if Path(override).exists():
            return override
        return override if icon_from_name(override, self) is not None else ""

    def _populate_plugin_table(self) -> None:
        self._building_plugin_table = True
        try:
            specs = self.services.manageable_plugin_specs(include_disabled=True)
            self.plugin_row_map = {}
            self.plugins_table.setRowCount(len(specs))
            self.plugins_table.setHorizontalHeaderLabels(
                [
                    "",
                    self.tr("plugins.icon", "Icon"),
                    self.tr("plugins.name", "Plugin"),
                    self.tr("plugins.category", "Category"),
                    self.tr("plugins.source", "Source"),
                    self.tr("plugins.trusted", "Trusted"),
                    self.tr("plugins.enabled", "Enabled"),
                    self.tr("plugins.hidden", "Hidden"),
                    self.tr("plugins.risk", "Risk"),
                    self.tr("plugins.status", "Status"),
                    self.tr("plugins.file", "File"),
                ]
            )
            language = self.services.i18n.current_language()
            for row_index, spec in enumerate(specs):
                self.plugin_row_map[spec.plugin_id] = row_index
                self.plugins_table.setCellWidget(row_index, 0, self._row_action_widget(spec, selected=False))
                self.plugins_table.removeCellWidget(row_index, 1)

                icon_item = QTableWidgetItem(self._icon_display_text(spec))
                icon_item.setIcon(self._icon_display_icon(spec) or self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon))
                icon_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                self.plugins_table.setItem(row_index, 1, icon_item)

                name_item = QTableWidgetItem(self.services.plugin_display_name(spec))
                name_item.setData(Qt.ItemDataRole.UserRole, spec.plugin_id)
                name_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                self.plugins_table.setItem(row_index, 2, name_item)

                category_item = QTableWidgetItem(spec.localized_category(language) or self.tr("plugins.standalone", "Standalone"))
                category_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                self.plugins_table.setItem(row_index, 3, category_item)

                source_item = QTableWidgetItem(self.tr(f"plugins.source.{spec.source_type.lower()}", spec.source_type.title()))
                source_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                self.plugins_table.setItem(row_index, 4, source_item)

                trusted_item = QTableWidgetItem()
                trusted_flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable
                trusted_item.setFlags(trusted_flags if spec.source_type == "custom" else Qt.ItemFlag.ItemIsEnabled)
                trusted_item.setCheckState(Qt.CheckState.Checked if spec.trusted else Qt.CheckState.Unchecked)
                self.plugins_table.setItem(row_index, 5, trusted_item)

                enabled_item = QTableWidgetItem()
                enabled_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
                enabled_item.setCheckState(Qt.CheckState.Checked if spec.enabled else Qt.CheckState.Unchecked)
                self.plugins_table.setItem(row_index, 6, enabled_item)

                hidden_item = QTableWidgetItem()
                hidden_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
                hidden_item.setCheckState(Qt.CheckState.Checked if spec.hidden else Qt.CheckState.Unchecked)
                self.plugins_table.setItem(row_index, 7, hidden_item)

                risk_item = QTableWidgetItem(self.tr(f"plugins.risk.{spec.risk_level.lower()}", spec.risk_level.title()))
                risk_item.setToolTip(self._plugin_review_details(spec))
                risk_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                self._style_risk_item(risk_item, spec.risk_level)
                self.plugins_table.setItem(row_index, 8, risk_item)

                status_item = QTableWidgetItem(self._plugin_status_text(spec))
                status_item.setToolTip(self._plugin_review_details(spec))
                status_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                self._style_risk_item(status_item, spec.risk_level)
                self.plugins_table.setItem(row_index, 9, status_item)

                file_item = QTableWidgetItem(spec.file_path.name)
                file_item.setToolTip(str(spec.file_path))
                file_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                self.plugins_table.setItem(row_index, 10, file_item)
        finally:
            self._building_plugin_table = False
        self.plugins_table.resizeColumnToContents(0)
        self.plugins_table.resizeColumnToContents(1)
        self._schedule_plugins_table_width_sync()

    def _is_row_selected_for_export(self, row: int) -> bool:
        widget = self.plugins_table.cellWidget(row, 0)
        if widget is None:
            return False
        checkbox = widget.findChild(QCheckBox)
        return bool(checkbox is not None and checkbox.isChecked())

    def _icon_display_text(self, spec) -> str:
        override = self._sanitized_plugin_icon_override(spec)
        return self._icon_display_name(override)

    def _icon_display_name(self, icon_value: str) -> str:
        if not icon_value:
            return ""
        options = {icon_id: label for icon_id, label, _icon in self._icon_options()}
        return options.get(icon_value, Path(icon_value).name or icon_value)

    def _icon_display_icon(self, spec):
        override = self._sanitized_plugin_icon_override(spec)
        effective = override or str(spec.preferred_icon or "").strip()
        return icon_from_name(effective, self) if effective else icon_from_name("plugin", self)

    def _plugin_spec_for_row(self, row: int):
        if row < 0:
            return None
        name_item = self.plugins_table.item(row, 2)
        if name_item is None:
            return None
        plugin_id = str(name_item.data(Qt.ItemDataRole.UserRole) or "")
        if not plugin_id:
            return None
        return self.services.plugin_manager.get_spec(plugin_id, include_disabled=True)

    def _toggle_plugin_row_check(self, row: int, column: int) -> None:
        item = self.plugins_table.item(row, column)
        if item is None:
            return
        current = item.checkState() == Qt.CheckState.Checked
        item.setCheckState(Qt.CheckState.Unchecked if current else Qt.CheckState.Checked)

    def _set_plugin_item_check_state(self, item: QTableWidgetItem | None, checked: bool) -> None:
        if item is None:
            return
        previous = self._building_plugin_table
        self._building_plugin_table = True
        try:
            item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        finally:
            self._building_plugin_table = previous

    def _handle_plugin_item_changed(self, item: QTableWidgetItem) -> None:
        if self._building_plugin_table or item.column() not in {5, 6, 7}:
            return

        row = item.row()
        spec = self._plugin_spec_for_row(row)
        if spec is None:
            return

        trusted_item = self.plugins_table.item(row, 5)
        enabled_item = self.plugins_table.item(row, 6)
        hidden_item = self.plugins_table.item(row, 7)
        trusted = trusted_item.checkState() == Qt.CheckState.Checked if trusted_item is not None else spec.trusted
        enabled = enabled_item.checkState() == Qt.CheckState.Checked if enabled_item is not None else spec.enabled
        hidden = hidden_item.checkState() == Qt.CheckState.Checked if hidden_item is not None else spec.hidden

        if spec.source_type in {"builtin", "signed"}:
            trusted = spec.trusted
            self._set_plugin_item_check_state(trusted_item, spec.trusted)

        if spec.source_type == "custom" and spec.risk_level == "critical" and (trusted or enabled):
            self.services.plugin_state_manager.quarantine(
                spec.plugin_id,
                self.tr(
                    "plugins.blocked.reason",
                    "The static safety scan detected critical-risk patterns. This plugin remains quarantined until removed or replaced.",
                ),
            )
            trusted = False
            enabled = False
            self._set_plugin_item_check_state(trusted_item, False)
            self._set_plugin_item_check_state(enabled_item, False)
            QMessageBox.warning(
                self,
                self.tr("plugins.blocked.title", "Plugins blocked"),
                self.tr(
                    "plugins.blocked.body",
                    "These custom plugins remain blocked because the static scan detected critical-risk patterns:\n\n{plugins}",
                    plugins=f"- {self.services.plugin_display_name(spec)}",
                ),
            )
        elif spec.source_type == "custom" and trusted and not spec.trusted and spec.risk_level in {"medium", "high"}:
            confirmed = confirm_action(
                self,
                title=self.tr("plugins.review_prompt.title", "Trust custom plugins?"),
                body=self.tr(
                    "plugins.review_prompt.body",
                    "The following custom plugins contain medium or high risk markers from the static safety scan:\n\n{plugins}\n\nTrusting them will allow the app to import and run their code. Only continue if you trust the author and reviewed the plugin contents.",
                    plugins=f"- {self.services.plugin_display_name(spec)}",
                ),
                confirm_text=self.tr("plugins.review_prompt.confirm", "Trust and apply"),
                cancel_text=self.tr("confirm.cancel", "Cancel"),
            )
            if not confirmed:
                trusted = False
                self._set_plugin_item_check_state(trusted_item, False)

        if spec.source_type == "custom" and not trusted and enabled:
            enabled = False
            self._set_plugin_item_check_state(enabled_item, False)
            QMessageBox.information(
                self,
                self.tr("plugins.trust_required.title", "Trust required"),
                self.tr("plugins.trust_required.body", "Review and trust this custom plugin before enabling it."),
            )

        self.services.plugin_state_manager.set_trusted(spec.plugin_id, trusted)
        self.services.plugin_state_manager.set_enabled(spec.plugin_id, enabled)
        self.services.plugin_state_manager.set_hidden(spec.plugin_id, hidden)
        self.services.refresh_plugin_catalog_views()
        self._populate_plugin_table()

    def _show_plugins_context_menu(self, position) -> None:
        index = self.plugins_table.indexAt(position)
        if not index.isValid():
            return
        row = index.row()
        self.plugins_table.selectRow(row)
        spec = self._plugin_spec_for_row(row)
        if spec is None:
            return

        items: list[MenuActionSpec] = []
        if spec.allow_name_override:
            items.append(
                MenuActionSpec(
                    label=self.tr("plugins.menu.rename", "Change name..."),
                    callback=lambda plugin_id=spec.plugin_id: self._change_plugin_name(plugin_id),
                )
            )
        if spec.allow_icon_override:
            items.append(
                MenuActionSpec(
                    label=self.tr("plugins.menu.icon", "Change icon..."),
                    callback=lambda plugin_id=spec.plugin_id: self._change_plugin_icon(plugin_id),
                )
            )
        items.append(
            MenuActionSpec(
                label=self.tr("plugins.menu.reset_visuals", "Reset name and icon"),
                callback=lambda plugin_id=spec.plugin_id: self._reset_plugin_visuals(plugin_id),
            )
        )

        items.append(MenuActionSpec(separator=True))
        items.append(
            MenuActionSpec(
                label=self.tr("plugins.menu.toggle_enabled", "Toggle enabled"),
                callback=lambda current_row=row: self._toggle_plugin_row_check(current_row, 6),
            )
        )
        items.append(
            MenuActionSpec(
                label=self.tr("plugins.menu.toggle_hidden", "Toggle hidden"),
                callback=lambda current_row=row: self._toggle_plugin_row_check(current_row, 7),
            )
        )
        if spec.source_type == "custom":
            items.append(
                MenuActionSpec(
                    label=self.tr("plugins.menu.toggle_trusted", "Toggle trusted"),
                    callback=lambda current_row=row: self._toggle_plugin_row_check(current_row, 5),
                )
            )

        dependency_summary = self._plugin_dependency_summary(spec)
        if dependency_summary.has_manifest:
            items.append(MenuActionSpec(separator=True))
            items.extend(
                [
                    MenuActionSpec(
                        label=self.tr("plugins.menu.view_deps", "View dependency file"),
                        callback=lambda plugin_id=spec.plugin_id: self._view_plugin_dependency_file(plugin_id),
                    ),
                    MenuActionSpec(
                        label=self.tr("plugins.menu.install_deps", "Install dependencies"),
                        callback=lambda plugin_id=spec.plugin_id: self._install_plugin_dependencies(plugin_id, repair=False),
                    ),
                    MenuActionSpec(
                        label=self.tr("plugins.menu.repair_deps", "Repair dependencies"),
                        callback=lambda plugin_id=spec.plugin_id: self._install_plugin_dependencies(plugin_id, repair=True),
                    ),
                    MenuActionSpec(
                        label=self.tr("plugins.menu.clear_deps", "Clear dependencies"),
                        callback=lambda plugin_id=spec.plugin_id: self._clear_plugin_dependencies(plugin_id),
                    ),
                ]
            )

        details = self._plugin_review_details(spec)
        if details:
            items.append(MenuActionSpec(separator=True))
            items.append(
                MenuActionSpec(
                    label=self.tr("plugins.menu.review", "Review details"),
                    callback=lambda text=details, title=self.services.plugin_display_name(spec): QMessageBox.information(self, title, text),
                )
            )
        show_context_menu(self, self.plugins_table.viewport().mapToGlobal(position), items)

    def _view_plugin_dependency_file(self, plugin_id: str) -> None:
        spec = self.services.plugin_manager.get_spec(plugin_id, include_disabled=True)
        if spec is None:
            return
        summary = self._plugin_dependency_summary(spec)
        if not summary.has_manifest or summary.manifest_path is None:
            QMessageBox.information(
                self,
                self.tr("plugins.deps.none.title", "No dependency file"),
                self.tr("plugins.deps.none.body", "This plugin does not declare a dependency sidecar."),
            )
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(summary.manifest_path)))

    def _install_plugin_dependencies(self, plugin_id: str, *, repair: bool) -> None:
        spec = self.services.plugin_manager.get_spec(plugin_id, include_disabled=True)
        if spec is None:
            return
        if spec.source_type not in {"custom", "signed"}:
            return
        if spec.source_type == "custom" and not spec.trusted:
            QMessageBox.warning(
                self,
                self.tr("plugins.deps.review_required.title", "Trust required"),
                self.tr("plugins.deps.review_required.body", "Review and trust this custom plugin before installing its dependencies."),
            )
            return
        summary = self._plugin_dependency_summary(spec)
        if not summary.has_manifest:
            QMessageBox.information(
                self,
                self.tr("plugins.deps.none.title", "No dependency file"),
                self.tr("plugins.deps.none.body", "This plugin does not declare a dependency sidecar."),
            )
            return
        if repair:
            confirmed = confirm_action(
                self,
                title=self.tr("plugins.deps.repair.title", "Repair dependencies?"),
                body=self.tr(
                    "plugins.deps.repair.body",
                    "This will clear the current dependency runtime for this plugin and reinstall it from the dependency sidecar.",
                ),
                confirm_text=self.tr("plugins.menu.repair_deps", "Repair dependencies"),
                cancel_text=self.tr("confirm.cancel", "Cancel"),
            )
            if not confirmed:
                return
        window = self.services.main_window
        if window is not None:
            window.begin_loading(
                self.tr(
                    "loading.plugin_deps_repair" if repair else "loading.plugin_deps_install",
                    "Repairing plugin dependencies..." if repair else "Installing plugin dependencies...",
                )
            )

        def _on_result(payload: object) -> None:
            result = dict(payload) if isinstance(payload, dict) else {}
            self.services.reload_plugins()
            QMessageBox.information(
                self,
                self.tr("plugins.deps.installed.title", "Dependencies ready"),
                self.tr(
                    "plugins.deps.installed.body",
                    "Dependencies for {plugin} were installed into {path}.",
                    plugin=self.services.plugin_display_name(spec),
                    path=str(result.get("site_packages") or ""),
                ),
            )

        def _on_error(payload: object) -> None:
            message = payload.get("message", self.tr("plugins.deps.failed.body", "Dependency installation failed.")) if isinstance(payload, dict) else str(payload)
            QMessageBox.critical(self, self.tr("plugins.deps.failed.title", "Dependency installation failed"), message)
            self._populate_plugin_table()

        def _on_finished() -> None:
            if window is not None:
                window.end_loading()
            self._populate_plugin_table()

        self.services.run_task(
            lambda context: self.services.plugin_dependency_manager.install_for_spec(spec, context, repair=repair),
            on_result=_on_result,
            on_error=_on_error,
            on_finished=_on_finished,
        )

    def _clear_plugin_dependencies(self, plugin_id: str) -> None:
        spec = self.services.plugin_manager.get_spec(plugin_id, include_disabled=True)
        if spec is None:
            return
        summary = self._plugin_dependency_summary(spec)
        if not summary.has_manifest:
            QMessageBox.information(
                self,
                self.tr("plugins.deps.none.title", "No dependency file"),
                self.tr("plugins.deps.none.body", "This plugin does not declare a dependency sidecar."),
            )
            return
        confirmed = confirm_action(
            self,
            title=self.tr("plugins.deps.clear.title", "Clear plugin dependencies?"),
            body=self.tr(
                "plugins.deps.clear.body",
                "This will remove the installed dependency runtime for this plugin. You can reinstall it later from the same dependency sidecar.",
            ),
            confirm_text=self.tr("plugins.menu.clear_deps", "Clear dependencies"),
            cancel_text=self.tr("confirm.cancel", "Cancel"),
        )
        if not confirmed:
            return
        removed = self.services.plugin_dependency_manager.clear_for_spec(spec)
        self.services.reload_plugins()
        QMessageBox.information(
            self,
            self.tr("plugins.deps.cleared.title", "Dependencies cleared"),
            self.tr("plugins.deps.cleared.body", "Dependency runtime cleared for {plugin}.", plugin=self.services.plugin_display_name(spec))
            if removed
            else self.tr("plugins.deps.cleared.empty", "No installed dependency runtime was found for {plugin}.", plugin=self.services.plugin_display_name(spec)),
        )

    def _change_plugin_name(self, plugin_id: str) -> None:
        spec = self.services.plugin_manager.get_spec(plugin_id, include_disabled=True)
        if spec is None:
            return
        current_override = self.services.plugin_override(plugin_id).get("display_name", "")
        current_text = current_override or self.services.plugin_display_name(spec)
        value, accepted = QInputDialog.getText(
            self,
            self.tr("plugins.rename.title", "Change display name"),
            self.tr("plugins.rename.prompt", "Display name"),
            text=current_text,
        )
        if not accepted:
            return
        override = value.strip()
        if override == spec.localized_name(self.i18n.current_language()):
            override = ""
        current_icon = self._sanitized_plugin_icon_override(spec)
        self.services.set_plugin_override(plugin_id, display_name=override, icon=current_icon)
        self._populate_plugin_table()

    def _change_plugin_icon(self, plugin_id: str) -> None:
        spec = self.services.plugin_manager.get_spec(plugin_id, include_disabled=True)
        if spec is None:
            return
        dialog = IconPickerDialog(self, self._icon_options(), self._sanitized_plugin_icon_override(spec))
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        current_name = self.services.plugin_override(plugin_id).get("display_name", "")
        self.services.set_plugin_override(plugin_id, display_name=current_name, icon=dialog.selected_icon())
        self._populate_plugin_table()

    def _reset_plugin_visuals(self, plugin_id: str) -> None:
        self.services.set_plugin_override(plugin_id, display_name="", icon="")
        self._populate_plugin_table()

    def _reset_plugin_defaults(self) -> None:
        if not self._confirm_risky(
            self.tr("confirm.reset_plugins.title", "Reset plugin defaults?"),
            self.tr("confirm.reset_plugins.body", "This will reset plugin overrides and plugin state entries back to their defaults. A safety backup will be attempted first."),
        ):
            return
        if not self._create_safety_backup("plugin_reset"):
            return
        self.services.config.set("plugin_overrides", {})
        specs = self.services.manageable_plugin_specs(include_disabled=True)
        for spec in specs:
            self.services.plugin_state_manager.reset(spec.plugin_id)
            if spec.source_type == "custom":
                self.services.plugin_state_manager.set_enabled(spec.plugin_id, False)
                self.services.plugin_state_manager.set_hidden(spec.plugin_id, False)
                self.services.plugin_state_manager.set_trusted(spec.plugin_id, False)
                self.services.plugin_state_manager.set_scan_report(
                    spec.plugin_id,
                    {"risk_level": spec.risk_level, "summary": spec.risk_summary},
                )
            elif spec.source_type == "signed":
                self.services.plugin_state_manager.set_enabled(spec.plugin_id, True)
                self.services.plugin_state_manager.set_hidden(spec.plugin_id, False)
                self.services.plugin_state_manager.set_trusted(spec.plugin_id, True)
                self.services.plugin_state_manager.set_scan_report(spec.plugin_id, {"risk_level": "low", "summary": ""})
        self.services.reload_plugins()
        QMessageBox.information(
            self,
            self.tr("plugins.reset.title", "Plugins reset"),
            self.tr("plugins.reset.body", "Plugin overrides and states were reset to their defaults."),
        )
        self._populate_plugin_table()

    def _create_safety_backup(self, reason: str) -> bool:
        try:
            self.services.create_backup(reason=reason)
            return True
        except Exception as exc:
            return confirm_action(
                self,
                title=self.tr("backup.safety_failed.title", "Backup unavailable"),
                body=self.tr("backup.safety_failed.body", "A safety backup could not be created before this reset:\n\n{error}\n\nContinue anyway?", error=str(exc)),
                confirm_text=self.tr("confirm.continue", "Continue"),
                cancel_text=self.tr("confirm.cancel", "Cancel"),
            )

    def _icon_options(self) -> list[tuple[str, str, object]]:
        rows: list[tuple[str, str, object]] = []
        for icon_id, fallback_label, icon in icon_choices(self):
            rows.append((icon_id, self.tr(f"plugins.icon.{icon_id.replace('-', '_')}", fallback_label), icon))
        return rows

    def _plugin_status_text(self, spec) -> str:
        dependency_summary = self._plugin_dependency_summary(spec)
        contract_label = self.tr(f"plugins.contract.{spec.contract_status}", spec.contract_status.replace("_", " ").title())
        if spec.quarantined:
            base = self.tr("plugins.status.quarantined", "Quarantined")
        elif spec.source_type == "custom" and not spec.trusted:
            base = self.tr("plugins.status.review", "Pending Review")
        elif not spec.enabled:
            base = self.tr("plugins.status.disabled", "Disabled")
        elif spec.last_error:
            base = self.tr("plugins.status.error", "Error Recorded")
        else:
            base = self.tr("plugins.status.ready", "Ready")
        base = self.tr("plugins.status.with_contract", "{status} · {contract}", status=base, contract=contract_label)
        if not dependency_summary.has_manifest:
            return base
        return self.tr("plugins.status.with_deps", "{status} · {deps}", status=base, deps=self._plugin_dependency_status_text(dependency_summary))

    def _plugin_dependency_summary(self, spec):
        return self.services.plugin_dependency_manager.summary_for_spec(spec)

    def _plugin_dependency_status_text(self, summary) -> str:
        return self.tr(f"plugins.deps.status.{summary.status}", summary.message.replace("_", " ").title())

    def _plugin_review_details(self, spec) -> str:
        details: list[str] = []
        if spec.risk_summary:
            details.append(spec.risk_summary)
        details.append(
            self.tr(
                "plugins.contract.detail",
                "Contract: {status}",
                status=self.tr(f"plugins.contract.{spec.contract_status}", spec.contract_status.replace("_", " ").title()),
            )
        )
        if spec.last_error:
            details.append(self.tr("plugins.error_detail", "Last error: {error}", error=spec.last_error))
        if spec.failure_count:
            details.append(self.tr("plugins.failure_detail", "Failure count: {count}", count=str(spec.failure_count)))
        dependency_summary = self._plugin_dependency_summary(spec)
        if dependency_summary.has_manifest:
            details.append(self.tr("plugins.deps.detail.status", "Dependency status: {status}", status=self._plugin_dependency_status_text(dependency_summary)))
            details.append(self.tr("plugins.deps.detail.file", "Dependency file: {path}", path=str(dependency_summary.manifest_path)))
            if dependency_summary.warning:
                details.append(self.tr("plugins.deps.detail.warning", "Dependency warning: {warning}", warning=dependency_summary.warning))
            if dependency_summary.error:
                details.append(self.tr("plugins.deps.detail.error", "Dependency error: {error}", error=dependency_summary.error))
        return "\n".join(details)

    def _style_risk_item(self, item: QTableWidgetItem, risk_level: str) -> None:
        normalized = (risk_level or "low").lower()
        if normalized in {"high", "critical"}:
            item.setForeground(QColor("#c62828"))
        elif normalized == "medium":
            item.setForeground(QColor("#b26a00"))
        else:
            item.setForeground(QColor("#1b5e20"))

    def _import_plugin_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(self, self.tr("plugins.import_file", "Import plugin file"), str(Path.home()), "Python Files (*.py)")
        if not file_path:
            return
        try:
            plugin_ids = self.services.plugin_package_manager.import_plugin_file(Path(file_path))
        except Exception as exc:
            QMessageBox.critical(self, self.tr("plugins.import_failed.title", "Import failed"), str(exc))
            return
        self.services.reload_plugins()
        self._populate_plugin_table()
        self._show_plugin_import_result(plugin_ids)

    def _import_plugin_folder(self) -> None:
        folder_path = QFileDialog.getExistingDirectory(self, self.tr("plugins.import_folder", "Import plugin folder"), str(Path.home()))
        if not folder_path:
            return
        try:
            plugin_ids = self.services.plugin_package_manager.import_plugin_folder(Path(folder_path))
        except Exception as exc:
            QMessageBox.critical(self, self.tr("plugins.import_failed.title", "Import failed"), str(exc))
            return
        self.services.reload_plugins()
        self._populate_plugin_table()
        self._show_plugin_import_result(plugin_ids)

    def _import_plugin_package(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("plugins.import_package", "Import plugin package"),
            str(Path.home()),
            self.tr("plugins.import_package.filter", "Plugin Package (*.zip)"),
        )
        if not file_path:
            return
        try:
            plugin_ids = self.services.plugin_package_manager.import_plugin_package(Path(file_path))
        except Exception as exc:
            QMessageBox.critical(self, self.tr("plugins.import_failed.title", "Import failed"), str(exc))
            return
        self.services.reload_plugins()
        self._populate_packages_table()
        self._populate_plugin_table()
        self._show_plugin_import_result(plugin_ids)

    def _show_plugin_import_result(self, plugin_ids: list[str]) -> None:
        dependency_plugins: list[str] = []
        signed_plugins: list[str] = []
        custom_plugins: list[str] = []
        for plugin_id in plugin_ids:
            spec = self.services.plugin_manager.get_spec(plugin_id, include_disabled=True)
            if spec is None:
                continue
            summary = self._plugin_dependency_summary(spec)
            if summary.has_manifest:
                dependency_plugins.append(self.services.plugin_display_name(spec))
            if spec.source_type == "signed":
                signed_plugins.append(self.services.plugin_display_name(spec))
            else:
                custom_plugins.append(self.services.plugin_display_name(spec))
        sections: list[str] = []
        if signed_plugins:
            sections.append(self.tr("plugins.imported.signed.body", "Installed signed first-party plugins: {plugins}. They were verified and added to the app immediately.", plugins=", ".join(signed_plugins)))
        if custom_plugins:
            sections.append(self.tr("plugins.imported.body", "Imported plugins: {plugins}. They were added disabled and untrusted pending review.", plugins=", ".join(custom_plugins)))
        body = "\n\n".join(section for section in sections if section)
        if dependency_plugins:
            body = "\n\n".join(
                [
                    body,
                    self.tr(
                        "plugins.imported.deps_body",
                        "Dependency sidecars were detected for: {plugins}. Use the plugin context menu to install or repair dependencies after the package or plugin is in place.",
                        plugins=", ".join(dependency_plugins),
                    ),
                ]
            )
        QMessageBox.information(self, self.tr("plugins.imported.title", "Plugin imported"), body)

    def _export_selected_plugins(self) -> None:
        specs = self._selected_export_specs()
        if not specs:
            QMessageBox.warning(self, self.tr("plugins.export_failed.title", "Nothing selected"), self.tr("plugins.export_failed.body", "Select at least one plugin to export."))
            return
        self._export_specs(specs)

    def _export_all_plugins(self) -> None:
        self._export_specs([spec for spec in self.services.manageable_plugin_specs(include_disabled=True) if spec.source_type == "custom"])

    def _export_specs(self, specs) -> None:
        suggested = Path.home() / "dngine_plugin_package.zip"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            self.tr("plugins.export_dialog", "Export plugin package"),
            str(suggested),
            self.tr("plugins.export_dialog.filter", "Plugin Package (*.zip)"),
        )
        if not file_path:
            return
        destination = Path(file_path)
        if destination.suffix.lower() != ".zip":
            destination = destination.with_suffix(".zip")
        try:
            exported = self.services.plugin_package_manager.export_plugins(specs, destination)
        except Exception as exc:
            QMessageBox.critical(self, self.tr("plugins.export_failed.title", "Export failed"), str(exc))
            return
        QMessageBox.information(self, self.tr("plugins.exported.title", "Plugin package exported"), self.tr("plugins.exported.body", "Plugin package written to {path}", path=str(exported)))

    def _selected_export_specs(self):
        specs_by_id = {
            spec.plugin_id: spec
            for spec in self.services.manageable_plugin_specs(include_disabled=True)
            if spec.source_type == "custom"
        }
        selected = []
        for row_index in range(self.plugins_table.rowCount()):
            name_item = self.plugins_table.item(row_index, 2)
            if name_item is None or not self._is_row_selected_for_export(row_index):
                continue
            spec = specs_by_id.get(name_item.data(Qt.ItemDataRole.UserRole))
            if spec is not None:
                selected.append(spec)
        return selected

    def _apply_texts(self) -> None:
        self._apply_theme_styles()
        self.title_label.setText(self._page_tr("title", "Plugin Manager"))
        self.description_label.setText(
            self._page_tr(
                "description",
                "Install, inspect, trust, enable, hide, import, and export plugins and signed packages from one place.",
            )
        )
        self.packages_note.setText(
            self.tr(
                "packages.note",
                "Browse the signed first-party package catalog here. Install optional groups on demand, refresh the catalog, or import a signed package archive directly.",
            )
        )
        self.refresh_package_catalog_button.setText(self.tr("packages.refresh", "Refresh Catalog"))
        self.install_package_button.setText(self.tr("packages.install", "Install Package"))
        self.remove_package_button.setText(self.tr("packages.remove", "Remove Package"))
        self.import_signed_package_button.setText(self.tr("packages.import_local", "Import Signed Package..."))
        self.refresh_package_catalog_button.setToolTip(self.refresh_package_catalog_button.text())
        self.install_package_button.setToolTip(self.install_package_button.text())
        self.remove_package_button.setToolTip(self.remove_package_button.text())
        self.import_signed_package_button.setToolTip(self.import_signed_package_button.text())

        self.plugins_note.setText(
            self.tr(
                "plugins.note",
                "Manage built-in, signed, and custom plugins here. Signed first-party packages install from the catalog above, while loose file and folder imports remain available for development and manual workflows.",
            )
        )
        self.import_package_button.setText(self.tr("plugins.import_package_button", "Import Package"))
        self.import_file_button.setText(self.tr("plugins.import_file_button", "Import File (Dev)"))
        self.import_folder_button.setText(self.tr("plugins.import_folder_button", "Import Folder (Dev)"))
        self.export_selected_button.setText(self.tr("plugins.export_selected", "Export Selected Package"))
        self.export_all_button.setText(self.tr("plugins.export_all", "Export All Packages"))
        self.reset_plugins_button.setText(self.tr("plugins.reset", "Reset plugin defaults"))
        self.refresh_plugins_button.setText(self.tr("plugins.refresh", "Refresh"))
        for button in (
            self.import_package_button,
            self.import_file_button,
            self.import_folder_button,
            self.export_selected_button,
            self.export_all_button,
            self.reset_plugins_button,
            self.refresh_plugins_button,
        ):
            button.setToolTip(button.text())

        self._populate_packages_table()
        self._populate_plugin_table()
        self._apply_responsive_layout(force=True)

    def _plugins_table_content_width(self) -> int:
        header = self.plugins_table.horizontalHeader()
        width = (self.plugins_table.frameWidth() * 2) + self.plugins_table.verticalHeader().width()
        for column in range(self.plugins_table.columnCount()):
            width += header.sectionSize(column)
        if self.plugins_table.verticalScrollBar().isVisible():
            width += self.plugins_table.verticalScrollBar().sizeHint().width()
        return width + 2

    def _schedule_plugins_table_width_sync(self, *_args) -> None:
        if self._plugins_table_width_sync_pending:
            return
        self._plugins_table_width_sync_pending = True
        QTimer.singleShot(0, self._sync_plugins_table_width)

    def _sync_plugins_table_width(self) -> None:
        self._plugins_table_width_sync_pending = False
        required_width = self._plugins_table_content_width()
        if self.plugins_table.minimumWidth() != required_width:
            self.plugins_table.setMinimumWidth(required_width)
        self.plugins_table.updateGeometry()
        self.plugins_card.updateGeometry()
        self.updateGeometry()

    def _sync_developer_plugin_actions(self) -> None:
        enabled = self.services.developer_mode_enabled()
        for button in self._developer_plugin_action_buttons:
            button.setHidden(not enabled)

    def _visible_plugin_action_buttons(self) -> list[QToolButton]:
        developer_enabled = self.services.developer_mode_enabled()
        developer_only = set(self._developer_plugin_action_buttons)
        buttons: list[QToolButton] = []
        for button in self._plugin_action_buttons:
            if button in developer_only and not developer_enabled:
                continue
            buttons.append(button)
        return buttons

    def _apply_responsive_layout(self, *, force: bool = False) -> None:
        bucket = width_breakpoint(self.width(), compact_max=760, medium_max=1180)
        if not force and bucket == self._responsive_bucket:
            return
        self._responsive_bucket = bucket
        available_width = min(
            visible_parent_width(self),
            self.plugins_card.contentsRect().width() or self.plugins_card.width() or self.width(),
        )

        while self.packages_actions_layout.count():
            item = self.packages_actions_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(self.packages_card)
        package_button_widths = [button.sizeHint().width() for button in self._package_action_buttons]
        package_spacing = self.packages_actions_layout.horizontalSpacing()
        required_package_width = sum(package_button_widths) + (package_spacing * max(0, len(package_button_widths) - 1))
        package_columns = len(package_button_widths) if available_width >= required_package_width else 2
        for index, button in enumerate(self._package_action_buttons):
            self.packages_actions_layout.addWidget(button, index // package_columns, index % package_columns)
        for column in range(package_columns):
            self.packages_actions_layout.setColumnStretch(column, 1)

        while self.plugins_actions_layout.count():
            item = self.plugins_actions_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(self.plugins_card)
        visible_plugin_buttons = self._visible_plugin_action_buttons()
        plugin_button_widths = [button.sizeHint().width() for button in visible_plugin_buttons]
        plugin_spacing = self.plugins_actions_layout.horizontalSpacing()
        required_for_single_row = sum(plugin_button_widths) + (plugin_spacing * max(0, len(plugin_button_widths) - 1))
        plugin_columns = len(plugin_button_widths) if available_width >= required_for_single_row else 4
        for index, button in enumerate(visible_plugin_buttons):
            self.plugins_actions_layout.addWidget(button, index // plugin_columns, index % plugin_columns)
        for column in range(plugin_columns):
            self.plugins_actions_layout.setColumnStretch(column, 1)

    def _schedule_responsive_refresh(self) -> None:
        if self._responsive_refresh_pending:
            return
        self._responsive_refresh_pending = True
        QTimer.singleShot(0, self._run_responsive_refresh)

    def _run_responsive_refresh(self) -> None:
        self._responsive_refresh_pending = False
        self._apply_responsive_layout()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._schedule_responsive_refresh()

    def _handle_theme_change(self, _mode: str) -> None:
        self._apply_theme_styles()
        self._populate_packages_table()
        self._populate_plugin_table()

    def _apply_theme_styles(self) -> None:
        palette = self.services.theme_manager.current_palette()
        self.setStyleSheet(
            f"""
            QWidget#PluginManagerPage {{
                background: {palette.base_bg};
            }}
            QToolTip {{
                background: {palette.component_bg};
                color: {palette.text_primary};
                border: 1px solid {palette.border};
                border-radius: 10px;
                padding: 6px 8px;
            }}
            """
        )
        apply_page_chrome(
            palette,
            title_label=self.title_label,
            description_label=self.description_label,
            cards=(self.packages_card, self.plugins_card),
            title_size=26,
            title_weight=700,
        )
        for label in (self.packages_note, self.plugins_note):
            label.setStyleSheet(muted_text_style(palette))
        for button in (
            self.refresh_package_catalog_button,
            self.install_package_button,
            self.remove_package_button,
            self.import_signed_package_button,
            self.import_package_button,
            self.import_file_button,
            self.import_folder_button,
            self.export_selected_button,
            self.export_all_button,
            self.reset_plugins_button,
            self.refresh_plugins_button,
        ):
            button.setStyleSheet("")
