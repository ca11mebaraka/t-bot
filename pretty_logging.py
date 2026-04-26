"""
Human-friendly console logging for T-Bot.
"""
from __future__ import annotations

import logging
import re
import sys
from itertools import cycle


RESET = "\033[0m"
DIM = "\033[2m"
BOLD = "\033[1m"

COLORS = {
    "time": "\033[38;5;245m",
    "debug": "\033[38;5;244m",
    "info": "\033[38;5;117m",
    "success": "\033[38;5;114m",
    "warning": "\033[38;5;221m",
    "error": "\033[38;5;203m",
    "critical": "\033[38;5;199m",
    "module": "\033[38;5;110m",
    "border": "\033[38;5;238m",
    "text": "\033[38;5;252m",
}

LEVEL_STYLES = {
    logging.DEBUG: ("·", "debug", "детали"),
    logging.INFO: ("●", "info", "инфо"),
    logging.WARNING: ("▲", "warning", "внимание"),
    logging.ERROR: ("■", "error", "ошибка"),
    logging.CRITICAL: ("◆", "critical", "критично"),
}

MODULE_NAMES = {
    "__main__": "Команда",
    "client": "Биржа",
    "portfolio": "Портфель",
    "trader": "Торговля",
    "risk": "Риск",
    "risk_history": "История риска",
    "llm_trading": "LLM",
    "llm.context_builder": "Стратегии",
    "llm.decision_logger": "Аудит LLM",
    "aggression": "Агрессивность",
    "t_tech.invest.logging": "T-Invest API",
}

API_ACTIONS = {
    "GetPortfolio": "загружаем портфель",
    "GetPositions": "загружаем денежные остатки и позиции",
    "GetOperations": "загружаем историю операций",
    "GetInstrumentBy": "уточняем данные инструмента",
    "GetLastPrices": "получаем последние цены",
    "GetCandles": "загружаем свечи",
    "PostOrder": "отправляем биржевую заявку",
    "PostSandboxOrder": "отправляем sandbox-заявку",
    "PostStopOrder": "ставим стоп-заявку",
    "Shares": "загружаем список акций",
    "Etfs": "загружаем список ETF",
}

TECHNICAL_PREFIX_RE = re.compile(r"^[0-9a-f]{16,}\s+([A-Za-z][A-Za-z0-9_]+)(?:\s+.*)?$")


class HumanConsoleFormatter(logging.Formatter):
    def __init__(self, use_color: bool = True):
        super().__init__(datefmt="%H:%M:%S")
        self.use_color = use_color
        self._spinner = cycle(("◐", "◓", "◑", "◒"))

    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        message = self._humanize_message(record.name, message)
        module = MODULE_NAMES.get(record.name, record.name.split(".")[-1])
        icon, color_key, level_name = LEVEL_STYLES.get(
            record.levelno,
            LEVEL_STYLES[logging.INFO],
        )
        spinner = next(self._spinner)
        timestamp = self.formatTime(record, self.datefmt)

        if self.use_color:
            border = COLORS["border"]
            level_color = COLORS[color_key]
            time_color = COLORS["time"]
            module_color = COLORS["module"]
            text_color = COLORS["text"]
            return (
                f"{border}╭─{RESET} {level_color}{spinner} {icon} {level_name:<8}{RESET} "
                f"{time_color}{timestamp}{RESET} "
                f"{border}│{RESET} {module_color}{module}{RESET}\n"
                f"{border}╰─{RESET} {text_color}{message}{RESET}"
            )

        return f"{spinner} {icon} {level_name:<8} {timestamp} | {module}: {message}"

    @staticmethod
    def _humanize_message(logger_name: str, message: str) -> str:
        if logger_name == "t_tech.invest.logging":
            match = TECHNICAL_PREFIX_RE.match(message)
            if match:
                method = match.group(1)
                action = API_ACTIONS.get(method, method)
                return f"{action} через T-Invest API"
        if "StatusCode.UNAVAILABLE" in message or "failed to connect" in message:
            return "Временная проблема соединения с T-Invest. Бот повторит попытку автоматически."
        if "RequestError" in message and "RESOURCE_EXHAUSTED" in message:
            return "T-Invest временно ограничил частоту запросов. Бот снизит темп и попробует снова."
        return message


def setup_pretty_logging(level: int = logging.INFO) -> None:
    """Configures readable colored logging for console output."""
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(HumanConsoleFormatter(use_color=sys.stdout.isatty()))
    root.addHandler(handler)

    # The SDK can be very chatty; keep useful API events, but avoid debug noise.
    logging.getLogger("grpc").setLevel(logging.WARNING)
