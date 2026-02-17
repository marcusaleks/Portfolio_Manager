"""Application use cases — orchestration of domain and infrastructure."""

from __future__ import annotations

import csv
import io
import logging
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from domain.entities import (
    PortfolioCustodian, Position, Transaction, TaxResult,
)
from domain.enums import (
    AssetClass, Currency, TradeType, TransactionType,
)
from domain.value_objects import round_monetary, to_decimal
from application.position_calculator import PositionCalculator, SaleResult
from application.tax_calculator import TaxCalculatorBR
from infrastructure.repositories import (
    CustodianRepository,
    PositionRepository,
    SettingsRepository,
    TaxLossRepository,
    TransactionRepository,
)

log = logging.getLogger(__name__)

ZERO = Decimal("0")


# ═══════════════════════════════════════════════════════════════════════════
# RebuildAll
# ═══════════════════════════════════════════════════════════════════════════

class RebuildAllUseCase:
    """Drops position cache & tax losses, then reprocesses everything
    from the transactions table (the single source of truth)."""

    def execute(self, session) -> dict:
        """Returns summary dict with counts."""
        # 1. Clear derived tables
        PositionRepository.clear_all(session)
        TaxLossRepository.clear_all(session)

        # 2. Load all transactions ordered by date
        transactions = TransactionRepository.get_all(session)
        if not transactions:
            return {"transactions": 0, "positions": 0, "tax_results": 0}

        # 3. Rebuild positions via PositionCalculator
        calc = PositionCalculator()
        sale_results: list[SaleResult] = []
        for tx in transactions:
            sr = calc.process(tx)
            if sr is not None:
                sale_results.append(sr)

        # Persist positions
        for pos in calc.get_positions():
            PositionRepository.upsert(session, pos)

        # 4. Rebuild custodians
        custodians = self._build_custodians(calc.get_open_positions())
        CustodianRepository.rebuild(session, custodians)

        # 5. Rebuild tax losses month by month
        tax_calc = TaxCalculatorBR()
        acc_losses: dict[tuple[AssetClass, TradeType], Decimal] = defaultdict(lambda: ZERO)
        sales_by_month: dict[str, list[SaleResult]] = defaultdict(list)
        for sr in sale_results:
            month = sr.date.strftime("%Y-%m")
            sales_by_month[month].append(sr)

        tax_results_total = 0
        for month in sorted(sales_by_month.keys()):
            results = tax_calc.calculate_monthly_tax(
                sales_by_month[month], acc_losses, month
            )
            for tr in results:
                TaxLossRepository.upsert(
                    session, tr.asset_class, tr.trade_type,
                    tr.accumulated_loss_after, tr.month_ref,
                )
                tax_results_total += 1

        # 6. Store rebuild timestamp
        SettingsRepository.set(
            session, "last_rebuild", datetime.utcnow().isoformat()
        )

        return {
            "transactions": len(transactions),
            "positions": len(calc.get_positions()),
            "tax_results": tax_results_total,
        }

    @staticmethod
    def _build_custodians(positions: list[Position]) -> list[PortfolioCustodian]:
        return [
            PortfolioCustodian(
                ticker=p.ticker,
                institution=p.institution,
                quantity=p.quantity,
            )
            for p in positions
            if p.quantity > ZERO
        ]


# ═══════════════════════════════════════════════════════════════════════════
# SaveTransaction
# ═══════════════════════════════════════════════════════════════════════════

