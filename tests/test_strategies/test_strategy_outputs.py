from strategies.base import StrategyResult
from strategies.breakout import BreakoutStrategy
from strategies.mean_reversion import MeanReversionStrategy
from strategies.ml_strategy import MLStrategy
from strategies.stat_arb import StatArbStrategy
from strategies.trend_following import TrendFollowingStrategy


def test_tool_strategies_return_strategy_result(make_ohlcv):
    data = make_ohlcv(rows=620, trend=0.05)
    strategies = [
        TrendFollowingStrategy({}),
        MeanReversionStrategy({}),
        BreakoutStrategy({}),
        MLStrategy({"train_size_bars": 160, "sequence_length": 30}),
    ]

    for strategy in strategies:
        result = strategy.compute(data.tail(strategy.get_required_history_bars()))
        assert isinstance(result, StrategyResult)
        assert 0 <= result.confidence <= 1
        assert isinstance(result.indicators, dict)


def test_stat_arb_pair_returns_two_results(make_ohlcv):
    data_a = make_ohlcv(rows=120, trend=0.03, start=100)
    data_b = make_ohlcv(rows=120, trend=0.02, start=80)
    data_a.attrs["ticker"] = "AAA"
    data_b.attrs["ticker"] = "BBB"

    result_a, result_b = StatArbStrategy({}).compute_pair(data_a, data_b)

    assert isinstance(result_a, StrategyResult)
    assert isinstance(result_b, StrategyResult)
    assert "z_score" in result_a.indicators
