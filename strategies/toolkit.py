from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from .backtester import Backtester
from .breakout import BreakoutStrategy
from .data_provider import TinkoffDataProvider
from .market_regime import MarketRegimeDetector
from .mean_reversion import MeanReversionStrategy
from .ml_strategy import MLStrategy
from .stat_arb import StatArbStrategy
from .trend_following import TrendFollowingStrategy

logger = logging.getLogger(__name__)


STRATEGY_REGISTRY = {
    "trend_following": TrendFollowingStrategy,
    "mean_reversion": MeanReversionStrategy,
    "stat_arb": StatArbStrategy,
    "breakout": BreakoutStrategy,
    "ml": MLStrategy,
}


class StrategyToolkit:
    """
    Emulated LLM tools. Methods return JSON-serializable dictionaries that are
    inserted into the prompt context for the existing LLM API flow.
    """

    def __init__(self, data_provider: TinkoffDataProvider, config_path: str | Path = "config/strategies.yaml"):
        self.data_provider = data_provider
        self.regime_detector = MarketRegimeDetector()
        self.default_params = self._load_params(config_path)

    def list_strategies(self) -> dict:
        return {
            "strategies": [
                {
                    "name": name,
                    "description": cls(self.default_params.get(name, {})).describe_for_llm(),
                    "default_params": self.default_params.get(name, cls.DEFAULT_PARAMS),
                }
                for name, cls in STRATEGY_REGISTRY.items()
            ]
        }

    def get_market_regime(self, ticker: str, interval: str = "1_HOUR") -> dict:
        data = self.data_provider.get_historical_ohlcv(ticker, interval, bars=200)
        regime_info = self.regime_detector.detect(data)
        logger.info("[%s] Market regime: %s", ticker, regime_info["regime"])
        return regime_info

    def run_strategy(
        self,
        strategy_name: str,
        ticker: str,
        params: dict,
        interval: str = "1_HOUR",
    ) -> dict:
        if strategy_name not in STRATEGY_REGISTRY:
            return {"error": f"Unknown strategy: {strategy_name}"}
        strategy_cls = STRATEGY_REGISTRY[strategy_name]
        merged_params = {**self.default_params.get(strategy_name, strategy_cls.DEFAULT_PARAMS), **(params or {})}
        strategy = strategy_cls(merged_params)
        data = self.data_provider.get_historical_ohlcv(ticker, interval, bars=strategy.get_required_history_bars())
        result = strategy.compute(data)
        logger.info("[%s] %s -> %s (confidence=%.2f)", ticker, strategy_name, result.signal.value, result.confidence)
        return {
            **result.to_dict(),
            "params_used": merged_params,
            "strategy_name": strategy_name,
        }

    def run_strategy_pair(
        self,
        ticker_a: str,
        ticker_b: str,
        params: dict,
        interval: str = "1_HOUR",
    ) -> dict:
        default_params = self.default_params.get("stat_arb", StatArbStrategy.DEFAULT_PARAMS)
        merged = {**default_params, **(params or {}), "ticker_a": ticker_a, "ticker_b": ticker_b}
        strategy = StatArbStrategy(merged)
        bars = strategy.get_required_history_bars()
        data_a = self.data_provider.get_historical_ohlcv(ticker_a, interval, bars)
        data_b = self.data_provider.get_historical_ohlcv(ticker_b, interval, bars)
        result_a, result_b = strategy.compute_pair(data_a, data_b)
        return {
            "signal_a": result_a.to_dict(),
            "signal_b": result_b.to_dict(),
            "spread_z_score": result_a.indicators.get("z_score"),
            "hedge_ratio": result_a.indicators.get("hedge_ratio"),
            "cointegration_pvalue": result_a.indicators.get("coint_pvalue"),
            "params_used": merged,
        }

    def backtest_strategy(
        self,
        strategy_name: str,
        ticker: str,
        params: dict,
        bars: int = 500,
        interval: str = "1_DAY",
    ) -> dict:
        if strategy_name not in STRATEGY_REGISTRY:
            return {"error": f"Unknown strategy: {strategy_name}"}
        strategy_cls = STRATEGY_REGISTRY[strategy_name]
        merged = {**self.default_params.get(strategy_name, strategy_cls.DEFAULT_PARAMS), **(params or {})}
        strategy = strategy_cls(merged)
        data = self.data_provider.get_historical_ohlcv(ticker, interval, bars)
        result = Backtester().run(strategy, data)
        return {
            "sharpe_ratio": round(result.sharpe_ratio, 3),
            "max_drawdown": round(result.max_drawdown, 4),
            "win_rate": round(result.win_rate, 3),
            "total_return": round(result.total_return, 4),
            "total_trades": result.total_trades,
            "params_tested": merged,
        }

    @staticmethod
    def _load_params(path: str | Path) -> dict[str, Any]:
        path = Path(path)
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as file:
            return yaml.safe_load(file) or {}
