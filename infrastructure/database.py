"""Database engine, session factory, and ORM models (SQLAlchemy 2.0+)."""

from __future__ import annotations

import os
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Column, Date, DateTime, Enum as SAEnum, Integer, Numeric, String, Text,
    create_engine, event, Index,
)
from sqlalchemy.orm import (
    DeclarativeBase, Mapped, Session, mapped_column, sessionmaker,
)


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# ORM Models
# ---------------------------------------------------------------------------

class TransactionModel(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    asset_class: Mapped[str] = mapped_column(String(20), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    trade_type: Mapped[str] = mapped_column(String(20), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="BRL")
    fx_rate: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False, default=1)
    institution: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    consistency_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )

    __table_args__ = (
        Index("ix_transactions_ticker_date", "ticker", "date"),
    )


class PositionModel(Base):
    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    asset_class: Mapped[str] = mapped_column(String(20), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    avg_price: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="BRL")
    total_cost: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    institution: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    consistency_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")

    __table_args__ = (
        Index("ix_positions_ticker_inst", "ticker", "institution"),
    )


class TaxLossModel(Base):
    __tablename__ = "tax_losses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_class: Mapped[str] = mapped_column(String(20), nullable=False)
    trade_type: Mapped[str] = mapped_column(String(20), nullable=False)
    accumulated_loss: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=0)
    month_ref: Mapped[str] = mapped_column(String(7), nullable=False)  # YYYY-MM

    __table_args__ = (
        Index("ix_tax_losses_ref", "asset_class", "trade_type", "month_ref"),
    )


class PortfolioCustodianModel(Base):
    __tablename__ = "portfolio_custodians"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    institution: Mapped[str] = mapped_column(String(100), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)


class AuditLogModel(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    table_name: Mapped[str] = mapped_column(String(50), nullable=False)
    record_id: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(10), nullable=False)
    old_data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    new_data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )


class AppSettingsModel(Base):
    """Simple key-value settings store."""
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False, default="")


class InstitutionModel(Base):
    """Registered institutions (custodians/brokers)."""
    __tablename__ = "institutions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    cnpj: Mapped[str] = mapped_column(String(18), nullable=False, default="")
    active: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


# ---------------------------------------------------------------------------
# Engine and session factory
# ---------------------------------------------------------------------------

_DB_DIR = os.path.join(os.path.expanduser("~"), ".portfolio_v3")
_DB_PATH = os.path.join(_DB_DIR, "portfolio.db")


def get_db_path() -> str:
    return _DB_PATH


def _set_wal_mode(dbapi_conn, connection_record):
    """Enable WAL journal mode for better concurrency."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def create_db_engine(db_path: str | None = None):
    """Create the SQLAlchemy engine with WAL mode enabled."""
    path = db_path or _DB_PATH
    is_memory = path == ":memory:"
    if not is_memory:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    url = "sqlite:///:memory:" if is_memory else f"sqlite:///{path}"
    engine = create_engine(url, echo=False)
    if not is_memory:
        event.listen(engine, "connect", _set_wal_mode)
    return engine


def create_tables(engine) -> None:
    """Create all tables if they don't exist."""
    Base.metadata.create_all(engine)


def make_session_factory(engine) -> sessionmaker:
    return sessionmaker(bind=engine, expire_on_commit=False)
