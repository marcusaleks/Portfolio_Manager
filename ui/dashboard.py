"""Dashboard — summary cards and matplotlib charts."""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
    QSizePolicy, QVBoxLayout, QWidget,
)

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from babel.numbers import format_currency

from domain.entities import Position
from domain.enums import AssetClass, Currency
from ui.styles import (
    PROFIT_COLOR, LOSS_COLOR, NEUTRAL_COLOR, CARD_BG, profit_loss_color,
)


def _fmt_brl(value: float) -> str:
    try:
        return format_currency(value, "BRL", locale="pt_BR")
    except Exception:
        return f"R$ {value:,.2f}"


# ═══════════════════════════════════════════════════════════════════════════
# Summary Card
# ═══════════════════════════════════════════════════════════════════════════

class SummaryCard(QFrame):
    """A small card showing a title and a big number."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet(
            f"background-color: {CARD_BG}; border: 1px solid #CCCCCC; "
            f"border-radius: 6px; padding: 12px;"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)

        self._title = QLabel(title)
        self._title.setObjectName("cardTitle")
        layout.addWidget(self._title)

        self._value = QLabel("—")
        self._value.setObjectName("cardValue")
        layout.addWidget(self._value)

    def set_value(self, text: str, color: str = NEUTRAL_COLOR) -> None:
        self._value.setText(text)
        self._value.setStyleSheet(f"color: {color}; font-size: 22px; font-weight: bold;")


# ═══════════════════════════════════════════════════════════════════════════
# Pie Chart Widget
# ═══════════════════════════════════════════════════════════════════════════

class AllocationPieChart(QWidget):
    """Matplotlib pie chart for asset allocation."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._fig = Figure(figsize=(4, 3.5), dpi=100)
        self._fig.patch.set_facecolor("#F5F5F5")
        self._canvas = FigureCanvasQTAgg(self._fig)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._canvas)

    def update_chart(self, data: dict[str, float]) -> None:
        """data = {asset_class_label: total_cost}."""
        self._fig.clear()
        ax = self._fig.add_subplot(111)

        if not data or all(v <= 0 for v in data.values()):
            ax.text(0.5, 0.5, "Sem dados", ha="center", va="center",
                    fontsize=14, color="#999999")
            ax.set_axis_off()
            self._canvas.draw()
            return

        labels = []
        sizes = []
        for k, v in sorted(data.items(), key=lambda x: -x[1]):
            if v > 0:
                labels.append(k)
                sizes.append(v)

        colors = ["#0078D4", "#00B294", "#FFB900", "#D83B01",
                  "#8764B8", "#107C10", "#E81123", "#00BCF2"]
        ax.pie(
            sizes, labels=labels, autopct="%1.1f%%",
            colors=colors[: len(sizes)],
            startangle=90, textprops={"fontsize": 9},
        )
        ax.set_title("Alocação por Classe", fontsize=11, fontweight="bold")
        self._fig.tight_layout()
        self._canvas.draw()


# ═══════════════════════════════════════════════════════════════════════════
# Bar Chart Widget
# ═══════════════════════════════════════════════════════════════════════════

class MonthlyGainsBarChart(QWidget):
    """Matplotlib bar chart for monthly gains/losses."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._fig = Figure(figsize=(6, 3.5), dpi=100)
        self._fig.patch.set_facecolor("#F5F5F5")
        self._canvas = FigureCanvasQTAgg(self._fig)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._canvas)

    def update_chart(self, data: dict[str, float]) -> None:
        """data = {YYYY-MM: gain_loss_brl}."""
        self._fig.clear()
        ax = self._fig.add_subplot(111)

        if not data:
            ax.text(0.5, 0.5, "Sem dados", ha="center", va="center",
                    fontsize=14, color="#999999")
            ax.set_axis_off()
            self._canvas.draw()
            return

        months = sorted(data.keys())[-12:]  # last 12 months
        values = [data[m] for m in months]
        colors = [PROFIT_COLOR if v >= 0 else LOSS_COLOR for v in values]

        bars = ax.bar(range(len(months)), values, color=colors, width=0.6)
        ax.set_xticks(range(len(months)))
        ax.set_xticklabels(months, rotation=45, ha="right", fontsize=8)
        ax.set_title("Resultado Mensal (últimos 12 meses)",
                      fontsize=11, fontweight="bold")
        ax.axhline(y=0, color="#999999", linewidth=0.5)
        ax.grid(axis="y", alpha=0.3)
        self._fig.tight_layout()
        self._canvas.draw()


# ═══════════════════════════════════════════════════════════════════════════
# Dashboard Widget
# ═══════════════════════════════════════════════════════════════════════════

class DashboardWidget(QWidget):
    """Main dashboard with summary cards and charts."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Title
        title = QLabel("Dashboard")
        title.setStyleSheet("font-size: 18px; font-weight: bold; padding: 4px;")
        layout.addWidget(title)

        # Cards row
        cards_layout = QHBoxLayout()
        self.card_equity = SummaryCard("Patrimônio Total")
        self.card_total_cost = SummaryCard("Custo Total")
        self.card_gain = SummaryCard("Ganho / Perda")
        self.card_positions = SummaryCard("Posições Abertas")

        for card in (self.card_equity, self.card_total_cost,
                     self.card_gain, self.card_positions):
            card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            cards_layout.addWidget(card)

        layout.addLayout(cards_layout)

        # Charts row
        charts_layout = QHBoxLayout()
        self.pie_chart = AllocationPieChart()
        self.bar_chart = MonthlyGainsBarChart()
        charts_layout.addWidget(self.pie_chart, 1)
        charts_layout.addWidget(self.bar_chart, 2)
        layout.addLayout(charts_layout)

        layout.addStretch()

    def refresh(
        self,
        positions: list[Position],
        monthly_gains: dict[str, float] | None = None,
        prices: dict[str, Decimal] | None = None,
    ) -> None:
        """Update dashboard with current data."""
        open_positions = [p for p in positions if p.quantity > Decimal("0")]

        total_cost = sum(float(p.total_cost) for p in open_positions)
        num_positions = len(open_positions)

        self.card_total_cost.set_value(_fmt_brl(total_cost))
        self.card_positions.set_value(str(num_positions))

        # Compute equity and gain/loss from market prices
        if prices:
            total_market = 0.0
            for p in open_positions:
                mkt = prices.get(p.ticker)
                if mkt is not None:
                    total_market += float(p.quantity * mkt)
                else:
                    total_market += float(p.total_cost)  # fallback to cost
            self.card_equity.set_value(_fmt_brl(total_market))

            gain = total_market - total_cost
            color = PROFIT_COLOR if gain > 0 else (LOSS_COLOR if gain < 0 else NEUTRAL_COLOR)
            self.card_gain.set_value(_fmt_brl(gain), color)
        else:
            self.card_equity.set_value(_fmt_brl(total_cost))
            self.card_gain.set_value("—", NEUTRAL_COLOR)

        # Pie chart — allocation by asset class
        alloc: dict[str, float] = {}
        for p in open_positions:
            label = p.asset_class.label
            alloc[label] = alloc.get(label, 0) + float(p.total_cost)
        self.pie_chart.update_chart(alloc)

        # Bar chart
        self.bar_chart.update_chart(monthly_gains or {})
