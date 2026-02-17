"""Tests for PositionCalculator (Weighted Moving Average / MPM)."""

import pytest
from datetime import date
from decimal import Decimal

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from domain.entities import Transaction
from domain.enums import AssetClass, Currency, TradeType, TransactionType
from application.position_calculator import PositionCalculator


def _make_tx(
    ticker="PETR4",
    tx_type=TransactionType.BUY,
    qty=100,
    price="30.00",
    trade_type=TradeType.SWING_TRADE,
    institution="XP",
    tx_date=None,
) -> Transaction:
    return Transaction(
        ticker=ticker,
        asset_class=AssetClass.ACAO,
        type=tx_type,
        trade_type=trade_type,
        date=tx_date or date(2025, 1, 15),
        quantity=Decimal(str(qty)),
        price=Decimal(price),
        currency=Currency.BRL,
        fx_rate=Decimal("1"),
        institution=institution,
    )


class TestPositionCalculator:
    def test_single_buy(self):
        calc = PositionCalculator()
        calc.process(_make_tx(qty=100, price="30.00"))
        positions = calc.get_positions()
        assert len(positions) == 1
        p = positions[0]
        assert p.ticker == "PETR4"
        assert p.quantity == Decimal("100")
        assert p.avg_price == Decimal("30.00")
        assert p.total_cost == Decimal("3000.00")

    def test_two_buys_weighted_average(self):
        calc = PositionCalculator()
        calc.process(_make_tx(qty=100, price="30.00"))
        calc.process(_make_tx(qty=50, price="36.00"))
        p = calc.get_positions()[0]
        # avg = (3000 + 1800) / 150 = 4800 / 150 = 32.00
        assert p.quantity == Decimal("150")
        assert p.avg_price == Decimal("32.00")
        assert p.total_cost == Decimal("4800.00")

    def test_buy_and_sell(self):
        calc = PositionCalculator()
        calc.process(_make_tx(qty=100, price="30.00"))
        result = calc.process(_make_tx(
            tx_type=TransactionType.SELL, qty=40, price="35.00"
        ))
        p = calc.get_positions()[0]
        # After sell: qty=60, avg=30, cost=1800
        assert p.quantity == Decimal("60")
        assert p.avg_price == Decimal("30.00")
        assert p.total_cost == Decimal("1800.00")
        # Gain: (35 - 30) * 40 = 200
        assert result is not None
        assert result.gain_loss == Decimal("200.00")

    def test_sell_all(self):
        calc = PositionCalculator()
        calc.process(_make_tx(qty=100, price="30.00"))
        calc.process(_make_tx(
            tx_type=TransactionType.SELL, qty=100, price="25.00"
        ))
        p = calc.get_positions()[0]
        assert p.quantity == Decimal("0")
        assert p.avg_price == Decimal("0")
        assert p.total_cost == Decimal("0")

    def test_sell_at_loss(self):
        calc = PositionCalculator()
        calc.process(_make_tx(qty=100, price="30.00"))
        result = calc.process(_make_tx(
            tx_type=TransactionType.SELL, qty=50, price="25.00"
        ))
        # Loss: (25 - 30) * 50 = -250
        assert result.gain_loss == Decimal("-250.00")

    def test_split(self):
        calc = PositionCalculator()
        calc.process(_make_tx(qty=100, price="40.00"))
        # 2:1 split
        calc.process(_make_tx(
            tx_type=TransactionType.SPLIT, qty=2, price="0"
        ))
        p = calc.get_positions()[0]
        assert p.quantity == Decimal("200")
        assert p.avg_price == Decimal("20.00")
        assert p.total_cost == Decimal("4000.00")

    def test_inplit(self):
        calc = PositionCalculator()
        calc.process(_make_tx(qty=100, price="10.00"))
        # 10:1 inplit (reverse split)
        calc.process(_make_tx(
            tx_type=TransactionType.INPLIT, qty=10, price="0"
        ))
        p = calc.get_positions()[0]
        assert p.quantity == Decimal("10")
        assert p.avg_price == Decimal("100.00")
        assert p.total_cost == Decimal("1000.00")

    def test_multiple_institutions(self):
        calc = PositionCalculator()
        calc.process(_make_tx(qty=100, price="30.00", institution="XP"))
        calc.process(_make_tx(qty=50, price="32.00", institution="BTG"))
        positions = calc.get_positions()
        assert len(positions) == 2
        tickers_inst = {p.market_key for p in positions}
        assert "PETR4@XP" in tickers_inst
        assert "PETR4@BTG" in tickers_inst
