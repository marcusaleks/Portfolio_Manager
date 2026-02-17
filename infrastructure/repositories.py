"""Repositories — data access layer for all domain entities."""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, Sequence

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from domain.entities import (
    AuditLogEntry, PortfolioCustodian, Position, TaxLoss, Transaction,
)
from domain.enums import AssetClass, Currency, TradeType, TransactionType
from infrastructure.database import (
    AuditLogModel, InstitutionModel, PortfolioCustodianModel, PositionModel,
    TaxLossModel, TransactionModel,
)


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _tx_model_to_entity(m: TransactionModel) -> Transaction:
    return Transaction(
        id=m.id,
        ticker=m.ticker,
        asset_class=AssetClass(m.asset_class),
        type=TransactionType(m.type),
        trade_type=TradeType(m.trade_type),
        date=m.date,
        quantity=m.quantity,
        price=m.price,
        currency=Currency(m.currency),
        fx_rate=m.fx_rate,
        institution=m.institution,
        notes=m.notes,
        consistency_hash=m.consistency_hash,
        created_at=m.created_at,
    )


def _tx_entity_to_model(e: Transaction) -> TransactionModel:
    return TransactionModel(
        id=e.id,
        ticker=e.ticker,
        asset_class=e.asset_class.value,
        type=e.type.value,
        trade_type=e.trade_type.value,
        date=e.date,
        quantity=e.quantity,
        price=e.price,
        currency=e.currency.value,
        fx_rate=e.fx_rate,
        institution=e.institution,
        notes=e.notes,
        consistency_hash=e.consistency_hash,
        created_at=e.created_at or datetime.utcnow(),
    )


def _pos_model_to_entity(m: PositionModel) -> Position:
    return Position(
        id=m.id,
        ticker=m.ticker,
        asset_class=AssetClass(m.asset_class),
        quantity=m.quantity,
        avg_price=m.avg_price,
        currency=Currency(m.currency),
        total_cost=m.total_cost,
        institution=m.institution,
        consistency_hash=m.consistency_hash,
    )


def _pos_entity_to_model(e: Position) -> PositionModel:
    return PositionModel(
        id=e.id,
        ticker=e.ticker,
        asset_class=e.asset_class.value,
        quantity=e.quantity,
        avg_price=e.avg_price,
        currency=e.currency.value,
        total_cost=e.total_cost,
        institution=e.institution,
        consistency_hash=e.consistency_hash,
    )


# ═══════════════════════════════════════════════════════════════════════════
# TransactionRepository
# ═══════════════════════════════════════════════════════════════════════════

class TransactionRepository:
    """CRUD + query operations for transactions."""

    # ── reads (can use any session) ────────────────────────────────────

    @staticmethod
    def get_all(session: Session) -> list[Transaction]:
        rows = session.execute(
            select(TransactionModel).order_by(TransactionModel.date, TransactionModel.id)
        ).scalars().all()
        return [_tx_model_to_entity(r) for r in rows]

    @staticmethod
    def get_by_ticker(session: Session, ticker: str) -> list[Transaction]:
        rows = session.execute(
            select(TransactionModel)
            .where(TransactionModel.ticker == ticker)
            .order_by(TransactionModel.date, TransactionModel.id)
        ).scalars().all()
        return [_tx_model_to_entity(r) for r in rows]

    @staticmethod
    def get_by_date_range(
        session: Session, start: date, end: date
    ) -> list[Transaction]:
        rows = session.execute(
            select(TransactionModel)
            .where(TransactionModel.date.between(start, end))
            .order_by(TransactionModel.date, TransactionModel.id)
        ).scalars().all()
        return [_tx_model_to_entity(r) for r in rows]

    @staticmethod
    def get_by_institution(session: Session, institution: str) -> list[Transaction]:
        rows = session.execute(
            select(TransactionModel)
            .where(TransactionModel.institution == institution)
            .order_by(TransactionModel.date, TransactionModel.id)
        ).scalars().all()
        return [_tx_model_to_entity(r) for r in rows]

    @staticmethod
    def get_by_id(session: Session, tx_id: int) -> Optional[Transaction]:
        m = session.get(TransactionModel, tx_id)
        return _tx_model_to_entity(m) if m else None

    @staticmethod
    def get_distinct_tickers(session: Session) -> list[str]:
        rows = session.execute(
            select(TransactionModel.ticker).distinct().order_by(TransactionModel.ticker)
        ).scalars().all()
        return list(rows)

    @staticmethod
    def get_distinct_institutions(session: Session) -> list[str]:
        rows = session.execute(
            select(TransactionModel.institution)
            .distinct()
            .order_by(TransactionModel.institution)
        ).scalars().all()
        return [r for r in rows if r]

    # ── writes (should be called via WriteQueueManager) ────────────────

    @staticmethod
    def insert(session: Session, tx: Transaction) -> int:
        tx.seal()
        model = _tx_entity_to_model(tx)
        model.id = None  # auto-increment
        session.add(model)
        session.flush()
        AuditLogRepository.log_action(
            session, "transactions", model.id, "INSERT", new_data=_model_to_json(model)
        )
        return model.id

    @staticmethod
    def update(session: Session, tx: Transaction) -> None:
        model = session.get(TransactionModel, tx.id)
        if not model:
            raise ValueError(f"Transaction {tx.id} not found")
        old_json = _model_to_json(model)
        tx.seal()
        model.ticker = tx.ticker
        model.asset_class = tx.asset_class.value
        model.type = tx.type.value
        model.trade_type = tx.trade_type.value
        model.date = tx.date
        model.quantity = tx.quantity
        model.price = tx.price
        model.currency = tx.currency.value
        model.fx_rate = tx.fx_rate
        model.institution = tx.institution
        model.notes = tx.notes
        model.consistency_hash = tx.consistency_hash
        session.flush()
        AuditLogRepository.log_action(
            session, "transactions", model.id, "UPDATE",
            old_data=old_json, new_data=_model_to_json(model),
        )

    @staticmethod
    def delete(session: Session, tx_id: int) -> None:
        model = session.get(TransactionModel, tx_id)
        if model:
            old_json = _model_to_json(model)
            session.delete(model)
            session.flush()
            AuditLogRepository.log_action(
                session, "transactions", tx_id, "DELETE", old_data=old_json,
            )


