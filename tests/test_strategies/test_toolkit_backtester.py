from strategies.backtester import Backtester
from strategies.toolkit import StrategyToolkit
from strategies.trend_following import TrendFollowingStrategy


def test_backtester_returns_metrics(make_ohlcv):
    data = make_ohlcv(rows=260, trend=0.2)
    result = Backtester().run(TrendFollowingStrategy({"fast_period": 5, "slow_period": 20}), data)

    assert result.total_trades >= 0
    assert 0 <= result.win_rate <= 1
    assert result.max_drawdown >= 0


def test_toolkit_lists_and_runs_strategy(make_ohlcv, StaticDataProvider):
    data = make_ohlcv(rows=260, trend=0.2)
    toolkit = StrategyToolkit(StaticDataProvider(data))

    listed = toolkit.list_strategies()
    result = toolkit.run_strategy(
        "trend_following",
        "TEST",
        {"fast_period": 5, "slow_period": 20, "adx_threshold": 0},
        interval="1_HOUR",
    )

    assert listed["strategies"]
    assert result["strategy_name"] == "trend_following"
    assert "signal" in result
