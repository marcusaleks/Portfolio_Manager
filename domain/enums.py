"""Domain enums for the Portfolio Control System."""

from enum import Enum


class AssetClass(str, Enum):
    """Classification of financial assets."""
    ACAO = "ACAO"
    FII = "FII"
    ETF = "ETF"
    BDR = "BDR"
    RENDA_FIXA = "RENDA_FIXA"
    CRIPTO = "CRIPTO"

    @property
    def label(self) -> str:
        _labels = {
            "ACAO": "Ações",
            "FII": "Fundos Imobiliários",
            "ETF": "ETFs",
            "BDR": "BDRs",
            "RENDA_FIXA": "Renda Fixa",
            "CRIPTO": "Criptomoedas",
        }
        return _labels[self.value]


class TransactionType(str, Enum):
    """Type of portfolio transaction."""
    BUY = "BUY"
    SELL = "SELL"
    SPLIT = "SPLIT"
    INPLIT = "INPLIT"
    DIVIDEND = "DIVIDEND"
    JCP = "JCP"
    BONUS = "BONUS"

    @property
    def label(self) -> str:
        _labels = {
            "BUY": "Compra",
            "SELL": "Venda",
            "SPLIT": "Desdobramento",
            "INPLIT": "Grupamento",
            "DIVIDEND": "Dividendo",
            "JCP": "JCP",
            "BONUS": "Bonificação",
        }
        return _labels.get(self.value, self.value)


class TradeType(str, Enum):
    """Trade classification for tax purposes."""
    SWING_TRADE = "SWING_TRADE"
    DAY_TRADE = "DAY_TRADE"


class Currency(str, Enum):
    """Supported currencies."""
    BRL = "BRL"
    USD = "USD"

    @property
    def symbol(self) -> str:
        return "R$" if self == Currency.BRL else "US$"
