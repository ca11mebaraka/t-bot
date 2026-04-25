"""
Точка входа T-Bot.

Команды:
  portfolio                       — текущий портфель
  report [--days N]               — сводный отчёт + CSV
  trade [--dry-run]               — торговый бот (ручной перезапуск)
  auto  [--dry-run]               — полный автомат (авто-перезапуск при ошибках,
                                    авто-сброс лимита на новый день)
  risk-status                     — текущее состояние риск-менеджера за сегодня
"""
import argparse
import logging
import sys
from typing import Optional

from config import Config
from portfolio import get_portfolio, get_operations, get_portfolio_balance
from reports import (
    print_portfolio,
    print_operations,
    print_summary_report,
    save_portfolio_csv,
    save_operations_csv,
)
from risk import DailyRiskManager
from risk_history import hydrate_risk_from_operations
from trader import run_trading_loop, run_auto_loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── helpers ───────────────────────────────────────────────────────────────────

def _build_risk_manager(config: Config) -> Optional[DailyRiskManager]:
    """Создаёт DailyRiskManager если MAX_DAILY_LOSS задан в конфиге."""
    if config.max_daily_loss is None:
        return None
    risk = DailyRiskManager(max_daily_loss=config.max_daily_loss)
    logger.info(
        "Риск-менеджер инициализирован. Лимит дневных потерь: -%s",
        config.max_daily_loss,
    )
    return risk


def _patch_dry_run() -> None:
    """Подменяет place_market_order заглушкой для dry-run."""
    import client as client_module

    def _fake_order(*a, **kw):
        from t_tech.invest import PostOrderResponse, Quotation, MoneyValue
        logger.info("[DRY-RUN] Заявка НЕ выставлена")
        resp = PostOrderResponse()
        resp.executed_order_price.CopyFrom(Quotation(units=0, nano=0))
        resp.executed_commission.CopyFrom(MoneyValue(units=0, nano=0, currency="rub"))
        resp.lots_executed = kw.get("quantity", 1)
        return resp

    client_module.place_market_order = _fake_order


# ── команды ───────────────────────────────────────────────────────────────────

def cmd_portfolio(config: Config, args: argparse.Namespace) -> None:
    logger.info("Загрузка портфеля...")
    positions = get_portfolio(config)
    balances = get_portfolio_balance(config)
    print_portfolio(positions, balances)


def cmd_report(config: Config, args: argparse.Namespace) -> None:
    days = getattr(args, "days", 30)
    logger.info("Загрузка данных за последние %d дней...", days)
    positions = get_portfolio(config)
    balances = get_portfolio_balance(config)
    operations = get_operations(config, days=days)

    print_portfolio(positions, balances)
    print_operations(operations)
    print_summary_report(positions, operations)

    p1 = save_portfolio_csv(positions, config)
    p2 = save_operations_csv(operations, config)
    print(f"CSV сохранены:\n  {p1}\n  {p2}")


def cmd_trade(config: Config, args: argparse.Namespace) -> None:
    """Запускает торговый цикл. При ошибке — останавливается (нет авто-перезапуска)."""
    if getattr(args, "dry_run", False):
        logger.info("Режим dry-run: сделки выставляться НЕ будут")
        _patch_dry_run()

    risk = _build_risk_manager(config)
    if risk is None:
        logger.warning(
            "MAX_DAILY_LOSS не задан — торговля без ограничения дневных потерь. "
            "Установите MAX_DAILY_LOSS в .env для защиты капитала."
        )

    logger.info("Запуск торгового бота (режим: %s)...", config.mode)
    try:
        run_trading_loop(config, risk)
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем.")
        if risk is not None:
            print(risk.daily_summary())


def cmd_auto(config: Config, args: argparse.Namespace) -> None:
    """
    Полный автомат. Отличия от trade:
      - Авто-перезапуск при сетевых/API ошибках (задержка AUTO_RESTART_DELAY сек.)
      - Требует MAX_DAILY_LOSS — без него запуск отклоняется
      - При достижении лимита переходит в режим ожидания, торговля
        возобновляется автоматически на следующий день
      - При остановке (Ctrl+C) выводит дневной итог
    """
    if getattr(args, "dry_run", False):
        logger.info("Режим dry-run: сделки выставляться НЕ будут")
        _patch_dry_run()

    if config.max_daily_loss is None:
        logger.error(
            "Для режима auto необходимо задать MAX_DAILY_LOSS в .env.\n"
            "Пример: MAX_DAILY_LOSS=1000"
        )
        sys.exit(1)

    risk = DailyRiskManager(max_daily_loss=config.max_daily_loss)
    logger.info(
        "Полный автомат запущен. Режим: %s | Лимит потерь: -%s/день | "
        "Перезапуск при ошибке: %ds",
        config.mode, config.max_daily_loss, config.auto_restart_delay,
    )

    try:
        run_auto_loop(config, risk)
    except KeyboardInterrupt:
        pass   # run_auto_loop сам логирует и выводит daily_summary


def cmd_risk_status(config: Config, args: argparse.Namespace) -> None:
    """Показывает текущее состояние риск-менеджера за сегодня из операций API."""
    if config.max_daily_loss is None:
        print("MAX_DAILY_LOSS не задан в .env.")
        return

    from client import get_client, resolve_account_id

    risk = DailyRiskManager(max_daily_loss=config.max_daily_loss)

    with get_client(config) as client:
        account_id = resolve_account_id(client, config)
        hydrate_risk_from_operations(risk, client, account_id, config)

    print(risk.daily_summary())


# ── точка входа ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="T-Invest Bot: автоматическая торговля и отчётность"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("portfolio", help="Показать текущий портфель")

    report_p = subparsers.add_parser("report", help="Сводный отчёт + экспорт CSV")
    report_p.add_argument("--days", type=int, default=30,
                          help="Глубина истории в днях (по умолчанию 30)")

    trade_p = subparsers.add_parser(
        "trade",
        help="Торговый бот (остановка при первой ошибке)",
    )
    trade_p.add_argument("--dry-run", action="store_true",
                         help="Генерировать сигналы без выставления заявок")

    auto_p = subparsers.add_parser(
        "auto",
        help="Полный автомат: авто-перезапуск + дневной лимит потерь (требует MAX_DAILY_LOSS)",
    )
    auto_p.add_argument("--dry-run", action="store_true",
                        help="Генерировать сигналы без выставления заявок")

    subparsers.add_parser(
        "risk-status",
        help="Показать P&L и комиссии за сегодня из истории операций",
    )

    args = parser.parse_args()

    try:
        config = Config()
    except KeyError as exc:
        logger.error("Отсутствует обязательная переменная окружения: %s", exc)
        logger.error("Скопируйте .env.example в .env и заполните INVEST_TOKEN")
        sys.exit(1)

    dispatch = {
        "portfolio":   cmd_portfolio,
        "report":      cmd_report,
        "trade":       cmd_trade,
        "auto":        cmd_auto,
        "risk-status": cmd_risk_status,
    }
    dispatch[args.command](config, args)


if __name__ == "__main__":
    main()
