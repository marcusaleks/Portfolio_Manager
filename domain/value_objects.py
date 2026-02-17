"""Domain value objects with strict rounding rules."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Any

from domain.enums import Currency


# ---------------------------------------------------------------------------
# Rounding helpers
# ---------------------------------------------------------------------------

MONETARY_PRECISION = Decimal("0.01")        # 2 decimal places
FX_PRECISION = Decimal("0.00000001")        # 8 decimal places
QTY_PRECISION = Decimal("0.00000001")       # 8 decimal places


def round_monetary(value: Decimal) -> Decimal:
    """Round a monetary value to 2 decimal places using ROUND_HALF_UP."""
    return value.quantize(MONETARY_PRECISION, rounding=ROUND_HALF_UP)


def round_fx(value: Decimal) -> Decimal:
    """Round an FX rate to 8 decimal places using ROUND_HALF_UP."""
    return value.quantize(FX_PRECISION, rounding=ROUND_HALF_UP)


def round_qty(value: Decimal) -> Decimal:
    """Round a quantity to 8 decimal places using ROUND_HALF_UP."""
    return value.quantize(QTY_PRECISION, rounding=ROUND_HALF_UP)


def to_decimal(value: Any) -> Decimal:
    """Safely convert a value to Decimal."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        return Decimal(str(value))
    try:
        return Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"Cannot convert {value!r} to Decimal") from exc


# ---------------------------------------------------------------------------
# Value Objects (immutable via frozen dataclass)
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class Money:
    """Monetary value with 2-decimal ROUND_HALF_UP precision."""

    amount: Decimal
    currency: Currency

    def __post_init__(self) -> None:
        object.__setattr__(self, "amount", round_monetary(to_decimal(self.amount)))

    # Arithmetic ---------------------------------------------------------
    def __add__(self, other: Money) -> Money:
        self._assert_same_currency(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: Money) -> Money:
        self._assert_same_currency(other)
        return Money(self.amount - other.amount, self.currency)

    def __mul__(self, factor: Decimal | int | float) -> Money:
        return Money(self.amount * to_decimal(factor), self.currency)

    def __neg__(self) -> Money:
        return Money(-self.amount, self.currency)

    def __abs__(self) -> Money:
        return Money(abs(self.amount), self.currency)

    # Comparison ---------------------------------------------------------
    def __lt__(self, other: Money) -> bool:
        self._assert_same_currency(other)
        return self.amount < other.amount

    def __le__(self, other: Money) -> bool:
        self._assert_same_currency(other)
        return self.amount <= other.amount

    def __gt__(self, other: Money) -> bool:
        self._assert_same_currency(other)
        return self.amount > other.amount

    def __ge__(self, other: Money) -> bool:
        self._assert_same_currency(other)
        return self.amount >= other.amount

    @property
    def is_zero(self) -> bool:
        return self.amount == Decimal("0")

    @property
    def is_positive(self) -> bool:
        return self.amount > Decimal("0")

    @property
    def is_negative(self) -> bool:
        return self.amount < Decimal("0")

    @staticmethod
    def zero(currency: Currency) -> Money:
        return Money(Decimal("0"), currency)

    def _assert_same_currency(self, other: Money) -> None:
        if self.currency != other.currency:
            raise ValueError(
                f"Currency mismatch: {self.currency} vs {other.currency}"
            )

    def __repr__(self) -> str:
        return f"Money({self.currency.symbol} {self.amount})"


@dataclass(frozen=True, slots=True)
class Quantity:
    """Quantity with 8-decimal precision for fractional shares."""

    value: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", round_qty(to_decimal(self.value)))

    def __add__(self, other: Quantity) -> Quantity:
        return Quantity(self.value + other.value)

    def __sub__(self, other: Quantity) -> Quantity:
        return Quantity(self.value - other.value)

    def __mul__(self, factor: Decimal | int | float) -> Quantity:
        return Quantity(self.value * to_decimal(factor))

    def __neg__(self) -> Quantity:
        return Quantity(-self.value)

    def __lt__(self, other: Quantity) -> bool:
        return self.value < other.value

    def __le__(self, other: Quantity) -> bool:
        return self.value <= other.value

    def __gt__(self, other: Quantity) -> bool:
        return self.value > other.value

    def __ge__(self, other: Quantity) -> bool:
        return self.value >= other.value

    @property
    def is_zero(self) -> bool:
        return self.value == Decimal("0")

    @staticmethod
    def zero() -> Quantity:
        return Quantity(Decimal("0"))

    def __repr__(self) -> str:
        return f"Qty({self.value})"


@dataclass(frozen=True, slots=True)
class FxRate:
    """Foreign-exchange rate with 8-decimal precision."""

    value: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", round_fx(to_decimal(self.value)))

    def convert(self, money: Money, target_currency: Currency) -> Money:
        """Convert a Money amount using this FX rate."""
        return Money(money.amount * self.value, target_currency)

    def __repr__(self) -> str:
        return f"FxRate({self.value})"


# ---------------------------------------------------------------------------
# Consistency Hash
# ---------------------------------------------------------------------------

def compute_consistency_hash(data: dict) -> str:
    """Compute SHA-256 of a canonical JSON representation.

    Keys are sorted, Decimals are serialized as strings to ensure
    determinism across platforms.
    """
    def _default(obj: Any) -> Any:
        if isinstance(obj, Decimal):
            return str(obj)
        if hasattr(obj, "value"):  # Enum
            return obj.value
        if hasattr(obj, "isoformat"):  # date/datetime
            return obj.isoformat()
        raise TypeError(f"Cannot serialize {type(obj)}")

    canonical = json.dumps(data, sort_keys=True, default=_default)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
