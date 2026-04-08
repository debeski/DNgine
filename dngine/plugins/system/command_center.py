from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QBoxLayout,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSlider,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QStyle,
    QStyleOptionTabWidgetFrame,
    QScrollArea,
    )

from dngine.core.confirm_dialog import confirm_action
from dngine.core.icon_registry import icon_from_name
from dngine.core.page_style import apply_page_chrome, apply_semantic_class, muted_text_style, section_title_style
from dngine.core.plugin_api import bind_tr
from dngine.core.app_config import DEFAULT_CONFIG
from dngine.core.shell_registry import DASHBOARD_PLUGIN_ID, INSPECTOR_PLUGIN_ID
from dngine.core.widgets import PathLineEdit, ScrollSafeComboBox, ScrollSafeSlider, adaptive_columns, adaptive_grid_columns, visible_parent_width, width_breakpoint
from dngine.sdk import AdvancedPagePlugin


QComboBox = ScrollSafeComboBox


class CurrentTabSizeWidget(QTabWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.currentChanged.connect(self._refresh_geometry)

    def sizeHint(self):
        return self._tab_aware_size_hint(minimum=False)

    def minimumSizeHint(self):
        return self._tab_aware_size_hint(minimum=True)

    def _tab_aware_size_hint(self, *, minimum: bool):
        current = self.currentWidget()
        if current is None:
            return super().minimumSizeHint() if minimum else super().sizeHint()

        page_hint = current.minimumSizeHint() if minimum else current.sizeHint()
        tab_bar_hint = self.tabBar().sizeHint()

        option = QStyleOptionTabWidgetFrame()
        self.initStyleOption(option)
        frame_width = self.style().pixelMetric(QStyle.PixelMetric.PM_DefaultFrameWidth, option, self)
        width = max(page_hint.width(), tab_bar_hint.width()) + (frame_width * 2)
        height = page_hint.height() + tab_bar_hint.height() + (frame_width * 2)
        return QSize(width, height)

    def _refresh_geometry(self, _index: int) -> None:
        self.updateGeometry()
        current = self.currentWidget()
        if current is not None:
            current.updateGeometry()


class ThemeSwatchButton(QToolButton):
    def __init__(self, label: str, color_hex: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._color_hex = color_hex
        apply_semantic_class(self, "swatch_button_class")
        self.setCheckable(True)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.setIconSize(QSize(22, 22))
        self.setFixedSize(34, 34)
        self.setToolTip(label)
        self._refresh_icon()

    def _refresh_icon(self) -> None:
        pixmap = QPixmap(26, 26)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#ffffff"), 1.4))
        painter.setBrush(QColor(self._color_hex))
        painter.drawEllipse(3, 3, 20, 20)
        painter.end()
        self.setIcon(QIcon(pixmap))


class ChoiceChipButton(QToolButton):
    def __init__(self, label: str, parent: QWidget | None = None):
        super().__init__(parent)
        apply_semantic_class(self, "chip_button_class")
        self.setText(label)
        self.setCheckable(True)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.setMinimumHeight(32)


class QuickAccessPreviewTile(QFrame):
    clicked = Signal()

    def __init__(self, label: str, icon: QIcon, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("QuickAccessPreviewTile")
        self._hovered = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(112, 96)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)
        self.icon_label = QLabel()
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setPixmap(icon.pixmap(38, 38))
        layout.addWidget(self.icon_label)
        self.text_label = QLabel(label)
        self.text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.text_label.setWordWrap(True)
        layout.addWidget(self.text_label)

    def apply_palette(self, palette) -> None:
        background = palette.accent_soft if self._hovered else "transparent"
        border = palette.accent if self._hovered else "transparent"
        self.setStyleSheet(
            f"""
            QFrame#QuickAccessPreviewTile {{
                background: {background};
                border: 1px solid {border};
                border-radius: 18px;
            }}
            QLabel {{
                background: transparent;
                color: {palette.text_primary};
                font-size: 12px;
                font-weight: 600;
            }}
            """
        )

    def enterEvent(self, event) -> None:
        self._hovered = True
        page = self.parentWidget()
        while page is not None and not hasattr(page, "services"):
            page = page.parentWidget()
        services = getattr(page, "services", None)
        if services is not None:
            self.apply_palette(services.theme_manager.current_palette())
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        page = self.parentWidget()
        while page is not None and not hasattr(page, "services"):
            page = page.parentWidget()
        services = getattr(page, "services", None)
        if services is not None:
            self.apply_palette(services.theme_manager.current_palette())
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class ClickSlider(ScrollSafeSlider):
    interaction_started = Signal(int)
    interaction_finished = Signal(int)

    def __init__(self, orientation: Qt.Orientation, parent: QWidget | None = None):
        super().__init__(orientation, parent)
        self._mouse_interaction_active = False

    def mouse_interaction_active(self) -> bool:
        return self._mouse_interaction_active

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._mouse_interaction_active = True
            self.interaction_started.emit(self.value())
            self._set_value_from_event(event)
            event.accept()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._set_value_from_event(event)
            event.accept()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            self._mouse_interaction_active = False
            self.interaction_finished.emit(self.value())

    def _set_value_from_event(self, event) -> None:
        if self.orientation() == Qt.Orientation.Horizontal:
            span = max(1, self.width())
            position = max(0, min(span, int(event.position().x())))
        else:
            span = max(1, self.height())
            position = max(0, min(span, int(event.position().y())))
        value = QStyle.sliderValueFromPosition(
            self.minimum(),
            self.maximum(),
            position,
            span,
            upsideDown=(self.orientation() == Qt.Orientation.Vertical),
        )
        self.setValue(value)


class CommandCenterPlugin(AdvancedPagePlugin):
    plugin_id = "command_center"
    name = "Command Center"
    description = "Application settings for appearance, automation, shortcuts, and shell behavior."
    category = ""
    standalone = True
    translations = {
        "en": {
            "plugin.name": "Command Center",
            "plugin.description": "Application settings for appearance, automation, shortcuts, and shell behavior.",
        },
        "ar": {
            "plugin.name": "مركز الأوامر",
            "plugin.description": "إعدادات التطبيق للمظهر، والأتمتة، والاختصارات، وسلوك الواجهة.",
        },
    }

    def build_advanced_widget(self, services) -> QWidget:
        return CommandCenterPage(services)


class CommandCenterPage(QWidget):
    plugin_id = "command_center"

    def __init__(self, services):
        super().__init__()
        self.setObjectName("CommandCenterPage")
        self.services = services
        self.i18n = services.i18n
        self.shortcut_action_ids: list[str] = []
        self.tr = bind_tr(services, "command_center")
        self._suspend_live_updates = False
        self._building_shortcut_table = False
        self._density_interaction_start_value: int | None = None
        self._scaling_interaction_start_value: int | None = None
        self._responsive_bucket = ""
        self._quick_access_preview_columns = 0
        self._geometry_refresh_pending = False
        self._responsive_refresh_pending = False
        self._theme_preview_timer = QTimer(self)
        self._theme_preview_timer.setSingleShot(True)
        self._theme_preview_timer.timeout.connect(self._apply_pending_theme_preview)
        self._font_preview_timer = QTimer(self)
        self._font_preview_timer.setSingleShot(True)
        self._font_preview_timer.timeout.connect(self._apply_pending_font_preview)
        self._language_preview_timer = QTimer(self)
        self._language_preview_timer.setSingleShot(True)
        self._language_preview_timer.timeout.connect(self._apply_pending_language_preview)
        self._density_preview_timer = QTimer(self)
        self._density_preview_timer.setSingleShot(True)
        self._density_preview_timer.timeout.connect(self._apply_pending_density_preview)
        self._scaling_preview_timer = QTimer(self)
        self._scaling_preview_timer.setSingleShot(True)
        self._scaling_preview_timer.timeout.connect(self._apply_pending_scaling_preview)
        self._build_ui()
        self._populate_values()
        self._apply_texts()
        self.i18n.language_changed.connect(self._apply_texts)
        self.services.theme_manager.theme_changed.connect(self._handle_theme_change)
        self.services.quick_access_changed.connect(self._render_quick_access_settings)
        self.services.plugin_visuals_changed.connect(lambda _plugin_id: self._render_quick_access_settings())
        self.services.plugin_visuals_changed.connect(lambda _plugin_id: self._populate_startup_page_combo())
        self.services.clip_monitor_state_changed.connect(self._sync_clip_monitor_checkbox)

    def sizeHint(self):
        return self._page_size_hint(minimum=False)

    def minimumSizeHint(self):
        return self._page_size_hint(minimum=True)

    def _page_size_hint(self, *, minimum: bool):
        title_hint = self.title_label.minimumSizeHint() if minimum else self.title_label.sizeHint()
        description_hint = self.description_label.minimumSizeHint() if minimum else self.description_label.sizeHint()
        tabs_hint = self.tabs.minimumSizeHint() if minimum else self.tabs.sizeHint()
        margins = self.layout().contentsMargins() if self.layout() is not None else self.contentsMargins()
        spacing = self.layout().spacing() if self.layout() is not None else 0
        width = max(title_hint.width(), description_hint.width(), tabs_hint.width()) + margins.left() + margins.right()
        height = (
            margins.top()
            + title_hint.height()
            + spacing
            + description_hint.height()
            + spacing
            + tabs_hint.height()
            + margins.bottom()
        )
        return QSize(width, height)

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 28, 28, 28)
        outer.setSpacing(16)

        self.title_label = QLabel()
        outer.addWidget(self.title_label)

        self.description_label = QLabel()
        self._configure_note_label(self.description_label)
        outer.addWidget(self.description_label)

        self.tabs = CurrentTabSizeWidget()
        self.tabs.currentChanged.connect(self._handle_tab_changed)
        outer.addWidget(self.tabs, 1)

        self.general_tab = QWidget()
        self.quick_access_tab = QWidget()
        self.shortcuts_tab = QWidget()
        self.tabs.addTab(self.general_tab, "")
        self.tabs.addTab(self.quick_access_tab, "")
        self.tabs.addTab(self.shortcuts_tab, "")

        self._build_general_tab()
        self._build_quick_access_tab()
        self._build_shortcuts_tab()

    @staticmethod
    def _configure_section_title_label(label: QLabel) -> None:
        label.setWordWrap(False)
        label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

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

    def _build_general_tab(self) -> None:
        layout = QVBoxLayout(self.general_tab)
        layout.setContentsMargins(20, 20, 20, 10)
        layout.setSpacing(14)

        self.output_card = QFrame()
        output_layout = QVBoxLayout(self.output_card)
        output_layout.setContentsMargins(18, 16, 18, 16)
        output_layout.setSpacing(10)
        self.output_title = QLabel()
        self._configure_section_title_label(self.output_title)
        output_layout.addWidget(self.output_title)
        self.general_note = QLabel()
        self._configure_note_label(self.general_note)
        output_layout.addWidget(self.general_note)
        self.output_label = QLabel()
        self.startup_page_label = QLabel()
        output_form = QFormLayout()
        output_form.setContentsMargins(0, 4, 0, 0)
        output_form.setSpacing(12)

        row = QHBoxLayout()
        self.output_dir_input = PathLineEdit(mode="directory")
        row.addWidget(self.output_dir_input, 1)
        self.output_browse_button = QPushButton()
        self.output_browse_button.clicked.connect(self._browse_output_dir)
        row.addWidget(self.output_browse_button)
        self.output_dir_input.editingFinished.connect(self._commit_output_dir)
        output_form.addRow(self.output_label, row)

        self.startup_page_combo = QComboBox()
        self.startup_page_combo.currentIndexChanged.connect(self._handle_startup_page_changed)
        output_form.addRow(self.startup_page_label, self.startup_page_combo)
        output_layout.addLayout(output_form)
        layout.addWidget(self.output_card)

        self.appearance_card = QFrame()
        appearance_layout = QVBoxLayout(self.appearance_card)
        appearance_layout.setContentsMargins(18, 16, 18, 16)
        appearance_layout.setSpacing(10)
        self.appearance_title = QLabel()
        self._configure_section_title_label(self.appearance_title)
        appearance_layout.addWidget(self.appearance_title)
        self.appearance_note = QLabel()
        self._configure_note_label(self.appearance_note)
        appearance_layout.addWidget(self.appearance_note)
        form = QFormLayout()
        form.setContentsMargins(0, 4, 0, 0)
        form.setSpacing(12)
        self.theme_label = QLabel()
        self.font_label = QLabel()
        self.language_label = QLabel()
        self.density_label = QLabel()
        self.scaling_label = QLabel()

        self.theme_button_group = QButtonGroup(self)
        self.theme_button_group.setExclusive(True)
        self.theme_color_buttons: dict[str, ThemeSwatchButton] = {}
        theme_picker_host = QWidget()
        self.theme_picker_host = theme_picker_host
        theme_picker_layout = QHBoxLayout(theme_picker_host)
        theme_picker_layout.setContentsMargins(0, 0, 0, 0)
        theme_picker_layout.setSpacing(8)
        for color_key, label, preview in self.services.theme_manager.available_theme_colors():
            button = ThemeSwatchButton(label, preview, theme_picker_host)
            button.clicked.connect(self._handle_live_theme_change)
            self.theme_button_group.addButton(button)
            self.theme_color_buttons[color_key] = button
            theme_picker_layout.addWidget(button)
        self.dark_mode_checkbox = ChoiceChipButton("", theme_picker_host)
        self.dark_mode_checkbox.setObjectName("DarkModeToggle")
        apply_semantic_class(self.dark_mode_checkbox, "toggle_class")
        self.dark_mode_checkbox.toggled.connect(self._handle_live_theme_change)
        theme_picker_layout.addWidget(self.dark_mode_checkbox)
        theme_picker_layout.addStretch(1)
        form.addRow(self.theme_label, theme_picker_host)

        self.font_combo = QComboBox()
        self.font_combo.currentIndexChanged.connect(self._handle_live_font_change)
        form.addRow(self.font_label, self.font_combo)

        self.language_button_group = QButtonGroup(self)
        self.language_button_group.setExclusive(True)
        self.language_buttons: dict[str, ChoiceChipButton] = {}
        language_host = QWidget()
        self.language_host = language_host
        language_layout = QHBoxLayout(language_host)
        language_layout.setContentsMargins(0, 0, 0, 0)
        language_layout.setSpacing(8)
        for code, label in self.i18n.available_languages():
            button = ChoiceChipButton(label, language_host)
            button.clicked.connect(self._handle_live_language_change)
            self.language_button_group.addButton(button)
            self.language_buttons[code] = button
            language_layout.addWidget(button)
        language_layout.addStretch(1)
        form.addRow(self.language_label, language_host)

        density_host = QWidget()
        self.density_host = density_host
        density_layout = QHBoxLayout(density_host)
        density_layout.setContentsMargins(0, 0, 0, 0)
        density_layout.setSpacing(10)
        self.density_slider = ClickSlider(Qt.Orientation.Horizontal)
        self.density_slider.setRange(-3, 3)
        self.density_slider.setSingleStep(1)
        self.density_slider.setPageStep(1)
        self.density_slider.setTickInterval(1)
        self.density_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.density_slider.interaction_started.connect(self._remember_density_interaction_start)
        self.density_slider.valueChanged.connect(self._handle_live_density_change)
        self.density_slider.interaction_finished.connect(self._handle_density_released)
        density_layout.addWidget(self.density_slider, 1)
        self.density_value_label = QLabel("0")
        density_layout.addWidget(self.density_value_label)
        form.addRow(self.density_label, density_host)

        scaling_host = QWidget()
        self.scaling_host = scaling_host
        scaling_layout = QHBoxLayout(scaling_host)
        scaling_layout.setContentsMargins(0, 0, 0, 0)
        scaling_layout.setSpacing(10)
        self.scaling_slider = ClickSlider(Qt.Orientation.Horizontal)
        self.scaling_slider.setRange(85, 160)
        self.scaling_slider.setSingleStep(10)
        self.scaling_slider.setPageStep(10)
        self.scaling_slider.setTickInterval(10)
        self.scaling_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.scaling_slider.interaction_started.connect(self._remember_scaling_interaction_start)
        self.scaling_slider.valueChanged.connect(self._handle_live_scaling_change)
        self.scaling_slider.interaction_finished.connect(self._handle_scaling_released)
        scaling_layout.addWidget(self.scaling_slider, 1)
        self.scaling_value_label = QLabel("100%")
        scaling_layout.addWidget(self.scaling_value_label)
        form.addRow(self.scaling_label, scaling_host)
        appearance_layout.addLayout(form)

        layout.addWidget(self.appearance_card)

        self.general_tools_row = QHBoxLayout()
        self.general_tools_row.setContentsMargins(0, 0, 0, 0)
        self.general_tools_row.setSpacing(12)

        self.automation_card = QFrame()
        card_layout = QVBoxLayout(self.automation_card)
        card_layout.setContentsMargins(18, 16, 18, 16)
        card_layout.setSpacing(8)
        self.behavior_title = QLabel()
        self._configure_section_title_label(self.behavior_title)
        card_layout.addWidget(self.behavior_title)
        self.behavior_note = QLabel()
        self._configure_note_label(self.behavior_note)
        card_layout.addWidget(self.behavior_note)

        self.clip_monitor_checkbox = QCheckBox()
        self.clip_monitor_checkbox.toggled.connect(self._handle_clip_monitor_toggled)
        card_layout.addWidget(self.clip_monitor_checkbox)
        self.confirm_on_exit_checkbox = QCheckBox()
        self.confirm_on_exit_checkbox.toggled.connect(self._handle_confirm_on_exit_toggled)
        card_layout.addWidget(self.confirm_on_exit_checkbox)
        self.run_on_startup_checkbox = QCheckBox()
        self.run_on_startup_checkbox.toggled.connect(self._handle_run_on_startup_toggled)
        card_layout.addWidget(self.run_on_startup_checkbox)
        self.start_minimized_checkbox = QCheckBox()
        self.start_minimized_checkbox.toggled.connect(self._handle_start_minimized_toggled)
        card_layout.addWidget(self.start_minimized_checkbox)
        self.developer_mode_checkbox = QCheckBox()
        self.developer_mode_checkbox.toggled.connect(self._handle_developer_mode_toggled)
        card_layout.addWidget(self.developer_mode_checkbox)
        self.autostart_status_label = QLabel()
        self._configure_note_label(self.autostart_status_label)
        card_layout.addWidget(self.autostart_status_label)
        self.general_tools_row.addWidget(self.automation_card, 1)

        self.backup_card = QFrame()
        backup_layout = QVBoxLayout(self.backup_card)
        backup_layout.setContentsMargins(18, 16, 18, 16)
        backup_layout.setSpacing(8)
        self.backup_title = QLabel()
        self._configure_section_title_label(self.backup_title)
        backup_layout.addWidget(self.backup_title)
        self.backup_note = QLabel()
        self._configure_note_label(self.backup_note)
        backup_layout.addWidget(self.backup_note)
        self.backup_schedule_label = QLabel()
        self.backup_schedule_combo = QComboBox()
        self.backup_schedule_combo.addItem("Daily", "daily")
        self.backup_schedule_combo.addItem("Weekly", "weekly")
        self.backup_schedule_combo.addItem("Monthly", "monthly")
        self.backup_schedule_combo.currentIndexChanged.connect(self._handle_backup_schedule_changed)
        backup_schedule_row = QHBoxLayout()
        backup_schedule_row.setContentsMargins(0, 0, 0, 0)
        backup_schedule_row.setSpacing(8)
        backup_schedule_row.addWidget(self.backup_schedule_label)
        backup_schedule_row.addWidget(self.backup_schedule_combo, 1)
        backup_layout.addLayout(backup_schedule_row)
        self.backup_status_label = QLabel()
        self._configure_note_label(self.backup_status_label)
        backup_layout.addWidget(self.backup_status_label)
        backup_actions = QHBoxLayout()
        backup_actions.setContentsMargins(0, 0, 0, 0)
        backup_actions.setSpacing(8)
        self.create_backup_button = QPushButton()
        self.create_backup_button.clicked.connect(self._create_backup_now)
        backup_actions.addWidget(self.create_backup_button)
        self.restore_backup_button = QPushButton()
        self.restore_backup_button.clicked.connect(self._restore_backup_from_file)
        backup_actions.addWidget(self.restore_backup_button)
        backup_actions.addStretch(1)
        backup_layout.addLayout(backup_actions)
        self.general_tools_row.addWidget(self.backup_card, 1)

        layout.addLayout(self.general_tools_row)
        layout.addStretch(1)

        self.general_actions = QHBoxLayout()
        self.general_actions.addStretch(1)
        self.general_reset_button = QPushButton()
        self.general_reset_button.clicked.connect(self._reset_general_defaults)
        self.general_actions.addWidget(self.general_reset_button)
        layout.addLayout(self.general_actions)

    def _build_quick_access_tab(self) -> None:
        layout = QVBoxLayout(self.quick_access_tab)
        layout.setContentsMargins(20, 20, 20, 10)
        layout.setSpacing(14)

        self.quick_access_tab_note = QLabel()
        self._configure_note_label(self.quick_access_tab_note)
        layout.addWidget(self.quick_access_tab_note)

        self.quick_access_card = QFrame()
        quick_layout = QVBoxLayout(self.quick_access_card)
        quick_layout.setContentsMargins(18, 18, 18, 18)
        quick_layout.setSpacing(12)

        self.quick_access_title = QLabel()
        self._configure_section_title_label(self.quick_access_title)
        quick_layout.addWidget(self.quick_access_title)
        self.quick_access_note = QLabel()
        self._configure_note_label(self.quick_access_note)
        quick_layout.addWidget(self.quick_access_note)

        self.quick_access_preview_frame = QFrame()
        self.quick_access_preview_frame.setObjectName("QuickAccessPreview")
        apply_semantic_class(self.quick_access_preview_frame, "hero_card_class")
        self.quick_access_preview_layout = QGridLayout(self.quick_access_preview_frame)
        self.quick_access_preview_layout.setContentsMargins(0, 0, 0, 0)
        self.quick_access_preview_layout.setHorizontalSpacing(10)
        self.quick_access_preview_layout.setVerticalSpacing(10)
        quick_layout.addWidget(self.quick_access_preview_frame)

        self.quick_add_row = QHBoxLayout()
        self.quick_add_row.setContentsMargins(0, 0, 0, 0)
        self.quick_add_row.setSpacing(8)
        self.quick_access_combo = QComboBox()
        self.quick_add_row.addWidget(self.quick_access_combo, 1)
        self.quick_access_add_button = QPushButton()
        apply_semantic_class(self.quick_access_add_button, "button_class")
        self.quick_access_add_button.clicked.connect(self._add_selected_quick_access_plugin)
        self.quick_add_row.addWidget(self.quick_access_add_button)
        quick_layout.addLayout(self.quick_add_row)

        self.quick_manage_row = QHBoxLayout()
        self.quick_manage_row.setContentsMargins(0, 0, 0, 0)
        self.quick_manage_row.setSpacing(8)
        self.quick_access_list = QListWidget()
        self.quick_access_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.quick_access_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.quick_access_list.setMaximumHeight(230)
        self.quick_access_list.itemSelectionChanged.connect(self._sync_quick_access_buttons)
        self.quick_access_list.model().rowsMoved.connect(self._persist_quick_access_from_settings_list)
        self.quick_manage_row.addWidget(self.quick_access_list, 1)

        self.quick_actions_host = QWidget()
        apply_semantic_class(self.quick_actions_host, "transparent_class")
        self.quick_actions_layout = QGridLayout(self.quick_actions_host)
        self.quick_actions_layout.setContentsMargins(0, 0, 0, 0)
        self.quick_actions_layout.setHorizontalSpacing(6)
        self.quick_actions_layout.setVerticalSpacing(6)
        self.quick_access_move_up_button = QPushButton()
        apply_semantic_class(self.quick_access_move_up_button, "button_class")
        self.quick_access_move_up_button.clicked.connect(lambda: self._move_selected_quick_access(-1))
        self.quick_access_move_down_button = QPushButton()
        apply_semantic_class(self.quick_access_move_down_button, "button_class")
        self.quick_access_move_down_button.clicked.connect(lambda: self._move_selected_quick_access(1))
        self.quick_access_open_button = QPushButton()
        apply_semantic_class(self.quick_access_open_button, "button_class")
        self.quick_access_open_button.clicked.connect(self._open_selected_quick_access_plugin)
        self.quick_access_remove_button = QPushButton()
        apply_semantic_class(self.quick_access_remove_button, "button_class")
        self.quick_access_remove_button.clicked.connect(self._remove_selected_quick_access_plugin)
        self._quick_action_buttons = [
            self.quick_access_move_up_button,
            self.quick_access_move_down_button,
            self.quick_access_open_button,
            self.quick_access_remove_button,
        ]
        self.quick_manage_row.addWidget(self.quick_actions_host)
        quick_layout.addLayout(self.quick_manage_row)

        layout.addWidget(self.quick_access_card, 1)

    def _build_shortcuts_tab(self) -> None:
        layout = QVBoxLayout(self.shortcuts_tab)
        layout.setContentsMargins(20, 20, 20, 10)
        layout.setSpacing(14)

        self.shortcut_note = QLabel()
        self._configure_note_label(self.shortcut_note)
        layout.addWidget(self.shortcut_note)

        self.shortcut_status_label = QLabel()
        self._configure_note_label(self.shortcut_status_label)
        layout.addWidget(self.shortcut_status_label)

        self.shortcut_actions = QHBoxLayout()
        self.start_helper_button = QPushButton()
        self.start_helper_button.clicked.connect(self._start_hotkey_helper)
        self.shortcut_actions.addWidget(self.start_helper_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.stop_helper_button = QPushButton()
        self.stop_helper_button.clicked.connect(self._stop_hotkey_helper)
        self.shortcut_actions.addWidget(self.stop_helper_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.shortcut_actions.addStretch(1)
        layout.addLayout(self.shortcut_actions)

        self.shortcut_table = QTableWidget(0, 3)
        self.shortcut_table.setAlternatingRowColors(True)
        self.shortcut_table.verticalHeader().setVisible(False)
        self.shortcut_table.horizontalHeader().setStretchLastSection(True)
        self.shortcut_table.itemChanged.connect(self._handle_shortcut_item_changed)
        layout.addWidget(self.shortcut_table, 1)

        self.shortcuts_footer_actions = QHBoxLayout()
        self.shortcuts_footer_actions.addStretch(1)
        self.shortcuts_reset_button = QPushButton()
        self.shortcuts_reset_button.clicked.connect(self._reset_shortcut_defaults)
        self.shortcuts_footer_actions.addWidget(self.shortcuts_reset_button)
        layout.addLayout(self.shortcuts_footer_actions)

    def _populate_values(self) -> None:
        self._suspend_live_updates = True
        self.output_dir_input.setText(str(self.services.default_output_path()))
        self._sync_theme_picker()
        self._sync_font_picker()
        self._sync_language_picker()
        self.density_slider.setValue(self.services.theme_manager.current_density_scale())
        self.density_value_label.setText(str(self.density_slider.value()))
        scaling_value = int(round(float(self.services.theme_manager.current_ui_scaling()) * 100))
        self.scaling_slider.setValue(max(85, min(160, scaling_value)))
        self.scaling_value_label.setText(f"{self.scaling_slider.value()}%")
        self.clip_monitor_checkbox.setChecked(self.services.clip_monitor_enabled())
        self.confirm_on_exit_checkbox.setChecked(bool(self.services.config.get("confirm_on_exit")))
        self.run_on_startup_checkbox.setChecked(bool(self.services.autostart_manager.is_enabled()))
        self.start_minimized_checkbox.setChecked(bool(self.services.config.get("start_minimized")))
        self.developer_mode_checkbox.setChecked(self.services.developer_mode_enabled())
        self._set_combo_value(self.backup_schedule_combo, self.services.backup_manager.schedule())
        self._populate_startup_page_combo(str(self.services.config.get("default_start_plugin") or DASHBOARD_PLUGIN_ID))
        self._render_quick_access_settings()
        self._populate_shortcuts()
        self._refresh_autostart_status()
        self._refresh_shortcut_status()
        self._refresh_backup_status()
        self._suspend_live_updates = False
        self._apply_responsive_layout(force=True)

    def _selected_theme_color(self) -> str:
        for color_key, button in self.theme_color_buttons.items():
            if button.isChecked():
                return color_key
        return self.services.theme_manager.current_color_key()

    def _sync_theme_picker(self) -> None:
        current_color = self.services.theme_manager.current_color_key()
        for color_key, button in self.theme_color_buttons.items():
            button.blockSignals(True)
            button.setChecked(color_key == current_color)
            button.blockSignals(False)
        self.dark_mode_checkbox.blockSignals(True)
        self.dark_mode_checkbox.setChecked(self.services.theme_manager.is_dark_mode())
        self.dark_mode_checkbox.blockSignals(False)

    def _selected_font_family(self) -> str:
        return str(self.font_combo.currentData() or self.services.theme_manager.current_font_family())

    def _sync_font_picker(self) -> None:
        current_font = self.services.theme_manager.current_font_family()
        available_fonts = self.services.theme_manager.available_font_families()
        self.font_combo.blockSignals(True)
        self.font_combo.clear()
        for family, label in available_fonts:
            self.font_combo.addItem(label, family)
        self._set_combo_value(self.font_combo, current_font)
        if self.font_combo.currentIndex() < 0 and self.font_combo.count() > 0:
            self.font_combo.setCurrentIndex(0)
        self.font_combo.blockSignals(False)

    def _sync_language_picker(self) -> None:
        current_language = self.i18n.current_language()
        for code, button in self.language_buttons.items():
            button.blockSignals(True)
            button.setChecked(code == current_language)
            button.blockSignals(False)

    def _handle_live_theme_change(self) -> None:
        if self._suspend_live_updates:
            return
        self._schedule_theme_preview()

    def _handle_live_font_change(self) -> None:
        if self._suspend_live_updates:
            return
        self._schedule_font_preview()

    def _handle_live_language_change(self) -> None:
        if self._suspend_live_updates:
            return
        self._schedule_language_preview()

    def _remember_density_interaction_start(self, value: int) -> None:
        self._density_interaction_start_value = int(value)

    def _remember_scaling_interaction_start(self, value: int) -> None:
        self._scaling_interaction_start_value = int(value)

    def _handle_live_density_change(self, value: int) -> None:
        self.density_value_label.setText(str(value))
        if self._suspend_live_updates:
            return
        if self.density_slider.mouse_interaction_active():
            return
        if not self.density_slider.isSliderDown():
            self._schedule_density_preview()

    def _handle_live_scaling_change(self, value: int) -> None:
        self.scaling_value_label.setText(f"{value}%")
        if self._suspend_live_updates:
            return
        if self.scaling_slider.mouse_interaction_active():
            return
        if not self.scaling_slider.isSliderDown():
            self._schedule_scaling_preview()

    def _handle_density_released(self, _value: int) -> None:
        if self._suspend_live_updates:
            return
        start_value = self._density_interaction_start_value
        self._density_interaction_start_value = None
        if start_value is not None and int(self.density_slider.value()) == int(start_value):
            return
        self._schedule_density_preview()

    def _handle_scaling_released(self, _value: int) -> None:
        if self._suspend_live_updates:
            return
        start_value = self._scaling_interaction_start_value
        self._scaling_interaction_start_value = None
        if start_value is not None and int(self.scaling_slider.value()) == int(start_value):
            return
        self._schedule_scaling_preview()

    def _selected_language(self) -> str:
        for code, button in self.language_buttons.items():
            if button.isChecked():
                return code
        return self.i18n.current_language()

    def _render_quick_access_settings(self, preferred_plugin_id: str | None = None) -> None:
        if not hasattr(self, "quick_access_list"):
            return

        while self.quick_access_preview_layout.count():
            item = self.quick_access_preview_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

        palette = self.services.theme_manager.current_palette()
        quick_ids = self.services.quick_access_ids()
        preview_columns = self._quick_access_preview_column_count()
        self._quick_access_preview_columns = preview_columns
        preview_count = 0
        if quick_ids:
            for plugin_id in quick_ids:
                spec = self.services.plugin_manager.get_spec(plugin_id)
                if spec is None:
                    continue
                tile = QuickAccessPreviewTile(
                    self.services.plugin_display_name(spec),
                    self._quick_access_preview_icon(spec),
                    self.quick_access_preview_frame,
                )
                tile.setToolTip(spec.localized_description(self.i18n.current_language()))
                tile.clicked.connect(lambda _checked=False, pid=plugin_id: self._open_quick_access_plugin(pid))
                self.quick_access_preview_layout.addWidget(tile, preview_count // preview_columns, preview_count % preview_columns)
                preview_count += 1
        else:
            empty = QLabel(self.tr("quick_access.empty", "No quick access tools selected yet."))
            empty.setStyleSheet(muted_text_style(palette, size=13))
            self.quick_access_preview_layout.addWidget(empty, 0, 0, 1, preview_columns)
        if preview_count:
            for column in range(preview_columns):
                self.quick_access_preview_layout.setColumnStretch(column, 1)
            self.quick_access_preview_layout.setRowStretch((preview_count // preview_columns) + 1, 1)

        current_selection = preferred_plugin_id
        current_item = self.quick_access_list.currentItem()
        if current_selection is None and current_item is not None:
            current_selection = str(current_item.data(Qt.ItemDataRole.UserRole) or "")

        self.quick_access_list.blockSignals(True)
        self.quick_access_list.clear()
        selected_row = -1
        for row_index, plugin_id in enumerate(quick_ids):
            spec = self.services.plugin_manager.get_spec(plugin_id)
            if spec is None:
                continue
            item = QListWidgetItem(self.services.plugin_display_name(spec))
            item.setData(Qt.ItemDataRole.UserRole, plugin_id)
            self.quick_access_list.addItem(item)
            if plugin_id == current_selection:
                selected_row = row_index
        if self.quick_access_list.count():
            self.quick_access_list.setCurrentRow(selected_row if selected_row >= 0 else 0)
        self.quick_access_list.blockSignals(False)

        self.quick_access_combo.blockSignals(True)
        self.quick_access_combo.clear()
        pinned = set(quick_ids)
        for spec in self.services.pinnable_plugin_specs():
            if spec.plugin_id in pinned:
                continue
            self.quick_access_combo.addItem(self.services.plugin_display_name(spec), spec.plugin_id)
        self.quick_access_combo.blockSignals(False)
        self._sync_quick_access_buttons()

    def _quick_access_preview_column_count(self) -> int:
        available_width = min(
            visible_parent_width(self),
            self.quick_access_preview_frame.contentsRect().width()
            or self.quick_access_preview_frame.width()
            or self.quick_access_card.contentsRect().width()
            or self.quick_access_card.width()
            or self.width(),
        )
        spacing = self.quick_access_preview_layout.horizontalSpacing()
        required_for_four = (120 * 4) + (spacing * 3)
        return 4 if available_width >= required_for_four else 2

    def _refresh_quick_access_preview_layout(self) -> None:
        if not hasattr(self, "quick_access_preview_layout"):
            return
        target_columns = self._quick_access_preview_column_count()
        if target_columns == self._quick_access_preview_columns:
            return
        current_item = self.quick_access_list.currentItem() if hasattr(self, "quick_access_list") else None
        preferred_plugin_id = None
        if current_item is not None:
            preferred_plugin_id = str(current_item.data(Qt.ItemDataRole.UserRole) or "")
        self._render_quick_access_settings(preferred_plugin_id)

    def _sync_quick_access_buttons(self) -> None:
        current_row = self.quick_access_list.currentRow()
        count = self.quick_access_list.count()
        has_selection = current_row >= 0
        self.quick_access_add_button.setEnabled(self.quick_access_combo.count() > 0)
        self.quick_access_move_up_button.setEnabled(has_selection and current_row > 0)
        self.quick_access_move_down_button.setEnabled(has_selection and current_row >= 0 and current_row < count - 1)
        self.quick_access_open_button.setEnabled(has_selection)
        self.quick_access_remove_button.setEnabled(has_selection)
        self._apply_responsive_layout()

    def _persist_quick_access_from_settings_list(self, *_args) -> None:
        plugin_ids: list[str] = []
        selected_plugin_id = ""
        current_item = self.quick_access_list.currentItem()
        if current_item is not None:
            selected_plugin_id = str(current_item.data(Qt.ItemDataRole.UserRole) or "")
        for row in range(self.quick_access_list.count()):
            item = self.quick_access_list.item(row)
            if item is not None:
                plugin_ids.append(str(item.data(Qt.ItemDataRole.UserRole) or ""))
        self.services.set_quick_access_ids(plugin_ids)
        self._render_quick_access_settings(selected_plugin_id)

    def _add_selected_quick_access_plugin(self) -> None:
        plugin_id = str(self.quick_access_combo.currentData() or "").strip()
        if not plugin_id:
            return
        updated = self.services.quick_access_ids() + [plugin_id]
        self.services.set_quick_access_ids(updated)
        self._render_quick_access_settings(plugin_id)

    def _remove_selected_quick_access_plugin(self) -> None:
        item = self.quick_access_list.currentItem()
        if item is None:
            return
        plugin_id = str(item.data(Qt.ItemDataRole.UserRole) or "").strip()
        if not plugin_id:
            return
        updated = [value for value in self.services.quick_access_ids() if value != plugin_id]
        self.services.set_quick_access_ids(updated)
        self._render_quick_access_settings()

    def _move_selected_quick_access(self, step: int) -> None:
        item = self.quick_access_list.currentItem()
        if item is None:
            return
        plugin_id = str(item.data(Qt.ItemDataRole.UserRole) or "").strip()
        plugin_ids = self.services.quick_access_ids()
        if plugin_id not in plugin_ids:
            return
        current_index = plugin_ids.index(plugin_id)
        target_index = current_index + int(step)
        if target_index < 0 or target_index >= len(plugin_ids):
            return
        plugin_ids[current_index], plugin_ids[target_index] = plugin_ids[target_index], plugin_ids[current_index]
        self.services.set_quick_access_ids(plugin_ids)
        self._render_quick_access_settings(plugin_id)

    def _open_selected_quick_access_plugin(self) -> None:
        item = self.quick_access_list.currentItem()
        if item is None:
            return
        self._open_quick_access_plugin(str(item.data(Qt.ItemDataRole.UserRole) or ""))

    def _open_quick_access_plugin(self, plugin_id: str) -> None:
        if plugin_id and self.services.main_window is not None:
            self.services.main_window.open_plugin(plugin_id)

    def _quick_access_preview_icon(self, spec) -> QIcon:
        main_window = self.services.main_window
        icon_getter = getattr(main_window, "_plugin_icon", None)
        if callable(icon_getter):
            try:
                return icon_getter(spec)
            except Exception:
                pass
        override = self._sanitized_plugin_icon_override(spec)
        if override:
            icon = icon_from_name(override, self)
            if icon is not None:
                return icon
        preferred = icon_from_name(str(spec.preferred_icon or ""), self)
        if preferred is not None:
            return preferred
        fallback = icon_from_name("desktop", self) or icon_from_name("tools", self)
        if fallback is not None:
            return fallback
        return self.style().standardIcon(self.style().StandardPixmap.SP_FileIcon)

    def _sanitized_plugin_icon_override(self, spec) -> str:
        override = str(self.services.plugin_icon_override(spec) or "").strip()
        if not override:
            return ""
        if Path(override).exists():
            return override
        return override if icon_from_name(override, self) is not None else ""

    def _schedule_theme_preview(self) -> None:
        self._theme_preview_timer.start(120)

    def _schedule_font_preview(self) -> None:
        self._font_preview_timer.start(120)

    def _schedule_language_preview(self) -> None:
        self._language_preview_timer.start(120)

    def _schedule_density_preview(self) -> None:
        self._density_preview_timer.start(1000)

    def _schedule_scaling_preview(self) -> None:
        self._scaling_preview_timer.start(1000)

    def _apply_pending_theme_preview(self) -> None:
        self.services.set_theme_selection(self._selected_theme_color(), self.dark_mode_checkbox.isChecked())

    def _apply_pending_font_preview(self) -> None:
        self.services.set_ui_font_family(self._selected_font_family())

    def _apply_pending_language_preview(self) -> None:
        self.services.set_language(self._selected_language())

    def _apply_pending_density_preview(self) -> None:
        self.services.set_density_scale(int(self.density_slider.value()))

    def _apply_pending_scaling_preview(self) -> None:
        self.services.set_ui_scaling(self.scaling_slider.value() / 100.0)

    def _populate_shortcuts(self) -> None:
        bindings = self.services.shortcut_manager.list_bindings()
        self.shortcut_action_ids = [binding.action_id for binding in bindings]
        self._building_shortcut_table = True
        self.shortcut_table.setRowCount(len(bindings))
        self.shortcut_table.setHorizontalHeaderLabels(
            [
                self.tr("shortcuts.action", "Action"),
                self.tr("shortcuts.sequence", "Shortcut"),
                self.tr("shortcuts.scope", "Scope"),
            ]
        )
        scope_options = self.services.shortcut_manager.available_scopes()
        for row_index, binding in enumerate(bindings):
            title = self.tr(f"shortcut.action.{binding.action_id}", binding.title)
            title_item = QTableWidgetItem(title)
            title_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            self.shortcut_table.setItem(row_index, 0, title_item)
            self.shortcut_table.setItem(row_index, 1, QTableWidgetItem(binding.sequence or binding.default_sequence))

            combo = QComboBox()
            for scope_id, label in scope_options:
                combo.addItem(self.tr(f"shortcut.scope.{scope_id}", label), scope_id)
            self._set_combo_value(combo, binding.scope)
            combo.currentIndexChanged.connect(
                lambda _index, action_id=binding.action_id, widget=combo: self._handle_shortcut_scope_changed(action_id, widget)
            )
            self.shortcut_table.setCellWidget(row_index, 2, combo)
        self._building_shortcut_table = False
        self._refresh_shortcut_status()

    def _browse_output_dir(self) -> None:
        current = self.output_dir_input.text().strip() or str(self.services.default_output_path())
        selected = QFileDialog.getExistingDirectory(self, self.tr("output.browse", "Choose output folder"), current)
        if selected:
            self.output_dir_input.setText(selected)
            self._commit_output_dir()

    def _startup_page_specs(self):
        specs = []
        for spec in self.services.plugin_manager.sidebar_plugins():
            if spec.plugin_id == INSPECTOR_PLUGIN_ID:
                continue
            specs.append(spec)
        return specs

    def _populate_startup_page_combo(self, preferred_plugin_id: str | None = None) -> None:
        if not hasattr(self, "startup_page_combo"):
            return
        selected_plugin_id = preferred_plugin_id
        if selected_plugin_id is None:
            selected_plugin_id = str(self.startup_page_combo.currentData() or self.services.config.get("default_start_plugin") or DASHBOARD_PLUGIN_ID)

        self.startup_page_combo.blockSignals(True)
        self.startup_page_combo.clear()
        for spec in self._startup_page_specs():
            self.startup_page_combo.addItem(self.services.plugin_display_name(spec), spec.plugin_id)
        self.startup_page_combo.blockSignals(False)
        self._set_combo_value(self.startup_page_combo, selected_plugin_id)

    def _commit_output_dir(self) -> None:
        if self._suspend_live_updates:
            return
        previous = str(self.services.default_output_path())
        output_dir = Path(self.output_dir_input.text().strip() or previous)
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            self.output_dir_input.blockSignals(True)
            self.output_dir_input.setText(previous)
            self.output_dir_input.blockSignals(False)
            QMessageBox.warning(
                self,
                self.tr("output.invalid.title", "Output folder unavailable"),
                self.tr(
                    "output.invalid.body",
                    "The selected output folder could not be used:\n\n{error}",
                    error=str(exc),
                ),
            )
            return
        normalized = str(output_dir)
        if self.output_dir_input.text().strip() != normalized:
            self.output_dir_input.blockSignals(True)
            self.output_dir_input.setText(normalized)
            self.output_dir_input.blockSignals(False)
        self.services.config.set("default_output_path", normalized)

    def _handle_startup_page_changed(self, *_args) -> None:
        if self._suspend_live_updates:
            return
        self.services.config.set("default_start_plugin", str(self.startup_page_combo.currentData() or DASHBOARD_PLUGIN_ID))

    def _handle_backup_schedule_changed(self, *_args) -> None:
        if not self._suspend_live_updates:
            self.services.config.set("backup_schedule", str(self.backup_schedule_combo.currentData() or "monthly"))
        self._refresh_backup_status()

    def _handle_clip_monitor_toggled(self, checked: bool) -> None:
        if self._suspend_live_updates:
            return
        self.services.set_clip_monitor_enabled(bool(checked))
        self._refresh_autostart_status()

    def _sync_clip_monitor_checkbox(self, enabled: bool) -> None:
        desired = bool(enabled)
        if self.clip_monitor_checkbox.isChecked() == desired:
            return
        self.clip_monitor_checkbox.blockSignals(True)
        self.clip_monitor_checkbox.setChecked(desired)
        self.clip_monitor_checkbox.blockSignals(False)
        self._refresh_autostart_status()

    def _handle_confirm_on_exit_toggled(self, checked: bool) -> None:
        if self._suspend_live_updates:
            return
        self.services.config.set("confirm_on_exit", bool(checked))

    def _sync_autostart_preferences(self) -> None:
        desired_run = self.run_on_startup_checkbox.isChecked()
        desired_minimized = self.start_minimized_checkbox.isChecked()
        previous_run = bool(self.services.config.get("run_on_startup"))
        previous_minimized = bool(self.services.config.get("start_minimized"))
        try:
            self.services.set_startup_preferences(
                desired_run,
                start_minimized=desired_minimized,
            )
        except Exception as exc:
            self._suspend_live_updates = True
            self.run_on_startup_checkbox.setChecked(previous_run)
            self.start_minimized_checkbox.setChecked(previous_minimized)
            self._suspend_live_updates = False
            QMessageBox.warning(
                self,
                self.tr("startup.failed.title", "Startup preference unavailable"),
                self.tr(
                    "startup.failed.body",
                    "The startup preference could not be updated:\n\n{error}",
                    error=str(exc),
                ),
            )
            self._refresh_autostart_status()
            return
        self._refresh_autostart_status()

    def _handle_run_on_startup_toggled(self, _checked: bool) -> None:
        if self._suspend_live_updates:
            return
        self._sync_autostart_preferences()

    def _handle_start_minimized_toggled(self, _checked: bool) -> None:
        if self._suspend_live_updates:
            return
        self._sync_autostart_preferences()

    def _handle_developer_mode_toggled(self, checked: bool) -> None:
        if self._suspend_live_updates:
            return
        self.services.set_developer_mode(bool(checked))
        self._apply_responsive_layout(force=True)

    def _reset_general_defaults(self) -> None:
        if not self._confirm_risky(
            self.tr("confirm.reset_general.title", "Reset general settings?"),
            self.tr("confirm.reset_general.body", "This will reset appearance, language preview, tray behavior, startup behavior, and backup settings in this tab back to their defaults."),
        ):
            return
        defaults = DEFAULT_CONFIG
        self._suspend_live_updates = True
        self.output_dir_input.setText(str(self.services.output_root))
        target_color = str(defaults.get("material_color") or "pink")
        for color_key, button in self.theme_color_buttons.items():
            button.setChecked(color_key == target_color)
        self.dark_mode_checkbox.setChecked(bool(defaults.get("material_dark")))
        self._set_combo_value(self.font_combo, str(defaults.get("ui_font_family") or "Amiri"))
        target_language = str(defaults.get("language") or "en")
        for code, button in self.language_buttons.items():
            button.setChecked(code == target_language)
        self.density_slider.setValue(int(defaults.get("density_scale") or 0))
        self.scaling_slider.setValue(int(round(float(defaults.get("ui_scaling") or 1.0) * 100)))
        self.clip_monitor_checkbox.setChecked(bool(defaults.get("clip_monitor_enabled")))
        self.confirm_on_exit_checkbox.setChecked(bool(defaults.get("confirm_on_exit")))
        self.run_on_startup_checkbox.setChecked(bool(defaults.get("run_on_startup")))
        self.start_minimized_checkbox.setChecked(bool(defaults.get("start_minimized")))
        self.developer_mode_checkbox.setChecked(bool(defaults.get("developer_mode")))
        self._set_combo_value(self.backup_schedule_combo, defaults.get("backup_schedule", "monthly"))
        self._populate_startup_page_combo(str(defaults.get("default_start_plugin") or DASHBOARD_PLUGIN_ID))
        self._suspend_live_updates = False
        self.density_value_label.setText(str(self.density_slider.value()))
        self.scaling_value_label.setText(f"{self.scaling_slider.value()}%")
        self._commit_output_dir()
        self._handle_startup_page_changed()
        self._handle_backup_schedule_changed()
        self._handle_clip_monitor_toggled(self.clip_monitor_checkbox.isChecked())
        self._handle_confirm_on_exit_toggled(self.confirm_on_exit_checkbox.isChecked())
        self._handle_run_on_startup_toggled(self.run_on_startup_checkbox.isChecked())
        self._handle_start_minimized_toggled(self.start_minimized_checkbox.isChecked())
        self._handle_developer_mode_toggled(self.developer_mode_checkbox.isChecked())
        self._apply_pending_language_preview()
        self._apply_pending_theme_preview()
        self._apply_pending_font_preview()
        self._apply_pending_density_preview()
        self._apply_pending_scaling_preview()

    def _apply_shortcut_updates(self) -> None:
        shortcut_updates: dict[str, dict[str, str]] = {}
        for row_index, action_id in enumerate(self.shortcut_action_ids):
            sequence_item = self.shortcut_table.item(row_index, 1)
            combo = self.shortcut_table.cellWidget(row_index, 2)
            shortcut_updates[action_id] = {
                "sequence": sequence_item.text().strip() if sequence_item is not None else "",
                "scope": combo.currentData() if isinstance(combo, QComboBox) else "application",
            }
        self.services.shortcut_manager.update_bindings(shortcut_updates)
        self._refresh_shortcut_status()

    def _handle_shortcut_item_changed(self, item: QTableWidgetItem) -> None:
        if self._building_shortcut_table or item.column() != 1:
            return
        self._apply_shortcut_updates()

    def _handle_shortcut_scope_changed(self, _action_id: str, _combo: QComboBox) -> None:
        if self._building_shortcut_table:
            return
        self._apply_shortcut_updates()

    def _reset_shortcut_defaults(self) -> None:
        if not self._confirm_risky(
            self.tr("confirm.reset_shortcuts.title", "Reset shortcuts?"),
            self.tr("confirm.reset_shortcuts.body", "This will replace the current shortcut edits in this tab with the default shortcut bindings."),
        ):
            return
        bindings = self.services.shortcut_manager.list_bindings()
        scope_options = self.services.shortcut_manager.available_scopes()
        self._building_shortcut_table = True
        for row_index, binding in enumerate(bindings):
            self.shortcut_table.setItem(row_index, 1, QTableWidgetItem(binding.default_sequence))
            combo = self.shortcut_table.cellWidget(row_index, 2)
            if isinstance(combo, QComboBox):
                combo.clear()
                for scope_id, label in scope_options:
                    combo.addItem(label, scope_id)
                self._set_combo_value(combo, binding.default_scope)
        self._building_shortcut_table = False
        self._apply_shortcut_updates()

    def _create_backup_now(self) -> None:
        window = self.services.main_window
        if window is not None:
            window.begin_loading(self.tr("loading.backup", "Creating encrypted backup..."))
        try:
            backup_path = self.services.create_backup(reason="manual")
        except Exception as exc:
            if window is not None:
                window.end_loading()
            QMessageBox.critical(self, self.tr("backup.failed.title", "Backup failed"), str(exc))
            return
        if window is not None:
            window.end_loading()
        self._refresh_backup_status()
        QMessageBox.information(self, self.tr("backup.created.title", "Backup created"), self.tr("backup.created.body", "Encrypted backup written to {path}", path=str(backup_path)))

    def _restore_backup_from_file(self) -> None:
        start_dir = self.services.backup_manager.backups_root
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("backup.restore_dialog", "Restore encrypted backup"),
            str(start_dir),
            "DNgine Backup (*.mtkbak)",
        )
        if not file_path:
            return
        confirmed = confirm_action(
            self,
            title=self.tr("backup.restore_confirm.title", "Restore backup"),
            body=self.tr("backup.restore_confirm.body", "This will overwrite app data and may replace bundled files. Continue?"),
            confirm_text=self.tr("backup.restore", "Restore backup"),
            cancel_text=self.tr("confirm.cancel", "Cancel"),
        )
        if not confirmed:
            return
        window = self.services.main_window
        if window is not None:
            window.begin_loading(self.tr("loading.restore", "Restoring backup..."))
        try:
            self.services.restore_backup(Path(file_path))
        except Exception as exc:
            if window is not None:
                window.end_loading()
            QMessageBox.critical(self, self.tr("backup.failed.title", "Backup failed"), str(exc))
            return
        if window is not None:
            window.end_loading()
        self._refresh_backup_status()
        QMessageBox.information(self, self.tr("backup.restored.title", "Backup restored"), self.tr("backup.restored.body", "The backup was restored. Restart DNgine to ensure every file is reloaded cleanly."))

    def _refresh_backup_status(self) -> None:
        backups = self.services.backup_manager.list_backups()
        latest_raw = backups[0]["modified_at"] if backups else ""
        
        if latest_raw:
            # Wrap date in RTL marker if we are in an RTL layout to prevent flip issues with hyphens/colons
            latest = f"\u200f{latest_raw}" if self.services.i18n.is_rtl() else latest_raw
        else:
            latest = self.tr("backup.none", "No backups yet")
            
        schedule_key = str(self.backup_schedule_combo.currentData() or self.services.backup_manager.schedule()).lower()
        schedule_text = self.tr(f"backup.schedule.{schedule_key}", schedule_key.title())
        
        self.backup_status_label.setText(
            self.tr(
                "backup.status",
                "Schedule: {schedule}. Last backup: {latest}.",
                schedule=schedule_text,
                latest=latest,
            )
        )

    def _refresh_shortcut_status(self) -> None:
        shortcut_manager = self.services.shortcut_manager
        helper_manager = self.services.hotkey_helper_manager
        if shortcut_manager.direct_global_hotkeys_supported():
            self.shortcut_status_label.setText(
                self.tr(
                    "shortcuts.status.available",
                    "Global shortcut registration is available in this session.",
                )
            )
            self.start_helper_button.setVisible(False)
            self.stop_helper_button.setVisible(False)
            return

        if helper_manager.is_active():
            self.shortcut_status_label.setText(
                self.tr(
                    "shortcuts.status.helper_active",
                    "The elevated hotkey helper is active for this session. Global shortcuts will be routed through the helper process.",
                )
            )
            self.start_helper_button.setVisible(False)
            self.stop_helper_button.setVisible(True)
            self.stop_helper_button.setText(self.tr("shortcuts.stop_helper", "Stop Hotkey Helper"))
            return

        reason = helper_manager.helper_reason() or self.tr(
            "shortcuts.status.unavailable",
            "Global shortcuts are unavailable in this session.",
        )
        if helper_manager.can_request_helper():
            self.shortcut_status_label.setText(
                self.tr(
                    "shortcuts.status.helper_available",
                    "Global shortcuts are currently unavailable. {reason} Start the hotkey helper if you want global capture without elevating the main app.",
                    reason=reason,
                )
            )
            self.start_helper_button.setVisible(True)
            self.start_helper_button.setText(self.tr("shortcuts.start_helper", "Start Hotkey Helper"))
            self.stop_helper_button.setVisible(False)
            return

        self.shortcut_status_label.setText(
            self.tr(
                "shortcuts.status.no_helper",
                "Global shortcuts are currently unavailable. {reason}",
                reason=reason,
            )
        )
        self.start_helper_button.setVisible(False)
        self.stop_helper_button.setVisible(False)

    def _start_hotkey_helper(self) -> None:
        try:
            result = self.services.command_registry.execute("app.start_hotkey_helper")
        except Exception as exc:
            QMessageBox.warning(
                self,
                self.tr("shortcuts.helper_failed.title", "Helper unavailable"),
                str(exc),
            )
            return
        QMessageBox.information(
            self,
            self.tr("shortcuts.helper_started.title", "Helper started"),
            str(result.get("message", self.tr("shortcuts.helper_started.body", "The hotkey helper is now active for this session."))),
        )
        self._refresh_shortcut_status()

    def _stop_hotkey_helper(self) -> None:
        self.services.command_registry.execute("app.stop_hotkey_helper")
        self._refresh_shortcut_status()

    def _refresh_autostart_status(self) -> None:
        enabled = self.services.autostart_manager.is_enabled()
        key = "startup.enabled" if enabled else "startup.disabled"
        self.autostart_status_label.setText(self.tr(key, "Autostart is disabled."))

    def _apply_texts(self) -> None:
        self._apply_theme_styles()
        self.title_label.setText(self.tr("title", "Command Center"))
        self.description_label.setText(
            self.tr(
                "description",
                "Control appearance, language, startup behavior, tray behavior, and shortcuts from one place.",
            )
        )
        self.tabs.setTabText(0, self.tr("tab.general", "General"))
        self.tabs.setTabText(1, self.tr("tab.quick_access", "Quick Access"))
        self.tabs.setTabText(2, self.tr("tab.shortcuts", "Shortcuts"))

        self.output_label.setText(self.tr("output.label", "Default output folder"))
        self.startup_page_label.setText(self.tr("output.startup_page", "Default startup page"))
        self.output_browse_button.setText(self.tr("output.browse_button", "Browse"))
        self.output_title.setText(self.tr("general.output.title", "Workspace"))
        self.general_note.setText(self.tr("output.note", "Tools export into this folder by default, and the app can open straight to your preferred page on launch."))
        self._populate_startup_page_combo()

        self.appearance_title.setText(self.tr("general.appearance.title", "Appearance"))
        self.theme_label.setText(self.tr("theme.label", "Theme"))
        self.font_label.setText(self.tr("font.label", "UI font"))
        color_labels = {
            "pink": self.tr("theme.color.pink", "Pink"),
            "blue": self.tr("theme.color.blue", "Blue"),
            "orange": self.tr("theme.color.orange", "Orange"),
            "green": self.tr("theme.color.green", "Green"),
            "red": self.tr("theme.color.red", "Red"),
        }
        for color_key, button in self.theme_color_buttons.items():
            button.setToolTip(color_labels.get(color_key, color_key.title()))
        self.dark_mode_checkbox.setText(self.tr("theme.dark_mode", "Dark Mode"))
        self.language_label.setText(self.tr("language.label", "Language"))
        self.density_label.setText(self.tr("density.label", "Density"))
        self.scaling_label.setText(self.tr("scaling.label", "UI scaling"))
        for code, button in self.language_buttons.items():
            for language_code, label in self.i18n.available_languages():
                if code == language_code:
                    button.setText(label)
                    break
        self.appearance_note.setText(
            self.tr("appearance.note", "Appearance, font, and language changes apply immediately.")
        )

        self.behavior_title.setText(self.tr("general.behavior.title", "Behavior"))
        self.behavior_note.setText(
            self.tr(
                "general.behavior.note",
                "Tray handling, startup behavior, exit confirmation, and developer mode live together here so the app shell is easier to reason about.",
            )
        )
        self.clip_monitor_checkbox.setText(self.tr("clip_monitor.toggle", "Enable Clip-Monitor"))
        self.confirm_on_exit_checkbox.setText(self.tr("exit.confirm", "Always ask on exit"))
        self.run_on_startup_checkbox.setText(self.tr("startup.run", "Start on system login"))
        self.start_minimized_checkbox.setText(self.tr("startup.minimized", "Start minimized"))
        self.developer_mode_checkbox.setText(self.tr("developer.mode", "Developer mode"))
        self.backup_title.setText(self.tr("general.backup.title", "Backups"))
        self.backup_note.setText(
            self.tr(
                "general.backup.note",
                "Keep an encrypted safety trail of your workspace state, then restore from here when you need to roll back quickly.",
            )
        )
        self.backup_schedule_label.setText(self.tr("backup.schedule", "Backup intensity"))
        for index in range(self.backup_schedule_combo.count()):
            value = str(self.backup_schedule_combo.itemData(index) or "")
            text = {
                "daily": self.tr("backup.schedule.daily", "Daily"),
                "weekly": self.tr("backup.schedule.weekly", "Weekly"),
                "monthly": self.tr("backup.schedule.monthly", "Monthly"),
            }.get(value, value.title())
            self.backup_schedule_combo.setItemText(index, text)
        self.create_backup_button.setText(self.tr("backup.create", "Create backup"))
        self.restore_backup_button.setText(self.tr("backup.restore", "Restore backup"))
        self.quick_access_tab_note.setText(
            self.tr(
                "quick_access.tab_note",
                "Build a desktop-style quick launch strip for your most-used tools. Add tools, reorder them, and test the launcher here.",
            )
        )
        self.quick_access_title.setText(self.tr("quick_access.title", "Quick access"))
        self.quick_access_note.setText(
            self.tr(
                "quick_access.note",
                "These icons mirror the dashboard launcher. Drag the list to reorder, or use the move buttons for precise placement.",
            )
        )
        self.quick_access_add_button.setText(self.tr("quick_access.add", "Add"))
        self.quick_access_move_up_button.setText(self.tr("quick_access.move_up", "Move up"))
        self.quick_access_move_down_button.setText(self.tr("quick_access.move_down", "Move down"))
        self.quick_access_open_button.setText(self.tr("quick_access.open", "Open"))
        self.quick_access_remove_button.setText(self.tr("quick_access.remove", "Remove"))

        self.shortcut_note.setText(
            self.tr(
                "shortcuts.note",
                "Application shortcuts are always available while the app is focused. Global shortcuts are optional, may depend on desktop permissions, and shortcut edits apply immediately.",
            )
        )
        self.general_reset_button.setText(self.tr("reset", "Reset defaults"))
        self.shortcuts_reset_button.setText(self.tr("shortcuts.reset", "Reset shortcuts"))
        self._populate_shortcuts()
        self._refresh_autostart_status()
        self._refresh_backup_status()
        self._render_quick_access_settings()
        self._apply_responsive_layout(force=True)

    def _set_combo_value(self, combo: QComboBox, value) -> None:
        for index in range(combo.count()):
            if combo.itemData(index) == value:
                combo.setCurrentIndex(index)
                return

    def _handle_tab_changed(self, index: int) -> None:
        self._schedule_responsive_refresh()
        self._schedule_page_geometry_refresh()
        window = self.services.main_window
        if window is not None and getattr(window, "current_plugin_id", None) == self.plugin_id:
            sync = getattr(window, "_sync_system_toolbar_selection", None)
            if callable(sync):
                sync(self.plugin_id)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_responsive_layout()
        self._schedule_responsive_refresh()
        self._schedule_page_geometry_refresh()

    def _refresh_page_geometry(self) -> None:
        self._geometry_refresh_pending = False
        self.tabs.updateGeometry()
        self.updateGeometry()
        target_height = self.sizeHint().height()
        self.setMinimumHeight(target_height)
        self.setMaximumHeight(target_height)
        if self.height() != target_height:
            self.resize(self.width(), target_height)
        parent = self.parentWidget()
        while parent is not None:
            if isinstance(parent, QScrollArea):
                widget = parent.widget()
                if widget is not None:
                    widget.updateGeometry()
                parent.updateGeometry()
                break
            parent = parent.parentWidget()

    def _schedule_page_geometry_refresh(self) -> None:
        if self._geometry_refresh_pending:
            return
        self._geometry_refresh_pending = True
        QTimer.singleShot(0, self._refresh_page_geometry)

    def _schedule_responsive_refresh(self) -> None:
        if self._responsive_refresh_pending:
            return
        self._responsive_refresh_pending = True
        QTimer.singleShot(0, self._run_responsive_refresh)

    def _run_responsive_refresh(self) -> None:
        self._responsive_refresh_pending = False
        self._apply_responsive_layout()

    def _apply_responsive_layout(self, *, force: bool = False) -> None:
        bucket = width_breakpoint(self.width(), compact_max=760, medium_max=1180)
        structure_changed = force or bucket != self._responsive_bucket
        self._responsive_bucket = bucket
        compact = bucket == "compact"

        if structure_changed:
            self.general_tools_row.setDirection(
                QBoxLayout.Direction.TopToBottom if compact else QBoxLayout.Direction.LeftToRight
            )
            self.quick_add_row.setDirection(
                QBoxLayout.Direction.TopToBottom if compact else QBoxLayout.Direction.LeftToRight
            )
            self.quick_manage_row.setDirection(
                QBoxLayout.Direction.TopToBottom if compact else QBoxLayout.Direction.LeftToRight
            )
            self.shortcut_actions.setDirection(
                QBoxLayout.Direction.TopToBottom if compact else QBoxLayout.Direction.LeftToRight
            )

        while self.quick_actions_layout.count():
            item = self.quick_actions_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(self.quick_actions_host)
        quick_columns = adaptive_grid_columns(
            min(
                visible_parent_width(self),
                self.quick_actions_host.contentsRect().width()
                or self.quick_actions_host.width()
                or self.quick_access_card.contentsRect().width()
                or self.quick_access_card.width(),
            ),
            item_widths=[button.sizeHint().width() for button in self._quick_action_buttons],
            spacing=self.quick_actions_layout.horizontalSpacing(),
            min_columns=2,
        )
        for index, button in enumerate(self._quick_action_buttons):
            self.quick_actions_layout.addWidget(button, index // quick_columns, index % quick_columns)
        for column in range(quick_columns):
            self.quick_actions_layout.setColumnStretch(column, 1)
        self._refresh_quick_access_preview_layout()

    def current_section_id(self) -> str:
        current = self.tabs.currentWidget()
        if current is self.quick_access_tab:
            return "quick_access"
        if current is self.shortcuts_tab:
            return "shortcuts"
        return "general"

    def open_quick_access_tab(self) -> None:
        self.tabs.setCurrentWidget(self.quick_access_tab)

    def open_shortcuts_tab(self) -> None:
        self.tabs.setCurrentWidget(self.shortcuts_tab)

    def open_general_tab(self) -> None:
        self.tabs.setCurrentWidget(self.general_tab)

    def _handle_theme_change(self, _mode: str) -> None:
        self._apply_theme_styles()
        self._sync_theme_picker()
        self._sync_font_picker()

    def _apply_theme_styles(self) -> None:
        palette = self.services.theme_manager.current_palette()
        self.setStyleSheet(
            f"""
            QWidget#CommandCenterPage {{
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
        for widget in (
            self.general_tab,
            self.quick_access_tab,
            self.shortcuts_tab,
            self.theme_picker_host,
            self.language_host,
            self.density_host,
            self.scaling_host,
        ):
            apply_semantic_class(widget, "transparent_class")
        self.tabs.setStyleSheet("")
        apply_page_chrome(
            palette,
            title_label=self.title_label,
            description_label=self.description_label,
            cards=(
                self.output_card,
                self.appearance_card,
                self.automation_card,
                self.backup_card,
                self.quick_access_card,
            ),
            title_size=26,
            title_weight=700,
        )
        for label in (
            self.general_note,
            self.appearance_note,
            self.autostart_status_label,
            self.quick_access_tab_note,
            self.quick_access_note,
            self.shortcut_note,
            self.shortcut_status_label,
            self.behavior_note,
            self.backup_note,
        ):
            if label is not None:
                label.setStyleSheet(muted_text_style(palette))
        for label in (
            self.output_title,
            self.appearance_title,
            self.behavior_title,
            self.backup_title,
        ):
            label.setStyleSheet(section_title_style(palette, size=18))
        self.quick_access_title.setStyleSheet(section_title_style(palette, size=18))
        self.quick_access_preview_frame.setStyleSheet("")
        for tile in self.quick_access_preview_frame.findChildren(QuickAccessPreviewTile):
            tile.apply_palette(palette)
        for button in (
            self.dark_mode_checkbox,
            *self.theme_color_buttons.values(),
            *self.language_buttons.values(),
        ):
            button.setStyleSheet("")
        for slider in (self.density_slider, self.scaling_slider):
            slider.setStyleSheet("")
