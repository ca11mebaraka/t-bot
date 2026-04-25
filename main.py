"""
Точка входа. Запуск:
  python main.py --help
  python main.py portfolio          # показать портфель
  python main.py report [--days N]  # сводный отчёт + CSV
  python main.py trade              # запустить торгового бота
  python main.py trade --dry-run    # только сигналы, без сделок
"""
import argparse
import logging
import sys

from config import Config
from portfolio import get_portfolio, get_operations, get_portfolio_balance
from reports import (
    print_portfolio,
    print_operations,
    print_summary_report,
    save_portfolio_csv,
    save_operations_csv,
)
from trader import run_trading_loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


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
    if getattr(args, "dry_run", False):
        logger.info("Режим dry-run: сделки выставляться НЕ будут")
        # В dry-run подменяем place_market_order на заглушку
        import client as client_module

        def _fake_order(*a, **kw):
            from tinkoff.invest import PostOrderResponse, Quotation, MoneyValue
            logger.info("[DRY-RUN] Заявка НЕ выставлена")
            resp = PostOrderResponse()
            resp.executed_order_price.CopyFrom(Quotation(units=0, nano=0))
            return resp

        client_module.place_market_order = _fake_order

    logger.info("Запуск торгового бота...")
    try:
        run_trading_loop(config)
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="T-Инвестиции: автоматическая торговля и отчётность"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # portfolio
    subparsers.add_parser("portfolio", help="Показать текущий портфель")

    # report
    report_parser = subparsers.add_parser("report", help="Сводный отчёт + экспорт CSV")
    report_parser.add_argument(
        "--days", type=int, default=30, help="Глубина истории операций в днях (по умолчанию 30)"
    )

    # trade
    trade_parser = subparsers.add_parser("trade", help="Запустить торгового бота")
    trade_parser.add_argument(
        "--dry-run", action="store_true", help="Только генерировать сигналы, без сделок"
    )

    args = parser.parse_args()

    try:
        config = Config()
    except KeyError as exc:
        logger.error("Отсутствует обязательная переменная окружения: %s", exc)
        logger.error("Скопируйте .env.example в .env и заполните INVEST_TOKEN")
        sys.exit(1)

    commands = {
        "portfolio": cmd_portfolio,
        "report": cmd_report,
        "trade": cmd_trade,
    }
    commands[args.command](config, args)


if __name__ == "__main__":
    main()
