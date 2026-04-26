from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .base import ToolBaseStrategy, ToolSignal


@dataclass
class BacktestResult:
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    total_return: float
    total_trades: int


class Backtester:
    def run(self, strategy: ToolBaseStrategy, data: pd.DataFrame) -> BacktestResult:
        required = min(strategy.get_required_history_bars(), max(20, len(data) // 3))
        position = 0
        entry_price = 0.0
        equity = 1.0
        equity_curve = []
        trade_returns = []

        for idx in range(required, len(data)):
            window = data.iloc[: idx + 1].copy()
            window.attrs.update(data.attrs)
            result = strategy.compute(window)
            price = float(window["close"].iloc[-1])
            if result.signal == ToolSignal.BUY and position == 0:
                position = 1
                entry_price = price
            elif result.signal == ToolSignal.SELL and position == 1:
                trade_return = (price - entry_price) / entry_price if entry_price else 0.0
                trade_returns.append(trade_return)
                equity *= 1 + trade_return
                position = 0
                entry_price = 0.0
            equity_curve.append(equity)

        if position == 1 and entry_price:
            last_price = float(data["close"].iloc[-1])
            trade_return = (last_price - entry_price) / entry_price
            trade_returns.append(trade_return)
            equity *= 1 + trade_return
            equity_curve.append(equity)

        returns = pd.Series(trade_returns, dtype="float64")
        sharpe = float(returns.mean() / returns.std(ddof=0) * (len(returns) ** 0.5)) if len(returns) > 1 and returns.std(ddof=0) else 0.0
        curve = pd.Series(equity_curve or [1.0], dtype="float64")
        drawdown = (curve / curve.cummax() - 1).min()
        wins = returns[returns > 0]
        return BacktestResult(
            sharpe_ratio=sharpe,
            max_drawdown=abs(float(drawdown)),
            win_rate=float(len(wins) / len(returns)) if len(returns) else 0.0,
            total_return=float(equity - 1),
            total_trades=len(trade_returns),
        )
