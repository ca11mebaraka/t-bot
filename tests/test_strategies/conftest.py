import pandas as pd
import pytest


@pytest.fixture
def make_ohlcv(rows: int = 260, trend: float = 0.1, start: float = 100.0) -> pd.DataFrame:
    def _make(rows: int = 260, trend: float = 0.1, start: float = 100.0) -> pd.DataFrame:
        values = [start + idx * trend for idx in range(rows)]
        frame = pd.DataFrame(
            {
                "time": pd.date_range("2024-01-01", periods=rows, freq="h"),
                "open": values,
                "high": [value * 1.01 for value in values],
                "low": [value * 0.99 for value in values],
                "close": values,
                "volume": [1000 + (idx % 10) * 10 for idx in range(rows)],
            }
        )
        frame = frame.set_index("time", drop=False)
        frame.attrs["ticker"] = "TEST"
        return frame

    return _make


@pytest.fixture
def StaticDataProvider():
    class _StaticDataProvider:
        def __init__(self, data):
            self.data = data

        def get_historical_ohlcv(self, ticker: str, interval: str, bars: int):
            frame = self.data.tail(bars).copy()
            frame.attrs["ticker"] = ticker
            return frame

    return _StaticDataProvider
