from __future__ import annotations

import pandas as pd
from statsmodels.tsa.stattools import adfuller

from .base import StrategyResult, ToolBaseStrategy, ToolSignal
from .indicators import bollinger_bands, rsi, z_score


class MeanReversionStrategy(ToolBaseStrategy):
    DEFAULT_PARAMS = {
        "bb_period": 20,
        "bb_std": 2.0,
        "rsi_period": 14,
        "rsi_oversold": 30,
        "rsi_overbought": 70,
        "adf_pvalue_threshold": 0.05,
        "z_score_threshold": 2.0,
    }

    def compute(self, data: pd.DataFrame) -> StrategyResult:
        ticker = str(data.attrs.get("ticker", "UNKNOWN"))
        close = data["close"]
        bb_upper, bb_mid, bb_lower = bollinger_bands(
            close,
            int(self.params["bb_period"]),
            float(self.params["bb_std"]),
        )
        rsi_value = rsi(close, int(self.params["rsi_period"]))
        z_value = z_score(close, int(self.params["bb_period"]))

        try:
            adf_pvalue = float(adfuller(close.dropna())[:2][1])
        except Exception:
            adf_pvalue = 1.0
        adf_warning = adf_pvalue > float(self.params["adf_pvalue_threshold"])

        latest_close = float(close.iloc[-1])
        latest_upper = float(bb_upper.iloc[-1])
        latest_mid = float(bb_mid.iloc[-1])
        latest_lower = float(bb_lower.iloc[-1])
        latest_rsi = float(rsi_value.iloc[-1])
        latest_z = float(z_value.iloc[-1]) if pd.notna(z_value.iloc[-1]) else 0.0

        signal = ToolSignal.HOLD
        confidence = 0.25
        if latest_close < latest_lower and latest_rsi < float(self.params["rsi_oversold"]):
            signal = ToolSignal.BUY
            confidence = min(1.0, 0.55 + abs(latest_z) / 10)
        elif latest_close > latest_upper and latest_rsi > float(self.params["rsi_overbought"]):
            signal = ToolSignal.SELL
            confidence = min(1.0, 0.55 + abs(latest_z) / 10)
        if adf_warning:
            confidence *= 0.7

        indicators = {
            "bb_upper": latest_upper,
            "bb_lower": latest_lower,
            "bb_mid": latest_mid,
            "rsi": latest_rsi,
            "z_score": latest_z,
            "adf_pvalue": adf_pvalue,
            "adf_warning": adf_warning,
        }
        return StrategyResult(
            signal=signal,
            ticker=ticker,
            confidence=round(confidence, 4),
            suggested_qty=1 if signal != ToolSignal.HOLD else 0,
            reason=f"Mean reversion: close={latest_close:.4f}, RSI={latest_rsi:.2f}, z={latest_z:.2f}",
            indicators=indicators,
            recommended_stop_loss=latest_close * 0.98 if signal == ToolSignal.BUY else None,
            recommended_take_profit=latest_mid if signal == ToolSignal.BUY else None,
        )

    def get_required_history_bars(self) -> int:
        return max(int(self.params["bb_period"]), int(self.params["rsi_period"])) + 80

    def describe_for_llm(self) -> str:
        return (
            "Возврат к среднему через Bollinger Bands + RSI. Оптимально для ranging-рынков "
            "и стационарных рядов. В trending-рынках учитывать adf_warning."
        )
