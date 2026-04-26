from __future__ import annotations

import pandas as pd

from .base import MarketRegime
from .indicators import adx, atr, bollinger_bands, ema, percentile_rank


class MarketRegimeDetector:
    def detect(self, data: pd.DataFrame) -> dict:
        if len(data) < 60:
            return {
                "regime": MarketRegime.RANGING.value,
                "adx": 0.0,
                "atr_pct": 0.0,
                "bb_width": 0.0,
                "trend_direction": "flat",
                "volatility_percentile": 0.0,
                "recommended_strategies": ["mean_reversion", "ml"],
            }

        close = data["close"]
        ma50 = ema(close, 50)
        ma200 = ema(close, 200) if len(data) >= 200 else ema(close, min(100, len(data) // 2))
        adx_series = adx(data, 14)
        atr_series = atr(data, 14)
        bb_upper, bb_mid, bb_lower = bollinger_bands(close, 20, 2.0)

        last_close = float(close.iloc[-1])
        last_adx = float(adx_series.iloc[-1])
        last_atr = float(atr_series.iloc[-1]) if pd.notna(atr_series.iloc[-1]) else 0.0
        atr_pct = last_atr / last_close if last_close else 0.0
        bb_width = (
            float((bb_upper.iloc[-1] - bb_lower.iloc[-1]) / bb_mid.iloc[-1])
            if pd.notna(bb_mid.iloc[-1]) and bb_mid.iloc[-1] != 0
            else 0.0
        )
        volatility_percentile = percentile_rank(atr_series / close, atr_pct)

        if ma50.iloc[-1] > ma200.iloc[-1]:
            trend_direction = "up"
        elif ma50.iloc[-1] < ma200.iloc[-1]:
            trend_direction = "down"
        else:
            trend_direction = "flat"

        if volatility_percentile > 95:
            regime = MarketRegime.HIGH_VOLATILITY
            recommended = ["mean_reversion", "ml"]
        elif bb_width < 0.01:
            regime = MarketRegime.LOW_VOLATILITY
            recommended = ["breakout", "trend_following"]
        elif last_adx > 25 and trend_direction == "up":
            regime = MarketRegime.TRENDING_UP
            recommended = ["trend_following", "breakout"]
        elif last_adx > 25 and trend_direction == "down":
            regime = MarketRegime.TRENDING_DOWN
            recommended = ["trend_following", "breakout"]
        elif last_adx < 20:
            regime = MarketRegime.RANGING
            recommended = ["mean_reversion", "stat_arb"]
        else:
            regime = MarketRegime.RANGING
            recommended = ["mean_reversion", "ml"]

        return {
            "regime": regime.value,
            "adx": round(last_adx, 4),
            "atr_pct": round(atr_pct, 6),
            "bb_width": round(bb_width, 6),
            "trend_direction": trend_direction,
            "volatility_percentile": round(volatility_percentile, 2),
            "recommended_strategies": recommended,
        }
