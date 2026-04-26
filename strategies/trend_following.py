from __future__ import annotations

import pandas as pd

from .base import StrategyResult, ToolBaseStrategy, ToolSignal
from .indicators import adx, atr, ema, sma


class TrendFollowingStrategy(ToolBaseStrategy):
    DEFAULT_PARAMS = {
        "fast_period": 50,
        "slow_period": 200,
        "ma_type": "EMA",
        "adx_period": 14,
        "adx_threshold": 25,
        "atr_multiplier": 2.0,
    }

    def compute(self, data: pd.DataFrame) -> StrategyResult:
        ticker = str(data.attrs.get("ticker", "UNKNOWN"))
        close = data["close"]
        ma_func = ema if str(self.params["ma_type"]).upper() == "EMA" else sma
        fast = ma_func(close, int(self.params["fast_period"]))
        slow = ma_func(close, int(self.params["slow_period"]))
        adx_value = adx(data, int(self.params["adx_period"]))
        atr_value = atr(data, int(self.params["adx_period"]))

        latest_fast = float(fast.iloc[-1])
        latest_slow = float(slow.iloc[-1])
        latest_adx = float(adx_value.iloc[-1])
        latest_atr = float(atr_value.iloc[-1]) if pd.notna(atr_value.iloc[-1]) else 0.0
        prev_fast = float(fast.iloc[-2]) if pd.notna(fast.iloc[-2]) else latest_fast
        prev_slow = float(slow.iloc[-2]) if pd.notna(slow.iloc[-2]) else latest_slow

        cross_type = None
        signal = ToolSignal.HOLD
        confidence = 0.2
        if latest_adx >= float(self.params["adx_threshold"]):
            if prev_fast <= prev_slow and latest_fast > latest_slow:
                signal = ToolSignal.BUY
                cross_type = "golden"
                confidence = min(1.0, 0.55 + latest_adx / 100)
            elif prev_fast >= prev_slow and latest_fast < latest_slow:
                signal = ToolSignal.SELL
                cross_type = "death"
                confidence = min(1.0, 0.55 + latest_adx / 100)

        indicators = {
            "fast_ma": latest_fast,
            "slow_ma": latest_slow,
            "adx": latest_adx,
            "atr": latest_atr,
            "cross_type": cross_type,
        }
        close_price = float(close.iloc[-1])
        return StrategyResult(
            signal=signal,
            ticker=ticker,
            confidence=confidence,
            suggested_qty=1 if signal != ToolSignal.HOLD else 0,
            reason=f"Trend following: {cross_type or 'no actionable cross'}, ADX={latest_adx:.2f}",
            indicators=indicators,
            recommended_stop_loss=close_price - latest_atr * float(self.params["atr_multiplier"]) if signal == ToolSignal.BUY else None,
            recommended_take_profit=close_price + latest_atr * float(self.params["atr_multiplier"]) * 2 if signal == ToolSignal.BUY else None,
        )

    def get_required_history_bars(self) -> int:
        return max(int(self.params["slow_period"]) + int(self.params["adx_period"]) + 5, 60)

    def describe_for_llm(self) -> str:
        return (
            "Следование за трендом через пересечение скользящих средних. Лучше всего работает "
            "при ADX > 25. Рекомендуется для trending_up и trending_down. Избегать ranging-рынков."
        )
