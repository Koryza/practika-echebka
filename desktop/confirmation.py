from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox, QWidget


def confirm_action(
    parent: QWidget,
    title: str,
    text: str,
    action: str,
    *,
    icon: QMessageBox.Icon = QMessageBox.Icon.Warning,
) -> bool:
    dialog = QMessageBox(icon, title, "", parent=parent)
    dialog.setTextFormat(Qt.TextFormat.PlainText)
    dialog.setText(text)
    action_button = dialog.addButton(action, QMessageBox.ButtonRole.DestructiveRole)
    cancel = dialog.addButton("Отмена", QMessageBox.ButtonRole.RejectRole)
    dialog.setDefaultButton(cancel)
    dialog.setEscapeButton(cancel)
    dialog.exec()
    return dialog.clickedButton() == action_button
