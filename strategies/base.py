from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Optional


class SignalType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass
class Signal:
    type: SignalType
    instrument_id: str
    price: Decimal
    reason: str
    lots: Optional[int] = None


class BaseStrategy(ABC):
    """Базовый класс торговой стратегии."""

    def __init__(self, instrument_id: str):
        self.instrument_id = instrument_id

    @abstractmethod
    def update(self, price: Decimal, volume: int = 0) -> Optional[Signal]:
        """
        Принимает новую цену, возвращает Signal или None.
        Вызывается на каждой новой свече/тике.
        """
        ...

    @property
    @abstractmethod
    def name(self) -> str: ...
