from __future__ import annotations

import pandas as pd

from .base import StrategyResult, ToolBaseStrategy, ToolSignal
from .indicators import atr, bollinger_bands, volume_ratio


class BreakoutStrategy(ToolBaseStrategy):
    DEFAULT_PARAMS = {
        "pivot_lookback": 20,
        "volume_ma_period": 50,
        "volume_surge_ratio": 1.10,
        "bb_squeeze_threshold": 0.02,
        "atr_stop_multiplier": 1.5,
        "momentum_confirmation_bars": 3,
    }

    def compute(self, data: pd.DataFrame) -> StrategyResult:
        ticker = str(data.attrs.get("ticker", "UNKNOWN"))
        lookback = int(self.params["pivot_lookback"])
        close = data["close"]
        high = data["high"]
        low = data["low"]
        pivot_high = float(high.iloc[-lookback - 1 : -1].max())
        pivot_low = float(low.iloc[-lookback - 1 : -1].min())
        latest_close = float(close.iloc[-1])
        vol_ratio = volume_ratio(data, int(self.params["volume_ma_period"]))
        latest_volume_ratio = float(vol_ratio.iloc[-1]) if pd.notna(vol_ratio.iloc[-1]) else 0.0
        bb_upper, bb_mid, bb_lower = bollinger_bands(close, 20, 2.0)
        bb_width = (
            float((bb_upper.iloc[-1] - bb_lower.iloc[-1]) / bb_mid.iloc[-1])
            if pd.notna(bb_mid.iloc[-1]) and bb_mid.iloc[-1] != 0
            else 0.0
        )
        bb_squeeze = bb_width < float(self.params["bb_squeeze_threshold"])
        latest_atr = float(atr(data, 14).iloc[-1])

        signal = ToolSignal.HOLD
        confidence = 0.25
        if latest_close > pivot_high and latest_volume_ratio >= float(self.params["volume_surge_ratio"]):
            signal = ToolSignal.BUY
            confidence = min(1.0, 0.6 + latest_volume_ratio / 10)
        elif latest_close < pivot_low and latest_volume_ratio >= float(self.params["volume_surge_ratio"]):
            signal = ToolSignal.SELL
            confidence = min(1.0, 0.6 + latest_volume_ratio / 10)

        indicators = {
            "pivot_high": pivot_high,
            "pivot_low": pivot_low,
            "volume_ratio": latest_volume_ratio,
            "bb_width": bb_width,
            "bb_squeeze": bb_squeeze,
            "atr": latest_atr,
        }
        return StrategyResult(
            signal=signal,
            ticker=ticker,
            confidence=round(confidence, 4),
            suggested_qty=1 if signal != ToolSignal.HOLD else 0,
            reason=f"Breakout: close={latest_close:.4f}, pivot_high={pivot_high:.4f}, volume_ratio={latest_volume_ratio:.2f}",
            indicators=indicators,
            recommended_stop_loss=latest_close - latest_atr * float(self.params["atr_stop_multiplier"]) if signal == ToolSignal.BUY else None,
            recommended_take_profit=latest_close + latest_atr * float(self.params["atr_stop_multiplier"]) * 2 if signal == ToolSignal.BUY else None,
        )

    def get_required_history_bars(self) -> int:
        return max(int(self.params["pivot_lookback"]), int(self.params["volume_ma_period"]), 50) + 5

    def describe_for_llm(self) -> str:
        return (
            "Пробой ключевых уровней с подтверждением объёма. Лучше после BB squeeze "
            "и перехода low_volatility в high_volatility."
        )
