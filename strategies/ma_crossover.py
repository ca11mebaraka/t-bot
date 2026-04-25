"""
Стратегия пересечения скользящих средних (MA Crossover).

Логика:
  BUY  — когда быстрая MA пересекает медленную снизу вверх
  SELL — когда быстрая MA пересекает медленную сверху вниз
"""
from collections import deque
from decimal import Decimal
from typing import Optional

from .base import BaseStrategy, Signal, SignalType


class MACrossoverStrategy(BaseStrategy):
    def __init__(self, instrument_id: str, short_period: int = 9, long_period: int = 21):
        super().__init__(instrument_id)
        self.short_period = short_period
        self.long_period = long_period
        self._prices: deque[Decimal] = deque(maxlen=long_period)
        self._prev_short_ma: Optional[Decimal] = None
        self._prev_long_ma: Optional[Decimal] = None

    @property
    def name(self) -> str:
        return f"MA({self.short_period}/{self.long_period})"

    def _ma(self, n: int) -> Optional[Decimal]:
        prices = list(self._prices)
        if len(prices) < n:
            return None
        window = prices[-n:]
        return sum(window) / Decimal(n)

    def update(self, price: Decimal, volume: int = 0) -> Optional[Signal]:
        self._prices.append(price)

        short_ma = self._ma(self.short_period)
        long_ma = self._ma(self.long_period)

        if short_ma is None or long_ma is None:
            return None

        signal = None
        if self._prev_short_ma is not None and self._prev_long_ma is not None:
            crossed_up = self._prev_short_ma <= self._prev_long_ma and short_ma > long_ma
            crossed_down = self._prev_short_ma >= self._prev_long_ma and short_ma < long_ma

            if crossed_up:
                signal = Signal(
                    type=SignalType.BUY,
                    instrument_id=self.instrument_id,
                    price=price,
                    reason=f"MA{self.short_period} ({short_ma:.4f}) пересекла MA{self.long_period} ({long_ma:.4f}) снизу",
                )
            elif crossed_down:
                signal = Signal(
                    type=SignalType.SELL,
                    instrument_id=self.instrument_id,
                    price=price,
                    reason=f"MA{self.short_period} ({short_ma:.4f}) пересекла MA{self.long_period} ({long_ma:.4f}) сверху",
                )

        self._prev_short_ma = short_ma
        self._prev_long_ma = long_ma
        return signal
