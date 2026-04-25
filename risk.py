"""
Дневной риск-менеджер.

Отслеживает реализованный P&L и комиссии по всем сделкам текущего дня.
Останавливает торговлю, когда чистый убыток достигает MAX_DAILY_LOSS.

Формула:
    net_result = realized_pnl - total_commissions
    if net_result <= -max_daily_loss → торговля запрещена до следующего дня

Реализованный P&L считается методом FIFO: при каждой продаже находим
самую раннюю открытую покупку для этого инструмента и фиксируем разницу.
"""
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class TradeRecord:
    timestamp: datetime
    figi: str
    direction: str        # "BUY" | "SELL"
    lots: int
    price_per_share: Decimal
    commission: Decimal
    realized_pnl: Decimal = Decimal(0)   # заполняется только для SELL


@dataclass
class DailyRiskState:
    trade_date: date
    trades: list[TradeRecord] = field(default_factory=list)
    realized_pnl: Decimal = field(default=Decimal(0))
    total_commissions: Decimal = field(default=Decimal(0))
    is_halted: bool = False
    halt_reason: str = ""

    @property
    def net_result(self) -> Decimal:
        return self.realized_pnl - self.total_commissions

    @property
    def trade_count(self) -> int:
        return len(self.trades)


class DailyRiskManager:
    """
    Потокобезопасность не гарантируется — предполагается однопоточный цикл.
    При смене даты состояние сбрасывается автоматически в методе _ensure_today().
    """

    def __init__(self, max_daily_loss: Decimal):
        if max_daily_loss <= 0:
            raise ValueError(f"max_daily_loss должен быть > 0, получено: {max_daily_loss}")
        self.max_daily_loss = max_daily_loss
        self._state: DailyRiskState = self._make_state()
        # FIFO книга позиций: figi -> deque[(price_per_share, total_shares)]
        self._book: dict[str, deque[tuple[Decimal, int]]] = {}
        self.history_loaded = False

    # ── внутренние методы ─────────────────────────────────────────────────────

    @staticmethod
    def _make_state() -> DailyRiskState:
        return DailyRiskState(trade_date=date.today())

    def _ensure_today(self) -> None:
        today = date.today()
        if self._state.trade_date != today:
            logger.info(
                "Новый торговый день (%s). Сброс риск-лимита. Итог прошлого дня: %+.4f",
                today,
                self._state.net_result,
            )
            self._state = self._make_state()

    def _fifo_close(self, figi: str, sell_price: Decimal, shares: int) -> Decimal:
        """
        Закрывает позицию методом FIFO. Возвращает реализованный P&L.
        Если в книге нет встречных покупок (например, покупка была до старта
        бота), стоимость базиса принимается равной цене продажи (P&L = 0).
        """
        book = self._book.get(figi, deque())
        pnl = Decimal(0)
        remaining = shares

        while remaining > 0 and book:
            buy_price, buy_shares = book[0]
            used = min(remaining, buy_shares)
            pnl += (sell_price - buy_price) * Decimal(used)
            remaining -= used
            if used == buy_shares:
                book.popleft()
            else:
                book[0] = (buy_price, buy_shares - used)

        # remaining > 0 означает, что продали больше чем купили сегодня
        # P&L для неизвестного базиса = 0 (консервативно)
        return pnl

    def _check_limit(self) -> None:
        if self._state.is_halted:
            return
        if self._state.net_result <= -self.max_daily_loss:
            self._state.is_halted = True
            self._state.halt_reason = (
                f"Лимит дневных потерь достигнут: "
                f"{self._state.net_result:+.2f} ≤ -{self.max_daily_loss:.2f}"
            )
            logger.warning("ТОРГОВЛЯ ОСТАНОВЛЕНА НА СЕГОДНЯ. %s", self._state.halt_reason)

    # ── публичный API ─────────────────────────────────────────────────────────

    def seed_buy(self, figi: str, shares: int, price_per_share: Decimal) -> None:
        """Добавляет историческую покупку в FIFO без влияния на дневной риск."""
        if shares > 0:
            self._book.setdefault(figi, deque()).append((price_per_share, shares))

    def seed_sell(self, figi: str, shares: int, price_per_share: Decimal) -> Decimal:
        """Закрывает историческую продажу в FIFO без влияния на дневной риск."""
        if shares <= 0:
            return Decimal(0)
        return self._fifo_close(figi, price_per_share, shares)

    def can_trade(self) -> tuple[bool, str]:
        """
        Вызвать перед каждой сделкой.
        Возвращает (True, "") если торговля разрешена,
        или (False, причина) если лимит достигнут.
        """
        self._ensure_today()
        if self._state.is_halted:
            return False, self._state.halt_reason
        return True, ""

    def record_buy(
        self,
        figi: str,
        lots: int,
        price_per_share: Decimal,
        lot_size: int,
        commission: Decimal,
        timestamp: Optional[datetime] = None,
    ) -> None:
        """Регистрирует исполненную покупку."""
        self._ensure_today()
        total_shares = lots * lot_size
        self._book.setdefault(figi, deque()).append((price_per_share, total_shares))
        self._state.total_commissions += commission
        self._state.trades.append(
            TradeRecord(
                timestamp=timestamp or datetime.now(timezone.utc),
                figi=figi, direction="BUY",
                lots=lots, price_per_share=price_per_share,
                commission=commission,
            )
        )
        logger.info(
            "[Риск] BUY  %s ×%d лот (×%d акц.) @ %.4f | комис. %+.4f | "
            "день P&L: %+.4f | до лимита: %.4f",
            figi, lots, total_shares, price_per_share,
            -commission, self._state.net_result,
            self.max_daily_loss + self._state.net_result,
        )
        self._check_limit()

    def record_sell(
        self,
        figi: str,
        lots: int,
        price_per_share: Decimal,
        lot_size: int,
        commission: Decimal,
        timestamp: Optional[datetime] = None,
    ) -> Decimal:
        """
        Регистрирует исполненную продажу.
        Возвращает реализованный P&L этой сделки (без учёта комиссии).
        """
        self._ensure_today()
        total_shares = lots * lot_size
        realized = self._fifo_close(figi, price_per_share, total_shares)
        self._state.realized_pnl += realized
        self._state.total_commissions += commission
        self._state.trades.append(
            TradeRecord(
                timestamp=timestamp or datetime.now(timezone.utc),
                figi=figi, direction="SELL",
                lots=lots, price_per_share=price_per_share,
                commission=commission, realized_pnl=realized,
            )
        )
        logger.info(
            "[Риск] SELL %s ×%d лот (×%d акц.) @ %.4f | реализ. P&L: %+.4f | "
            "комис. %+.4f | день P&L: %+.4f | до лимита: %.4f",
            figi, lots, total_shares, price_per_share,
            realized, -commission, self._state.net_result,
            self.max_daily_loss + self._state.net_result,
        )
        self._check_limit()
        return realized

    def record_commission(self, commission: Decimal) -> None:
        """Регистрирует комиссию, пришедшую отдельной операцией API."""
        self._ensure_today()
        self._state.total_commissions += commission
        logger.info(
            "[Риск] Комиссия %.4f | день P&L: %+.4f | до лимита: %.4f",
            commission,
            self._state.net_result,
            self.max_daily_loss + self._state.net_result,
        )
        self._check_limit()

    def status_line(self) -> str:
        """Однострочный статус для периодического логирования."""
        self._ensure_today()
        s = self._state
        status = "СТОП" if s.is_halted else "OK"
        remaining = self.max_daily_loss + s.net_result
        return (
            f"[Риск:{status}] "
            f"сделок={s.trade_count} "
            f"P&L={s.realized_pnl:+.2f} "
            f"комис={s.total_commissions:.2f} "
            f"итого={s.net_result:+.2f} "
            f"лимит=-{self.max_daily_loss:.2f} "
            f"осталось={remaining:.2f}"
        )

    def daily_summary(self) -> str:
        """Развёрнутый итог дня (для логов при остановке)."""
        self._ensure_today()
        s = self._state
        buys  = [t for t in s.trades if t.direction == "BUY"]
        sells = [t for t in s.trades if t.direction == "SELL"]
        lines = [
            f"{'='*50}",
            f"  Дневной итог  {s.trade_date}",
            f"{'='*50}",
            f"  Покупок:              {len(buys)}",
            f"  Продаж:               {len(sells)}",
            f"  Реализованный P&L:   {s.realized_pnl:>+10.4f}",
            f"  Комиссии (итого):    {-s.total_commissions:>+10.4f}",
            f"  Чистый результат:    {s.net_result:>+10.4f}",
            f"  Лимит дневных потерь: -{self.max_daily_loss:.4f}",
            f"  Статус:               {'ОСТАНОВЛЕН' if s.is_halted else 'норма'}",
            f"{'='*50}",
        ]
        if s.trades:
            lines.append("  Сделки:")
            for t in s.trades:
                sign = "+" if t.direction == "SELL" else "-"
                pnl_str = f"  P&L {t.realized_pnl:+.2f}" if t.direction == "SELL" else ""
                lines.append(
                    f"    {t.timestamp.strftime('%H:%M:%S')} "
                    f"{t.direction:4} {t.figi} ×{t.lots} @ {t.price_per_share:.4f}"
                    f"  комис={sign}{abs(t.commission):.4f}{pnl_str}"
                )
        return "\n".join(lines)

    @property
    def state(self) -> DailyRiskState:
        self._ensure_today()
        return self._state
