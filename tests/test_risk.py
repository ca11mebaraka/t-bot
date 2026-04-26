from decimal import Decimal

from risk import DailyRiskManager


def test_separate_broker_fee_is_visible_in_trade_summary():
    risk = DailyRiskManager(max_daily_loss=Decimal("1000"))

    risk.record_buy(
        figi="TEST",
        lots=1,
        price_per_share=Decimal("10"),
        lot_size=1,
        commission=Decimal("0"),
    )
    risk.record_commission(Decimal("0.42"))

    summary = risk.daily_summary()

    assert risk.state.total_commissions == Decimal("0.42")
    assert "Комиссии (итого):       -0.4200" in summary
    assert "комис=-0.4200" in summary
