import logging
from datetime import date, timedelta
from decimal import Decimal

from t_tech.invest import OperationType
from t_tech.invest.utils import now

from client import money_value_to_decimal
from config import Config
from risk import DailyRiskManager

logger = logging.getLogger(__name__)


def _load_operations(client, account_id: str, config: Config):
    from_ = now() - timedelta(days=config.risk_history_days)
    if config.is_sandbox:
        return client.sandbox.get_sandbox_operations(
            account_id=account_id,
            from_=from_,
            to=now(),
        ).operations
    return client.operations.get_operations(
        account_id=account_id,
        from_=from_,
        to=now(),
    ).operations


def _get_lot_size(client, figi: str, cache: dict[str, int]) -> int:
    if figi in cache:
        return cache[figi]
    try:
        info = client.instruments.get_instrument_by(id_type=1, id=figi).instrument
        cache[figi] = info.lot or 1
    except Exception:
        cache[figi] = 1
    return cache[figi]


def hydrate_risk_from_operations(
    risk: DailyRiskManager,
    client,
    account_id: str,
    config: Config,
) -> None:
    """Restores FIFO cost basis and today's risk state from account operations."""
    if risk.history_loaded:
        return

    operations = sorted(_load_operations(client, account_id, config), key=lambda op: op.date)
    today = date.today()
    lot_cache: dict[str, int] = {}

    buys = 0
    sells = 0
    fees = Decimal(0)
    for op in operations:
        op_date = op.date.date()

        if op.operation_type in (
            OperationType.OPERATION_TYPE_BUY,
            OperationType.OPERATION_TYPE_SELL,
        ):
            if op.quantity <= 0:
                continue

            lot_size = _get_lot_size(client, op.figi, lot_cache)
            lots = op.quantity // lot_size or 1
            shares = lots * lot_size
            price = money_value_to_decimal(op.price)

            if op.operation_type == OperationType.OPERATION_TYPE_BUY:
                if op_date == today:
                    risk.record_buy(op.figi, lots, price, lot_size, Decimal(0), timestamp=op.date)
                    buys += 1
                else:
                    risk.seed_buy(op.figi, shares, price)
            else:
                if op_date == today:
                    risk.record_sell(op.figi, lots, price, lot_size, Decimal(0), timestamp=op.date)
                    sells += 1
                else:
                    risk.seed_sell(op.figi, shares, price)

        elif op.operation_type == OperationType.OPERATION_TYPE_BROKER_FEE and op_date == today:
            risk.record_commission(abs(money_value_to_decimal(op.payment)))
            fees += abs(money_value_to_decimal(op.payment))

    risk.history_loaded = True
    logger.info(
        "Риск восстановлен из операций за %d дн.: покупок сегодня=%d, продаж сегодня=%d, комиссий=%.4f",
        config.risk_history_days,
        buys,
        sells,
        fees,
    )
