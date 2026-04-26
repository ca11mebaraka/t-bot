"""
LLM decision layer for autonomous trading.

The model is allowed to choose instruments and propose BUY/SELL/HOLD decisions,
but every decision is validated locally before it reaches the broker.
"""
import json
import logging
import re
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable, Optional, TypeVar

from grpc import StatusCode
from t_tech.invest import InstrumentStatus
from t_tech.invest.exceptions import RequestError

from aggression import AggressionController
from client import money_value_to_decimal, quotation_to_decimal
from config import Config
from llm.context_builder import ContextBuilder
from llm.decision_logger import DecisionLogger
from llm_client import LLMClient, LLMError, LLMMessage
from risk import DailyRiskManager
from strategies import Signal, SignalType
from strategies.data_provider import TinkoffDataProvider
from strategies.toolkit import StrategyToolkit

logger = logging.getLogger(__name__)
T = TypeVar("T")

_TRANSIENT_API_CODES = {
    StatusCode.UNAVAILABLE,
    StatusCode.DEADLINE_EXCEEDED,
    StatusCode.RESOURCE_EXHAUSTED,
}


@dataclass
class MarketCandidate:
    figi: str
    ticker: str
    name: str
    currency: str
    lot: int
    price: Decimal
    min_price_increment: Decimal
    buy_available: bool
    sell_available: bool
    instrument_type: str


@dataclass
class PositionSnapshot:
    figi: str
    ticker: str
    name: str
    quantity: int
    avg_price: Decimal
    current_price: Decimal
    pnl: Decimal
    pnl_pct: float


@dataclass
class LLMDecision:
    action: SignalType
    figi: str
    ticker: str
    lots: int
    confidence: float
    reason: str
    risk_notes: str
    strategy_mode: str = ""
    strategy_used: str = ""
    params_override: dict | None = None
    reasoning: str = ""
    confidence_final: float | None = None


