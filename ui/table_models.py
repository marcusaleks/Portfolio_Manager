"""Custom QAbstractTableModel subclasses for transactions and positions."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtGui import QColor

from babel.numbers import format_currency

from domain.entities import Position, Transaction
from domain.enums import Currency
from ui.styles import PROFIT_COLOR, LOSS_COLOR


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

ZERO = Decimal("0")

def _fmt_money(value: Decimal, currency: Currency) -> str:
    locale = "pt_BR" if currency == Currency.BRL else "en_US"
    curr = "BRL" if currency == Currency.BRL else "USD"
    try:
        return format_currency(float(value), curr, locale=locale)
    except Exception:
        return f"{currency.symbol} {value:,.2f}"


def _fmt_qty(value: Decimal) -> str:
    v = float(value)
    if v == int(v):
        return f"{int(v):,}".replace(",", ".")
    return f"{v:,.8f}".rstrip("0").rstrip(".")


# ═══════════════════════════════════════════════════════════════════════════
# TransactionTableModel
# ═══════════════════════════════════════════════════════════════════════════

class TransactionTableModel(QAbstractTableModel):
    HEADERS = [
        "Data", "Ticker", "Tipo", "DT/ST", "Qtd", "Preço",
        "Total", "Moeda", "FX", "Instituição", "Notas",
    ]

    def __init__(self, transactions: list[Transaction] | None = None, parent=None):
        super().__init__(parent)
        self._data: list[Transaction] = transactions or []

    def set_data(self, transactions: list[Transaction]) -> None:
        self.beginResetModel()
        self._data = transactions
        self.endResetModel()

    def get_transaction(self, row: int) -> Transaction | None:
        if 0 <= row < len(self._data):
            return self._data[row]
        return None

    # ── QAbstractTableModel interface ──────────────────────────────────

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._data)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.HEADERS[section]
        return None

    def data(self, index: QModelIndex, role=Qt.DisplayRole) -> Any:
        if not index.isValid():
            return None
        tx = self._data[index.row()]
        col = index.column()

        if role == Qt.DisplayRole:
            return self._display(tx, col)
        if role == Qt.ForegroundRole:
            return self._foreground(tx, col)
        if role == Qt.TextAlignmentRole:
            if col >= 4:  # numeric columns
                return Qt.AlignRight | Qt.AlignVCenter
        return None

    def _display(self, tx: Transaction, col: int) -> str:
        if col == 0:
            return tx.date.strftime("%d/%m/%Y")
        if col == 1:
            return tx.ticker
        if col == 2:
            return tx.type.value
        if col == 3:
            return "DT" if tx.trade_type.value == "DAY_TRADE" else "ST"
        if col == 4:
            return _fmt_qty(tx.quantity)
        if col == 5:
            return _fmt_money(tx.price, tx.currency)
        if col == 6:
            return _fmt_money(tx.total_value, tx.currency)
        if col == 7:
            return tx.currency.value
        if col == 8:
            return str(tx.fx_rate) if tx.currency == Currency.USD else "—"
        if col == 9:
            return tx.institution
        if col == 10:
            return "📝" if tx.notes and tx.notes.strip() else ""
        return ""

    @staticmethod
    def _foreground(tx: Transaction, col: int) -> Optional[QColor]:
        if col == 2:
            if tx.type.value == "BUY":
                return QColor(PROFIT_COLOR)
            if tx.type.value == "SELL":
                return QColor(LOSS_COLOR)
        return None


# ═══════════════════════════════════════════════════════════════════════════
# PositionTableModel
# ═══════════════════════════════════════════════════════════════════════════

class PositionTableModel(QAbstractTableModel):
    """Supports two display modes:

    * **Consolidated** (default): groups positions by ticker, sums
      quantities/costs, hides the *Instituição* column.
    * **Detailed**: shows one row per ticker×institution.
    """

    price_changed = Signal(str, object)  # ticker, new_price (Decimal)

    HEADERS_CONSOLIDATED = [
        "Ticker", "Classe", "Qtd", "Preço Médio", "Preço de Mercado",
        "Custo Total", "Valor Mercado", "Resultado Realizável",
        "Moeda",
    ]
    HEADERS_DETAILED = [
        "Ticker", "Classe", "Qtd", "Preço Médio", "Preço de Mercado",
        "Custo Total", "Valor Mercado", "Resultado Realizável",
        "Moeda", "Instituição",
    ]

    # Column indices (same for both modes, detailed just adds col 9)
    _COL_TICKER = 0
    _COL_CLASSE = 1
    _COL_QTD = 2
    _COL_PM = 3
    _COL_PU = 4
    _COL_CUSTO = 5
    _COL_MV = 6
    _COL_RESULT = 7
    _COL_MOEDA = 8
    _COL_INST = 9  # only in detailed mode

    def __init__(self, positions: list[Position] | None = None, parent=None):
        super().__init__(parent)
        self._raw_data: list[Position] = positions or []
        self._data: list[Position] = []
        self._prices: dict[str, Decimal] = {}
        self._show_totals = True
        self._consolidated = True  # default: consolidated view
        self._rebuild_view()

    # ── public API ─────────────────────────────────────────────────────

    @property
    def headers(self) -> list[str]:
        return self.HEADERS_CONSOLIDATED if self._consolidated else self.HEADERS_DETAILED

    def set_data(
        self,
        positions: list[Position],
        prices: dict[str, Decimal] | None = None,
    ) -> None:
        self.beginResetModel()
        self._raw_data = positions
        self._prices = prices or {}
        self._rebuild_view()
        self.endResetModel()

    def set_consolidated(self, consolidated: bool) -> None:
        """Toggle between consolidated and detailed view."""
        if consolidated == self._consolidated:
            return
        self.beginResetModel()
        self._consolidated = consolidated
        self._rebuild_view()
        self.endResetModel()

    @property
    def is_consolidated(self) -> bool:
        return self._consolidated

    def get_position(self, row: int) -> Position | None:
        if 0 <= row < len(self._data):
            return self._data[row]
        return None

    # ── consolidation logic ────────────────────────────────────────────

    def _rebuild_view(self) -> None:
        if self._consolidated:
            self._data = self._consolidate(self._raw_data)
        else:
            self._data = list(self._raw_data)

    @staticmethod
    def _consolidate(positions: list[Position]) -> list[Position]:
        """Group positions by ticker, summing qty/cost, keeping shared PM."""
        from collections import OrderedDict
        grouped: OrderedDict[str, dict] = OrderedDict()
        for p in positions:
            if p.ticker not in grouped:
                grouped[p.ticker] = {
                    "ticker": p.ticker,
                    "asset_class": p.asset_class,
                    "currency": p.currency,
                    "quantity": ZERO,
                    "total_cost": ZERO,
                    "avg_price": p.avg_price,  # global PM is the same
                    "institution": "",  # consolidated
                }
            g = grouped[p.ticker]
            g["quantity"] += p.quantity
            g["total_cost"] += p.total_cost
            # avg_price is already global per ticker (same across institutions)

        result = []
        for g in grouped.values():
            pos = Position(
                ticker=g["ticker"],
                asset_class=g["asset_class"],
                quantity=g["quantity"],
                avg_price=g["avg_price"],
                currency=g["currency"],
                total_cost=g["total_cost"],
                institution=g["institution"],
            )
            pos.seal()
            result.append(pos)
        return result

    # ── market helpers ─────────────────────────────────────────────────

    def _market_value(self, pos: Position) -> Decimal | None:
        price = self._prices.get(pos.ticker)
        if price is not None:
            return pos.quantity * price
        return None

    def _unrealized_gain(self, pos: Position) -> Decimal | None:
        mv = self._market_value(pos)
        if mv is not None:
            return mv - pos.total_cost
        return None

    # ── Qt model interface ─────────────────────────────────────────────

    def rowCount(self, parent=QModelIndex()) -> int:
        n = len(self._data)
        if n > 0 and self._show_totals:
            return n + 1
        return n

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(self.headers)

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        base = super().flags(index)
        if not index.isValid():
            return base
        row = index.row()
        is_totals = (self._show_totals and row == len(self._data))
        if not is_totals and index.column() == self._COL_PU:
            return base | Qt.ItemIsEditable
        return base

    def setData(self, index: QModelIndex, value, role=Qt.EditRole) -> bool:
        if role != Qt.EditRole or index.column() != self._COL_PU:
            return False
        row = index.row()
        if row >= len(self._data):
            return False
        raw = str(value).strip()
        cleaned = raw.replace("R$", "").replace("US$", "").strip()
        cleaned = cleaned.replace(".", "").replace(",", ".")
        try:
            new_price = Decimal(cleaned)
            if new_price <= ZERO:
                raise ValueError
        except (InvalidOperation, ValueError):
            return False

        pos = self._data[row]
        self._prices[pos.ticker] = new_price
        self.dataChanged.emit(index, index)
        # Re-emit all changed columns for this row (market value, result)
        top_left = self.index(row, 0)
        bottom_right = self.index(row, len(self.headers) - 1)
        self.dataChanged.emit(top_left, bottom_right)
        # Notify other views about the price change
        self.price_changed.emit(pos.ticker, new_price)
        return True

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            h = self.headers
            if section < len(h):
                return h[section]
        return None

    def data(self, index: QModelIndex, role=Qt.DisplayRole) -> Any:
        if not index.isValid():
            return None
        col = index.column()
        row = index.row()

        is_totals = (self._show_totals and row == len(self._data))

        if role == Qt.DisplayRole:
            if is_totals:
                return self._display_totals(col)
            return self._display(self._data[row], col)

        if role == Qt.ForegroundRole:
            if is_totals:
                if col == self._COL_RESULT:
                    total_gain = sum(
                        (self._unrealized_gain(p) or ZERO) for p in self._data
                    )
                    if total_gain > ZERO:
                        return QColor(PROFIT_COLOR)
                    if total_gain < ZERO:
                        return QColor(LOSS_COLOR)
                return None
            pos = self._data[row]
            if col == self._COL_PU:
                mkt = self._prices.get(pos.ticker)
                if mkt is not None and pos.avg_price > ZERO:
                    if mkt > pos.avg_price:
                        return QColor(PROFIT_COLOR)
                    if mkt < pos.avg_price:
                        return QColor(LOSS_COLOR)
                return None
            if col == self._COL_RESULT:
                gain = self._unrealized_gain(pos)
                if gain is not None:
                    if gain > ZERO:
                        return QColor(PROFIT_COLOR)
                    if gain < ZERO:
                        return QColor(LOSS_COLOR)
            return None

        if role == Qt.FontRole:
            if is_totals:
                from PySide6.QtGui import QFont
                font = QFont()
                font.setBold(True)
                return font
            return None

        if role == Qt.TextAlignmentRole:
            if col >= 2:
                return Qt.AlignRight | Qt.AlignVCenter
        return None

    def _display(self, pos: Position, col: int) -> str:
        if col == self._COL_TICKER:
            return pos.ticker
        if col == self._COL_CLASSE:
            return pos.asset_class.label
        if col == self._COL_QTD:
            return _fmt_qty(pos.quantity)
        if col == self._COL_PM:
            return _fmt_money(pos.avg_price, pos.currency)
        if col == self._COL_PU:
            price = self._prices.get(pos.ticker)
            if price is not None:
                return _fmt_money(price, pos.currency)
            return "—"
        if col == self._COL_CUSTO:
            return _fmt_money(pos.total_cost, pos.currency)
        if col == self._COL_MV:
            mv = self._market_value(pos)
            if mv is not None:
                return _fmt_money(mv, pos.currency)
            return "—"
        if col == self._COL_RESULT:
            gain = self._unrealized_gain(pos)
            if gain is not None:
                return _fmt_money(gain, pos.currency)
            return "—"
        if col == self._COL_MOEDA:
            return pos.currency.value
        if col == self._COL_INST:
            return pos.institution
        return ""

    def _display_totals(self, col: int) -> str:
        if col == self._COL_TICKER:
            return "TOTAL"
        if col == self._COL_CUSTO:
            total = sum(p.total_cost for p in self._data)
            if self._data:
                return _fmt_money(total, self._data[0].currency)
            return "—"
        if col == self._COL_MV:
            total = ZERO
            has_any = False
            for p in self._data:
                mv = self._market_value(p)
                if mv is not None:
                    total += mv
                    has_any = True
            if has_any:
                return _fmt_money(total, self._data[0].currency)
            return "—"
        if col == self._COL_RESULT:
            total = ZERO
            has_any = False
            for p in self._data:
                gain = self._unrealized_gain(p)
                if gain is not None:
                    total += gain
                    has_any = True
            if has_any:
                return _fmt_money(total, self._data[0].currency)
            return "—"
        return ""


