from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


class DecisionLogger:
    def __init__(self, log_dir: str = "logs/decisions"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def log(
        self,
        ticker: str,
        strategy_result: dict,
        llm_decision: dict,
        tool_calls: list[dict],
    ) -> None:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ticker": ticker,
            "strategy_result": strategy_result,
            "llm_decision": llm_decision,
            "tool_calls_trace": tool_calls,
        }
        log_file = self.log_dir / f"decisions_{datetime.now().strftime('%Y-%m-%d')}.jsonl"
        with log_file.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")

        logger.info(
            "[DECISION] %s | %s | strategy=%s | confidence=%s | %s",
            ticker,
            llm_decision.get("action"),
            llm_decision.get("strategy_used"),
            llm_decision.get("confidence_final"),
            str(llm_decision.get("reasoning", ""))[:120],
        )
