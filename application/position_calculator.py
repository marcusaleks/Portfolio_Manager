"""PositionCalculator — Weighted Moving Average (Média Ponderada Móvel).

Brazilian tax rules require that the average price (*preço médio*) for a
given ticker be computed across ALL custodians/institutions:

    PM(ticker) = sum(total_cost per institution) / sum(qty per institution)

The calculator therefore maintains:
  * Per-institution positions (qty, total_cost) — so we know how many
    shares sit at each custodian.
  * A global avg_price per ticker — shared by every institution that
    holds the same asset.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as _date
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from domain.entities import Position, Transaction
from domain.enums import AssetClass, Currency, TradeType, TransactionType
from domain.value_objects import round_monetary, round_qty


ZERO = Decimal("0")
MONETARY_Q = Decimal("0.01")
QTY_Q = Decimal("0.00000001")


# ═══════════════════════════════════════════════════════════════════════════
# Internal mutable helper
# ═══════════════════════════════════════════════════════════════════════════

class _MutablePosition:
    __slots__ = (
        "ticker", "asset_class", "currency", "institution",
        "quantity", "avg_price", "total_cost",
    )

    def __init__(
        self,
        ticker: str,
        asset_class: AssetClass,
        currency: Currency,
        institution: str,
    ) -> None:
        self.ticker = ticker
        self.asset_class = asset_class
        self.currency = currency
        self.institution = institution
        self.quantity = ZERO
        self.avg_price = ZERO
        self.total_cost = ZERO


class _TickerGlobal:
    """Aggregated totals for a single ticker across all institutions."""
    __slots__ = ("quantity", "total_cost", "avg_price")

    def __init__(self) -> None:
        self.quantity = ZERO
        self.total_cost = ZERO
        self.avg_price = ZERO


# ═══════════════════════════════════════════════════════════════════════════
# Sale result VO
# ═══════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class SaleResult:
    """Result of processing a SELL transaction."""
    ticker: str
    date: _date
    trade_type: TradeType
    asset_class: AssetClass
    sell_qty: Decimal
    sell_price: Decimal
    avg_cost: Decimal
    proceeds: Decimal
    cost_of_sold: Decimal
    gain_loss: Decimal
    currency: Currency
    fx_rate: Decimal

    @property
    def gain_loss_brl(self) -> Decimal:
        return round_monetary(self.gain_loss * self.fx_rate)

    @property
    def proceeds_brl(self) -> Decimal:
        return round_monetary(self.proceeds * self.fx_rate)


# ═══════════════════════════════════════════════════════════════════════════
# PositionCalculator
# ═══════════════════════════════════════════════════════════════════════════

class PositionCalculator:
    """Computes positions from an ordered list of transactions using MPM.

    The average price (preço médio) is global per ticker across all
    institutions, following Brazilian tax rules.

    Usage::

        calc = PositionCalculator()
        for tx in sorted_transactions:
            calc.process(tx)
        positions = calc.get_positions()
    """

    def __init__(self) -> None:
        # key = "TICKER@INSTITUTION"
        self._positions: dict[str, _MutablePosition] = {}
        # key = "TICKER"  — global avg_price tracker
        self._globals: dict[str, _TickerGlobal] = {}

    def reset(self) -> None:
        self._positions.clear()
        self._globals.clear()

    def _get_global(self, ticker: str) -> _TickerGlobal:
        g = self._globals.get(ticker)
        if g is None:
            g = _TickerGlobal()
            self._globals[ticker] = g
        return g

    def process(self, tx: Transaction) -> SaleResult | None:
        """Process a single transaction and return a SaleResult for sells."""
        key = f"{tx.ticker}@{tx.institution}"
        pos = self._positions.get(key)

        if pos is None:
            pos = _MutablePosition(
                ticker=tx.ticker,
                asset_class=tx.asset_class,
                currency=tx.currency,
                institution=tx.institution,
            )
            self._positions[key] = pos

        if tx.type == TransactionType.BUY:
            return self._buy(pos, tx)
        elif tx.type == TransactionType.SELL:
            return self._sell(pos, tx)
        elif tx.type == TransactionType.SPLIT:
            return self._split(pos, tx)
        elif tx.type == TransactionType.INPLIT:
            return self._inplit(pos, tx)
        elif tx.type == TransactionType.BONUS:
            return self._bonus(pos, tx)
        elif tx.type in (TransactionType.DIVIDEND, TransactionType.JCP):
            return None  # dividends/JCP don't affect position
        return None

    # ── operations ─────────────────────────────────────────────────────

    def _buy(self, pos: _MutablePosition, tx: Transaction) -> None:
        """BUY: update per-institution and global-per-ticker totals."""
        buy_qty = tx.quantity
        buy_cost = round_monetary(tx.quantity * tx.price)

        # Update per-institution
        pos.quantity = round_qty(pos.quantity + buy_qty)
        pos.total_cost = round_monetary(pos.total_cost + buy_cost)

        # Update global per-ticker
        g = self._get_global(tx.ticker)
        g.quantity = round_qty(g.quantity + buy_qty)
        g.total_cost = round_monetary(g.total_cost + buy_cost)
        g.avg_price = (
            round_monetary(g.total_cost / g.quantity)
            if g.quantity > ZERO else ZERO
        )

        # Propagate global avg_price to ALL positions of this ticker
        self._sync_avg_price(tx.ticker)
        return None

    def _sell(self, pos: _MutablePosition, tx: Transaction) -> SaleResult:
        """SELL: use global avg_price for cost basis."""
        sell_qty = tx.quantity
        sell_price = tx.price
        g = self._get_global(tx.ticker)
        avg = g.avg_price  # global avg_price

        cost_of_sold = round_monetary(sell_qty * avg)
        proceeds = round_monetary(sell_qty * sell_price)
        gain_loss = round_monetary(proceeds - cost_of_sold)

        # Update per-institution
        new_qty = round_qty(pos.quantity - sell_qty)
        if new_qty <= ZERO:
            pos.quantity = ZERO
            pos.total_cost = ZERO
        else:
            pos.quantity = new_qty
            pos.total_cost = round_monetary(new_qty * avg)

        # Update global
        g.quantity = round_qty(g.quantity - sell_qty)
        if g.quantity <= ZERO:
            g.quantity = ZERO
            g.total_cost = ZERO
            g.avg_price = ZERO
        else:
            g.total_cost = round_monetary(g.quantity * avg)
            # avg_price doesn't change on sell

        # Propagate global avg_price to all positions of this ticker
        self._sync_avg_price(tx.ticker)

        return SaleResult(
            ticker=tx.ticker,
            date=tx.date,
            trade_type=tx.trade_type,
            asset_class=tx.asset_class,
            sell_qty=sell_qty,
            sell_price=sell_price,
            avg_cost=avg,
            proceeds=proceeds,
            cost_of_sold=cost_of_sold,
            gain_loss=gain_loss,
            currency=tx.currency,
            fx_rate=tx.fx_rate,
        )

    def _split(self, pos: _MutablePosition, tx: Transaction) -> None:
        """SPLIT: multiply qty, divide avg_price. tx.quantity = split factor."""
        factor = tx.quantity
        if factor <= ZERO:
            return

        # Update per-institution
        pos.quantity = round_qty(pos.quantity * factor)
        # total_cost stays the same

        # Update global
        g = self._get_global(tx.ticker)
        g.quantity = round_qty(g.quantity * (factor - Decimal("1")))  # add the delta
        # Actually simpler: recalc from all positions after split
        # But since split applies to the whole ticker, we need to handle
        # all positions of this ticker. Let's do it differently.
        # WAIT: A split comes as a single transaction for a specific
        # institution. But the split factor applies to ALL shares.
        # Since we're called once per institution, the caller should
        # have one split tx per institution. The global total is the
        # sum of all per-institution quantities.
        # After applying the factor to this institution's qty, we
        # recalc the global from scratch.
        self._recalc_global(tx.ticker)

    def _inplit(self, pos: _MutablePosition, tx: Transaction) -> None:
        """INPLIT (reverse split): divide qty, multiply avg_price."""
        factor = tx.quantity
        if factor <= ZERO:
            return

        # Update per-institution
        pos.quantity = round_qty(pos.quantity / factor)
        # total_cost stays the same

        # Recalc global from all positions
        self._recalc_global(tx.ticker)

    def _bonus(self, pos: _MutablePosition, tx: Transaction) -> None:
        """BONUS shares: increase qty at zero cost → reduces avg_price."""
        bonus_qty = tx.quantity

        # Update per-institution
        pos.quantity = round_qty(pos.quantity + bonus_qty)
        # total_cost stays the same

        # Update global
        g = self._get_global(tx.ticker)
        g.quantity = round_qty(g.quantity + bonus_qty)
        # total_cost stays the same
        g.avg_price = (
            round_monetary(g.total_cost / g.quantity)
            if g.quantity > ZERO else ZERO
        )

        # Propagate global avg_price
        self._sync_avg_price(tx.ticker)

    # ── helpers ────────────────────────────────────────────────────────

    def _sync_avg_price(self, ticker: str) -> None:
        """Copy the global avg_price to all per-institution positions."""
        g = self._globals.get(ticker)
        if g is None:
            return
        for pos in self._positions.values():
            if pos.ticker == ticker:
                pos.avg_price = g.avg_price
                # Also sync total_cost = qty * avg_price
                pos.total_cost = (
                    round_monetary(pos.quantity * g.avg_price)
                    if pos.quantity > ZERO else ZERO
                )

    def _recalc_global(self, ticker: str) -> None:
        """Recompute global totals from per-institution positions."""
        total_qty = ZERO
        total_cost = ZERO
        for pos in self._positions.values():
            if pos.ticker == ticker:
                total_qty = round_qty(total_qty + pos.quantity)
                total_cost = round_monetary(total_cost + pos.total_cost)
        g = self._get_global(ticker)
        g.quantity = total_qty
        g.total_cost = total_cost
        g.avg_price = (
            round_monetary(total_cost / total_qty)
            if total_qty > ZERO else ZERO
        )
        self._sync_avg_price(ticker)

    # ── results ────────────────────────────────────────────────────────

    def get_positions(self) -> list[Position]:
        """Return the current state of all positions as domain entities."""
        result = []
        for pos in self._positions.values():
            p = Position(
                ticker=pos.ticker,
                asset_class=pos.asset_class,
                quantity=pos.quantity,
                avg_price=pos.avg_price,
                currency=pos.currency,
                total_cost=pos.total_cost,
                institution=pos.institution,
            )
            p.seal()
            result.append(p)
        return result

    def get_open_positions(self) -> list[Position]:
        return [p for p in self.get_positions() if p.is_open]
