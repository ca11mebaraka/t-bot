"""
Модуль работы с портфелем: позиции, операции, P&L.
"""
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from tinkoff.invest import OperationType
from tinkoff.invest.utils import now

from client import get_client, resolve_account_id, money_value_to_decimal, quotation_to_decimal
from config import Config

logger = logging.getLogger(__name__)


@dataclass
class PositionSummary:
    figi: str
    ticker: str
    name: str
    quantity: int
    avg_price: Decimal
    current_price: Decimal
    currency: str

    @property
    def market_value(self) -> Decimal:
        return self.quantity * self.current_price

    @property
    def pnl(self) -> Decimal:
        return (self.current_price - self.avg_price) * self.quantity

    @property
    def pnl_pct(self) -> float:
        if self.avg_price == 0:
            return 0.0
        return float((self.current_price - self.avg_price) / self.avg_price * 100)


@dataclass
class OperationRecord:
    date: datetime
    type: str
    ticker: str
    figi: str
    quantity: int
    price: Decimal
    payment: Decimal
    currency: str


def get_portfolio(config: Config) -> list[PositionSummary]:
    """Возвращает список позиций с рыночными ценами."""
    with get_client(config) as client:
        account_id = resolve_account_id(client, config)

        if config.is_sandbox:
            portfolio = client.sandbox.get_sandbox_portfolio(account_id=account_id)
        else:
            portfolio = client.operations.get_portfolio(account_id=account_id)

        positions = []
        for pos in portfolio.positions:
            figi = pos.figi
            quantity = int(quotation_to_decimal(pos.quantity))
            avg_price = money_value_to_decimal(pos.average_buy_price)
            current_price = money_value_to_decimal(pos.current_price)
            currency = pos.average_buy_price.currency

            try:
                info = client.instruments.get_instrument_by(id_type=1, id=figi).instrument
                ticker = info.ticker
                name = info.name
            except Exception:
                ticker = figi
                name = figi

            positions.append(
                PositionSummary(
                    figi=figi,
                    ticker=ticker,
                    name=name,
                    quantity=quantity,
                    avg_price=avg_price,
                    current_price=current_price,
                    currency=currency,
                )
            )

        return positions


def get_operations(config: Config, days: int = 30) -> list[OperationRecord]:
    """Возвращает историю операций за последние N дней."""
    with get_client(config) as client:
        account_id = resolve_account_id(client, config)

        from_ = now() - timedelta(days=days)

        if config.is_sandbox:
            ops_response = client.sandbox.get_sandbox_operations(
                account_id=account_id,
                from_=from_,
                to=now(),
            )
        else:
            ops_response = client.operations.get_operations(
                account_id=account_id,
                from_=from_,
                to=now(),
            )

        records = []
        for op in ops_response.operations:
            if op.operation_type in (
                OperationType.OPERATION_TYPE_BUY,
                OperationType.OPERATION_TYPE_SELL,
            ):
                try:
                    info = client.instruments.get_instrument_by(
                        id_type=1, id=op.figi
                    ).instrument
                    ticker = info.ticker
                except Exception:
                    ticker = op.figi

                records.append(
                    OperationRecord(
                        date=op.date,
                        type="BUY" if op.operation_type == OperationType.OPERATION_TYPE_BUY else "SELL",
                        ticker=ticker,
                        figi=op.figi,
                        quantity=op.quantity,
                        price=money_value_to_decimal(op.price),
                        payment=money_value_to_decimal(op.payment),
                        currency=op.payment.currency,
                    )
                )
        return records


def get_portfolio_balance(config: Config) -> dict[str, Decimal]:
    """Возвращает денежные остатки по валютам."""
    with get_client(config) as client:
        account_id = resolve_account_id(client, config)

        if config.is_sandbox:
            positions_resp = client.sandbox.get_sandbox_positions(account_id=account_id)
        else:
            positions_resp = client.operations.get_positions(account_id=account_id)

        return {
            mv.currency.upper(): money_value_to_decimal(mv)
            for mv in positions_resp.money
        }