# ═══════════════════════════════════════════════════════════════════════════
# PositionRepository
# ═══════════════════════════════════════════════════════════════════════════

class PositionRepository:

    @staticmethod
    def get_all(session: Session) -> list[Position]:
        rows = session.execute(
            select(PositionModel).order_by(PositionModel.ticker)
        ).scalars().all()
        return [_pos_model_to_entity(r) for r in rows]

    @staticmethod
    def get_open(session: Session) -> list[Position]:
        """Return only positions with quantity > 0."""
        rows = session.execute(
            select(PositionModel)
            .where(PositionModel.quantity > 0)
            .order_by(PositionModel.ticker)
        ).scalars().all()
        return [_pos_model_to_entity(r) for r in rows]

    @staticmethod
    def get_by_ticker(session: Session, ticker: str) -> list[Position]:
        rows = session.execute(
            select(PositionModel).where(PositionModel.ticker == ticker)
        ).scalars().all()
        return [_pos_model_to_entity(r) for r in rows]

    @staticmethod
    def get_position_at_institution(
        session: Session, ticker: str, institution: str
    ) -> Position | None:
        """Return position for a ticker at a specific institution (or None)."""
        row = session.execute(
            select(PositionModel).where(
                PositionModel.ticker == ticker,
                PositionModel.institution == institution,
            )
        ).scalar_one_or_none()
        return _pos_model_to_entity(row) if row else None

    @staticmethod
    def clear_all(session: Session) -> None:
        session.execute(delete(PositionModel))
        session.flush()

    @staticmethod
    def upsert(session: Session, pos: Position) -> None:
        pos.seal()
        existing = session.execute(
            select(PositionModel).where(
                PositionModel.ticker == pos.ticker,
                PositionModel.institution == pos.institution,
            )
        ).scalar_one_or_none()
        if existing:
            existing.quantity = pos.quantity
            existing.avg_price = pos.avg_price
            existing.total_cost = pos.total_cost
            existing.asset_class = pos.asset_class.value
            existing.currency = pos.currency.value
            existing.consistency_hash = pos.consistency_hash
        else:
            model = _pos_entity_to_model(pos)
            model.id = None
            session.add(model)
        session.flush()


# ═══════════════════════════════════════════════════════════════════════════
# TaxLossRepository
# ═══════════════════════════════════════════════════════════════════════════

class TaxLossRepository:

    @staticmethod
    def get_latest(
        session: Session, asset_class: AssetClass, trade_type: TradeType
    ) -> Decimal:
        """Return the latest accumulated loss (or 0)."""
        row = session.execute(
            select(TaxLossModel)
            .where(
                TaxLossModel.asset_class == asset_class.value,
                TaxLossModel.trade_type == trade_type.value,
            )
            .order_by(TaxLossModel.month_ref.desc())
            .limit(1)
        ).scalar_one_or_none()
        return row.accumulated_loss if row else Decimal("0")

    @staticmethod
    def upsert(
        session: Session,
        asset_class: AssetClass,
        trade_type: TradeType,
        accumulated_loss: Decimal,
        month_ref: str,
    ) -> None:
        existing = session.execute(
            select(TaxLossModel).where(
                TaxLossModel.asset_class == asset_class.value,
                TaxLossModel.trade_type == trade_type.value,
                TaxLossModel.month_ref == month_ref,
            )
        ).scalar_one_or_none()
        if existing:
            existing.accumulated_loss = accumulated_loss
        else:
            session.add(TaxLossModel(
                asset_class=asset_class.value,
                trade_type=trade_type.value,
                accumulated_loss=accumulated_loss,
                month_ref=month_ref,
            ))
        session.flush()

    @staticmethod
    def clear_all(session: Session) -> None:
        session.execute(delete(TaxLossModel))
        session.flush()


