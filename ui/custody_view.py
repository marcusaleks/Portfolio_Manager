"""Custódia por Instituição — shows asset allocation per broker/bank."""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QHeaderView, QLabel, QMessageBox,
    QPushButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from babel.numbers import format_currency

from domain.entities import PortfolioCustodian
from reports.report_export import export_csv, export_pdf

log = logging.getLogger(__name__)

ZERO = Decimal("0")


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _fmt_qty(value) -> str:
    v = float(value)
    if v == int(v):
        return f"{int(v):,}".replace(",", ".")
    return f"{v:,.8f}".rstrip("0").rstrip(".")


def _fmt_brl(value) -> str:
    try:
        return format_currency(float(value), "BRL", locale="pt_BR")
    except Exception:
        return f"R$ {float(value):,.2f}"


# ═══════════════════════════════════════════════════════════════════════════
# CustodyView
# ═══════════════════════════════════════════════════════════════════════════

class CustodyView(QWidget):
    """Tree view grouped by institution showing tickers, quantities,
    market prices, and market values with per-institution and grand totals.

    Market prices are editable: double-click the 'Preço de Mercado' cell
    for any asset row to manually override the price.
    """

    price_changed = Signal(str, object)  # ticker, new_price (Decimal)

    # Column indices
    _COL_NAME = 0
    _COL_QTY = 1
    _COL_PRICE = 2
    _COL_VALUE = 3

    def __init__(self, parent_window=None):
        super().__init__()
        self.main_win = parent_window
        self._custodians: list[PortfolioCustodian] = []
        self._prices: dict[str, Decimal] = {}
        self._avg_prices: dict[str, Decimal] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Header
        header = QHBoxLayout()
        title = QLabel("Custódia por Instituição")
        title.setStyleSheet("font-size: 18px; font-weight: bold; padding: 4px;")
        header.addWidget(title)
        header.addStretch()

        self.refresh_btn = QPushButton("🔄 Atualizar Cotações")
        self.refresh_btn.setStyleSheet(
            "QPushButton { padding: 6px 14px; font-size: 13px; }"
        )
        self.refresh_btn.clicked.connect(self._fetch_prices)
        header.addWidget(self.refresh_btn)

        btn_pdf = QPushButton("📄 PDF")
        btn_pdf.setStyleSheet("QPushButton { padding: 6px 12px; font-size: 13px; }")
        btn_pdf.clicked.connect(self._export_pdf)
        header.addWidget(btn_pdf)

        btn_csv = QPushButton("📊 CSV")
        btn_csv.setStyleSheet("QPushButton { padding: 6px 12px; font-size: 13px; }")
        btn_csv.clicked.connect(self._export_csv)
        header.addWidget(btn_csv)

        layout.addLayout(header)

        # Tree widget
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([
            "Instituição / Ticker", "Quantidade",
            "Preço de Mercado", "Valor de Mercado",
        ])
        self.tree.setAlternatingRowColors(True)
        self.tree.setRootIsDecorated(True)
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        for col in (1, 2, 3):
            self.tree.header().setSectionResizeMode(col, QHeaderView.ResizeToContents)
        self.tree.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.tree)

    # ── public API ─────────────────────────────────────────────────────

    def refresh(self, custodians: list[PortfolioCustodian],
                avg_prices: dict[str, Decimal] | None = None) -> None:
        """Rebuild the tree from custodian data, keeping existing prices."""
        self._custodians = custodians
        if avg_prices is not None:
            self._avg_prices = avg_prices
        self._rebuild_tree()

    # ── price fetching ─────────────────────────────────────────────────

    def _fetch_prices(self) -> None:
        """Fetch market prices for all tickers via the price provider."""
        if self.main_win is None:
            return
        provider = self.main_win._price_provider
        tickers = list({c.ticker for c in self._custodians})
        for ticker in tickers:
            price = provider.get_last_price(ticker)
            if price is not None:
                self._prices[ticker] = price
                log.info("Market price for %s: %s", ticker, price)
            else:
                log.warning("Could not fetch price for %s", ticker)
        self._rebuild_tree()

    # ── tree building ──────────────────────────────────────────────────

    def _rebuild_tree(self) -> None:
        self.tree.blockSignals(True)
        self.tree.clear()

        # Group by institution
        by_inst: dict[str, list[PortfolioCustodian]] = {}
        for c in self._custodians:
            by_inst.setdefault(c.institution, []).append(c)

        grand_total = ZERO
        bold_font = QFont()
        bold_font.setBold(True)

        for inst in sorted(by_inst.keys()):
            items = by_inst[inst]
            total_items = len(items)
            inst_market_total = ZERO

            parent_item = QTreeWidgetItem([
                f"🏦 {inst}  ({total_items} ativo{'s' if total_items != 1 else ''})",
                "", "", "",
            ])
            parent_item.setFlags(parent_item.flags() | Qt.ItemIsEnabled)
            parent_item.setFont(0, bold_font)

            for c in sorted(items, key=lambda x: x.ticker):
                price = self._prices.get(c.ticker)
                price_str = _fmt_brl(price) if price is not None else "—"
                if price is not None:
                    mkt_value = c.quantity * price
                    inst_market_total += mkt_value
                    value_str = _fmt_brl(mkt_value)
                else:
                    value_str = "—"

                child = QTreeWidgetItem([
                    c.ticker, _fmt_qty(c.quantity),
                    price_str, value_str,
                ])
                # Make the price cell editable
                child.setFlags(child.flags() | Qt.ItemIsEditable)
                # Store ticker as data for later retrieval
                child.setData(0, Qt.UserRole, c.ticker)
                child.setData(1, Qt.UserRole, c.quantity)

                for col in (1, 2, 3):
                    child.setTextAlignment(col, Qt.AlignRight | Qt.AlignVCenter)

                # Color-code market price vs avg price
                if price is not None:
                    avg = self._avg_prices.get(c.ticker)
                    if avg is not None and avg > ZERO:
                        if price > avg:
                            child.setForeground(2, QBrush(QColor("#2e7d32")))
                        elif price < avg:
                            child.setForeground(2, QBrush(QColor("#c62828")))

                parent_item.addChild(child)

            # Institution total row
            grand_total += inst_market_total
            parent_item.setText(3, _fmt_brl(inst_market_total))
            parent_item.setTextAlignment(3, Qt.AlignRight | Qt.AlignVCenter)
            parent_item.setFont(3, bold_font)

            self.tree.addTopLevelItem(parent_item)
            parent_item.setExpanded(True)

        # Grand total row
        if by_inst:
            total_item = QTreeWidgetItem(["📊 TOTAL GERAL", "", "", _fmt_brl(grand_total)])
            total_item.setFont(0, bold_font)
            total_item.setFont(3, bold_font)
            total_item.setTextAlignment(3, Qt.AlignRight | Qt.AlignVCenter)
            total_item.setFlags(Qt.ItemIsEnabled)
            self.tree.addTopLevelItem(total_item)

        self.tree.blockSignals(False)

    # ── editable price handling ────────────────────────────────────────

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        """Handle manual edit of the market price column."""
        if column != self._COL_PRICE:
            return
        ticker = item.data(0, Qt.UserRole)
        if ticker is None:
            return  # not an asset row

        raw = item.text(self._COL_PRICE).strip()
        # Clean up: remove currency symbols, dots as thousands sep, replace comma with dot
        cleaned = raw.replace("R$", "").replace("US$", "").strip()
        cleaned = cleaned.replace(".", "").replace(",", ".")

        try:
            new_price = Decimal(cleaned)
            if new_price <= ZERO:
                raise ValueError
        except (InvalidOperation, ValueError):
            # Revert to previous price
            old_price = self._prices.get(ticker)
            self.tree.blockSignals(True)
            item.setText(self._COL_PRICE, _fmt_brl(old_price) if old_price else "—")
            self.tree.blockSignals(False)
            return

        self._prices[ticker] = new_price
        log.info("Manual price override for %s: %s", ticker, new_price)

        # Recalculate this row and totals
        self._rebuild_tree()

        # Notify other views about the price change
        self.price_changed.emit(ticker, new_price)

    # ── export ─────────────────────────────────────────────────────────

    def _get_table_data(self) -> tuple[list[str], list[list[str]]]:
        headers = ["Instituição", "Ticker", "Quantidade",
                   "Preço de Mercado", "Valor de Mercado"]
        rows: list[list[str]] = []
        grand_total = ZERO
        by_inst: dict[str, list[PortfolioCustodian]] = {}
        for c in self._custodians:
            by_inst.setdefault(c.institution, []).append(c)

        for inst in sorted(by_inst.keys()):
            items = by_inst[inst]
            inst_total = ZERO
            for c in sorted(items, key=lambda x: x.ticker):
                price = self._prices.get(c.ticker)
                price_str = _fmt_brl(price) if price else "—"
                if price:
                    mv = c.quantity * price
                    inst_total += mv
                    mv_str = _fmt_brl(mv)
                else:
                    mv_str = "—"
                rows.append([inst, c.ticker, _fmt_qty(c.quantity), price_str, mv_str])
            rows.append([inst, "SUBTOTAL", "", "", _fmt_brl(inst_total)])
            grand_total += inst_total
        rows.append(["TOTAL GERAL", "", "", "", _fmt_brl(grand_total)])
        return headers, rows

    def _export_pdf(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Salvar PDF", "custodia_instituicao.pdf", "PDF (*.pdf)"
        )
        if not path:
            return
        headers, rows = self._get_table_data()
        export_pdf(path, "Custódia por Instituição", headers, rows)
        QMessageBox.information(self, "Exportado", f"PDF salvo em:\n{path}")

    def _export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Salvar CSV", "custodia_instituicao.csv", "CSV (*.csv)"
        )
        if not path:
            return
        headers, rows = self._get_table_data()
        export_csv(path, headers, rows)
        QMessageBox.information(self, "Exportado", f"CSV salvo em:\n{path}")
