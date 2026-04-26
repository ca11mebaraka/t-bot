from __future__ import annotations

import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier

from .base import StrategyResult, ToolBaseStrategy, ToolSignal
from .indicators import atr, bollinger_bands, macd, obv, rsi, volume_ratio


class MLStrategy(ToolBaseStrategy):
    DEFAULT_PARAMS = {
        "mode": "sklearn",
        "sequence_length": 60,
        "confidence_threshold": 0.65,
        "retrain_every_n_bars": 100,
        "train_size_bars": 500,
        "features": [
            "returns_1d",
            "returns_5d",
            "rsi_14",
            "macd",
            "macd_signal",
            "atr_14",
            "bb_pct_b",
            "obv_normalized",
            "volume_ratio",
        ],
        "sklearn_model": "GradientBoosting",
    }

    def compute(self, data: pd.DataFrame) -> StrategyResult:
        ticker = str(data.attrs.get("ticker", "UNKNOWN"))
        features = self._build_features(data).dropna()
        threshold = float(self.params["confidence_threshold"])
        if len(features) < 120:
            return StrategyResult(ToolSignal.HOLD, ticker, 0.0, 0, "ML: not enough clean feature rows", {})

        horizon_return = data["close"].pct_change().shift(-1).reindex(features.index)
        target = horizon_return.apply(lambda value: 1 if value > 0.001 else -1 if value < -0.001 else 0).dropna()
        features = features.loc[target.index]
        train_size = min(int(self.params["train_size_bars"]), len(features) - 1)
        if train_size < 80:
            return StrategyResult(ToolSignal.HOLD, ticker, 0.0, 0, "ML: not enough train rows", {})

        x_train = features.iloc[-train_size:-1]
        y_train = target.iloc[-train_size:-1]
        x_last = features.iloc[[-1]]
        if y_train.nunique() < 2:
            return StrategyResult(
                ToolSignal.HOLD,
                ticker,
                0.0,
                0,
                "ML: target has only one class in training window",
                {"class_count": int(y_train.nunique())},
            )

        model = GradientBoostingClassifier(random_state=42)
        model.fit(x_train, y_train)
        probabilities_raw = model.predict_proba(x_last)[0]
        classes = list(model.classes_)
        probabilities = {self._class_to_signal(cls): float(prob) for cls, prob in zip(classes, probabilities_raw)}
        buy_prob = probabilities.get("buy", 0.0)
        sell_prob = probabilities.get("sell", 0.0)
        hold_prob = probabilities.get("hold", 0.0)

        signal = ToolSignal.HOLD
        confidence = max(buy_prob, sell_prob, hold_prob)
        if buy_prob >= threshold and buy_prob >= sell_prob:
            signal = ToolSignal.BUY
            confidence = buy_prob
        elif sell_prob >= threshold:
            signal = ToolSignal.SELL
            confidence = sell_prob

        importances = {
            name: float(value)
            for name, value in zip(features.columns, model.feature_importances_)
        }
        indicators = {
            "predicted_class": signal.value,
            "probabilities": probabilities,
            "feature_importances": dict(sorted(importances.items(), key=lambda item: item[1], reverse=True)[:5]),
            "last_retrain_bar": int(len(data)),
        }
        return StrategyResult(
            signal=signal,
            ticker=ticker,
            confidence=round(confidence, 4),
            suggested_qty=1 if signal != ToolSignal.HOLD else 0,
            reason=f"ML: predicted={signal.value}, confidence={confidence:.2f}",
            indicators=indicators,
        )

    def get_required_history_bars(self) -> int:
        return int(self.params["train_size_bars"]) + int(self.params["sequence_length"]) + 20

    def describe_for_llm(self) -> str:
        return (
            "ML-стратегия GradientBoosting на технических признаках. Использовать, когда "
            "probabilities['buy'] или ['sell'] выше 0.7 и feature_importances стабильны."
        )

    @staticmethod
    def _class_to_signal(value: int) -> str:
        if value > 0:
            return "buy"
        if value < 0:
            return "sell"
        return "hold"

    @staticmethod
    def _build_features(data: pd.DataFrame) -> pd.DataFrame:
        close = data["close"]
        bb_upper, _, bb_lower = bollinger_bands(close, 20, 2.0)
        macd_line, macd_signal = macd(close)
        obv_series = obv(data)
        bb_range = (bb_upper - bb_lower).replace(0, pd.NA)
        features = pd.DataFrame(index=data.index)
        features["returns_1d"] = close.pct_change()
        features["returns_5d"] = close.pct_change(5)
        features["rsi_14"] = rsi(close, 14)
        features["macd"] = macd_line
        features["macd_signal"] = macd_signal
        features["atr_14"] = atr(data, 14)
        features["bb_pct_b"] = (close - bb_lower) / bb_range
        features["obv_normalized"] = obv_series / obv_series.abs().rolling(60, min_periods=10).max().replace(0, pd.NA)
        features["volume_ratio"] = volume_ratio(data, 50)
        return features