# ═══════════════════════════════════════════════════════════════════════════
# CustodianRepository
# ═══════════════════════════════════════════════════════════════════════════

class CustodianRepository:

    @staticmethod
    def get_all(session: Session) -> list[PortfolioCustodian]:
        rows = session.execute(
            select(PortfolioCustodianModel)
            .order_by(PortfolioCustodianModel.institution, PortfolioCustodianModel.ticker)
        ).scalars().all()
        return [
            PortfolioCustodian(
                id=r.id, ticker=r.ticker, institution=r.institution, quantity=r.quantity,
            )
            for r in rows
        ]

    @staticmethod
    def rebuild(session: Session, custodians: list[PortfolioCustodian]) -> None:
        session.execute(delete(PortfolioCustodianModel))
        for c in custodians:
            session.add(PortfolioCustodianModel(
                ticker=c.ticker, institution=c.institution, quantity=c.quantity,
            ))
        session.flush()


# ═══════════════════════════════════════════════════════════════════════════
# AuditLogRepository
# ═══════════════════════════════════════════════════════════════════════════

class AuditLogRepository:

    @staticmethod
    def log_action(
        session: Session,
        table_name: str,
        record_id: int,
        action: str,
        old_data: str | None = None,
        new_data: str | None = None,
    ) -> None:
        session.add(AuditLogModel(
            table_name=table_name,
            record_id=record_id,
            action=action,
            old_data=old_data,
            new_data=new_data,
            timestamp=datetime.utcnow(),
        ))

    @staticmethod
    def get_recent(session: Session, limit: int = 100) -> list[AuditLogEntry]:
        rows = session.execute(
            select(AuditLogModel)
            .order_by(AuditLogModel.timestamp.desc())
            .limit(limit)
        ).scalars().all()
        return [
            AuditLogEntry(
                id=r.id, table_name=r.table_name, record_id=r.record_id,
                action=r.action, old_data=r.old_data, new_data=r.new_data,
                timestamp=r.timestamp,
            )
            for r in rows
        ]


# ═══════════════════════════════════════════════════════════════════════════
# InstitutionRepository
# ═══════════════════════════════════════════════════════════════════════════

class InstitutionRepository:

    @staticmethod
    def get_all(session: Session) -> list[dict]:
        """Return all institutions as dicts with id, name, cnpj, active."""
        rows = session.execute(
            select(InstitutionModel).order_by(InstitutionModel.name)
        ).scalars().all()
        return [
            {"id": r.id, "name": r.name, "cnpj": r.cnpj, "active": bool(r.active)}
            for r in rows
        ]

    @staticmethod
    def get_active_names(session: Session) -> list[str]:
        """Return names of active institutions."""
        rows = session.execute(
            select(InstitutionModel.name)
            .where(InstitutionModel.active == 1)
            .order_by(InstitutionModel.name)
        ).scalars().all()
        return list(rows)

    @staticmethod
    def add(session: Session, name: str, cnpj: str = "") -> int:
        existing = session.execute(
            select(InstitutionModel).where(InstitutionModel.name == name)
        ).scalar_one_or_none()
        if existing:
            raise ValueError(f"Instituição '{name}' já existe.")
        m = InstitutionModel(name=name, cnpj=cnpj, active=1)
        session.add(m)
        session.flush()
        return m.id

    @staticmethod
    def delete(session: Session, inst_id: int) -> None:
        m = session.get(InstitutionModel, inst_id)
        if m:
            session.delete(m)
            session.flush()

    @staticmethod
    def seed_defaults(session: Session) -> None:
        """Seed default institutions if the table is empty."""
        count = session.execute(
            select(InstitutionModel)
        ).scalars().first()
        if count is not None:
            return  # already seeded
        defaults = [
            "XP Investimentos", "BTG Pactual", "Rico", "Clear",
            "Nu Invest", "Inter", "Itaú", "Bradesco", "Modal",
        ]
        for name in defaults:
            session.add(InstitutionModel(name=name, cnpj="", active=1))
        session.flush()


# ═══════════════════════════════════════════════════════════════════════════
# Settings helpers
# ═══════════════════════════════════════════════════════════════════════════

class SettingsRepository:

    @staticmethod
    def get(session: Session, key: str, default: str = "") -> str:
        from infrastructure.database import AppSettingsModel
        row = session.execute(
            select(AppSettingsModel).where(AppSettingsModel.key == key)
        ).scalar_one_or_none()
        return row.value if row else default

    @staticmethod
    def set(session: Session, key: str, value: str) -> None:
        from infrastructure.database import AppSettingsModel
        row = session.execute(
            select(AppSettingsModel).where(AppSettingsModel.key == key)
        ).scalar_one_or_none()
        if row:
            row.value = value
        else:
            session.add(AppSettingsModel(key=key, value=value))
        session.flush()


# ═══════════════════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════════════════

def _decimal_default(obj):
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    raise TypeError(f"Not serializable: {type(obj)}")


def _model_to_json(model) -> str:
    data = {
        c.name: getattr(model, c.name)
        for c in model.__table__.columns
    }
    return json.dumps(data, default=_decimal_default, sort_keys=True)