class SaveTransactionUseCase:
    """Validates and persists a single transaction, updating caches."""

    def __init__(self, tax_strict_mode: bool = False) -> None:
        self._strict = tax_strict_mode

    def execute(self, session, tx: Transaction) -> int:
        """Save (insert or update) a transaction.
        Returns the transaction ID.
        """
        import logging
        _log = logging.getLogger(__name__)

        # Tax Strict Mode check
        if self._strict and tx.currency == Currency.USD:
            if tx.fx_rate <= ZERO:
                raise ValueError(
                    "Tax Strict Mode: taxa FX (PTAX) obrigatória para "
                    "transações em USD."
                )

        # ── Sell validation (against position AT the sell date) ────────
        if tx.type == TransactionType.SELL:
            self._validate_sell_at_date(session, tx, _log)

        if tx.id is None:
            tx_id = TransactionRepository.insert(session, tx)
        else:
            TransactionRepository.update(session, tx)
            tx_id = tx.id

        # Recalculate positions for this ticker+institution
        self._recalc_and_update_custody(session, tx.ticker, tx.institution, _log)
        return tx_id

    @staticmethod
    def _validate_sell_at_date(session, tx: Transaction, _log) -> None:
        """Validate sell against the position AT the sell date.

        We replay all existing transactions for this ticker@institution
        up to (and including) the sell date, to compute the position that
        would exist at that point in time.  Then we check if the sell
        quantity is feasible.
        """
        _log.info(
            "SELL VALIDATION: %s qty=%s date=%s inst='%s'",
            tx.ticker, tx.quantity, tx.date, tx.institution,
        )

        # Get all existing transactions for this ticker at this institution
        all_tx = TransactionRepository.get_by_ticker(session, tx.ticker)
        inst_tx = sorted(
            [t for t in all_tx if t.institution == tx.institution],
            key=lambda t: (t.date, t.id or 0),
        )

        if not inst_tx:
            raise ValueError(
                f"Não há nenhuma operação de {tx.ticker} na instituição "
                f"'{tx.institution}'. Não é possível vender."
            )

        # Replay transactions up to the sell date to get position at that point
        calc = PositionCalculator()
        for t in inst_tx:
            if t.date <= tx.date:
                calc.process(t)

        # Check the position at the sell date
        positions = calc.get_positions()
        pos_qty = ZERO
        for p in positions:
            if p.institution == tx.institution:
                pos_qty = p.quantity

        _log.info(
            "SELL VALIDATION at date %s: position_qty=%s, sell_qty=%s",
            tx.date, pos_qty, tx.quantity,
        )

        if pos_qty <= ZERO:
            raise ValueError(
                f"Não há posição de {tx.ticker} na instituição "
                f"'{tx.institution}' na data {tx.date.strftime('%d/%m/%Y')}. "
                f"Não é possível vender."
            )
        if tx.quantity > pos_qty:
            raise ValueError(
                f"Quantidade de venda ({tx.quantity}) excede a posição "
                f"disponível ({pos_qty}) de {tx.ticker} em "
                f"'{tx.institution}' na data {tx.date.strftime('%d/%m/%Y')}."
            )

    @staticmethod
    def _recalc_and_update_custody(
        session, ticker: str, institution: str, _log
    ) -> None:
        """Recompute positions for ALL institutions of *ticker* and
        update the custodians table so the custody view is always fresh.

        When a buy with an earlier date is inserted the average price
        changes, so we must replay every transaction of this ticker —
        across all institutions — in chronological order.
        """
        all_tx = TransactionRepository.get_by_ticker(session, ticker)
        # all_tx is already sorted by (date, id) from the repository

        calc = PositionCalculator()
        for t in all_tx:
            calc.process(t)

        for pos in calc.get_positions():
            PositionRepository.upsert(session, pos)

        _log.info(
            "Recalculated %d position(s) for ticker %s",
            len(calc.get_positions()), ticker,
        )

        # Also rebuild custodians for ALL tickers (keeps custody view fresh)
        all_positions = PositionRepository.get_open(session)
        custodians = []
        for p in all_positions:
            custodians.append(
                PortfolioCustodian(
                    ticker=p.ticker,
                    institution=p.institution,
                    quantity=p.quantity,
                )
            )
        CustodianRepository.rebuild(session, custodians)
        _log.info(
            "Updated %d custodian record(s) after saving %s@%s",
            len(custodians), ticker, institution,
        )


# ═══════════════════════════════════════════════════════════════════════════
# ImportB3Csv
# ═══════════════════════════════════════════════════════════════════════════

class ImportB3CsvUseCase:
    """Parses a B3-style CSV and returns a preview for user confirmation."""

    EXPECTED_HEADERS = {
        "Data do Negócio", "Tipo de Movimentação", "Código de Negociação",
        "Quantidade", "Preço", "Valor",
    }

    def parse_preview(self, file_path: str) -> list[Transaction]:
        """Parse CSV and return unsaved Transaction objects for preview."""
        transactions: list[Transaction] = []
        with open(file_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f, delimiter=";")
            for row in reader:
                try:
                    tx = self._row_to_transaction(row)
                    transactions.append(tx)
                except Exception as e:
                    log.warning("Skipping CSV row: %s — %s", row, e)
        return transactions

    def persist(self, session, transactions: list[Transaction]) -> int:
        """Persist confirmed transactions. Returns count of inserted."""
        count = 0
        for tx in transactions:
            TransactionRepository.insert(session, tx)
            count += 1
        return count

    @staticmethod
    def _row_to_transaction(row: dict) -> Transaction:
        """Convert a CSV row dict to a Transaction entity."""
        raw_date = row.get("Data do Negócio", "").strip()
        tx_date = datetime.strptime(raw_date, "%d/%m/%Y").date()

        raw_type = row.get("Tipo de Movimentação", "").strip().upper()
        tx_type = TransactionType.BUY if "COMPRA" in raw_type else TransactionType.SELL

        ticker = row.get("Código de Negociação", "").strip().upper()

        qty_str = row.get("Quantidade", "0").strip().replace(".", "").replace(",", ".")
        price_str = row.get("Preço", "0").strip().replace(".", "").replace(",", ".")

        quantity = to_decimal(qty_str)
        price = to_decimal(price_str)

        institution = row.get("Instituição", "").strip() or "B3"

        return Transaction(
            ticker=ticker,
            asset_class=AssetClass.ACAO,  # default; user can adjust
            type=tx_type,
            trade_type=TradeType.SWING_TRADE,  # default
            date=tx_date,
            quantity=quantity,
            price=price,
            currency=Currency.BRL,
            fx_rate=Decimal("1"),
            institution=institution,
        )


# ═══════════════════════════════════════════════════════════════════════════
# DetectCorporateAction
# ═══════════════════════════════════════════════════════════════════════════

class DetectCorporateActionUseCase:
    """Flags tickers where current price deviates >30% from avg_price."""

    def __init__(self, price_provider) -> None:
        self._provider = price_provider

    def check_all(self, session) -> list[str]:
        """Returns list of warning messages for suspicious price moves."""
        positions = PositionRepository.get_all(session)
        warnings: list[str] = []
        for pos in positions:
            if pos.quantity <= ZERO or pos.avg_price <= ZERO:
                continue
            msg = self._provider.detect_corporate_action(
                pos.ticker, pos.avg_price
            )
            if msg:
                warnings.append(msg)
        return warnings
