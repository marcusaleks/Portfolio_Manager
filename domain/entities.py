"""Domain entities — pure data structures, no infrastructure dependencies."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from domain.enums import AssetClass, Currency, TradeType, TransactionType
from domain.value_objects import (
    Quantity,
    compute_consistency_hash,
    round_monetary,
    to_decimal,
)


@dataclass
class Transaction:
    """A single portfolio transaction — the canonical source of truth."""

    ticker: str
    asset_class: AssetClass
    type: TransactionType
    trade_type: TradeType
    date: date
    quantity: Decimal           # raw Decimal, wrapped in Quantity when needed
    price: Decimal              # unit price in *currency*
    currency: Currency
    fx_rate: Decimal            # 1.0 for BRL transactions
    institution: str
    notes: str = ""
    id: Optional[int] = None
    consistency_hash: str = ""
    created_at: Optional[datetime] = None

    def __post_init__(self) -> None:
        self.quantity = to_decimal(self.quantity)
        self.price = round_monetary(to_decimal(self.price))
        self.fx_rate = to_decimal(self.fx_rate)

    @property
    def total_value(self) -> Decimal:
        """Gross value = quantity × price."""
        return round_monetary(self.quantity * self.price)

    @property
    def total_value_brl(self) -> Decimal:
        """Total value converted to BRL."""
        return round_monetary(self.total_value * self.fx_rate)

    def compute_hash(self) -> str:
        """Return the SHA-256 consistency hash for this transaction."""
        data = {
            "ticker": self.ticker,
            "asset_class": self.asset_class,
            "type": self.type,
            "trade_type": self.trade_type,
            "date": self.date,
            "quantity": self.quantity,
            "price": self.price,
            "currency": self.currency,
            "fx_rate": self.fx_rate,
            "institution": self.institution,
        }
        return compute_consistency_hash(data)

    def seal(self) -> None:
        """Compute and set the consistency hash."""
        self.consistency_hash = self.compute_hash()


@dataclass
class Position:
    """Derived position cache — rebuilt from transactions."""

    ticker: str
    asset_class: AssetClass
    quantity: Decimal
    avg_price: Decimal          # average price in *currency*
    currency: Currency
    total_cost: Decimal         # total cost-basis in *currency*
    institution: str
    id: Optional[int] = None
    consistency_hash: str = ""

    def __post_init__(self) -> None:
        self.quantity = to_decimal(self.quantity)
        self.avg_price = round_monetary(to_decimal(self.avg_price))
        self.total_cost = round_monetary(to_decimal(self.total_cost))

    @property
    def is_open(self) -> bool:
        return self.quantity > Decimal("0")

    @property
    def market_key(self) -> str:
        """Unique key for grouping: ticker@institution."""
        return f"{self.ticker}@{self.institution}"

    def compute_hash(self) -> str:
        data = {
            "ticker": self.ticker,
            "asset_class": self.asset_class,
            "quantity": self.quantity,
            "avg_price": self.avg_price,
            "currency": self.currency,
            "total_cost": self.total_cost,
            "institution": self.institution,
        }
        return compute_consistency_hash(data)

    def seal(self) -> None:
        self.consistency_hash = self.compute_hash()


@dataclass
class TaxLoss:
    """Accumulated tax losses carried forward, per asset class + trade type."""

    asset_class: AssetClass
    trade_type: TradeType
    accumulated_loss: Decimal   # positive value = loss to offset
    month_ref: str              # YYYY-MM
    id: Optional[int] = None

    def __post_init__(self) -> None:
        self.accumulated_loss = round_monetary(to_decimal(self.accumulated_loss))


@dataclass
class PortfolioCustodian:
    """Which broker/bank holds each asset."""

    ticker: str
    institution: str
    quantity: Decimal
    id: Optional[int] = None

    def __post_init__(self) -> None:
        self.quantity = to_decimal(self.quantity)


@dataclass
class AuditLogEntry:
    """Immutable audit record for every DB mutation."""

    table_name: str
    record_id: int
    action: str                 # INSERT / UPDATE / DELETE
    old_data: Optional[str] = None   # JSON
    new_data: Optional[str] = None   # JSON
    timestamp: Optional[datetime] = field(default_factory=datetime.utcnow)
    id: Optional[int] = None


@dataclass
class TaxResult:
    """Result of monthly tax calculation."""

    month_ref: str
    asset_class: AssetClass
    trade_type: TradeType
    gross_gain: Decimal
    accumulated_loss_before: Decimal
    taxable_gain: Decimal
    tax_rate: Decimal
    tax_due: Decimal
    irrf_withheld: Decimal
    darf_to_pay: Decimal
    accumulated_loss_after: Decimal

    def __post_init__(self) -> None:
        for attr in (
            "gross_gain", "accumulated_loss_before", "taxable_gain",
            "tax_due", "irrf_withheld", "darf_to_pay", "accumulated_loss_after",
        ):
            setattr(self, attr, round_monetary(to_decimal(getattr(self, attr))))
