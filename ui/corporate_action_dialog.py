"""Corporate Action detection dialog."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QLabel, QListWidget, QVBoxLayout,
)

from ui.styles import WARNING_COLOR


class CorporateActionDialog(QDialog):
    """Alert dialog for detected corporate actions (>30% price change)."""

    def __init__(self, warnings: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚠️ Ações Corporativas Detectadas")
        self.setMinimumWidth(500)
        self.setMinimumHeight(300)

        layout = QVBoxLayout(self)

        header = QLabel(
            "As seguintes variações de preço superiores a 30% foram "
            "detectadas, o que pode indicar um Split ou Inplit:"
        )
        header.setWordWrap(True)
        header.setStyleSheet(
            f"font-size: 13px; color: {WARNING_COLOR}; font-weight: bold; "
            f"padding: 8px;"
        )
        layout.addWidget(header)

        self.list_widget = QListWidget()
        for w in warnings:
            self.list_widget.addItem(w)
        self.list_widget.setStyleSheet("font-size: 12px;")
        layout.addWidget(self.list_widget)

        info = QLabel(
            "Verifique se houve operação de Split ou Inplit e registre "
            "a transação correspondente para ajustar as posições."
        )
        info.setWordWrap(True)
        info.setStyleSheet("font-size: 11px; color: #666; padding: 4px;")
        layout.addWidget(info)

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok)
        btn_box.accepted.connect(self.accept)
        layout.addWidget(btn_box)
