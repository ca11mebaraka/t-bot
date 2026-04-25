"""
Отчётность: вывод в консоль и сохранение CSV.
"""
import csv
import logging
from datetime import datetime, timezone
from pathlib import Path

from tabulate import tabulate

from config import Config
from portfolio import PositionSummary, OperationRecord

logger = logging.getLogger(__name__)


def _ensure_reports_dir(config: Config) -> Path:
    config.reports_dir.mkdir(parents=True, exist_ok=True)
    return config.reports_dir


def print_portfolio(positions: list[PositionSummary], balances: dict) -> None:
    """Выводит таблицу позиций в консоль."""
    if not positions:
        print("\nПортфель пуст.\n")
        return

    rows = []
    total_value = 0
    total_pnl = 0

    for p in positions:
        rows.append([
            p.ticker,
            p.name[:30],
            p.quantity,
            f"{p.avg_price:.4f}",
            f"{p.current_price:.4f}",
            f"{p.market_value:.2f} {p.currency}",
            f"{p.pnl:+.2f}",
            f"{p.pnl_pct:+.2f}%",
        ])
        total_value += float(p.market_value)
        total_pnl += float(p.pnl)

    headers = ["Тикер", "Название", "Кол-во", "Ср.цена", "Тек.цена", "Стоимость", "P&L", "P&L%"]
    print("\n=== ПОРТФЕЛЬ ===")
    print(tabulate(rows, headers=headers, tablefmt="rounded_grid"))
    print(f"\nИтого рыночная стоимость: {total_value:,.2f}")
    print(f"Итого P&L:               {total_pnl:+,.2f}")

    if balances:
        print("\nДенежные остатки:")
        for currency, amount in sorted(balances.items()):
            print(f"  {currency}: {amount:,.2f}")
    print()


def print_operations(operations: list[OperationRecord]) -> None:
    """Выводит историю операций в консоль."""
    if not operations:
        print("\nОпераций нет.\n")
        return

    rows = [
        [
            op.date.strftime("%Y-%m-%d %H:%M"),
            op.type,
            op.ticker,
            op.quantity,
            f"{op.price:.4f}",
            f"{op.payment:+.2f} {op.currency}",
        ]
        for op in sorted(operations, key=lambda o: o.date, reverse=True)
    ]
    headers = ["Дата", "Тип", "Тикер", "Кол-во", "Цена", "Сумма"]
    print("\n=== ОПЕРАЦИИ ===")
    print(tabulate(rows, headers=headers, tablefmt="rounded_grid"))
    print()


def save_portfolio_csv(positions: list[PositionSummary], config: Config) -> Path:
    """Сохраняет позиции в CSV-файл."""
    reports_dir = _ensure_reports_dir(config)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = reports_dir / f"portfolio_{ts}.csv"

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["ticker", "name", "quantity", "avg_price", "current_price",
                         "market_value", "pnl", "pnl_pct", "currency"])
        for p in positions:
            writer.writerow([
                p.ticker, p.name, p.quantity,
                f"{p.avg_price:.4f}", f"{p.current_price:.4f}",
                f"{p.market_value:.2f}", f"{p.pnl:.2f}",
                f"{p.pnl_pct:.2f}", p.currency,
            ])

    logger.info("Портфель сохранён: %s", path)
    return path


def save_operations_csv(operations: list[OperationRecord], config: Config) -> Path:
    """Сохраняет историю операций в CSV-файл."""
    reports_dir = _ensure_reports_dir(config)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = reports_dir / f"operations_{ts}.csv"

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "type", "ticker", "figi", "quantity", "price", "payment", "currency"])
        for op in sorted(operations, key=lambda o: o.date):
            writer.writerow([
                op.date.strftime("%Y-%m-%d %H:%M:%S"),
                op.type, op.ticker, op.figi,
                op.quantity, f"{op.price:.4f}",
                f"{op.payment:.2f}", op.currency,
            ])

    logger.info("Операции сохранены: %s", path)
    return path


def print_summary_report(positions: list[PositionSummary], operations: list[OperationRecord]) -> None:
    """Краткий итоговый отчёт."""
    buys = [o for o in operations if o.type == "BUY"]
    sells = [o for o in operations if o.type == "SELL"]
    total_spent = sum(abs(float(o.payment)) for o in buys)
    total_received = sum(abs(float(o.payment)) for o in sells)

    print("\n=== СВОДНЫЙ ОТЧЁТ ===")
    print(f"Позиций в портфеле:  {len(positions)}")
    print(f"Операций покупки:    {len(buys)}")
    print(f"Операций продажи:    {len(sells)}")
    print(f"Потрачено (BUY):     {total_spent:,.2f}")
    print(f"Получено  (SELL):    {total_received:,.2f}")
    print(f"Реализ. P&L:         {total_received - total_spent:+,.2f}")
    unrealized = sum(float(p.pnl) for p in positions)
    print(f"Нереализ. P&L:       {unrealized:+,.2f}")
    print()
