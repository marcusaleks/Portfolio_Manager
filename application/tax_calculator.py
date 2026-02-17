"""TaxCalculatorBR — Brazilian income tax on capital gains (IR)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from domain.entities import TaxResult
from domain.enums import AssetClass, TradeType
from domain.value_objects import round_monetary

ZERO = Decimal("0")

# ── Tax rates ──────────────────────────────────────────────────────────

SWING_TRADE_RATE = Decimal("0.15")    # 15 %
DAY_TRADE_RATE   = Decimal("0.20")    # 20 %

# IRRF (dedo-duro)
IRRF_SWING_RATE  = Decimal("0.00005") # 0,005 % sobre valor da venda
IRRF_DAY_RATE    = Decimal("0.01")    # 1 % sobre o ganho

# Isenção mensal de alienações de ações (swing trade)
MONTHLY_EXEMPTION_LIMIT = Decimal("20000.00")


class TaxCalculatorBR:
    """Calcula o imposto de renda sobre ganho de capital no Brasil.

    Regras implementadas:
    - Separação Day Trade vs Swing Trade.
    - IRRF (dedo-duro): 0,005 % valor venda (swing); 1 % ganho (day trade).
    - DARF = imposto_devido - IRRF retido.
    - Prejuízo acumulado por classe de ativo + tipo de trade, carry-forward.
    - Isenção mensal de R$20.000 em alienações de ações (swing trade).
    """

    def calculate_monthly_tax(
        self,
        sale_results: list,          # list[SaleResult]
        accumulated_losses: dict,    # {(AssetClass, TradeType): Decimal}
        month_ref: str,              # YYYY-MM
    ) -> list[TaxResult]:
        """Compute taxes for all sales in a given month.

        Returns a list of TaxResult objects and **mutates** accumulated_losses
        in-place to carry forward updated values.
        """
        # Group sales by (asset_class, trade_type)
        groups: dict[tuple[AssetClass, TradeType], list] = defaultdict(list)
        for sr in sale_results:
            groups[(sr.asset_class, sr.trade_type)].append(sr)

        results: list[TaxResult] = []

        for (asset_class, trade_type), sales in groups.items():
            total_gain_brl = sum(sr.gain_loss_brl for sr in sales)
            total_proceeds_brl = sum(sr.proceeds_brl for sr in sales)

            # Check monthly exemption for ações (swing trade only)
            if (
                trade_type == TradeType.SWING_TRADE
                and asset_class == AssetClass.ACAO
                and total_proceeds_brl <= MONTHLY_EXEMPTION_LIMIT
            ):
                # Exempt — no tax, but losses are NOT offset
                results.append(TaxResult(
                    month_ref=month_ref,
                    asset_class=asset_class,
                    trade_type=trade_type,
                    gross_gain=total_gain_brl,
                    accumulated_loss_before=accumulated_losses.get(
                        (asset_class, trade_type), ZERO
                    ),
                    taxable_gain=ZERO,
                    tax_rate=SWING_TRADE_RATE,
                    tax_due=ZERO,
                    irrf_withheld=ZERO,
                    darf_to_pay=ZERO,
                    accumulated_loss_after=accumulated_losses.get(
                        (asset_class, trade_type), ZERO
                    ),
                ))
                continue

            # Accumulated loss carry-forward
            loss_key = (asset_class, trade_type)
            acc_loss = accumulated_losses.get(loss_key, ZERO)

            if total_gain_brl < ZERO:
                # Month had a net LOSS → accumulate
                new_acc_loss = round_monetary(acc_loss + abs(total_gain_brl))
                accumulated_losses[loss_key] = new_acc_loss
                results.append(TaxResult(
                    month_ref=month_ref,
                    asset_class=asset_class,
                    trade_type=trade_type,
                    gross_gain=total_gain_brl,
                    accumulated_loss_before=acc_loss,
                    taxable_gain=ZERO,
                    tax_rate=self._rate(trade_type),
                    tax_due=ZERO,
                    irrf_withheld=ZERO,
                    darf_to_pay=ZERO,
                    accumulated_loss_after=new_acc_loss,
                ))
                continue

            # Net gain — offset with accumulated losses
            taxable = round_monetary(total_gain_brl - acc_loss)
            if taxable < ZERO:
                # Still has remaining loss
                remaining_loss = round_monetary(abs(taxable))
                accumulated_losses[loss_key] = remaining_loss
                results.append(TaxResult(
                    month_ref=month_ref,
                    asset_class=asset_class,
                    trade_type=trade_type,
                    gross_gain=total_gain_brl,
                    accumulated_loss_before=acc_loss,
                    taxable_gain=ZERO,
                    tax_rate=self._rate(trade_type),
                    tax_due=ZERO,
                    irrf_withheld=ZERO,
                    darf_to_pay=ZERO,
                    accumulated_loss_after=remaining_loss,
                ))
                continue

            # Taxable gain exists
            accumulated_losses[loss_key] = ZERO
            rate = self._rate(trade_type)
            tax_due = round_monetary(taxable * rate)

            # IRRF (dedo-duro)
            irrf = self._compute_irrf(
                trade_type, total_proceeds_brl, total_gain_brl
            )

            darf = round_monetary(max(tax_due - irrf, ZERO))

            results.append(TaxResult(
                month_ref=month_ref,
                asset_class=asset_class,
                trade_type=trade_type,
                gross_gain=total_gain_brl,
                accumulated_loss_before=acc_loss,
                taxable_gain=taxable,
                tax_rate=rate,
                tax_due=tax_due,
                irrf_withheld=irrf,
                darf_to_pay=darf,
                accumulated_loss_after=ZERO,
            ))

        return results

    # ── helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _rate(trade_type: TradeType) -> Decimal:
        return DAY_TRADE_RATE if trade_type == TradeType.DAY_TRADE else SWING_TRADE_RATE

    @staticmethod
    def _compute_irrf(
        trade_type: TradeType,
        total_proceeds_brl: Decimal,
        total_gain_brl: Decimal,
    ) -> Decimal:
        """IRRF (dedo-duro):
        - Swing Trade: 0,005 % sobre valor da venda.
        - Day Trade:   1 % sobre o ganho líquido (se positivo).
        """
        if trade_type == TradeType.DAY_TRADE:
            if total_gain_brl > ZERO:
                return round_monetary(total_gain_brl * IRRF_DAY_RATE)
            return ZERO
        else:
            return round_monetary(total_proceeds_brl * IRRF_SWING_RATE)
