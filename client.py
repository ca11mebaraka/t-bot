"""
Обёртка над tinkoff.invest Client/SandboxClient.
Предоставляет единый интерфейс для боевого и тестового режимов,
а также вспомогательные конверторы типов.
"""
import logging
import uuid
from contextlib import contextmanager
from decimal import Decimal
from typing import Generator

from tinkoff.invest import (
    Client,
    OrderDirection,
    OrderType,
    Quotation,
    MoneyValue,
    StopOrderType,
    StopOrderExpirationType,
)
from tinkoff.invest.constants import INVEST_GRPC_API, INVEST_GRPC_API_SANDBOX
from tinkoff.invest.sandbox.client import SandboxClient

from config import Config

logger = logging.getLogger(__name__)


def quotation_to_decimal(q: Quotation) -> Decimal:
    return Decimal(q.units) + Decimal(q.nano) / Decimal("1e9")


def money_value_to_decimal(mv: MoneyValue) -> Decimal:
    return Decimal(mv.units) + Decimal(mv.nano) / Decimal("1e9")


def decimal_to_quotation(value: Decimal) -> Quotation:
    units = int(value)
    nano = int((value - units) * Decimal("1e9"))
    return Quotation(units=units, nano=nano)


@contextmanager
def get_client(config: Config) -> Generator:
    """Возвращает подключённый клиент в зависимости от режима."""
    if config.is_sandbox:
        logger.info("Подключение к Sandbox API")
        with SandboxClient(
            token=config.token, target=INVEST_GRPC_API_SANDBOX
        ) as client:
            yield client
    else:
        logger.info("Подключение к Production API")
        with Client(token=config.token, target=INVEST_GRPC_API) as client:
            yield client


def resolve_account_id(client, config: Config) -> str:
    """Возвращает account_id из конфига или берёт первый доступный счёт."""
    if config.account_id:
        return config.account_id

    if config.is_sandbox:
        accounts = client.sandbox.get_sandbox_accounts().accounts
        if not accounts:
            response = client.sandbox.open_sandbox_account()
            logger.info("Открыт новый sandbox-счёт: %s", response.account_id)
            return response.account_id
    else:
        accounts = client.users.get_accounts().accounts

    if not accounts:
        raise RuntimeError("Нет доступных торговых счётов")

    account_id = accounts[0].id
    logger.info("Используется счёт: %s", account_id)
    return account_id


def place_market_order(
    client,
    account_id: str,
    instrument_id: str,
    direction: OrderDirection,
    quantity: int,
) -> object:
    """Выставляет рыночную заявку. Возвращает PostOrderResponse."""
    order_id = str(uuid.uuid4())
    logger.info(
        "Выставляем рыночную заявку: %s %d лот(ов) %s",
        "BUY" if direction == OrderDirection.ORDER_DIRECTION_BUY else "SELL",
        quantity,
        instrument_id,
    )
    if hasattr(client, "sandbox"):
        return client.sandbox.post_sandbox_order(
            order_type=OrderType.ORDER_TYPE_MARKET,
            direction=direction,
            instrument_id=instrument_id,
            quantity=quantity,
            account_id=account_id,
            order_id=order_id,
        )
    return client.orders.post_order(
        order_type=OrderType.ORDER_TYPE_MARKET,
        direction=direction,
        instrument_id=instrument_id,
        quantity=quantity,
        account_id=account_id,
        order_id=order_id,
    )


def place_stop_orders(
    client,
    account_id: str,
    instrument_id: str,
    executed_price: Decimal,
    quantity: int,
    take_profit_pct: float = 0.05,
    stop_loss_pct: float = 0.02,
    price_step: Decimal = Decimal("0.01"),
) -> None:
    """Выставляет тейк-профит и стоп-лосс после исполнения заявки."""
    from datetime import datetime, timedelta, timezone

    expire_date = datetime.now(timezone.utc) + timedelta(days=1)

    take_price = (executed_price * Decimal(1 + take_profit_pct)).quantize(price_step)
    stop_price = (executed_price * Decimal(1 - stop_loss_pct)).quantize(price_step)

    for label, stop_type, price in (
        ("Take-profit", StopOrderType.STOP_ORDER_TYPE_TAKE_PROFIT, take_price),
        ("Stop-loss", StopOrderType.STOP_ORDER_TYPE_STOP_LOSS, stop_price),
    ):
        logger.info("%s: %.4f", label, price)
        client.stop_orders.post_stop_order(
            instrument_id=instrument_id,
            quantity=quantity,
            stop_price=decimal_to_quotation(price),
            direction=OrderDirection.ORDER_DIRECTION_SELL,
            account_id=account_id,
            stop_order_type=stop_type,
            expire_date=expire_date,
            expiration_type=StopOrderExpirationType.STOP_ORDER_EXPIRATION_TYPE_GOOD_TILL_DATE,
        )
