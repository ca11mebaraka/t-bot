from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Optional

import pandas as pd


class SignalType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class ToolSignal(str, Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


class MarketRegime(str, Enum):
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGING = "ranging"
    HIGH_VOLATILITY = "high_volatility"
    LOW_VOLATILITY = "low_volatility"


@dataclass
class Signal:
    type: SignalType
    instrument_id: str
    price: Decimal
    reason: str
    lots: Optional[int] = None


@dataclass
class StrategyResult:
    """Pure strategy output passed to the LLM orchestrator for final decisions."""

    signal: ToolSignal
    ticker: str
    confidence: float
    suggested_qty: int
    reason: str
    indicators: dict
    recommended_stop_loss: Optional[float] = None
    recommended_take_profit: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "signal": self.signal.value,
            "ticker": self.ticker,
            "confidence": self.confidence,
            "suggested_qty": self.suggested_qty,
            "reason": self.reason,
            "indicators": self.indicators,
            "recommended_stop_loss": self.recommended_stop_loss,
            "recommended_take_profit": self.recommended_take_profit,
        }


@dataclass
class LLMDecision:
    """Structured LLM decision after analyzing one or more StrategyResult values."""

    action: ToolSignal
    approved_qty: int
    strategy_name: str
    params_override: dict = field(default_factory=dict)
    reasoning: str = ""
    confidence_override: Optional[float] = None
    skip_reason: Optional[str] = None


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


class ToolBaseStrategy(ABC):
    """Base class for deterministic strategy tools used by the LLM orchestrator."""

    DEFAULT_PARAMS: dict = {}

    def __init__(self, params: dict):
        self.params = {**self.DEFAULT_PARAMS, **params}

    @abstractmethod
    def compute(self, data: pd.DataFrame) -> StrategyResult:
        """Deterministic calculation. No side effects and no final trading decision."""
        ...

    @abstractmethod
    def get_required_history_bars(self) -> int:
        ...

    @abstractmethod
    def describe_for_llm(self) -> str:
        """Human-readable strategy description for the LLM prompt."""
        ...
