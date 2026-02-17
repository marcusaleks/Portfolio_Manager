"""Price provider — real Yahoo Finance integration via yfinance."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Optional

log = logging.getLogger(__name__)


class PriceProvider(ABC):
    """Abstract interface for fetching market prices."""

    @abstractmethod
    def get_last_price(self, ticker: str) -> Optional[Decimal]:
        """Return the last known price for *ticker*, or None on failure."""

    @abstractmethod
    def get_previous_close(self, ticker: str) -> Optional[Decimal]:
        """Return the previous closing price for *ticker*."""


class YahooFinanceProvider(PriceProvider):
    """Real Yahoo Finance provider using yfinance library."""

    def __init__(self) -> None:
        try:
            import yfinance  # noqa: F401
            self._available = True
        except ImportError:
            self._available = False
            log.warning("yfinance not installed — price fetching disabled")

    def _suffix(self, ticker: str) -> str:
        """Add .SA suffix for B3 tickers if not already present."""
        if "." in ticker or ticker.endswith("-USD"):
            return ticker
        return f"{ticker}.SA"

    def get_last_price(self, ticker: str) -> Optional[Decimal]:
        if not self._available:
            return None
        try:
            import yfinance as yf
            t = yf.Ticker(self._suffix(ticker))
            info = t.fast_info
            price = getattr(info, "last_price", None)
            if price is not None:
                return Decimal(str(round(price, 2)))
            return None
        except Exception:
            log.exception("Failed to fetch price for %s", ticker)
            return None

    def get_previous_close(self, ticker: str) -> Optional[Decimal]:
        if not self._available:
            return None
        try:
            import yfinance as yf
            t = yf.Ticker(self._suffix(ticker))
            info = t.fast_info
            price = getattr(info, "previous_close", None)
            if price is not None:
                return Decimal(str(round(price, 2)))
            return None
        except Exception:
            log.exception("Failed to fetch previous close for %s", ticker)
            return None

    def detect_corporate_action(
        self, ticker: str, expected_price: Decimal
    ) -> Optional[str]:
        """Check if current price deviates >30% from expected — signals
        a possible split/inplit (corporate action)."""
        current = self.get_last_price(ticker)
        if current is None or expected_price <= 0:
            return None
        ratio = abs(current - expected_price) / expected_price
        if ratio > Decimal("0.30"):
            return (
                f"Possível ação corporativa detectada para {ticker}: "
                f"preço esperado {expected_price}, atual {current} "
                f"(variação de {ratio * 100:.1f}%)"
            )
        return None
