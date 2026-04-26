from __future__ import annotations

import math

import pandas as pd


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(period, min_periods=period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def true_range(data: pd.DataFrame) -> pd.Series:
    high_low = data["high"] - data["low"]
    high_close = (data["high"] - data["close"].shift()).abs()
    low_close = (data["low"] - data["close"].shift()).abs()
    return pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)


def atr(data: pd.DataFrame, period: int = 14) -> pd.Series:
    return true_range(data).rolling(period, min_periods=period).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gains = delta.clip(lower=0)
    losses = -delta.clip(upper=0)
    avg_gain = gains.rolling(period, min_periods=period).mean()
    avg_loss = losses.rolling(period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, math.nan)
    value = 100 - (100 / (1 + rs))
    return value.fillna(100)


def bollinger_bands(series: pd.Series, period: int = 20, std: float = 2.0) -> tuple[pd.Series, pd.Series, pd.Series]:
    mid = sma(series, period)
    deviation = series.rolling(period, min_periods=period).std(ddof=0)
    upper = mid + deviation * std
    lower = mid - deviation * std
    return upper, mid, lower


def z_score(series: pd.Series, period: int = 20) -> pd.Series:
    mean = series.rolling(period, min_periods=period).mean()
    std = series.rolling(period, min_periods=period).std(ddof=0)
    return (series - mean) / std.replace(0, math.nan)


def adx(data: pd.DataFrame, period: int = 14) -> pd.Series:
    high = data["high"]
    low = data["low"]
    close = data["close"]

    plus_dm = (high.diff()).where(lambda value: value > 0, 0.0)
    minus_dm = (-low.diff()).where(lambda value: value > 0, 0.0)
    tr = pd.concat(
        [
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr_value = tr.rolling(period, min_periods=period).mean()
    plus_di = 100 * plus_dm.rolling(period, min_periods=period).mean() / atr_value.replace(0, math.nan)
    minus_di = 100 * minus_dm.rolling(period, min_periods=period).mean() / atr_value.replace(0, math.nan)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, math.nan)
    return dx.rolling(period, min_periods=period).mean().fillna(0)


def obv(data: pd.DataFrame) -> pd.Series:
    direction = data["close"].diff().fillna(0).apply(lambda value: 1 if value > 0 else -1 if value < 0 else 0)
    return (direction * data["volume"]).cumsum()


def volume_ratio(data: pd.DataFrame, period: int = 50) -> pd.Series:
    avg_volume = data["volume"].rolling(period, min_periods=period).mean()
    return data["volume"] / avg_volume.replace(0, math.nan)


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[pd.Series, pd.Series]:
    macd_line = ema(series, fast) - ema(series, slow)
    signal_line = ema(macd_line, signal)
    return macd_line, signal_line


def percentile_rank(series: pd.Series, value: float) -> float:
    valid = series.dropna()
    if valid.empty:
        return 0.0
    return float((valid <= value).mean() * 100)
