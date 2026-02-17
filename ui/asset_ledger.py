"""Razão Auxiliar de Ativos — full transaction ledger filtered by ticker."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Optional

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QHBoxLayout, QHeaderView, QLabel,
    QMessageBox, QPushButton, QTableView, QVBoxLayout, QWidget,
)

from babel.numbers import format_currency

from domain.entities import Transaction
from domain.enums import Currency, TransactionType
from domain.value_objects import round_monetary, round_qty
from ui.styles import PROFIT_COLOR, LOSS_COLOR
from reports.report_export import export_csv, export_pdf


ZERO = Decimal("0")


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _fmt_brl(value) -> str:
    try:
        return format_currency(float(value), "BRL", locale="pt_BR")
    except Exception:
        return f"R$ {float(value):,.2f}"


def _fmt_money(value: Decimal, currency: Currency) -> str:
    locale = "pt_BR" if currency == Currency.BRL else "en_US"
    curr = "BRL" if currency == Currency.BRL else "USD"
    try:
        return format_currency(float(value), curr, locale=locale)
    except Exception:
        return f"{curr} {value:,.2f}"


def _fmt_qty(value: Decimal) -> str:
    v = float(value)
    if v == int(v):
        return f"{int(v):,}".replace(",", ".")
    return f"{v:,.8f}".rstrip("0").rstrip(".")


# ═══════════════════════════════════════════════════════════════════════════
# Row data: transaction + computed running values
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class _LedgerRow:
    tx: Transaction
    running_qty: Decimal        # saldo de quantidade
    running_avg: Decimal        # preço médio corrente
    realized_gain: Decimal | None  # resultado apurado (só em vendas)


# ═══════════════════════════════════════════════════════════════════════════
# LedgerTableModel
# ═══════════════════════════════════════════════════════════════════════════

class LedgerTableModel(QAbstractTableModel):
    """Transaction table model with extra running-balance columns."""

    HEADERS = [
        "Data", "Ticker", "Tipo", "DT/ST", "Qtd", "Preço",
        "Total", "Saldo Qtd", "Preço Médio", "Resultado",
        "Moeda", "FX", "Instituição", "Notas",
    ]

    _COL_DATE = 0
    _COL_TICKER = 1
    _COL_TIPO = 2
    _COL_DS = 3
    _COL_QTD = 4
    _COL_PRECO = 5
    _COL_TOTAL = 6
    _COL_SALDO = 7
    _COL_PM = 8
    _COL_RESULT = 9
    _COL_MOEDA = 10
    _COL_FX = 11
    _COL_INST = 12
    _COL_NOTAS = 13

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: list[_LedgerRow] = []

    def set_data(self, transactions: list[Transaction]) -> None:
        self.beginResetModel()
        self._rows = self._compute_rows(transactions)
        self.endResetModel()

    @property
    def final_qty(self) -> Decimal:
        return self._rows[-1].running_qty if self._rows else ZERO

    @property
    def final_avg(self) -> Decimal:
        return self._rows[-1].running_avg if self._rows else ZERO

    @property
    def final_cost(self) -> Decimal:
        if not self._rows:
            return ZERO
        r = self._rows[-1]
        return round_monetary(r.running_qty * r.running_avg) if r.running_qty > ZERO else ZERO

    # ── computation ────────────────────────────────────────────────────

    @staticmethod
    def _compute_rows(transactions: list[Transaction]) -> list[_LedgerRow]:
        rows: list[_LedgerRow] = []
        qty = ZERO
        total_cost = ZERO
        avg_price = ZERO

        for tx in transactions:
            realized: Decimal | None = None

            if tx.type == TransactionType.BUY:
                cost = round_monetary(tx.quantity * tx.price)
                total_cost = round_monetary(total_cost + cost)
                qty = round_qty(qty + tx.quantity)
                avg_price = round_monetary(total_cost / qty) if qty > ZERO else ZERO

            elif tx.type == TransactionType.SELL:
                cost_of_sold = round_monetary(tx.quantity * avg_price)
                proceeds = round_monetary(tx.quantity * tx.price)
                realized = round_monetary(proceeds - cost_of_sold)
                total_cost = round_monetary(total_cost - cost_of_sold)
                qty = round_qty(qty - tx.quantity)
                if qty <= ZERO:
                    qty = ZERO
                    total_cost = ZERO
                    avg_price = ZERO

            elif tx.type == TransactionType.SPLIT:
                factor = tx.quantity
                if factor > ZERO and qty > ZERO:
                    qty = round_qty(qty * factor)
                    avg_price = round_monetary(total_cost / qty) if qty > ZERO else ZERO

            elif tx.type == TransactionType.INPLIT:
                factor = tx.quantity
                if factor > ZERO and qty > ZERO:
                    qty = round_qty(qty / factor)
                    avg_price = round_monetary(total_cost / qty) if qty > ZERO else ZERO

            elif tx.type == TransactionType.BONUS:
                qty = round_qty(qty + tx.quantity)
                avg_price = round_monetary(total_cost / qty) if qty > ZERO else ZERO

            rows.append(_LedgerRow(
                tx=tx,
                running_qty=qty,
                running_avg=avg_price,
                realized_gain=realized,
            ))
        return rows

    # ── Qt model interface ─────────────────────────────────────────────

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._rows)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            if section < len(self.HEADERS):
                return self.HEADERS[section]
        return None

    def data(self, index: QModelIndex, role=Qt.DisplayRole) -> Any:
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        col = index.column()

        if role == Qt.DisplayRole:
            return self._display(row, col)

        if role == Qt.ForegroundRole:
            return self._foreground(row, col)

        if role == Qt.FontRole:
            # Bold the 3 new columns for emphasis
            if col in (self._COL_SALDO, self._COL_PM, self._COL_RESULT):
                font = QFont()
                font.setBold(True)
                return font
            return None

        if role == Qt.TextAlignmentRole:
            if col >= self._COL_QTD:
                return Qt.AlignRight | Qt.AlignVCenter
        return None

    def _display(self, row: _LedgerRow, col: int) -> str:
        tx = row.tx
        cur = tx.currency
        if col == self._COL_DATE:
            return tx.date.strftime("%d/%m/%Y")
        if col == self._COL_TICKER:
            return tx.ticker
        if col == self._COL_TIPO:
            return tx.type.value
        if col == self._COL_DS:
            return "DT" if tx.trade_type.value == "DAY_TRADE" else "ST"
        if col == self._COL_QTD:
            return _fmt_qty(tx.quantity)
        if col == self._COL_PRECO:
            return _fmt_money(tx.price, cur)
        if col == self._COL_TOTAL:
            return _fmt_money(tx.total_value, cur)
        if col == self._COL_SALDO:
            return _fmt_qty(row.running_qty)
        if col == self._COL_PM:
            return _fmt_money(row.running_avg, cur)
        if col == self._COL_RESULT:
            if row.realized_gain is not None:
                return _fmt_money(row.realized_gain, cur)
            return "—"
        if col == self._COL_MOEDA:
            return cur.value
        if col == self._COL_FX:
            return str(tx.fx_rate) if cur == Currency.USD else "—"
        if col == self._COL_INST:
            return tx.institution
        if col == self._COL_NOTAS:
            return "📝" if tx.notes and tx.notes.strip() else ""
        return ""

    @staticmethod
    def _foreground(row: _LedgerRow, col: int) -> Optional[QColor]:
        if col == LedgerTableModel._COL_TIPO:
            if row.tx.type == TransactionType.BUY:
                return QColor(PROFIT_COLOR)
            if row.tx.type == TransactionType.SELL:
                return QColor(LOSS_COLOR)
        if col == LedgerTableModel._COL_RESULT:
            if row.realized_gain is not None:
                if row.realized_gain > ZERO:
                    return QColor(PROFIT_COLOR)
                if row.realized_gain < ZERO:
                    return QColor(LOSS_COLOR)
        return None


# ═══════════════════════════════════════════════════════════════════════════
# AssetLedgerWidget
# ═══════════════════════════════════════════════════════════════════════════

class AssetLedgerWidget(QWidget):
    """Widget showing full transaction history for a specific ticker,
    with running average-price and balance columns."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._all_transactions: list[Transaction] = []
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        title = QLabel("Razão Auxiliar de Ativos")
        title.setStyleSheet("font-size: 18px; font-weight: bold; padding: 4px;")

        header = QHBoxLayout()
        header.addWidget(title)
        header.addStretch()

        btn_pdf = QPushButton("📄 PDF")
        btn_pdf.setStyleSheet("QPushButton { padding: 6px 12px; font-size: 13px; }")
        btn_pdf.clicked.connect(self._export_pdf)
        header.addWidget(btn_pdf)

        btn_csv = QPushButton("📊 CSV")
        btn_csv.setStyleSheet("QPushButton { padding: 6px 12px; font-size: 13px; }")
        btn_csv.clicked.connect(self._export_csv)
        header.addWidget(btn_csv)

        layout.addLayout(header)

        # Ticker filter
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Ticker:"))
        self.ticker_combo = QComboBox()
        self.ticker_combo.setMinimumWidth(150)
        self.ticker_combo.currentTextChanged.connect(self._on_ticker_changed)
        filter_layout.addWidget(self.ticker_combo)
        filter_layout.addStretch()

        # Summary labels
        self.lbl_qty = QLabel("Qtd: —")
        self.lbl_qty.setStyleSheet("font-weight: bold;")
        self.lbl_avg = QLabel("PM: —")
        self.lbl_avg.setStyleSheet("font-weight: bold;")
        self.lbl_cost = QLabel("Custo: —")
        self.lbl_cost.setStyleSheet("font-weight: bold;")
        filter_layout.addWidget(self.lbl_qty)
        filter_layout.addWidget(self.lbl_avg)
        filter_layout.addWidget(self.lbl_cost)

        layout.addLayout(filter_layout)

        # Table
        self.table = QTableView()
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self._model = LedgerTableModel()
        self.table.setModel(self._model)
        self.table.clicked.connect(self._on_table_click)
        layout.addWidget(self.table)

    def _on_table_click(self, index) -> None:
        """If the user clicks the Notas column, show the note content."""
        if index.column() != LedgerTableModel._COL_NOTAS:
            return
        row = self._model._rows[index.row()] if index.row() < len(self._model._rows) else None
        if row is None:
            return
        tx = row.tx
        if tx.notes and tx.notes.strip():
            QMessageBox.information(
                self, "Notas da Transação",
                f"Ticker: {tx.ticker}  |  Data: {tx.date.strftime('%d/%m/%Y')}\n\n"
                f"{tx.notes}",
            )

    def set_transactions(self, transactions: list[Transaction]) -> None:
        """Set the full transaction list and populate the ticker combo."""
        self._all_transactions = transactions
        tickers = sorted(set(t.ticker for t in transactions))
        current = self.ticker_combo.currentText()
        self.ticker_combo.blockSignals(True)
        self.ticker_combo.clear()
        self.ticker_combo.addItems(tickers)
        if current in tickers:
            self.ticker_combo.setCurrentText(current)
        self.ticker_combo.blockSignals(False)
        self._on_ticker_changed(self.ticker_combo.currentText())

    def _on_ticker_changed(self, ticker: str) -> None:
        if not ticker:
            self._model.set_data([])
            return
        filtered = [t for t in self._all_transactions if t.ticker == ticker]
        self._model.set_data(filtered)

        # Update summary labels from model's final values
        self.lbl_qty.setText(f"Qtd: {self._model.final_qty}")
        self.lbl_avg.setText(f"PM: {_fmt_brl(self._model.final_avg)}")
        self.lbl_cost.setText(f"Custo: {_fmt_brl(self._model.final_cost)}")

    def _get_table_data(self) -> tuple[list[str], list[list[str]]]:
        model = self._model
        headers = list(model.HEADERS)
        rows = []
        for row in model._rows:
            r = [model._display(row, c) for c in range(len(headers))]
            rows.append(r)
        return headers, rows

    def _export_pdf(self) -> None:
        ticker = self.ticker_combo.currentText() or "ativos"
        path, _ = QFileDialog.getSaveFileName(
            self, "Salvar PDF", f"razao_auxiliar_{ticker}.pdf", "PDF (*.pdf)"
        )
        if not path:
            return
        headers, rows = self._get_table_data()
        export_pdf(path, f"Razão Auxiliar de Ativos — {ticker}", headers, rows,
                   landscape_mode=True)
        QMessageBox.information(self, "Exportado", f"PDF salvo em:\n{path}")

    def _export_csv(self) -> None:
        ticker = self.ticker_combo.currentText() or "ativos"
        path, _ = QFileDialog.getSaveFileName(
            self, "Salvar CSV", f"razao_auxiliar_{ticker}.csv", "CSV (*.csv)"
        )
        if not path:
            return
        headers, rows = self._get_table_data()
        export_csv(path, headers, rows)
        QMessageBox.information(self, "Exportado", f"CSV salvo em:\n{path}")
