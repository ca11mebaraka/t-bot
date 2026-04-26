from __future__ import annotations

import logging
from typing import Any

from .tools_schema import STRATEGY_TOOLS
from strategies.toolkit import StrategyToolkit

logger = logging.getLogger(__name__)


class ContextBuilder:
    """
    Adds strategy tool schemas and precomputed tool results to the existing LLM
    context. This is an emulated tool-call layer for providers without native
    tool loop support in the current client.
    """

    def __init__(self, toolkit: StrategyToolkit):
        self.toolkit = toolkit

    def enrich_api_call(self, existing_api_kwargs: dict) -> dict:
        enriched = existing_api_kwargs.copy()
        enriched["tools"] = enriched.get("tools", []) + STRATEGY_TOOLS
        instructions = self._build_strategy_system_instructions()
        if "system" in enriched:
            enriched["system"] = enriched["system"] + "\n\n" + instructions
        else:
            enriched["system"] = instructions
        return enriched

    def enrich_context(self, context: dict[str, Any]) -> dict[str, Any]:
        enriched = dict(context)
        candidates = context.get("market_candidates", [])
        max_decisions = int(context.get("limits", {}).get("max_decisions", 8) or 8)
        analysis_limit = min(max(24, max_decisions), len(candidates))
        tool_results = []
        for candidate in candidates[:analysis_limit]:
            ticker = candidate.get("ticker") or candidate.get("figi")
            instrument_id = candidate.get("figi") or ticker
            if not ticker:
                continue
            try:
                regime = self.toolkit.get_market_regime(instrument_id)
                strategies = regime.get("recommended_strategies", ["trend_following", "mean_reversion"])[:2]
                results = [
                    self.toolkit.run_strategy(strategy, instrument_id, params={}, interval="1_HOUR")
                    for strategy in strategies
                    if strategy != "stat_arb"
                ]
                backtests = [
                    self.toolkit.backtest_strategy(
                        strategy_name=results[0]["strategy_name"],
                        ticker=instrument_id,
                        params=results[0].get("params_used", {}),
                        bars=180,
                        interval="1_DAY",
                    )
                ] if results else []
                tool_results.append(
                    {
                        "ticker": ticker,
                        "figi": candidate.get("figi"),
                        "market_regime": regime,
                        "strategy_results": results,
                        "backtests": backtests,
                    }
                )
            except Exception as exc:
                logger.warning("Strategy tool emulation failed for %s: %s", ticker, exc)
                tool_results.append({"ticker": ticker, "error": str(exc)})

        enriched["strategy_tools"] = {
            "mode": "emulated",
            "analysis_limit": analysis_limit,
            "schemas": STRATEGY_TOOLS,
            "available_strategies": self.toolkit.list_strategies(),
            "tool_results": tool_results,
            "instructions": self._build_strategy_system_instructions(),
        }
        return enriched

    def _build_strategy_system_instructions(self) -> str:
        return """
## Торговые стратегии — инструкции по использованию

Тебе доступны результаты детерминированных стратегий в блоке strategy_tools.tool_results.
Это эмуляция tool calls: код уже локально вызвал get_market_regime, run_strategy и быстрый backtest.
Анализируй весь список strategy_tools.tool_results, а не только первые 3-4 тикера.

Порядок анализа:
1. Смотри market_regime для каждого тикера.
2. Сравни strategy_results и indicators.
3. При конфликте индикаторов или слабом backtest выбирай HOLD.
4. Подтверждай BUY только если confidence >= 0.6 и сигнал согласован с режимом рынка.
5. Для stat_arb требуй cointegration_pvalue < 0.05 и abs(spread_z_score) > 2.0.
6. Всегда указывай strategy_used, params_override, reasoning и confidence_final в решении.

Стратегии:
- trending_up / trending_down -> trend_following или breakout
- ranging -> mean_reversion или stat_arb
- high_volatility -> осторожный mean_reversion или ml
- low_volatility -> breakout после squeeze
"""
