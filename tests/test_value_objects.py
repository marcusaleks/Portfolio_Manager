"""Tests for domain value objects."""

import pytest
from decimal import Decimal

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from domain.enums import Currency
from domain.value_objects import (
    Money, Quantity, FxRate, compute_consistency_hash,
    round_monetary, round_fx, round_qty,
)


class TestMoney:
    def test_rounding(self):
        m = Money(Decimal("10.555"), Currency.BRL)
        assert m.amount == Decimal("10.56")  # ROUND_HALF_UP

    def test_rounding_half_up(self):
        m = Money(Decimal("10.545"), Currency.BRL)
        assert m.amount == Decimal("10.55")

    def test_addition(self):
        a = Money(Decimal("10.50"), Currency.BRL)
        b = Money(Decimal("5.25"), Currency.BRL)
        c = a + b
        assert c.amount == Decimal("15.75")

    def test_subtraction(self):
        a = Money(Decimal("10.50"), Currency.BRL)
        b = Money(Decimal("5.25"), Currency.BRL)
        c = a - b
        assert c.amount == Decimal("5.25")

    def test_currency_mismatch(self):
        a = Money(Decimal("10"), Currency.BRL)
        b = Money(Decimal("5"), Currency.USD)
        with pytest.raises(ValueError, match="Currency mismatch"):
            a + b

    def test_zero(self):
        z = Money.zero(Currency.BRL)
        assert z.is_zero
        assert not z.is_positive
        assert not z.is_negative

    def test_multiplication(self):
        m = Money(Decimal("10.00"), Currency.BRL)
        r = m * 3
        assert r.amount == Decimal("30.00")


class TestQuantity:
    def test_precision(self):
        q = Quantity(Decimal("100.123456789"))
        assert q.value == Decimal("100.12345679")  # 8 decimals, ROUND_HALF_UP

    def test_addition(self):
        a = Quantity(Decimal("100"))
        b = Quantity(Decimal("50"))
        assert (a + b).value == Decimal("150.00000000")


class TestFxRate:
    def test_precision(self):
        fx = FxRate(Decimal("5.123456789"))
        assert fx.value == Decimal("5.12345679")

    def test_convert(self):
        fx = FxRate(Decimal("5.00"))
        m = Money(Decimal("100.00"), Currency.USD)
        result = fx.convert(m, Currency.BRL)
        assert result.amount == Decimal("500.00")
        assert result.currency == Currency.BRL


class TestConsistencyHash:
    def test_determinism(self):
        data = {"ticker": "PETR4", "qty": Decimal("100")}
        h1 = compute_consistency_hash(data)
        h2 = compute_consistency_hash(data)
        assert h1 == h2
        assert len(h1) == 64  # SHA-256

    def test_different_data(self):
        h1 = compute_consistency_hash({"a": "1"})
        h2 = compute_consistency_hash({"a": "2"})
        assert h1 != h2
