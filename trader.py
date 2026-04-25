"""
Торговый движок: загружает исторические свечи, инициализирует стратегии,
в цикле запрашивает последние цены и исполняет сигналы.
"""
import logging
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from tinkoff.invest import CandleInterval, OrderDirection
from tinkoff.invest.utils import now

from client import (
    get_client,
    resolve_account_id,
    quotation_to_decimal,
    place_market_order,
    place_stop_orders,
)
from config import Config
from strategies import BaseStrategy, MACrossoverStrategy, RSIStrategy, Signal, SignalType

logger = logging.getLogger(__name__)


def _load_candles(client, instrument_id: str, days: int = 30) -> list[Decimal]:
    """Загружает дневные свечи за последние N дней для инициализации стратегии."""
    prices = []
    for candle in client.get_all_candles(
        instrument_id=instrument_id,
        from_=now() - timedelta(days=days),
        to=now(),
        interval=CandleInterval.CANDLE_INTERVAL_DAY,
    ):
        prices.append(quotation_to_decimal(candle.close))
    return prices


def _get_last_price(client, instrument_id: str) -> Optional[Decimal]:
    """Возвращает последнюю цену инструмента."""
    response = client.market_data.get_last_prices(instrument_id=[instrument_id])
    if not response.last_prices:
        return None
    return quotation_to_decimal(response.last_prices[0].price)


def _get_instrument_info(client, instrument_id: str) -> dict:
    """Получает минимальный шаг цены и размер лота."""
    info = client.instruments.get_instrument_by(
        id_type=1,  # INSTRUMENT_ID_TYPE_FIGI
        id=instrument_id,
    ).instrument
    return {
        "lot": info.lot,
        "min_price_increment": quotation_to_decimal(info.min_price_increment),
        "name": info.name,
        "ticker": info.ticker,
        "currency": info.currency,
    }


def _execute_signal(
    client,
    account_id: str,
    signal: Signal,
    config: Config,
    price_step: Decimal,
) -> None:
    """Исполняет торговый сигнал: выставляет рыночную заявку + стоп-ордера."""
    direction = (
        OrderDirection.ORDER_DIRECTION_BUY
        if signal.type == SignalType.BUY
        else OrderDirection.ORDER_DIRECTION_SELL
    )

    try:
        response = place_market_order(
            client,
            account_id=account_id,
            instrument_id=signal.instrument_id,
            direction=direction,
            quantity=config.max_lots,
        )
        executed_price = quotation_to_decimal(response.executed_order_price)
        logger.info(
            "Заявка исполнена: %s %s по %.4f",
            signal.type.value,
            signal.instrument_id,
            executed_price,
        )

        if signal.type == SignalType.BUY and not config.is_sandbox:
            place_stop_orders(
                client,
                account_id=account_id,
                instrument_id=signal.instrument_id,
                executed_price=executed_price,
                quantity=config.max_lots,
                price_step=price_step,
            )
    except Exception as exc:
        logger.error("Ошибка исполнения заявки: %s", exc)


def build_strategies(config: Config, instruments_info: dict) -> dict[str, list[BaseStrategy]]:
    """Создаёт экземпляры стратегий для каждого инструмента."""
    strategies: dict[str, list[BaseStrategy]] = {}
    for figi in config.instruments:
        strategies[figi] = [
            MACrossoverStrategy(figi, config.ma_short, config.ma_long),
            RSIStrategy(figi, config.rsi_period, config.rsi_oversold, config.rsi_overbought),
        ]
    return strategies


def warm_up_strategies(
    client,
    strategies: dict[str, list[BaseStrategy]],
    days: int = 60,
) -> None:
    """Прогрев стратегий на исторических данных."""
    for figi, strat_list in strategies.items():
        logger.info("Прогрев стратегий для %s ...", figi)
        prices = _load_candles(client, figi, days=days)
        for price in prices:
            for strat in strat_list:
                strat.update(price)
        logger.info("  Загружено %d свечей", len(prices))


def run_trading_loop(config: Config) -> None:
    """Основной торговый цикл."""
    with get_client(config) as client:
        account_id = resolve_account_id(client, config)
        logger.info("Счёт: %s | Режим: %s", account_id, config.mode)

        instruments_info = {}
        for figi in config.instruments:
            try:
                info = _get_instrument_info(client, figi)
                instruments_info[figi] = info
                logger.info("Инструмент: %s (%s)", info["name"], info["ticker"])
            except Exception as exc:
                logger.warning("Не удалось получить info для %s: %s", figi, exc)
                instruments_info[figi] = {"lot": 1, "min_price_increment": Decimal("0.01")}

        strategies = build_strategies(config, instruments_info)
        warm_up_strategies(client, strategies)

        logger.info("Торговый цикл запущен. Интервал проверки: %ds", config.check_interval)
        while True:
            for figi, strat_list in strategies.items():
                price = _get_last_price(client, figi)
                if price is None:
                    logger.warning("Нет цены для %s", figi)
                    continue

                info = instruments_info.get(figi, {})
                price_step = info.get("min_price_increment", Decimal("0.01"))

                for strat in strat_list:
                    signal = strat.update(price)
                    if signal is not None:
                        logger.info(
                            "[%s] Сигнал %s: %s (цена %.4f)",
                            strat.name,
                            signal.type.value,
                            signal.reason,
                            price,
                        )
                        _execute_signal(client, account_id, signal, config, price_step)

            time.sleep(config.check_interval)
