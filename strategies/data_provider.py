from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pandas as pd
from t_tech.invest import CandleInterval
from t_tech.invest.utils import now

from client import quotation_to_decimal


INTERVAL_MAP = {
    "1_MIN": CandleInterval.CANDLE_INTERVAL_1_MIN,
    "5_MIN": CandleInterval.CANDLE_INTERVAL_5_MIN,
    "1_HOUR": CandleInterval.CANDLE_INTERVAL_HOUR,
    "1_DAY": CandleInterval.CANDLE_INTERVAL_DAY,
}

_INTERVAL_TO_TIMEDELTA = {
    "1_MIN": timedelta(minutes=1),
    "5_MIN": timedelta(minutes=5),
    "1_HOUR": timedelta(hours=1),
    "1_DAY": timedelta(days=1),
}


class TinkoffDataProvider:
    def __init__(self, client):
        self.client = client
        self._ticker_to_figi: dict[str, str] = {}

    def get_historical_ohlcv(
        self,
        ticker: str,
        interval: str,
        bars: int,
    ) -> pd.DataFrame:
        figi = self._resolve_figi(ticker)
        interval_key = interval.upper()
        candle_interval = INTERVAL_MAP.get(interval_key, CandleInterval.CANDLE_INTERVAL_HOUR)
        delta = _INTERVAL_TO_TIMEDELTA.get(interval_key, timedelta(hours=1))
        # Add a buffer because exchanges have gaps and weekends.
        from_ = now() - delta * max(bars * 3, bars + 10)

        rows = []
        for candle in self.client.get_all_candles(
            instrument_id=figi,
            from_=from_,
            to=now(),
            interval=candle_interval,
        ):
            rows.append(
                {
                    "time": candle.time,
                    "open": _to_float(quotation_to_decimal(candle.open)),
                    "high": _to_float(quotation_to_decimal(candle.high)),
                    "low": _to_float(quotation_to_decimal(candle.low)),
                    "close": _to_float(quotation_to_decimal(candle.close)),
                    "volume": float(candle.volume),
                }
            )

        frame = pd.DataFrame(rows).tail(bars)
        if frame.empty:
            frame = pd.DataFrame(columns=["time", "open", "high", "low", "close", "volume"])
        frame = frame.set_index("time", drop=False) if "time" in frame else frame
        frame.attrs["ticker"] = ticker
        frame.attrs["figi"] = figi
        return frame

    def _resolve_figi(self, ticker_or_figi: str) -> str:
        if ticker_or_figi.startswith("BBG") or ticker_or_figi.startswith("TCS"):
            return ticker_or_figi
        if ticker_or_figi in self._ticker_to_figi:
            return self._ticker_to_figi[ticker_or_figi]

        result = self.client.instruments.find_instrument(query=ticker_or_figi).instruments
        for instrument in result:
            if instrument.ticker.upper() == ticker_or_figi.upper() and instrument.figi:
                self._ticker_to_figi[ticker_or_figi] = instrument.figi
                return instrument.figi
        if result and result[0].figi:
            self._ticker_to_figi[ticker_or_figi] = result[0].figi
            return result[0].figi
        raise ValueError(f"Не удалось найти FIGI для {ticker_or_figi}")


def _to_float(value: Decimal) -> float:
    return float(value)
