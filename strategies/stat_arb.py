from __future__ import annotations

import math

import pandas as pd
import statsmodels.api as sm
from statsmodels.tsa.stattools import coint

from .base import StrategyResult, ToolBaseStrategy, ToolSignal


class StatArbStrategy(ToolBaseStrategy):
    DEFAULT_PARAMS = {
        "lookback_period": 60,
        "z_entry_threshold": 2.0,
        "z_exit_threshold": 0.5,
        "cointegration_pvalue": 0.05,
        "rebalance_every_n_bars": 20,
    }

    def compute(self, data: pd.DataFrame) -> StrategyResult:
        return StrategyResult(
            signal=ToolSignal.HOLD,
            ticker=str(data.attrs.get("ticker", "PAIR_ONLY")),
            confidence=0.0,
            suggested_qty=0,
            reason="StatArb requires run_strategy_pair with two instruments",
            indicators={},
        )

    def compute_pair(
        self,
        data_a: pd.DataFrame,
        data_b: pd.DataFrame,
    ) -> tuple[StrategyResult, StrategyResult]:
        ticker_a = str(data_a.attrs.get("ticker", "A"))
        ticker_b = str(data_b.attrs.get("ticker", "B"))
        lookback = int(self.params["lookback_period"])
        a = data_a["close"].tail(lookback).reset_index(drop=True)
        b = data_b["close"].tail(lookback).reset_index(drop=True)

        model = sm.OLS(a, sm.add_constant(b)).fit()
        hedge_ratio = float(model.params.iloc[1])
        spread = a - hedge_ratio * b
        spread_mean = spread.mean()
        spread_std = spread.std(ddof=0) or math.nan
        z = float((spread.iloc[-1] - spread_mean) / spread_std) if spread_std else 0.0
        try:
            coint_pvalue = float(coint(a, b)[1])
        except Exception:
            coint_pvalue = 1.0

        entry = float(self.params["z_entry_threshold"])
        confidence = 0.0 if coint_pvalue > float(self.params["cointegration_pvalue"]) else min(1.0, abs(z) / (entry * 2))
        signal_a = ToolSignal.HOLD
        signal_b = ToolSignal.HOLD
        if confidence > 0 and z > entry:
            signal_a = ToolSignal.SELL
            signal_b = ToolSignal.BUY
        elif confidence > 0 and z < -entry:
            signal_a = ToolSignal.BUY
            signal_b = ToolSignal.SELL

        half_life = self._estimate_half_life(spread)
        indicators = {
            "spread": float(spread.iloc[-1]),
            "z_score": z,
            "hedge_ratio": hedge_ratio,
            "half_life": half_life,
            "coint_pvalue": coint_pvalue,
        }
        return (
            StrategyResult(signal_a, ticker_a, confidence, 1 if signal_a != ToolSignal.HOLD else 0, "StatArb leg A", indicators),
            StrategyResult(signal_b, ticker_b, confidence, 1 if signal_b != ToolSignal.HOLD else 0, "StatArb leg B", indicators),
        )

    def get_required_history_bars(self) -> int:
        return int(self.params["lookback_period"]) + 20

    def describe_for_llm(self) -> str:
        return (
            "Парный трейдинг на основе коинтеграции. Применять только через run_strategy_pair "
            "и только при coint_pvalue < 0.05."
        )

    @staticmethod
    def _estimate_half_life(spread: pd.Series) -> float:
        lagged = spread.shift(1).dropna()
        delta = spread.diff().dropna()
        if len(lagged) != len(delta) or len(delta) < 3:
            return 0.0
        model = sm.OLS(delta, sm.add_constant(lagged)).fit()
        beta = float(model.params.iloc[1])
        if beta >= 0:
            return 0.0
        return float(-math.log(2) / beta)
