"""Tests for TaxCalculatorBR."""

import pytest
from decimal import Decimal
from datetime import date

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from domain.enums import AssetClass, Currency, TradeType
from application.tax_calculator import TaxCalculatorBR
from application.position_calculator import SaleResult

ZERO = Decimal("0")


def _make_sale(
    gain_loss_brl: str,
    proceeds_brl: str,
    asset_class=AssetClass.ACAO,
    trade_type=TradeType.SWING_TRADE,
) -> SaleResult:
    """Helper to create a SaleResult with specific BRL values."""
    gl = Decimal(gain_loss_brl)
    pr = Decimal(proceeds_brl)
    return SaleResult(
        ticker="TEST",
        date=date(2025, 3, 15),
        trade_type=trade_type,
        asset_class=asset_class,
        sell_qty=Decimal("100"),
        sell_price=Decimal("10"),
        avg_cost=Decimal("9"),
        proceeds=pr,
        cost_of_sold=pr - gl,
        gain_loss=gl,
        currency=Currency.BRL,
        fx_rate=Decimal("1"),
    )


class TestTaxCalculatorBR:
    def test_swing_trade_basic_gain(self):
        calc = TaxCalculatorBR()
        sale = _make_sale("1000.00", "25000.00")  # above 20k exemption
        acc = {}
        results = calc.calculate_monthly_tax([sale], acc, "2025-03")
        assert len(results) == 1
        r = results[0]
        assert r.taxable_gain == Decimal("1000.00")
        assert r.tax_rate == Decimal("0.15")
        assert r.tax_due == Decimal("150.00")
        # IRRF swing = 0.005% * 25000 = 1.25
        assert r.irrf_withheld == Decimal("1.25")
        # DARF = 150 - 1.25 = 148.75
        assert r.darf_to_pay == Decimal("148.75")

    def test_swing_trade_monthly_exemption(self):
        """Swing trade ações with < R$20k in proceeds → exempt."""
        calc = TaxCalculatorBR()
        sale = _make_sale("500.00", "15000.00")  # below 20k
        acc = {}
        results = calc.calculate_monthly_tax([sale], acc, "2025-03")
        r = results[0]
        assert r.tax_due == ZERO
        assert r.darf_to_pay == ZERO

    def test_day_trade_gain(self):
        calc = TaxCalculatorBR()
        sale = _make_sale(
            "2000.00", "30000.00",
            trade_type=TradeType.DAY_TRADE,
        )
        acc = {}
        results = calc.calculate_monthly_tax([sale], acc, "2025-03")
        r = results[0]
        assert r.tax_rate == Decimal("0.20")
        assert r.tax_due == Decimal("400.00")
        # IRRF day trade = 1% of gain = 20
        assert r.irrf_withheld == Decimal("20.00")
        assert r.darf_to_pay == Decimal("380.00")

    def test_loss_accumulation(self):
        calc = TaxCalculatorBR()
        loss_sale = _make_sale("-500.00", "25000.00")
        acc = {}
        results = calc.calculate_monthly_tax([loss_sale], acc, "2025-01")
        assert acc[(AssetClass.ACAO, TradeType.SWING_TRADE)] == Decimal("500.00")

    def test_loss_offset(self):
        """Previous loss offsets current gain."""
        calc = TaxCalculatorBR()
        acc = {(AssetClass.ACAO, TradeType.SWING_TRADE): Decimal("300.00")}
        sale = _make_sale("1000.00", "25000.00")
        results = calc.calculate_monthly_tax([sale], acc, "2025-03")
        r = results[0]
        # taxable = 1000 - 300 = 700
        assert r.taxable_gain == Decimal("700.00")
        assert r.tax_due == Decimal("105.00")  # 700 * 0.15

    def test_loss_exceeds_gain(self):
        """Loss larger than gain → remaining loss carried forward."""
        calc = TaxCalculatorBR()
        acc = {(AssetClass.ACAO, TradeType.SWING_TRADE): Decimal("2000.00")}
        sale = _make_sale("500.00", "25000.00")
        results = calc.calculate_monthly_tax([sale], acc, "2025-03")
        r = results[0]
        assert r.taxable_gain == ZERO
        assert r.tax_due == ZERO
        assert r.accumulated_loss_after == Decimal("1500.00")

    def test_fii_no_exemption(self):
        """FIIs have no monthly exemption."""
        calc = TaxCalculatorBR()
        sale = _make_sale("500.00", "15000.00", asset_class=AssetClass.FII)
        acc = {}
        results = calc.calculate_monthly_tax([sale], acc, "2025-03")
        r = results[0]
        # FII has no exemption even below 20k
        assert r.taxable_gain == Decimal("500.00")
        assert r.tax_due == Decimal("75.00")
