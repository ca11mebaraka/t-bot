"""
Стратегия на основе RSI (Relative Strength Index).

Логика:
  BUY  — RSI выходит из зоны перепроданности (пересекает oversold снизу вверх)
  SELL — RSI выходит из зоны перекупленности (пересекает overbought сверху вниз)
"""
from collections import deque
from decimal import Decimal
from typing import Optional

from .base import BaseStrategy, Signal, SignalType


class RSIStrategy(BaseStrategy):
    def __init__(
        self,
        instrument_id: str,
        period: int = 14,
        oversold: float = 30.0,
        overbought: float = 70.0,
    ):
        super().__init__(instrument_id)
        self.period = period
        self.oversold = oversold
        self.overbought = overbought
        self._prices: deque[Decimal] = deque(maxlen=period + 1)
        self._prev_rsi: Optional[float] = None

    @property
    def name(self) -> str:
        return f"RSI({self.period})"

    def _compute_rsi(self) -> Optional[float]:
        prices = list(self._prices)
        if len(prices) < self.period + 1:
            return None

        gains, losses = [], []
        for i in range(1, len(prices)):
            delta = float(prices[i] - prices[i - 1])
            (gains if delta > 0 else losses).append(abs(delta))

        avg_gain = sum(gains) / self.period if gains else 0.0
        avg_loss = sum(losses) / self.period if losses else 0.0

        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1 + rs))

    def update(self, price: Decimal, volume: int = 0) -> Optional[Signal]:
        self._prices.append(price)
        rsi = self._compute_rsi()

        if rsi is None:
            return None

        signal = None
        if self._prev_rsi is not None:
            exiting_oversold = self._prev_rsi <= self.oversold < rsi
            exiting_overbought = self._prev_rsi >= self.overbought > rsi

            if exiting_oversold:
                signal = Signal(
                    type=SignalType.BUY,
                    instrument_id=self.instrument_id,
                    price=price,
                    reason=f"RSI выходит из перепроданности ({rsi:.1f} > {self.oversold})",
                )
            elif exiting_overbought:
                signal = Signal(
                    type=SignalType.SELL,
                    instrument_id=self.instrument_id,
                    price=price,
                    reason=f"RSI выходит из перекупленности ({rsi:.1f} < {self.overbought})",
                )

        self._prev_rsi = rsi
        return signal
