"""Tests for RebuildAll use case."""

import pytest
from datetime import date
from decimal import Decimal

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from domain.entities import Transaction
from domain.enums import AssetClass, Currency, TradeType, TransactionType
from infrastructure.database import Base, create_db_engine, make_session_factory, create_tables
from infrastructure.repositories import TransactionRepository, PositionRepository
from application.use_cases import RebuildAllUseCase


@pytest.fixture
def session():
    """In-memory SQLite session for testing."""
    engine = create_db_engine(":memory:")
    create_tables(engine)
    factory = make_session_factory(engine)
    sess = factory()
    yield sess
    sess.close()


def _insert_tx(session, ticker, tx_type, qty, price, tx_date, institution="XP"):
    tx = Transaction(
        ticker=ticker,
        asset_class=AssetClass.ACAO,
        type=tx_type,
        trade_type=TradeType.SWING_TRADE,
        date=tx_date,
        quantity=Decimal(str(qty)),
        price=Decimal(str(price)),
        currency=Currency.BRL,
        fx_rate=Decimal("1"),
        institution=institution,
    )
    TransactionRepository.insert(session, tx)
    session.commit()


class TestRebuildAll:
    def test_rebuild_produces_correct_positions(self, session):
        _insert_tx(session, "PETR4", TransactionType.BUY, 100, "30.00", date(2025, 1, 10))
        _insert_tx(session, "PETR4", TransactionType.BUY, 50, "36.00", date(2025, 2, 10))
        _insert_tx(session, "VALE3", TransactionType.BUY, 200, "65.00", date(2025, 1, 15))

        uc = RebuildAllUseCase()
        result = uc.execute(session)
        session.commit()

        assert result["transactions"] == 3
        assert result["positions"] == 2

        positions = PositionRepository.get_all(session)
        by_ticker = {p.ticker: p for p in positions}

        petr = by_ticker["PETR4"]
        assert petr.quantity == Decimal("150")
        assert petr.avg_price == Decimal("32.00")
        assert petr.total_cost == Decimal("4800.00")

        vale = by_ticker["VALE3"]
        assert vale.quantity == Decimal("200")
        assert vale.avg_price == Decimal("65.00")

    def test_rebuild_idempotent(self, session):
        _insert_tx(session, "PETR4", TransactionType.BUY, 100, "30.00", date(2025, 1, 10))
        _insert_tx(session, "PETR4", TransactionType.SELL, 50, "35.00", date(2025, 2, 10))

        uc = RebuildAllUseCase()

        # First rebuild
        r1 = uc.execute(session)
        session.commit()
        pos1 = PositionRepository.get_all(session)

        # Second rebuild
        r2 = uc.execute(session)
        session.commit()
        pos2 = PositionRepository.get_all(session)

        assert len(pos1) == len(pos2)
        for p1, p2 in zip(pos1, pos2):
            assert p1.ticker == p2.ticker
            assert p1.quantity == p2.quantity
            assert p1.avg_price == p2.avg_price
            assert p1.consistency_hash == p2.consistency_hash
