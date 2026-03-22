from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from PySide6.QtCore import QEvent, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDockWidget,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QStatusBar,
    QStyle,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from micro_toolkit.core.icon_registry import icon_from_name
from micro_toolkit.core.plugin_manager import PluginSpec
from micro_toolkit.core.services import AppServices
from micro_toolkit.core.shell_registry import (
    DASHBOARD_PLUGIN_ID,
    NON_SIDEBAR_PLUGIN_IDS,
    SYSTEM_TOOLBAR_PLUGIN_IDS,
    UNSCROLLED_PLUGIN_IDS,
)

PLUGIN_ID_ROLE = Qt.ItemDataRole.UserRole + 1
GROUP_KEY_ROLE = Qt.ItemDataRole.UserRole + 2


class MicroToolkitWindow(QMainWindow):
    def __init__(self, services: AppServices, *, initial_plugin_id: str | None = None):
        super().__init__()
        self.services = services
        self.plugin_manager = self.services.plugin_manager
        self.all_specs: list[PluginSpec] = []
        self.plugin_specs: list[PluginSpec] = []
        self.plugin_by_id: dict[str, PluginSpec] = {}
        self.system_toolbar_buttons: dict[str, QToolButton] = {}
        self.page_indices: dict[str, int] = {}
        self.initial_plugin_id = initial_plugin_id
        self.current_plugin_id: str | None = None
        self._quitting = False

        self.setWindowTitle("Micro Toolkit")
        self.resize(1420, 900)
        self.setMinimumSize(1180, 720)

        self._refresh_specs()
        self._build_ui()
        self._bind_signals()
        self._populate_sidebar()
        self._open_initial_page()
        self._register_shortcuts()
        self._apply_shell_texts()
        self.services.attach_main_window(self)

    def _build_ui(self) -> None:
        central = QWidget(self)
        outer_layout = QHBoxLayout(central)
        outer_layout.setContentsMargins(18, 18, 18, 18)
        outer_layout.setSpacing(18)
        self.setCentralWidget(central)

        sidebar_card = QFrame()
        sidebar_card.setObjectName("SidebarCard")
        sidebar_card.setFixedWidth(308)
        sidebar_layout = QVBoxLayout(sidebar_card)
        sidebar_layout.setContentsMargins(18, 18, 18, 18)
        sidebar_layout.setSpacing(14)

        brand_row = QHBoxLayout()
        brand_row.setContentsMargins(0, 0, 0, 0)
        brand_row.setSpacing(10)
        self.app_title_label = QLabel("Micro Toolkit")
        self.app_title_label.setObjectName("AppTitle")
        brand_row.addWidget(self.app_title_label)
        brand_row.addStretch(1)
        sidebar_layout.addLayout(brand_row)

        self.sidebar_system_tools = QHBoxLayout()
        self.sidebar_system_tools.setContentsMargins(0, 0, 0, 0)
        self.sidebar_system_tools.setSpacing(6)

        for plugin_id, fallback_icon, fallback_label in (
            (DASHBOARD_PLUGIN_ID, QStyle.StandardPixmap.SP_DirHomeIcon, "Dashboard"),
            ("clip_manager", QStyle.StandardPixmap.SP_FileDialogContentsView, "Clipboard"),
            ("workflow_studio", QStyle.StandardPixmap.SP_BrowserReload, "Workflows"),
            ("about_center", QStyle.StandardPixmap.SP_FileDialogInfoView, "About"),
            ("settings_center", QStyle.StandardPixmap.SP_FileDialogDetailedView, "Settings"),
        ):
            button = self._make_tool_button(
                icon=self.style().standardIcon(fallback_icon),
                tooltip=fallback_label,
                handler=lambda _checked=False, pid=plugin_id: self.open_plugin(pid),
                checkable=True,
            )
            button.setIconSize(QSize(22, 22))
            button.setFixedSize(38, 38)
            self.system_toolbar_buttons[plugin_id] = button
            self.sidebar_system_tools.addWidget(button)
        self.sidebar_system_tools.addStretch(1)
        sidebar_layout.addLayout(self.sidebar_system_tools)

        self.search_input = QLineEdit()
        sidebar_layout.addWidget(self.search_input)

        self.sidebar_tree = QTreeWidget()
        self.sidebar_tree.setHeaderHidden(True)
        self.sidebar_tree.setRootIsDecorated(True)
        self.sidebar_tree.setIndentation(16)
        self.sidebar_tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.sidebar_tree.setUniformRowHeights(True)
        self.sidebar_tree.setAnimated(True)
        sidebar_layout.addWidget(self.sidebar_tree, 1)

        content_shell = QWidget()
        content_layout = QVBoxLayout(content_shell)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(18)

        header_card = QFrame()
        header_card.setObjectName("HeaderCard")
        header_layout = QVBoxLayout(header_card)
        header_layout.setContentsMargins(22, 18, 22, 18)
        header_layout.setSpacing(10)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(12)

        title_column = QVBoxLayout()
        title_column.setContentsMargins(0, 0, 0, 0)
        title_column.setSpacing(4)

        self.page_context = QLabel()
        self.page_context.setObjectName("SectionEyebrow")
        title_column.addWidget(self.page_context)

        self.page_title = QLabel()
        self.page_title.setObjectName("PageTitle")
        title_column.addWidget(self.page_title)
        top_row.addLayout(title_column, 1)

        self.pin_current_button = self._make_tool_button(
            icon=self.style().standardIcon(QStyle.StandardPixmap.SP_DialogApplyButton),
            tooltip="Pin to quick access",
            handler=self._toggle_current_quick_access,
            checkable=True,
        )
        self.pin_current_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.pin_current_button.setAutoRaise(False)
        top_row.addWidget(self.pin_current_button)

        header_layout.addLayout(top_row)

        self.page_description = QLabel()
        self.page_description.setObjectName("PageDescription")
        self.page_description.setWordWrap(True)
        header_layout.addWidget(self.page_description)

        content_layout.addWidget(header_card)

        page_card = QFrame()
        page_card.setObjectName("PageCard")
        page_layout = QVBoxLayout(page_card)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)

        self.page_stack = QStackedWidget()
        page_layout.addWidget(self.page_stack)
        content_layout.addWidget(page_card, 1)

        outer_layout.addWidget(sidebar_card)
        outer_layout.addWidget(content_shell, 1)

        self.log_dock = QDockWidget(self)
        self.log_dock.setAllowedAreas(
            Qt.DockWidgetArea.BottomDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMaximumBlockCount(800)
        self.log_output.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.log_dock.setWidget(self.log_output)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.log_dock)

        status = QStatusBar()
        self.status_label = QLabel()
        status.addWidget(self.status_label, 1)
        self.console_button = self._make_tool_button(
            icon=self._named_icon("terminal", fallback=QStyle.StandardPixmap.SP_ComputerIcon),
            tooltip="Show activity console",
            handler=self.toggle_activity_dock,
            checkable=True,
        )
        self.console_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.console_button.setIconSize(QSize(16, 16))
        self.console_button.setFixedSize(24, 20)
        status.addPermanentWidget(self.console_button)
        self.setStatusBar(status)

        placeholder = self._build_placeholder_page()
        self.page_stack.addWidget(placeholder)
        self.page_stack.setCurrentWidget(placeholder)

    def _make_tool_button(self, *, icon, tooltip: str, handler, checkable: bool = False) -> QToolButton:
        button = QToolButton()
        button.setIcon(icon)
        button.setToolTip(tooltip)
        button.setAutoRaise(True)
        button.setCheckable(checkable)
        button.clicked.connect(handler)
        return button

    def _bind_signals(self) -> None:
        self.search_input.textChanged.connect(self._apply_filter)
        self.sidebar_tree.itemSelectionChanged.connect(self._handle_selection_change)
        self.sidebar_tree.itemExpanded.connect(lambda item: self._store_group_state(item, expanded=True))
        self.sidebar_tree.itemCollapsed.connect(lambda item: self._store_group_state(item, expanded=False))
        self.services.logger.message_logged.connect(self._append_log)
        self.services.logger.status_changed.connect(self.status_label.setText)
        self.services.i18n.language_changed.connect(self._handle_language_change)
        self.services.theme_manager.theme_changed.connect(self._handle_theme_change)
        self.services.plugin_visuals_changed.connect(self.refresh_plugin_visuals)
        self.log_dock.visibilityChanged.connect(self._sync_console_button)

    def _build_placeholder_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(14)

        self.placeholder_eyebrow = QLabel()
        self.placeholder_eyebrow.setObjectName("SectionEyebrow")
        layout.addWidget(self.placeholder_eyebrow)

        self.placeholder_title = QLabel()
        self.placeholder_title.setObjectName("PlaceholderTitle")
        layout.addWidget(self.placeholder_title)

        self.placeholder_body = QLabel()
        self.placeholder_body.setWordWrap(True)
        self.placeholder_body.setObjectName("PlaceholderBody")
        layout.addWidget(self.placeholder_body)
        layout.addStretch(1)
        return page

    def _refresh_specs(self) -> None:
        self.all_specs = self.plugin_manager.discover_plugins(include_disabled=True)
        self.plugin_by_id = {spec.plugin_id: spec for spec in self.all_specs}
        self.plugin_specs = [
            spec
            for spec in self.plugin_manager.sidebar_plugins()
            if spec.plugin_id not in NON_SIDEBAR_PLUGIN_IDS
        ]

    def _group_collapsed_state(self) -> dict[str, bool]:
        raw = self.services.config.get("collapsed_groups") or {}
        return raw if isinstance(raw, dict) else {}

    def _set_group_collapsed_state(self, group_key: str, collapsed: bool) -> None:
        state = dict(self._group_collapsed_state())
        state[group_key] = bool(collapsed)
        self.services.config.set("collapsed_groups", state)

    def _populate_sidebar(self) -> None:
        self.sidebar_tree.clear()
        language = self.services.i18n.current_language()
        collapsed_state = self._group_collapsed_state()

        quick_group = QTreeWidgetItem([self.services.i18n.tr("shell.quick_access", "Quick Access")])
        quick_group.setData(0, GROUP_KEY_ROLE, "quick_access")
        quick_group.setFlags(Qt.ItemFlag.ItemIsEnabled)
        quick_group.setExpanded(not collapsed_state.get("quick_access", False))
        quick_group.setIcon(0, self._named_icon("bolt", fallback=QStyle.StandardPixmap.SP_DialogOpenButton))
        self.sidebar_tree.addTopLevelItem(quick_group)

        quick_specs = [self.plugin_by_id[plugin_id] for plugin_id in self.services.quick_access_ids() if plugin_id in self.plugin_by_id]
        for spec in quick_specs:
            child = QTreeWidgetItem([self.services.plugin_display_name(spec)])
            child.setToolTip(0, spec.localized_description(language))
            child.setData(0, PLUGIN_ID_ROLE, spec.plugin_id)
            child.setIcon(0, self._plugin_icon(spec))
            quick_group.addChild(child)

        categories: dict[str, list[PluginSpec]] = defaultdict(list)
        for spec in self.plugin_specs:
            if spec.plugin_id == DASHBOARD_PLUGIN_ID:
                continue
            category_name = spec.localized_category(language).strip() or self.services.i18n.tr("shell.tools", "Tools")
            if category_name.lower() == "general" and spec.plugin_id != DASHBOARD_PLUGIN_ID:
                continue
            categories[category_name].append(spec)

        for category in sorted(categories):
            category_key = f"category::{category}"
            category_item = QTreeWidgetItem([category])
            category_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            category_item.setFirstColumnSpanned(True)
            category_item.setData(0, GROUP_KEY_ROLE, category_key)
            category_item.setExpanded(not collapsed_state.get(category_key, False))
            category_item.setIcon(0, self._group_icon(categories[category]))
            self.sidebar_tree.addTopLevelItem(category_item)

            for spec in sorted(categories[category], key=lambda item: self.services.plugin_display_name(item).lower()):
                child = QTreeWidgetItem([self.services.plugin_display_name(spec)])
                child.setToolTip(0, spec.localized_description(language))
                child.setData(0, PLUGIN_ID_ROLE, spec.plugin_id)
                child.setIcon(0, self._plugin_icon(spec))
                category_item.addChild(child)

    def _open_initial_page(self) -> None:
        initial_id = self.initial_plugin_id if self.initial_plugin_id in self.plugin_by_id else None
        if initial_id is None:
            initial_id = DASHBOARD_PLUGIN_ID if DASHBOARD_PLUGIN_ID in self.plugin_by_id else None
        if initial_id is None and self.plugin_specs:
            initial_id = self.plugin_specs[0].plugin_id
        if initial_id is not None:
            self._select_plugin_item(initial_id)
            self.open_plugin(initial_id)

    def _select_plugin_item(self, plugin_id: str) -> None:
        root = self.sidebar_tree.invisibleRootItem()
        for i in range(root.childCount()):
            top_item = root.child(i)
            if top_item.data(0, PLUGIN_ID_ROLE) == plugin_id:
                self.sidebar_tree.setCurrentItem(top_item)
                return
            for j in range(top_item.childCount()):
                item = top_item.child(j)
                if item.data(0, PLUGIN_ID_ROLE) == plugin_id:
                    self.sidebar_tree.setCurrentItem(item)
                    return

    def _apply_filter(self, text: str) -> None:
        needle = text.strip().lower()
        root = self.sidebar_tree.invisibleRootItem()
        language = self.services.i18n.current_language()
        for i in range(root.childCount()):
            item = root.child(i)
            plugin_id = item.data(0, PLUGIN_ID_ROLE)
            if plugin_id:
                spec = self.plugin_by_id.get(plugin_id)
                haystack = " ".join(
                    [
                        self.services.plugin_display_name(spec) if spec else "",
                        spec.localized_description(language) if spec else "",
                    ]
                ).lower()
                item.setHidden(bool(needle) and needle not in haystack)
                continue

            visible_children = 0
            for j in range(item.childCount()):
                child = item.child(j)
                child_plugin_id = child.data(0, PLUGIN_ID_ROLE)
                spec = self.plugin_by_id.get(child_plugin_id)
                haystack = " ".join(
                    [
                        self.services.plugin_display_name(spec) if spec else "",
                        spec.localized_description(language) if spec else "",
                        spec.localized_category(language) if spec else "",
                    ]
                ).lower()
                hidden = bool(needle) and needle not in haystack
                child.setHidden(hidden)
                if not hidden:
                    visible_children += 1
            item.setHidden(visible_children == 0 and bool(needle))
            if needle and visible_children:
                item.setExpanded(True)

    def _handle_selection_change(self) -> None:
        item = self.sidebar_tree.currentItem()
        if item is None:
            return
        plugin_id = item.data(0, PLUGIN_ID_ROLE)
        if plugin_id:
            self.open_plugin(plugin_id)

    def _store_group_state(self, item: QTreeWidgetItem, *, expanded: bool) -> None:
        if item is None:
            return
        group_key = item.data(0, GROUP_KEY_ROLE)
        if not group_key:
            return
        self._set_group_collapsed_state(str(group_key), not expanded)

    def _toggle_current_quick_access(self):
        if self.current_plugin_id is None or self.current_plugin_id not in {spec.plugin_id for spec in self.services.pinnable_plugin_specs()}:
            return {"pinned": False}
        pinned = self.services.toggle_quick_access(self.current_plugin_id)
        self.pin_current_button.setChecked(pinned)
        return {"pinned": pinned}

    def open_plugin(self, plugin_id: str) -> None:
        spec = self.plugin_by_id.get(plugin_id)
        if spec is None:
            return

        try:
            if plugin_id not in self.page_indices:
                plugin = self.plugin_manager.load_plugin(plugin_id)
                plugin_widget = plugin.create_widget(self.services)
                self._normalize_theme_styles(plugin_widget)
                self._suppress_duplicate_page_header(plugin_widget, spec)
                if plugin_id in UNSCROLLED_PLUGIN_IDS:
                    page_widget = plugin_widget
                else:
                    scroll_area = QScrollArea()
                    scroll_area.setWidgetResizable(True)
                    scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
                    scroll_area.setWidget(plugin_widget)
                    page_widget = scroll_area

                page_index = self.page_stack.addWidget(page_widget)
                self.page_indices[plugin_id] = page_index
        except Exception as exc:
            self._handle_plugin_open_error(spec, exc)
            return

        self.current_plugin_id = plugin_id
        self._sync_system_toolbar_selection(plugin_id)
        if plugin_id in SYSTEM_TOOLBAR_PLUGIN_IDS:
            self.sidebar_tree.blockSignals(True)
            self.sidebar_tree.clearSelection()
            self.sidebar_tree.setCurrentItem(None)
            self.sidebar_tree.blockSignals(False)
        else:
            self._select_plugin_item(plugin_id)
        self.page_stack.setCurrentIndex(self.page_indices[plugin_id])
        self._sync_header(spec)
        self.services.logger.set_status(f"Loaded {self.services.plugin_display_name(spec)}")
        if spec.source_type == "custom":
            self.services.plugin_state_manager.clear_failures(plugin_id)

    def _sync_header(self, spec: PluginSpec) -> None:
        language = self.services.i18n.current_language()
        self.page_title.setText(self.services.plugin_display_name(spec))
        self.page_description.setText(spec.localized_description(language))
        if spec.plugin_id == DASHBOARD_PLUGIN_ID:
            self.page_context.setText(self.services.i18n.tr("shell.dashboard", "Dashboard"))
        elif spec.plugin_id in SYSTEM_TOOLBAR_PLUGIN_IDS:
            self.page_context.setText(self.services.i18n.tr("shell.system_tools", "System Tools"))
        else:
            self.page_context.setText(spec.localized_category(language) or self.services.i18n.tr("shell.tools", "Tools"))

        is_pinnable = spec.plugin_id in {item.plugin_id for item in self.services.pinnable_plugin_specs()}
        self.pin_current_button.setVisible(is_pinnable)
        is_pinned = is_pinnable and self.services.is_quick_access(spec.plugin_id)
        self.pin_current_button.setChecked(is_pinned)
        self.pin_current_button.setText(
            self.services.i18n.tr("shell.unpin", "Unpin from quick access")
            if is_pinned
            else self.services.i18n.tr("shell.pin", "Pin to quick access")
        )
        self.pin_current_button.setToolTip(self.pin_current_button.text())

    def _suppress_duplicate_page_header(self, plugin_widget: QWidget, spec: PluginSpec) -> None:
        if spec.plugin_id == DASHBOARD_PLUGIN_ID:
            return

        layout = plugin_widget.layout()
        if layout is None:
            return

        hidden_labels = 0
        for index in range(min(layout.count(), 4)):
            item = layout.itemAt(index)
            widget = item.widget() if item is not None else None
            if not isinstance(widget, QLabel):
                continue

            text = self._normalized_text(widget.text())
            if not text:
                continue
            widget.hide()
            hidden_labels += 1
            if hidden_labels >= 2:
                break

    @staticmethod
    def _normalized_text(value: str) -> str:
        return " ".join(str(value or "").split()).strip().casefold()

    def _normalize_theme_styles(self, root_widget: QWidget) -> None:
        replacements = self._theme_style_replacements()
        widgets = [root_widget] + root_widget.findChildren(QWidget)
        for widget in widgets:
            current = widget.styleSheet()
            if not current:
                continue
            original = widget.property("_micro_original_stylesheet")
            if original is None:
                widget.setProperty("_micro_original_stylesheet", current)
                original = current
            themed = str(original)
            for source, target in replacements.items():
                themed = themed.replace(source, target)
            if themed != current:
                widget.setStyleSheet(themed)

    def _theme_style_replacements(self) -> dict[str, str]:
        palette = self.services.theme_manager.current_palette()
        return {
            "color: palette(mid);": f"color: {palette.text_muted};",
            "border: 1px solid palette(mid);": f"border: 1px solid {palette.border};",
            "background: palette(base);": f"background: {palette.input_bg};",
            "#10232c": palette.text_primary,
            "#8a1f11": palette.danger,
            "#6a2218": palette.danger,
            "#43535c": palette.text_muted,
            "#56646b": palette.text_muted,
            "#34444d": palette.text_muted,
            "#6a382f": palette.text_muted,
            "#7c5c57": palette.text_muted,
            "#fffdf9": palette.surface_alt_bg,
            "#fffaf3": palette.surface_bg,
            "#fff7f2": palette.surface_alt_bg,
            "#eadfce": palette.border,
            "#e0d5c6": palette.border,
            "#efd3c9": palette.border,
            "#b63f26": palette.danger,
            "#9e341e": palette.danger,
            "#d79a8b": palette.border,
        }

    def _append_log(self, timestamp: str, level: str, message: str) -> None:
        self.log_output.appendPlainText(f"{timestamp} [{level}] {message}")

    def _apply_shell_texts(self) -> None:
        tr = self.services.i18n.tr
        self.search_input.setPlaceholderText(tr("shell.search", "Filter tools..."))
        for plugin_id, label in (
            (DASHBOARD_PLUGIN_ID, tr("shell.dashboard", "Dashboard")),
            ("clip_manager", tr("shell.clipboard", "Clipboard")),
            ("workflow_studio", tr("shell.workflows", "Workflows")),
            ("about_center", tr("shell.about", "About")),
            ("settings_center", tr("shell.settings", "Settings")),
        ):
            button = self.system_toolbar_buttons.get(plugin_id)
            if button is not None:
                spec = self.plugin_by_id.get(plugin_id)
                button.setToolTip(self.services.plugin_display_name(spec) if spec is not None else label)
                if spec is not None:
                    button.setIcon(self._plugin_icon(spec))
        self.console_button.setToolTip(tr("shell.activity", "Activity"))
        self.console_button.setIcon(self._named_icon("terminal", fallback=QStyle.StandardPixmap.SP_ComputerIcon))
        self.log_dock.setWindowTitle(tr("shell.activity", "Activity"))
        if not self.page_title.text():
            self.page_title.setText(tr("shell.welcome.title", "Dashboard"))
        if not self.page_description.text():
            self.page_description.setText(tr("shell.welcome.description", "Pick a tool from the left to load it into the workspace."))
        self.status_label.setText(tr("shell.ready", "Ready"))
        self.placeholder_eyebrow.setText(tr("shell.placeholder.eyebrow", "Platform Layer"))
        self.placeholder_title.setText(tr("shell.placeholder.title", "The app core is built for desktop use."))
        self.placeholder_body.setText(
            tr(
                "shell.placeholder.body",
                "Themes, language switching, workflows, shortcuts, startup behavior, and tray integration now live directly in the app core.",
            )
        )

    def _register_shortcuts(self) -> None:
        self.services.shortcut_manager.register_action("focus_search", "Focus search", "Ctrl+K", self.focus_search)
        self.services.shortcut_manager.register_action("open_settings", "Open settings", "Ctrl+,", lambda: self.open_plugin("settings_center"))
        self.services.shortcut_manager.register_action("open_workflows", "Open workflows", "Ctrl+Shift+W", lambda: self.open_plugin("workflow_studio"))
        self.services.shortcut_manager.register_action("open_clipboard", "Open clipboard", "Ctrl+Shift+V", lambda: self.open_plugin("clip_manager"))
        self.services.shortcut_manager.register_action(
            "show_clipboard_quick_panel",
            "Quick clipboard history",
            "Ctrl+Alt+V",
            self.services.clipboard_quick_panel.toggle,
            default_scope="global",
        )
        self.services.shortcut_manager.register_action("toggle_activity", "Toggle activity panel", "F12", self.toggle_activity_dock)

    def focus_search(self):
        self.restore_from_tray()
        self.search_input.setFocus()
        self.search_input.selectAll()
        return {"focused": "search"}

    def toggle_activity_dock(self):
        self.log_dock.setVisible(not self.log_dock.isVisible())
        self._sync_console_button(self.log_dock.isVisible())
        return {"visible": self.log_dock.isVisible()}

    def _sync_console_button(self, visible: bool) -> None:
        self.console_button.blockSignals(True)
        self.console_button.setChecked(bool(visible))
        self.console_button.blockSignals(False)

    def restore_from_tray(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()
        return {"restored": True}

    def quit_from_tray(self):
        self._quitting = True
        self.close()

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange and self.isMinimized():
            if self.services.config.get("minimize_to_tray") and self.services.tray_manager.tray_icon is not None:
                QTimer.singleShot(0, self._hide_to_tray)

    def closeEvent(self, event) -> None:
        if not self._quitting and self.services.config.get("close_to_tray") and self.services.tray_manager.tray_icon is not None:
            event.ignore()
            self._hide_to_tray()
            return
        self._quitting = True
        super().closeEvent(event)

    def _hide_to_tray(self) -> None:
        self.hide()
        self.services.tray_manager.show_message(
            self.services.i18n.tr("tray.hidden.title", "Running in tray"),
            self.services.i18n.tr("tray.hidden.body", "Micro Toolkit is still running in the system tray."),
        )

    def reload_plugin_catalog(self, *, preferred_plugin_id: str | None = None) -> None:
        current_plugin_id = preferred_plugin_id or self.current_plugin_id
        self._refresh_specs()
        self.page_indices.clear()

        self.sidebar_tree.blockSignals(True)
        self._populate_sidebar()
        self.sidebar_tree.blockSignals(False)

        while self.page_stack.count():
            widget = self.page_stack.widget(0)
            self.page_stack.removeWidget(widget)
            widget.deleteLater()
        placeholder = self._build_placeholder_page()
        self.page_stack.addWidget(placeholder)
        self.page_stack.setCurrentWidget(placeholder)

        target_id = current_plugin_id if current_plugin_id in self.plugin_by_id else None
        if target_id is None:
            target_id = DASHBOARD_PLUGIN_ID if DASHBOARD_PLUGIN_ID in self.plugin_by_id else None
        if target_id is None and self.plugin_specs:
            target_id = self.plugin_specs[0].plugin_id
        if target_id is not None:
            self._select_plugin_item(target_id)
            self.open_plugin(target_id)

    def refresh_sidebar(self) -> None:
        current_plugin_id = self.current_plugin_id
        self._refresh_specs()
        self.sidebar_tree.blockSignals(True)
        self._populate_sidebar()
        self.sidebar_tree.blockSignals(False)
        if current_plugin_id is not None and current_plugin_id not in SYSTEM_TOOLBAR_PLUGIN_IDS:
            self._select_plugin_item(current_plugin_id)

    def refresh_plugin_visuals(self, plugin_id: str | None = None) -> None:
        self.refresh_sidebar()
        self._sync_system_toolbar_selection(self.current_plugin_id)
        if self.current_plugin_id is not None:
            spec = self.plugin_by_id.get(self.current_plugin_id)
            if spec is not None:
                self._sync_header(spec)
        self._apply_shell_texts()

    def _plugin_icon(self, spec: PluginSpec) -> QIcon:
        override = self.services.plugin_icon_override(spec)
        if override:
            path = Path(override)
            if path.exists():
                return QIcon(str(path))
            registry_icon = icon_from_name(override, self)
            if registry_icon is not None:
                return registry_icon
            qt_icon = self._qt_icon_from_name(override)
            if qt_icon is not None:
                return qt_icon
        for candidate in self._plugin_icon_candidates(spec):
            if candidate.exists():
                return QIcon(str(candidate))
        preferred = icon_from_name(spec.preferred_icon, self) or self._qt_icon_from_name(spec.preferred_icon)
        if preferred is not None:
            return preferred
        fallback = self._default_plugin_icon(spec)
        if fallback is not None:
            return fallback
        return self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)

    def _named_icon(self, icon_name: str, *, fallback: QStyle.StandardPixmap) -> QIcon:
        return icon_from_name(icon_name, self) or self.style().standardIcon(fallback)

    def _sync_system_toolbar_selection(self, plugin_id: str | None) -> None:
        active_id = plugin_id if plugin_id in SYSTEM_TOOLBAR_PLUGIN_IDS else None
        for button_plugin_id, button in self.system_toolbar_buttons.items():
            button.blockSignals(True)
            button.setChecked(button_plugin_id == active_id)
            button.blockSignals(False)

    def _plugin_icon_candidates(self, spec: PluginSpec) -> list[Path]:
        stem_name = spec.file_path.stem
        return [
            spec.file_path.with_suffix(".ico"),
            spec.file_path.parent / f"{stem_name}.ico",
            spec.file_path.parent / "plugin.ico",
            spec.container_path / "plugin.ico" if spec.container_path.exists() else spec.file_path.parent / "plugin.ico",
        ]

    def _group_icon(self, specs: list[PluginSpec]) -> QIcon:
        for candidate in self._group_icon_candidates(specs):
            if candidate.exists():
                return QIcon(str(candidate))
        return self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon)

    def _group_icon_candidates(self, specs: list[PluginSpec]) -> list[Path]:
        candidates: list[Path] = []
        seen: set[Path] = set()
        for spec in specs:
            parent = spec.file_path.parent
            for candidate in (parent / "folder.ico", parent / "group.ico", spec.container_path / "folder.ico"):
                if candidate not in seen:
                    seen.add(candidate)
                    candidates.append(candidate)
        return candidates

    def _default_plugin_icon(self, spec: PluginSpec) -> QIcon | None:
        by_id = {
            "welcome_overview": "home",
            "clip_manager": "clipboard",
            "workflow_studio": "workflow",
            "about_center": "info",
            "settings_center": "settings",
        }
        if spec.plugin_id in by_id:
            icon = icon_from_name(by_id[spec.plugin_id], self)
            if icon is not None:
                return icon
        category = (spec.category or "").lower()
        if "file" in category:
            return icon_from_name("folder-open", self) or self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon)
        if "office" in category:
            return icon_from_name("office", self) or self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogListView)
        if "media" in category:
            return icon_from_name("media", self) or self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay)
        if "it" in category or "system" in category:
            return icon_from_name("computer", self) or self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        if "validation" in category or "analysis" in category:
            return icon_from_name("analytics", self) or self.style().standardIcon(QStyle.StandardPixmap.SP_DialogApplyButton)
        return None

    def _qt_icon_from_name(self, icon_name: str) -> QIcon | None:
        key = str(icon_name or "").strip()
        if not key:
            return None
        mapping = {
            "desktop": QStyle.StandardPixmap.SP_DesktopIcon,
            "computer": QStyle.StandardPixmap.SP_ComputerIcon,
            "folder": QStyle.StandardPixmap.SP_DirIcon,
            "folder-open": QStyle.StandardPixmap.SP_DirOpenIcon,
            "file": QStyle.StandardPixmap.SP_FileIcon,
            "settings": QStyle.StandardPixmap.SP_FileDialogDetailedView,
            "clipboard": QStyle.StandardPixmap.SP_FileDialogContentsView,
            "workflow": QStyle.StandardPixmap.SP_BrowserReload,
            "analytics": QStyle.StandardPixmap.SP_DialogApplyButton,
            "office": QStyle.StandardPixmap.SP_FileDialogListView,
            "media": QStyle.StandardPixmap.SP_MediaPlay,
            "search": QStyle.StandardPixmap.SP_FileDialogContentsView,
            "info": QStyle.StandardPixmap.SP_FileDialogInfoView,
        }
        pixmap = mapping.get(key.lower())
        if pixmap is None:
            return None
        return self.style().standardIcon(pixmap)

    def _handle_language_change(self) -> None:
        self._apply_shell_texts()
        self.reload_plugin_catalog(preferred_plugin_id=self.current_plugin_id)

    def _handle_theme_change(self, _mode: str) -> None:
        for plugin_id, page_index in list(self.page_indices.items()):
            page = self.page_stack.widget(page_index)
            if isinstance(page, QScrollArea):
                widget = page.widget()
            else:
                widget = page
            if isinstance(widget, QWidget):
                self._normalize_theme_styles(widget)
        self.refresh_plugin_visuals()

    def _handle_plugin_open_error(self, spec: PluginSpec, exc: Exception) -> None:
        message = str(exc)
        self.services.log(f"Plugin '{spec.plugin_id}' failed to open: {message}", "ERROR")
        if spec.source_type == "custom":
            state = self.services.plugin_state_manager.record_failure(spec.plugin_id, message)
            if state.get("quarantined"):
                self.services.log(
                    f"Custom plugin '{spec.plugin_id}' was quarantined after repeated failures.",
                    "WARNING",
                )
                self.reload_plugin_catalog(preferred_plugin_id="settings_center")
        self.page_stack.setCurrentIndex(0)
        self.page_title.setText(spec.localized_name(self.services.i18n.current_language()))
        self.page_description.setText(message)
        self.placeholder_eyebrow.setText(self.services.i18n.tr("shell.activity", "Activity"))
        self.placeholder_title.setText(f"Could not open {spec.localized_name(self.services.i18n.current_language())}")
        self.placeholder_body.setText(message)
        self.services.logger.set_status(message)
