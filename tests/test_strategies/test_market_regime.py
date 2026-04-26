from strategies.market_regime import MarketRegimeDetector


def test_market_regime_returns_recommendations(make_ohlcv):
    data = make_ohlcv(rows=260, trend=0.2)
    result = MarketRegimeDetector().detect(data)

    assert result["regime"] in {
        "trending_up",
        "trending_down",
        "ranging",
        "high_volatility",
        "low_volatility",
    }
    assert result["recommended_strategies"]
