from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


class ConfirmDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None,
        *,
        title: str,
        body: str,
        confirm_text: str = "Continue",
        cancel_text: str = "Cancel",
        option_text: str | None = None,
        option_checked: bool = False,
    ):
        super().__init__(
            None,
            Qt.WindowType.Window
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowSystemMenuHint
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowMinimizeButtonHint,
        )
        self._anchor = parent
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setModal(True)
        self.setWindowTitle(title)
        self.resize(500, 220)
        if parent is not None:
            self.setWindowIcon(parent.windowIcon())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)

        title_label = QLabel(title)
        title_label.setObjectName("ConfirmDialogTitle")
        layout.addWidget(title_label)

        body_label = QLabel(body)
        body_label.setObjectName("ConfirmDialogBody")
        body_label.setWordWrap(True)
        body_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(body_label, 1)

        actions = QHBoxLayout()
        self.option_checkbox: QCheckBox | None = None
        if option_text:
            self.option_checkbox = QCheckBox(option_text)
            self.option_checkbox.setChecked(option_checked)
            actions.addWidget(self.option_checkbox, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)

        actions.addStretch(1)

        cancel_button = QPushButton(cancel_text)
        cancel_button.clicked.connect(self.reject)
        actions.addWidget(cancel_button)

        confirm_button = QPushButton(confirm_text)
        confirm_button.setDefault(True)
        confirm_button.clicked.connect(self.accept)
        actions.addWidget(confirm_button)

        layout.addLayout(actions)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        parent = self._anchor
        if parent is not None:
            center = parent.frameGeometry().center()
            rect = self.frameGeometry()
            rect.moveCenter(center)
            self.move(rect.topLeft())

    def option_state(self) -> bool:
        return self.option_checkbox.isChecked() if self.option_checkbox is not None else False


def confirm_action(
    parent: QWidget | None,
    *,
    title: str,
    body: str,
    confirm_text: str = "Continue",
    cancel_text: str = "Cancel",
) -> bool:
    dialog = ConfirmDialog(
        parent,
        title=title,
        body=body,
        confirm_text=confirm_text,
        cancel_text=cancel_text,
    )
    return dialog.exec() == QDialog.DialogCode.Accepted


def confirm_action_with_option(
    parent: QWidget | None,
    *,
    title: str,
    body: str,
    confirm_text: str = "Continue",
    cancel_text: str = "Cancel",
    option_text: str,
    option_checked: bool = False,
) -> tuple[bool, bool]:
    dialog = ConfirmDialog(
        parent,
        title=title,
        body=body,
        confirm_text=confirm_text,
        cancel_text=cancel_text,
        option_text=option_text,
        option_checked=option_checked,
    )
    accepted = dialog.exec() == QDialog.DialogCode.Accepted
    return accepted, dialog.option_state()