def _decimal_str(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.0001")), "f")


def _chunks(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _safe_bool(value: Any) -> bool:
    return bool(value) if value is not None else False


def _with_api_retry(description: str, call: Callable[[], T], attempts: int = 3) -> T:
    delay = 1.0
    for attempt in range(1, attempts + 1):
        try:
            return call()
        except RequestError as exc:
            if exc.code not in _TRANSIENT_API_CODES or attempt >= attempts:
                raise
            logger.warning(
                "Временная ошибка T-Invest API при %s: %s. Повтор %d/%d через %.1fs",
                description,
                exc.details,
                attempt + 1,
                attempts,
                delay,
            )
            time.sleep(delay)
            delay *= 2
    raise RuntimeError(f"Не удалось выполнить T-Invest API call: {description}")


class LLMTradingController:
    def __init__(self, config: Config):
        self.config = config
        self.llm = LLMClient(config)
        self.decision_logger = DecisionLogger()
        self._scan_offset = 0

    def make_decisions(
        self,
        client,
        account_id: str,
        risk: Optional[DailyRiskManager],
        aggression: Optional[AggressionController] = None,
    ) -> list[tuple[Signal, MarketCandidate]]:
        positions = self._load_positions(client, account_id)
        candidates = self._scan_market(
            client,
            priority_figis={position.figi for position in positions},
        )
        context = self._build_context(candidates, positions, risk, aggression)
        toolkit = StrategyToolkit(TinkoffDataProvider(client))
        context = ContextBuilder(toolkit).enrich_context(context)
        messages = [
            LLMMessage(role="system", content=self._system_prompt()),
            LLMMessage(role="user", content=json.dumps(context, ensure_ascii=False, indent=2)),
        ]

        self._print_request(messages, context)
        response = self.llm.complete(messages)
        self._print_response(response.content)

        raw = self._parse_json(response.content)
        decisions = self._parse_decisions(raw, candidates)
        self._log_decisions(decisions, context)
        return self._validate_decisions(decisions, candidates, positions, risk, aggression)

    def _scan_market(self, client, priority_figis: Optional[set[str]] = None) -> list[MarketCandidate]:
        instruments = []
        instruments.extend(
            ("share", item)
            for item in _with_api_retry(
                "загрузке акций",
                lambda: client.instruments.shares(
                    instrument_status=InstrumentStatus.INSTRUMENT_STATUS_BASE
                ),
            ).instruments
        )
        try:
            instruments.extend(
                ("etf", item)
                for item in _with_api_retry(
                    "загрузке ETF",
                    lambda: client.instruments.etfs(
                        instrument_status=InstrumentStatus.INSTRUMENT_STATUS_BASE
                    ),
                ).instruments
            )
        except Exception as exc:
            logger.warning("Не удалось получить ETF universe: %s", exc)

        priority_figis = priority_figis or set()
        filtered = []
        seen: set[str] = set()
        for instrument_type, item in instruments:
            if item.figi in seen:
                continue
            if item.currency.lower() != "rub":
                continue
            if not _safe_bool(getattr(item, "api_trade_available_flag", True)):
                continue
            if _safe_bool(getattr(item, "for_qual_investor_flag", False)):
                continue
            seen.add(item.figi)
            filtered.append((instrument_type, item))

        filtered.sort(key=lambda pair: pair[1].ticker)
        filtered_by_figi = {item.figi: (instrument_type, item) for instrument_type, item in filtered}

        limit = max(1, self.config.llm_universe_limit)
        selected: list[tuple[str, Any]] = []
        if filtered:
            start = self._scan_offset % len(filtered)
            rotated = filtered[start:] + filtered[:start]
            selected = rotated[:limit]
            self._scan_offset = (self._scan_offset + limit) % len(filtered)

        # Keep open positions visible to the LLM, but do not pin them to the top forever.
        selected_figis = {item.figi for _, item in selected}
        for figi in priority_figis:
            if figi in filtered_by_figi and figi not in selected_figis:
                if len(selected) >= limit:
                    selected[-1] = filtered_by_figi[figi]
                else:
                    selected.append(filtered_by_figi[figi])
                selected_figis.add(figi)

        figis = [item.figi for _, item in selected]

        prices: dict[str, Decimal] = {}
        for chunk in _chunks(figis, 250):
            response = _with_api_retry(
                "загрузке последних цен",
                lambda chunk=chunk: client.market_data.get_last_prices(instrument_id=chunk),
            )
            for last_price in response.last_prices:
                prices[last_price.figi] = quotation_to_decimal(last_price.price)

        candidates = []
        for instrument_type, item in selected:
            price = prices.get(item.figi)
            if price is None or price <= 0:
                continue
            candidates.append(
                MarketCandidate(
                    figi=item.figi,
                    ticker=item.ticker,
                    name=item.name,
                    currency=item.currency,
                    lot=item.lot or 1,
                    price=price,
                    min_price_increment=quotation_to_decimal(item.min_price_increment),
                    buy_available=_safe_bool(getattr(item, "buy_available_flag", True)),
                    sell_available=_safe_bool(getattr(item, "sell_available_flag", True)),
                    instrument_type=instrument_type,
                )
            )
        logger.info(
            "LLM universe shortlist (%d/%d, offset=%d): %s",
            len(candidates),
            len(filtered),
            self._scan_offset,
            ", ".join(candidate.ticker for candidate in candidates[:20]),
        )
        return candidates[:limit]

    def _load_positions(self, client, account_id: str) -> list[PositionSnapshot]:
        portfolio = _with_api_retry(
            "загрузке портфеля",
            lambda: (
                client.sandbox.get_sandbox_portfolio(account_id=account_id)
                if self.config.is_sandbox
                else client.operations.get_portfolio(account_id=account_id)
            ),
        )
        positions: list[PositionSnapshot] = []
        for position in portfolio.positions:
            quantity = int(quotation_to_decimal(position.quantity))
            if quantity <= 0:
                continue
            figi = position.figi
            avg_money = (
                getattr(position, "average_buy_price", None)
                or getattr(position, "average_position_price_fifo", None)
                or getattr(position, "average_position_price", None)
            )
            avg_price = money_value_to_decimal(avg_money) if avg_money else Decimal(0)
            current_price = money_value_to_decimal(position.current_price)
            try:
                info = _with_api_retry(
                    f"загрузке инструмента {figi}",
                    lambda figi=figi: client.instruments.get_instrument_by(id_type=1, id=figi),
                ).instrument
                ticker = getattr(position, "ticker", "") or info.ticker
                name = info.name
            except Exception:
                ticker = getattr(position, "ticker", "") or figi
                name = figi
            pnl = (current_price - avg_price) * Decimal(quantity)
            pnl_pct = float((current_price - avg_price) / avg_price * 100) if avg_price else 0.0
            positions.append(
                PositionSnapshot(
                    figi=figi,
                    ticker=ticker,
                    name=name,
                    quantity=quantity,
                    avg_price=avg_price,
                    current_price=current_price,
                    pnl=pnl,
                    pnl_pct=pnl_pct,
                )
            )
        return positions

    def _build_context(
        self,
        candidates: list[MarketCandidate],
        positions: list[PositionSnapshot],
        risk: Optional[DailyRiskManager],
        aggression: Optional[AggressionController] = None,
    ) -> dict[str, Any]:
        risk_status = risk.status_line() if risk is not None else "risk-manager disabled"
        remaining_risk = None
        if risk is not None:
            state = risk.state
            remaining_risk = _decimal_str(risk.max_daily_loss + state.net_result)

        max_lots = (
            aggression.max_lots(self.config.effective_llm_max_lots)
            if aggression is not None
            else self.config.effective_llm_max_lots
        )
        max_decisions = aggression.max_llm_decisions() if aggression is not None else self.config.llm_max_tickers
        target_decisions = min(max_decisions, len(candidates))

        return {
            "mode": self.config.mode,
            "aggression": aggression.describe() if aggression is not None else "disabled",
            "limits": {
                "max_lots_per_decision": max_lots,
                "max_decisions": max_decisions,
                "target_decisions": target_decisions,
                "decision_policy": (
                    "Return exactly target_decisions items whenever market_candidates contains enough data. "
                    "Review the full shortlist, not only one ticker. Include HOLD decisions for "
                    "attractive-but-not-actionable candidates when BUY/SELL is not justified."
                ),
                "daily_loss_limit": _decimal_str(self.config.max_daily_loss) if self.config.max_daily_loss else None,
                "remaining_daily_risk": remaining_risk,
            },
            "risk_status": risk_status,
            "positions": [
                {
                    "figi": p.figi,
                    "ticker": p.ticker,
                    "name": p.name,
                    "quantity_shares": p.quantity,
                    "avg_price": _decimal_str(p.avg_price),
                    "current_price": _decimal_str(p.current_price),
                    "unrealized_pnl": _decimal_str(p.pnl),
                    "unrealized_pnl_pct": round(p.pnl_pct, 2),
                }
                for p in positions
            ],
            "market_candidates": [
                {
                    "figi": c.figi,
                    "ticker": c.ticker,
                    "name": c.name,
                    "type": c.instrument_type,
                    "currency": c.currency,
                    "lot": c.lot,
                    "last_price": _decimal_str(c.price),
                    "buy_available": c.buy_available,
                    "sell_available": c.sell_available,
                }
                for c in candidates
            ],
            "response_schema": {
                "decisions": [
                    {
                        "figi": "string from market_candidates or positions",
                        "ticker": "string",
                        "action": "BUY | SELL | HOLD",
                        "lots": "integer, 0 for HOLD",
                        "confidence": "0.0..1.0",
                        "strategy_mode": "capital_preservation | balanced | opportunity_seeking",
                        "reason": "short human-readable explanation",
                        "risk_notes": "commission/risk/position notes",
                    }
                ]
            },
        }

    def _system_prompt(self) -> str:
        return (
            "Ты автономный риск-ориентированный торговый ассистент для T-Invest. "
            "Твоя цель — выбирать только такие действия, у которых положительное ожидаемое "
            "математическое ожидание после комиссий и приемлемый risk/reward. "
            "Если преимущество неочевидно, отвечай HOLD. "
            "Учитывай дневной FIFO P&L, комиссии, остаток дневного риска, открытые позиции, "
            "ликвидность по доступности торговли, размер лота, текущий уровень агрессивности "
            "и режим sandbox/production. Чем ниже агрессивность, тем чаще выбирай HOLD и меньший lots; "
            "чем выше агрессивность, тем можно чаще выбирать BUY/SELL, но только в пределах лимитов и риска. "
            "Динамически подстраивай торговое поведение под изменения рынка и финансовые результаты текущей сессии: "
            "если чистый результат ухудшается, растут комиссии или увеличивается просадка, переходи к более осторожной "
            "стратегии, уменьшая частоту сделок, lots и предпочитая HOLD; если результаты устойчиво улучшаются и риск "
            "остаётся в норме, допускай более активный поиск возможностей. "
            "При каждом ответе оцени, нужно ли сменить стратегический режим: capital_preservation, balanced или opportunity_seeking. "
            "В reason/risk_notes явно указывай, почему выбран текущий режим и как на него повлияли P&L, комиссии, позиции, "
            "остаток риска и рыночные условия. "
            "Используй блок strategy_tools.tool_results как результаты вызова стратегических tools. "
            "Выбирай strategy_used из strategy_results, можешь указать params_override, если хочешь изменить параметры. "
            "Не исполняй сигнал стратегии автоматически: стратегия только вычисляет, финальное решение принимаешь ты. "
            "Не продавай инструмент, если позиции нет. Не превышай лимиты lots. "
            "Обязательно оцени несколько market_candidates из разных тикеров, а не только первый, SBER/GAZP "
            "или уже знакомый тикер. "
            "market_candidates ротируются между циклами, поэтому каждый цикл сравнивай текущий shortlist заново "
            "и не фиксируйся на тикерах из прошлых ответов. "
            "Используй весь блок strategy_tools.tool_results; не ограничивай анализ 3-4 тикерами, "
            "если в контексте доступно больше инструментов. "
            "Верни максимально возможное число решений: ровно limits.target_decisions, "
            "если столько market_candidates доступно, но не больше limits.max_decisions. "
            "Каждое решение должно быть по разному FIGI. "
            "Если есть только одна реальная сделка, добавь HOLD-разборы по другим перспективным кандидатам, "
            "чтобы человек видел сравнение альтернатив. "
            "Если сделок делать не нужно, верни несколько HOLD по наиболее релевантным кандидатам "
            "с figi, ticker, lots=0, confidence и подробной причиной отказа от сделки. "
            "Никогда не возвращай пустой массив decisions. "
            "Верни только валидный JSON без markdown. Формат: "
            "{\"decisions\":[{\"figi\":\"...\",\"ticker\":\"...\",\"action\":\"BUY|SELL|HOLD\","
            "\"lots\":1,\"confidence\":0.0,\"strategy_mode\":\"balanced\","
            "\"strategy_used\":\"trend_following\",\"params_override\":{},"
            "\"reasoning\":\"audit trail на русском\",\"reason\":\"...\",\"risk_notes\":\"...\"}]}. "
            "BUY/SELL используй только при высокой уверенности; при сомнениях HOLD."
        )

    def _parse_json(self, content: str) -> dict[str, Any]:
        text = content.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMError(f"LLM вернула невалидный JSON: {content[:500]}") from exc
        if not isinstance(value, dict):
            raise LLMError("LLM JSON должен быть объектом")
        return value

    def _parse_decisions(
        self,
        raw: dict[str, Any],
        candidates: Optional[list[MarketCandidate]] = None,
    ) -> list[LLMDecision]:
        items = raw.get("decisions", [])
        if not isinstance(items, list):
            raise LLMError("Поле decisions должно быть массивом")
        if not items:
            logger.info("LLM вернула пустой decisions[]; интерпретируем как HOLD без сделки")
            print("LLM: решений нет, торговля пропущена до следующего интервала.")
            fallback_candidates = (candidates or [])[: max(1, min(3, self.config.llm_max_tickers))]
            items = [
                {
                    "figi": candidate.figi,
                    "ticker": candidate.ticker,
                    "action": "HOLD",
                    "lots": 0,
                    "confidence": 0,
                    "reason": "Модель вернула пустой список решений",
                    "risk_notes": "Сделка не выполняется",
                }
                for candidate in fallback_candidates
            ] or [
                {
                    "action": "HOLD",
                    "lots": 0,
                    "confidence": 0,
                    "reason": "Модель вернула пустой список решений",
                    "risk_notes": "Сделка не выполняется",
                }
            ]

        decisions = []
        for item in items[: self.config.llm_max_tickers]:
            if not isinstance(item, dict):
                continue
            action_raw = str(item.get("action", "HOLD")).upper()
            action = SignalType.BUY if action_raw == "BUY" else SignalType.SELL if action_raw == "SELL" else SignalType.HOLD
            try:
                lots = int(item.get("lots", 0 if action == SignalType.HOLD else 1))
            except (TypeError, ValueError):
                lots = 0
            try:
                confidence = float(item.get("confidence", 0))
            except (TypeError, ValueError):
                confidence = 0.0
            decisions.append(
                LLMDecision(
                    action=action,
                    figi=str(item.get("figi", "")).strip(),
                    ticker=str(item.get("ticker", "")).strip(),
                    lots=lots,
                    confidence=max(0.0, min(1.0, confidence)),
                    reason=str(item.get("reason", "")).strip(),
                    risk_notes=str(item.get("risk_notes", "")).strip(),
                    strategy_mode=str(item.get("strategy_mode", "")).strip(),
                    strategy_used=str(item.get("strategy_used", "")).strip(),
                    params_override=item.get("params_override", {}) if isinstance(item.get("params_override", {}), dict) else {},
                    reasoning=str(item.get("reasoning", item.get("reason", ""))).strip(),
                    confidence_final=float(item.get("confidence_final", confidence)) if item.get("confidence_final") is not None else None,
                )
            )
        return decisions

    def _log_decisions(self, decisions: list[LLMDecision], context: dict[str, Any]) -> None:
        tool_results = context.get("strategy_tools", {}).get("tool_results", [])
        results_by_ticker = {item.get("ticker"): item for item in tool_results if isinstance(item, dict)}
        for decision in decisions:
            ticker = decision.ticker or decision.figi or "UNKNOWN"
            strategy_result = results_by_ticker.get(ticker, {})
            self.decision_logger.log(
                ticker=ticker,
                strategy_result=strategy_result,
                llm_decision={
                    "action": decision.action.value,
                    "approved_qty": decision.lots,
                    "strategy_used": decision.strategy_used,
                    "params_override": decision.params_override or {},
                    "reasoning": decision.reasoning or decision.reason,
                    "confidence_final": decision.confidence_final if decision.confidence_final is not None else decision.confidence,
                    "skip_reason": decision.risk_notes if decision.action == SignalType.HOLD else None,
                    "strategy_mode": decision.strategy_mode,
                },
                tool_calls=[{"name": "emulated_strategy_tools", "result": strategy_result}],
            )

    def _validate_decisions(
        self,
        decisions: list[LLMDecision],
        candidates: list[MarketCandidate],
        positions: list[PositionSnapshot],
        risk: Optional[DailyRiskManager],
        aggression: Optional[AggressionController] = None,
    ) -> list[tuple[Signal, MarketCandidate]]:
        candidates_by_figi = {candidate.figi: candidate for candidate in candidates}
        positions_by_figi = {position.figi: position for position in positions}
        valid: list[tuple[Signal, MarketCandidate]] = []
        max_decisions = aggression.max_llm_decisions() if aggression is not None else self.config.llm_max_tickers

        if risk is not None:
            allowed, reason = risk.can_trade()
            if not allowed:
                logger.warning("LLM-решения отклонены: риск-лимит остановил торговлю: %s", reason)
                return valid

        for decision in decisions:
            if decision.action == SignalType.HOLD:
                logger.info("LLM HOLD %s: %s", decision.ticker or decision.figi or "-", decision.reason)
                continue
            candidate = candidates_by_figi.get(decision.figi)
            if candidate is None:
                logger.warning("LLM-решение отклонено: неизвестный FIGI %s", decision.figi)
                continue
            if decision.action == SignalType.BUY and not candidate.buy_available:
                logger.warning("LLM BUY %s отклонён: покупка недоступна", candidate.ticker)
                continue
            if decision.action == SignalType.SELL:
                position = positions_by_figi.get(candidate.figi)
                if position is None or position.quantity <= 0:
                    logger.warning("LLM SELL %s отклонён: позиции нет", candidate.ticker)
                    continue
                max_sell_lots = max(1, position.quantity // candidate.lot)
                if decision.lots > max_sell_lots:
                    logger.warning(
                        "LLM SELL %s урезан с %d до %d лот(ов) по позиции",
                        candidate.ticker,
                        decision.lots,
                        max_sell_lots,
                    )
                    decision.lots = max_sell_lots
                if not candidate.sell_available:
                    logger.warning("LLM SELL %s отклонён: продажа недоступна", candidate.ticker)
                    continue

            max_lots = (
                aggression.max_lots(self.config.effective_llm_max_lots)
                if aggression is not None
                else self.config.effective_llm_max_lots
            )
            lots = max(1, min(decision.lots, max_lots))
            signal = Signal(
                type=decision.action,
                instrument_id=candidate.figi,
                price=candidate.price,
                reason=(
                    f"LLM {decision.confidence:.2f} [{decision.strategy_used or 'no_strategy'}]: {decision.reason} "
                    f"| риск: {decision.risk_notes}"
                ),
                lots=lots,
            )
            valid.append((signal, candidate))
            if len(valid) >= max_decisions:
                break
        return valid

    def _print_request(self, messages: list[LLMMessage], context: dict[str, Any]) -> None:
        if not self.config.llm_show_prompts:
            return
        print("\n" + "=" * 80)
        print("LLM REQUEST")
        print("=" * 80)
        print(f"Provider: {self.config.llm_provider} | Model: {self.config.llm_model or 'default'}")
        print(f"Risk: {context['risk_status']}")
        print(f"Candidates: {len(context['market_candidates'])} | Positions: {len(context['positions'])}")
        print("-" * 80)
        for message in messages:
            print(f"[{message.role.upper()}]")
            print(message.content)
            print("-" * 80)

    def _print_response(self, content: str) -> None:
        if not self.config.llm_show_prompts:
            return
        print("LLM RESPONSE")
        print("=" * 80)
        print(content)
        print("=" * 80 + "\n")
