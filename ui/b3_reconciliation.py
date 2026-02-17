"""Reconciliação B3 — CSV import preview and confirmation."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QGroupBox,
    QHBoxLayout, QHeaderView, QLabel, QPushButton, QTableView,
    QVBoxLayout, QWidget, QMessageBox,
)

from domain.entities import Transaction
from ui.table_models import TransactionTableModel


class B3ReconciliationWidget(QWidget):
    """CSV import wizard: pick file → preview → confirm → persist."""

    import_confirmed = Signal(list)  # emits list[Transaction]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._preview_data: list[Transaction] = []
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        title = QLabel("Reconciliação B3 — Importação CSV")
        title.setStyleSheet("font-size: 18px; font-weight: bold; padding: 4px;")
        layout.addWidget(title)

        # File picker row
        file_row = QHBoxLayout()
        self.btn_pick = QPushButton("📂 Selecionar Arquivo CSV")
        self.btn_pick.setObjectName("primaryBtn")
        self.btn_pick.clicked.connect(self._pick_file)
        file_row.addWidget(self.btn_pick)

        self.lbl_file = QLabel("Nenhum arquivo selecionado")
        self.lbl_file.setStyleSheet("color: #666; font-style: italic;")
        file_row.addWidget(self.lbl_file, 1)
        layout.addLayout(file_row)

        # Preview info
        self.lbl_count = QLabel("")
        self.lbl_count.setStyleSheet("font-weight: bold; font-size: 13px;")
        layout.addWidget(self.lbl_count)

        # Preview table
        group = QGroupBox("Preview das Transações")
        g_layout = QVBoxLayout(group)
        self.table = QTableView()
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setSelectionMode(QTableView.MultiSelection)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self._model = TransactionTableModel()
        self.table.setModel(self._model)
        g_layout.addWidget(self.table)
        layout.addWidget(group)

        # Action buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self.btn_select_all = QPushButton("Selecionar Todos")
        self.btn_select_all.clicked.connect(self._select_all)
        btn_row.addWidget(self.btn_select_all)

        self.btn_deselect = QPushButton("Limpar Seleção")
        self.btn_deselect.clicked.connect(self._deselect_all)
        btn_row.addWidget(self.btn_deselect)

        self.btn_confirm = QPushButton("✅ Confirmar Importação")
        self.btn_confirm.setObjectName("primaryBtn")
        self.btn_confirm.setEnabled(False)
        self.btn_confirm.clicked.connect(self._confirm)
        btn_row.addWidget(self.btn_confirm)

        layout.addLayout(btn_row)

    def set_parse_function(self, fn) -> None:
        """Set the function used to parse CSV files (from use case)."""
        self._parse_fn = fn

    def _pick_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Selecionar CSV B3", "",
            "CSV Files (*.csv);;All Files (*)"
        )
        if not path:
            return
        self.lbl_file.setText(path)
        try:
            self._preview_data = self._parse_fn(path)
            self._model.set_data(self._preview_data)
            self.lbl_count.setText(
                f"{len(self._preview_data)} transação(ões) encontrada(s)"
            )
            self.btn_confirm.setEnabled(len(self._preview_data) > 0)
            self._select_all()
        except Exception as e:
            QMessageBox.critical(self, "Erro ao ler CSV", str(e))

    def _select_all(self) -> None:
        self.table.selectAll()

    def _deselect_all(self) -> None:
        self.table.clearSelection()

    def _confirm(self) -> None:
        selected_rows = set(idx.row() for idx in self.table.selectedIndexes())
        if not selected_rows:
            QMessageBox.information(self, "Aviso", "Selecione ao menos uma transação.")
            return
        confirmed = [
            self._preview_data[r] for r in sorted(selected_rows)
            if r < len(self._preview_data)
        ]
        reply = QMessageBox.question(
            self, "Confirmar Importação",
            f"Importar {len(confirmed)} transação(ões)?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.import_confirmed.emit(confirmed)

    _parse_fn = None
