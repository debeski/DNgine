from __future__ import annotations

from datetime import datetime

from PySide6.QtCharts import QBarCategoryAxis, QBarSeries, QBarSet, QChart, QChartView, QPieSeries, QValueAxis
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from micro_toolkit.core.page_style import (
    body_text_style,
    card_style,
    muted_text_style,
    page_title_style,
    section_title_style,
    tinted_card_style,
)
from micro_toolkit.core.plugin_api import QtPlugin


class WelcomeOverviewPlugin(QtPlugin):
    plugin_id = "welcome_overview"
    name = "Dashboard"
    description = "A live dashboard for your toolkit activity, system snapshot, and quick access shortcuts."
    category = "General"
    translations = {
        "en": {
            "plugin.name": "Dashboard",
            "plugin.description": "A live dashboard for your toolkit activity, system snapshot, and quick access shortcuts.",
        },
        "ar": {
            "plugin.name": "لوحة التحكم",
            "plugin.description": "لوحة حية لنشاط الأدوات ولمحة النظام واختصارات الوصول السريع.",
        },
    }

    def create_widget(self, services) -> QWidget:
        return DashboardPage(services, self.plugin_id)


class DashboardPage(QWidget):
    def __init__(self, services, plugin_id: str):
        super().__init__()
        self.services = services
        self.plugin_id = plugin_id
        self.quick_bar_layout: QHBoxLayout | None = None
        self.quick_access_list: QListWidget | None = None
        self.quick_access_combo: QComboBox | None = None
        self.hero_card: QFrame | None = None
        self.hero_stats_grid = None
        self.hero_side_panel: QFrame | None = None
        self.quick_access_card: QFrame | None = None
        self.activity_card: QFrame | None = None
        self.top_tools_card: QFrame | None = None
        self.status_card: QFrame | None = None
        self.hero_eyebrow: QLabel | None = None
        self.hero_title: QLabel | None = None
        self.hero_body: QLabel | None = None
        self.quick_access_title: QLabel | None = None
        self.activity_title: QLabel | None = None
        self.activity_stack: QVBoxLayout | None = None
        self.top_tools_chart = QChartView()
        self.status_chart = QChartView()
        self._build_ui()
        self._refresh()
        self.services.i18n.language_changed.connect(self._refresh)
        self.services.theme_manager.theme_changed.connect(self._handle_theme_change)
        self.services.quick_access_changed.connect(self._render_quick_access)
        self.services.plugin_visuals_changed.connect(self._handle_plugin_visuals_changed)

    def _pt(self, key: str, default: str, **kwargs) -> str:
        return self.services.plugin_text(self.plugin_id, key, default, **kwargs)

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 28, 28, 28)
        outer.setSpacing(18)

        self.hero_card = QFrame()
        self.hero_card.setObjectName("DashboardWelcomeCard")
        hero_layout = QHBoxLayout(self.hero_card)
        hero_layout.setContentsMargins(26, 24, 26, 24)
        hero_layout.setSpacing(20)

        hero_left = QVBoxLayout()
        hero_left.setSpacing(10)
        self.hero_eyebrow = QLabel()
        self.hero_title = QLabel()
        self.hero_title.setWordWrap(True)
        self.hero_body = QLabel()
        self.hero_body.setWordWrap(True)
        hero_left.addWidget(self.hero_eyebrow)
        hero_left.addWidget(self.hero_title)
        hero_left.addWidget(self.hero_body)

        from PySide6.QtWidgets import QGridLayout

        self.hero_stats_grid = QGridLayout()
        self.hero_stats_grid.setContentsMargins(0, 8, 0, 0)
        self.hero_stats_grid.setHorizontalSpacing(12)
        self.hero_stats_grid.setVerticalSpacing(12)
        hero_left.addLayout(self.hero_stats_grid)
        hero_layout.addLayout(hero_left, 1)
        outer.addWidget(self.hero_card)

        operational_row = QHBoxLayout()
        operational_row.setSpacing(14)

        self.quick_access_card = QFrame()
        quick_layout = QVBoxLayout(self.quick_access_card)
        quick_layout.setContentsMargins(20, 20, 20, 20)
        quick_layout.setSpacing(14)

        self.quick_access_title = QLabel()
        quick_layout.addWidget(self.quick_access_title)

        self.quick_bar_frame = QFrame()
        self.quick_bar_frame.setObjectName("QuickAccessRail")
        self.quick_bar_layout = QHBoxLayout(self.quick_bar_frame)
        self.quick_bar_layout.setContentsMargins(0, 0, 0, 0)
        self.quick_bar_layout.setSpacing(10)
        quick_layout.addWidget(self.quick_bar_frame)

        editor_row = QHBoxLayout()
        editor_row.setSpacing(14)

        self.quick_access_list = QListWidget()
        self.quick_access_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.quick_access_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.quick_access_list.model().rowsMoved.connect(self._persist_quick_access_from_list)
        editor_row.addWidget(self.quick_access_list, 1)

        editor_side = QVBoxLayout()
        editor_side.setSpacing(10)
        self.quick_access_combo = QComboBox()
        editor_side.addWidget(self.quick_access_combo)

        self.add_button = QPushButton()
        self.add_button.clicked.connect(self._add_selected_plugin)
        editor_side.addWidget(self.add_button)

        self.remove_button = QPushButton()
        self.remove_button.clicked.connect(self._remove_selected_plugin)
        editor_side.addWidget(self.remove_button)

        self.open_button = QPushButton()
        self.open_button.clicked.connect(self._open_selected_plugin)
        editor_side.addWidget(self.open_button)
        editor_side.addStretch(1)
        editor_row.addLayout(editor_side)
        quick_layout.addLayout(editor_row)
        operational_row.addWidget(self.quick_access_card, 3)

        self.activity_card = QFrame()
        activity_layout = QVBoxLayout(self.activity_card)
        activity_layout.setContentsMargins(20, 20, 20, 20)
        activity_layout.setSpacing(14)
        self.activity_title = QLabel()
        activity_layout.addWidget(self.activity_title)
        activity_stack_host = QFrame()
        self.activity_stack = QVBoxLayout(activity_stack_host)
        self.activity_stack.setContentsMargins(0, 0, 0, 0)
        self.activity_stack.setSpacing(12)
        activity_layout.addWidget(activity_stack_host, 1)
        operational_row.addWidget(self.activity_card, 3)
        outer.addLayout(operational_row, 1)

        analytics_row = QHBoxLayout()
        analytics_row.setSpacing(14)

        self.top_tools_card = QFrame()
        top_tools_layout = QVBoxLayout(self.top_tools_card)
        top_tools_layout.setContentsMargins(18, 16, 18, 16)
        top_tools_layout.setSpacing(10)
        self.top_tools_title = QLabel()
        top_tools_layout.addWidget(self.top_tools_title)
        self.top_tools_chart.setRenderHint(QPainter.RenderHint.Antialiasing)
        top_tools_layout.addWidget(self.top_tools_chart)
        analytics_row.addWidget(self.top_tools_card, 2)

        self.status_card = QFrame()
        status_layout = QVBoxLayout(self.status_card)
        status_layout.setContentsMargins(18, 16, 18, 16)
        status_layout.setSpacing(10)
        self.status_title = QLabel()
        status_layout.addWidget(self.status_title)
        self.status_chart.setRenderHint(QPainter.RenderHint.Antialiasing)
        status_layout.addWidget(self.status_chart)
        analytics_row.addWidget(self.status_card, 1)

        outer.addLayout(analytics_row, 1)

    def _refresh(self) -> None:
        greeting, date_text = self._welcome_texts()
        self.hero_eyebrow.setText(self._pt("hero.eyebrow", "Welcome back"))
        self.hero_title.setText(greeting)
        self.hero_body.setText(date_text)
        self.quick_access_title.setText(self._pt("quick.title", "Quick launch"))
        self.add_button.setText(self._pt("quick.add", "Add shortcut"))
        self.remove_button.setText(self._pt("quick.remove", "Remove selected"))
        self.open_button.setText(self._pt("quick.open", "Open selected"))
        self.activity_title.setText(self._pt("activity.title", "Recent activity"))
        self.top_tools_title.setText(self._pt("chart.top_tools", "Most used tools"))
        self.status_title.setText(self._pt("chart.status", "Run outcomes"))
        self._render_hero_stats()
        self._render_charts()
        self._render_quick_access()
        self._render_recent_activity()
        self._apply_card_styles()

    def _handle_theme_change(self, _mode: str) -> None:
        self._refresh()

    def _handle_plugin_visuals_changed(self, _plugin_id: str) -> None:
        self._refresh()

    def _apply_card_styles(self) -> None:
        palette = self.services.theme_manager.current_palette()
        for frame in (
            self.hero_card,
            self.hero_side_panel,
            self.quick_access_card,
            self.activity_card,
            self.top_tools_card,
            self.status_card,
        ):
            if frame is not None:
                frame.setStyleSheet(card_style(palette, radius=16))
        self.hero_card.setStyleSheet(self._hero_card_style())
        if self.hero_side_panel is not None:
            self.hero_side_panel.setStyleSheet(
                card_style(palette, radius=16)
                + f"QFrame#DashboardHeroPanel {{ background: {palette.surface_bg}; }}"
            )
        eyebrow_color, title_color, body_color = self._hero_text_colors()
        self.hero_eyebrow.setStyleSheet(
            f"color: {eyebrow_color}; font-size: 12px; font-weight: 700; text-transform: uppercase;"
        )
        self.hero_title.setStyleSheet(f"color: {title_color}; font-size: 34px; font-weight: 800;")
        self.hero_body.setStyleSheet(f"color: {body_color}; font-size: 15px; font-weight: 500;")
        if self.quick_access_combo is not None:
            self.quick_access_combo.setStyleSheet(
                f"background: {palette.input_bg}; border: none; border-radius: 0px; color: {palette.text_primary};"
            )
        if self.quick_access_list is not None:
            self.quick_access_list.setStyleSheet(
                f"""
                QListWidget {{
                    background: {palette.input_bg};
                    border: none;
                    border-radius: 0px;
                    color: {palette.text_primary};
                }}
                QListWidget::item {{
                    border: none;
                    margin: 0;
                    padding: 8px 10px;
                }}
                QListWidget::item:selected {{
                    background: {palette.accent_soft};
                    color: {palette.text_primary};
                }}
                """
            )
        for label in (self.quick_access_title, self.activity_title, self.top_tools_title, self.status_title):
            label.setStyleSheet(section_title_style(palette, size=20))

    def _welcome_texts(self) -> tuple[str, str]:
        now = datetime.now()
        hour = now.hour
        if hour < 12:
            greeting = self._pt("hero.greeting.morning", "Good morning")
        elif hour < 18:
            greeting = self._pt("hero.greeting.afternoon", "Good afternoon")
        else:
            greeting = self._pt("hero.greeting.evening", "Good evening")
        date_text = now.strftime("%A, %B %d, %Y")
        return greeting, date_text

    def _hero_text_colors(self) -> tuple[str, str, str]:
        palette = self.services.theme_manager.current_palette()
        if palette.mode == "dark":
            return ("rgba(255, 255, 255, 0.82)", "#ffffff", "rgba(255, 255, 255, 0.90)")
        return ("rgba(20, 33, 49, 0.70)", "#142131", "rgba(20, 33, 49, 0.84)")

    def _render_hero_stats(self) -> None:
        while self.hero_stats_grid.count():
            item = self.hero_stats_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        summary = self.services.session_manager.get_summary(days=7)
        top_tools = summary.get("top_tools", [])
        top_tool_name = self._pt("hero.none", "No activity yet")
        if top_tools:
            top_tool_id = str(top_tools[0].get("tool_id", "")).strip()
            spec = self.services.plugin_manager.get_spec(top_tool_id)
            if spec is not None:
                top_tool_name = self.services.plugin_display_name(spec)
            elif top_tool_id:
                top_tool_name = top_tool_id
        available_plugins = len(self.services.manageable_plugin_specs())
        pinned_count = len(self.services.quick_access_ids())
        shortcut_count = len(self.services.shortcut_manager.list_bindings())
        workflow_count = len(self.services.workflow_manager.list_workflows())
        success_count = int((summary.get("status_counts") or {}).get("success", 0))
        stats = [
            (self._pt("hero.stat.available", "Available Plugins"), str(available_plugins)),
            (self._pt("hero.stat.pinned", "Pinned"), str(pinned_count)),
            (self._pt("hero.stat.shortcuts", "Shortcuts"), str(shortcut_count)),
            (self._pt("hero.stat.workflows", "Workflows"), str(workflow_count)),
            (self._pt("hero.stat.success", "Successful runs"), str(success_count)),
            (self._pt("hero.stat.most_used", "Most used tool"), top_tool_name),
        ]
        palette = self.services.theme_manager.current_palette()
        stat_bg = "rgba(255, 255, 255, 0.10)" if palette.mode == "dark" else "rgba(255, 255, 255, 0.42)"
        stat_value_color = "#ffffff" if palette.mode == "dark" else palette.text_primary
        stat_label_color = "rgba(255, 255, 255, 0.76)" if palette.mode == "dark" else "rgba(20, 33, 49, 0.64)"
        for index, (label, value) in enumerate(stats):
            card = QFrame()
            card.setStyleSheet(
                f"background: {stat_bg};"
                "border: none;"
                "border-radius: 12px;"
            )
            layout = QVBoxLayout(card)
            layout.setContentsMargins(14, 9, 14, 9)
            layout.setSpacing(4)
            value_label = QLabel(value)
            value_label.setWordWrap(True)
            value_label.setStyleSheet(
                f"color: {stat_value_color}; font-size: {'13px' if index == 5 else '15px'}; font-weight: 700;"
            )
            text_label = QLabel(label)
            text_label.setStyleSheet(f"color: {stat_label_color}; font-size: 11px; font-weight: 600;")
            layout.addWidget(value_label)
            layout.addWidget(text_label)
            self.hero_stats_grid.addWidget(card, index // 3, index % 3)

    def _render_charts(self) -> None:
        summary = self.services.session_manager.get_summary(days=7)
        self.top_tools_chart.setChart(self._build_top_tools_chart(summary.get("top_tools", [])))
        self.status_chart.setChart(self._build_status_chart(summary.get("status_counts", {})))

    def _build_top_tools_chart(self, rows) -> QChart:
        palette = self.services.theme_manager.current_palette()
        chart = QChart()
        chart.legend().hide()
        chart.setBackgroundVisible(False)
        chart.setPlotAreaBackgroundVisible(False)
        chart.setMargins(type(chart.margins())(0, 0, 0, 0))

        categories = []
        values = []
        for row in rows or []:
            spec = self.services.plugin_manager.get_spec(str(row.get("tool_id")))
            label = self.services.plugin_display_name(spec) if spec is not None else str(row.get("tool_id"))
            categories.append(label)
            values.append(int(row.get("count", 0)))

        if not categories:
            categories = [self._pt("chart.none", "No data yet")]
            values = [0]

        series = QBarSeries()
        bar_set = QBarSet(self._pt("chart.runs", "Runs"))
        bar_set.setColor(QColor(palette.accent))
        bar_set.append(values)
        series.append(bar_set)
        chart.addSeries(series)

        axis_x = QBarCategoryAxis()
        axis_x.append(categories)
        axis_x.setLabelsColor(QColor(palette.text_muted))
        chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        series.attachAxis(axis_x)

        axis_y = QValueAxis()
        axis_y.setLabelFormat("%d")
        axis_y.setRange(0, max(values + [1]))
        axis_y.setLabelsColor(QColor(palette.text_muted))
        grid_pen = axis_y.gridLinePen()
        grid_pen.setColor(QColor(palette.border))
        axis_y.setGridLinePen(grid_pen)
        chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(axis_y)
        return chart

    def _build_status_chart(self, status_counts) -> QChart:
        palette = self.services.theme_manager.current_palette()
        chart = QChart()
        chart.setBackgroundVisible(False)
        chart.legend().setVisible(True)
        chart.legend().setAlignment(Qt.AlignmentFlag.AlignBottom)
        chart.legend().setColor(QColor(palette.text_muted))

        series = QPieSeries()
        if not status_counts:
            slice_obj = series.append(self._pt("chart.none", "No data yet"), 1)
            slice_obj.setColor(QColor(palette.accent_soft))
        else:
            status_colors = {
                "success": QColor("#4caf7a"),
                "warning": QColor("#f0b84a"),
                "error": QColor(palette.danger),
                "failed": QColor(palette.danger),
            }
            for status, count in status_counts.items():
                slice_obj = series.append(str(status).title(), int(count))
                slice_obj.setColor(status_colors.get(str(status).lower(), QColor(palette.accent)))
        chart.addSeries(series)
        return chart

    def _render_quick_access(self) -> None:
        while self.quick_bar_layout.count():
            item = self.quick_bar_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        quick_ids = self.services.quick_access_ids()
        for plugin_id in quick_ids:
            spec = self.services.plugin_manager.get_spec(plugin_id)
            if spec is None:
                continue
            button = QToolButton()
            button.setText(self.services.plugin_display_name(spec))
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            button.setAutoRaise(False)
            button.clicked.connect(lambda _checked=False, pid=plugin_id: self._open_plugin(pid))
            self.quick_bar_layout.addWidget(button)
        self.quick_bar_layout.addStretch(1)

        self.quick_access_list.blockSignals(True)
        self.quick_access_list.clear()
        for plugin_id in quick_ids:
            spec = self.services.plugin_manager.get_spec(plugin_id)
            if spec is None:
                continue
            item = QListWidgetItem(self.services.plugin_display_name(spec))
            item.setData(Qt.ItemDataRole.UserRole, plugin_id)
            self.quick_access_list.addItem(item)
        self.quick_access_list.blockSignals(False)

        self.quick_access_combo.clear()
        pinned = set(quick_ids)
        for spec in self.services.pinnable_plugin_specs():
            if spec.plugin_id in pinned:
                continue
            self.quick_access_combo.addItem(self.services.plugin_display_name(spec), spec.plugin_id)

    def _render_recent_activity(self) -> None:
        while self.activity_stack.count():
            item = self.activity_stack.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        palette = self.services.theme_manager.current_palette()
        history = self.services.session_manager.get_history(limit=5)
        if not history:
            empty = QLabel(self._pt("activity.none", "No tool activity has been logged yet."))
            empty.setWordWrap(True)
            empty.setStyleSheet(muted_text_style(palette, size=14))
            self.activity_stack.addWidget(empty)
            self.activity_stack.addStretch(1)
            return

        for _id, tool_id, status, timestamp, details in history:
            spec = self.services.plugin_manager.get_spec(str(tool_id))
            title = self.services.plugin_display_name(spec) if spec is not None else str(tool_id)
            entry = QFrame()
            entry.setStyleSheet(card_style(palette, radius=14))
            layout = QVBoxLayout(entry)
            layout.setContentsMargins(16, 14, 16, 14)
            layout.setSpacing(6)

            top = QHBoxLayout()
            label = QLabel(title)
            label.setStyleSheet(section_title_style(palette, size=17))
            top.addWidget(label)
            top.addStretch(1)
            status_label = QLabel(str(status).title())
            status_label.setStyleSheet(self._status_badge_style(str(status)))
            top.addWidget(status_label)
            layout.addLayout(top)

            when = QLabel(self._format_timestamp(timestamp))
            when.setStyleSheet(muted_text_style(palette, size=12))
            layout.addWidget(when)

            if details:
                detail_label = QLabel(str(details))
                detail_label.setWordWrap(True)
                detail_label.setStyleSheet(muted_text_style(palette, size=13))
                layout.addWidget(detail_label)
            self.activity_stack.addWidget(entry)
        self.activity_stack.addStretch(1)

    def _status_badge_style(self, status: str) -> str:
        palette = self.services.theme_manager.current_palette()
        status_lower = status.lower()
        if status_lower == "success":
            background = "#d9f2e2" if palette.mode == "light" else "#1f4732"
            foreground = "#23633f" if palette.mode == "light" else "#9ee0b2"
        elif status_lower in {"failed", "error"}:
            background = "#f9dfdb" if palette.mode == "light" else "#4e2522"
            foreground = palette.danger
        else:
            background = palette.accent_soft
            foreground = palette.accent
        return (
            "padding: 4px 10px; border-radius: 999px; "
            f"background: {background}; color: {foreground}; font-size: 12px; font-weight: 700;"
        )

    def _persist_quick_access_from_list(self, *args) -> None:
        plugin_ids = []
        for row in range(self.quick_access_list.count()):
            item = self.quick_access_list.item(row)
            if item is not None:
                plugin_ids.append(str(item.data(Qt.ItemDataRole.UserRole)))
        self.services.set_quick_access_ids(plugin_ids)
        self._render_quick_access()

    def _add_selected_plugin(self) -> None:
        plugin_id = self.quick_access_combo.currentData()
        if not plugin_id:
            return
        updated = self.services.quick_access_ids() + [str(plugin_id)]
        self.services.set_quick_access_ids(updated)
        self._render_quick_access()

    def _remove_selected_plugin(self) -> None:
        item = self.quick_access_list.currentItem()
        if item is None:
            return
        plugin_id = str(item.data(Qt.ItemDataRole.UserRole))
        updated = [value for value in self.services.quick_access_ids() if value != plugin_id]
        self.services.set_quick_access_ids(updated)
        self._render_quick_access()

    def _open_selected_plugin(self) -> None:
        item = self.quick_access_list.currentItem()
        if item is None:
            return
        self._open_plugin(str(item.data(Qt.ItemDataRole.UserRole)))

    def _open_plugin(self, plugin_id: str) -> None:
        if self.services.main_window is not None:
            self.services.main_window.open_plugin(plugin_id)

    def _format_timestamp(self, timestamp) -> str:
        try:
            return datetime.fromtimestamp(float(timestamp)).strftime("%b %d, %Y · %H:%M")
        except Exception:
            return str(timestamp)

    def _hero_card_style(self) -> str:
        palette = self.services.theme_manager.current_palette()
        if palette.mode == "dark":
            gradient = "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #16233b, stop:0.55 #1d345b, stop:1 #274774)"
        else:
            gradient = "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #dff0ff, stop:0.55 #c9e5ff, stop:1 #b2d9ff)"
        return (
            "QFrame#DashboardWelcomeCard {"
            f"background: {gradient};"
            "border: none;"
            "border-radius: 16px;"
            "}"
        )
