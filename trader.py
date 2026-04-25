"""
Торговый движок: загружает исторические свечи, инициализирует стратегии,
в цикле запрашивает последние цены и исполняет сигналы.
"""
import logging
import time
from datetime import timedelta
from decimal import Decimal
from typing import Optional

from tinkoff.invest import CandleInterval, OrderDirection
from tinkoff.invest.utils import now

from client import (
    get_client,
    resolve_account_id,
    quotation_to_decimal,
    money_value_to_decimal,
    place_market_order,
    place_stop_orders,
)
from config import Config
from risk import DailyRiskManager
from strategies import BaseStrategy, MACrossoverStrategy, RSIStrategy, Signal, SignalType

logger = logging.getLogger(__name__)

# Сколько секунд ждать в auto-режиме после достижения дневного лимита
# перед каждой следующей проверкой состояния
_HALTED_POLL_INTERVAL = 60


def _load_candles(client, instrument_id: str, days: int = 30) -> list[Decimal]:
    """Загружает дневные свечи за последние N дней для инициализации стратегий."""
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
    response = client.market_data.get_last_prices(instrument_id=[instrument_id])
    if not response.last_prices:
        return None
    return quotation_to_decimal(response.last_prices[0].price)


def _get_instrument_info(client, instrument_id: str) -> dict:
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
    lot_size: int,
    risk: Optional[DailyRiskManager],
) -> bool:
    """
    Исполняет торговый сигнал.
    Возвращает True если заявка выставлена успешно, False при ошибке.
    """
    # ── проверка риск-лимита ─────────────────────────────────────────────────
    if risk is not None:
        allowed, reason = risk.can_trade()
        if not allowed:
            logger.warning("Сигнал %s пропущен — торговля остановлена: %s",
                           signal.type.value, reason)
            return False

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
        commission = money_value_to_decimal(response.executed_commission)
        lots_done = response.lots_executed or config.max_lots

        logger.info(
            "Заявка исполнена: %s %s по %.4f | лоты: %d | комиссия: %.4f",
            signal.type.value,
            signal.instrument_id,
            executed_price,
            lots_done,
            commission,
        )

        # ── запись в риск-менеджер ────────────────────────────────────────────
        if risk is not None and executed_price > 0:
            if signal.type == SignalType.BUY:
                risk.record_buy(
                    figi=signal.instrument_id,
                    lots=lots_done,
                    price_per_share=executed_price,
                    lot_size=lot_size,
                    commission=commission,
                )
            else:
                risk.record_sell(
                    figi=signal.instrument_id,
                    lots=lots_done,
                    price_per_share=executed_price,
                    lot_size=lot_size,
                    commission=commission,
                )

        # ── стоп-ордера только в production после покупки ─────────────────────
        if signal.type == SignalType.BUY and not config.is_sandbox and executed_price > 0:
            place_stop_orders(
                client,
                account_id=account_id,
                instrument_id=signal.instrument_id,
                executed_price=executed_price,
                quantity=lots_done,
                price_step=price_step,
            )

        return True

    except Exception as exc:
        logger.error("Ошибка исполнения заявки: %s", exc)
        return False


def build_strategies(config: Config) -> dict[str, list[BaseStrategy]]:
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
    for figi, strat_list in strategies.items():
        logger.info("Прогрев стратегий для %s ...", figi)
        prices = _load_candles(client, figi, days=days)
        for price in prices:
            for strat in strat_list:
                strat.update(price)
        logger.info("  Загружено %d свечей", len(prices))


def run_trading_loop(
    config: Config,
    risk: Optional[DailyRiskManager] = None,
) -> None:
    """
    Основной торговый цикл. Завершается только при KeyboardInterrupt или
    необработанном исключении (не перехватывает — пусть поднимается выше).
    """
    with get_client(config) as client:
        account_id = resolve_account_id(client, config)
        logger.info("Счёт: %s | Режим: %s", account_id, config.mode)

        instruments_info: dict[str, dict] = {}
        for figi in config.instruments:
            try:
                info = _get_instrument_info(client, figi)
                instruments_info[figi] = info
                logger.info("Инструмент: %s (%s) | лот=%d", info["name"], info["ticker"], info["lot"])
            except Exception as exc:
                logger.warning("Не удалось получить info для %s: %s", figi, exc)
                instruments_info[figi] = {"lot": 1, "min_price_increment": Decimal("0.01")}

        strategies = build_strategies(config)
        warm_up_strategies(client, strategies)

        if risk is not None:
            logger.info("Риск-менеджер активен. Лимит: -%s в день", risk.max_daily_loss)

        logger.info("Торговый цикл запущен. Интервал: %ds", config.check_interval)

        last_status_ts = time.monotonic()

        while True:
            # ── периодический лог статуса ─────────────────────────────────────
            if risk is not None and config.status_interval > 0:
                if time.monotonic() - last_status_ts >= config.status_interval:
                    logger.info(risk.status_line())
                    last_status_ts = time.monotonic()

            # ── если лимит достигнут — пропускаем торговлю, ждём нового дня ──
            if risk is not None:
                allowed, reason = risk.can_trade()
                if not allowed:
                    logger.debug("Торговля остановлена: %s. Ожидание...", reason)
                    time.sleep(_HALTED_POLL_INTERVAL)
                    continue

            # ── основной торговый проход ──────────────────────────────────────
            for figi, strat_list in strategies.items():
                price = _get_last_price(client, figi)
                if price is None:
                    logger.warning("Нет цены для %s", figi)
                    continue

                info = instruments_info.get(figi, {})
                price_step = info.get("min_price_increment", Decimal("0.01"))
                lot_size   = info.get("lot", 1)

                for strat in strat_list:
                    signal = strat.update(price)
                    if signal is not None:
                        logger.info(
                            "[%s] Сигнал %s: %s (цена %.4f)",
                            strat.name, signal.type.value, signal.reason, price,
                        )
                        _execute_signal(
                            client, account_id, signal, config,
                            price_step, lot_size, risk,
                        )

            time.sleep(config.check_interval)


def run_auto_loop(config: Config, risk: DailyRiskManager) -> None:
    """
    Полный автомат: торговый цикл с автоматическим перезапуском при ошибках.
    Останавливается только по Ctrl+C.

    При достижении дневного лимита цикл не прерывается — он переходит
    в режим ожидания (polling раз в минуту) и возобновляет торговлю
    на следующий день автоматически (DailyRiskManager сбрасывается сам).
    """
    restart_delay = config.auto_restart_delay
    attempt = 0

    while True:
        attempt += 1
        try:
            logger.info("Запуск торгового цикла (попытка %d)", attempt)
            run_trading_loop(config, risk)
            # Нормальный выход из цикла не должен происходить — если вышли,
            # значит что-то завершило loop без исключения; перезапускаем.
            logger.warning("Торговый цикл завершился без исключения. Перезапуск...")
        except KeyboardInterrupt:
            logger.info("\nАвтомат остановлен пользователем (Ctrl+C).")
            logger.info(risk.daily_summary())
            raise
        except Exception as exc:
            logger.error(
                "Необработанная ошибка: %s. Перезапуск через %ds...",
                exc, restart_delay, exc_info=True,
            )

        time.sleep(restart_delay)
