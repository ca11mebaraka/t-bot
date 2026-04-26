import os
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


def _parse_decimal(env_var: str, default: Optional[str] = None) -> Optional[Decimal]:
    raw = os.getenv(env_var, default)
    if raw is None or raw.strip() == "":
        return None
    return Decimal(raw.strip())


def _parse_bool(env_var: str, default: str = "false") -> bool:
    return os.getenv(env_var, default).strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Config:
    token: str = field(default_factory=lambda: os.environ["INVEST_TOKEN"])
    mode: str = field(default_factory=lambda: os.getenv("TRADING_MODE", "sandbox"))
    account_id: str = field(default_factory=lambda: os.getenv("ACCOUNT_ID", ""))
    instruments: list[str] = field(
        default_factory=lambda: [
            i.strip()
            for i in os.getenv("INSTRUMENTS", "BBG004730ZJ9").split(",")
            if i.strip()
        ]
    )
    max_lots: int = field(default_factory=lambda: int(os.getenv("MAX_LOTS", "1")))
    check_interval: int = field(default_factory=lambda: int(os.getenv("CHECK_INTERVAL", "60")))
    reports_dir: Path = field(default_factory=lambda: Path(os.getenv("REPORTS_DIR", "reports")))
    # MA strategy
    ma_short: int = field(default_factory=lambda: int(os.getenv("MA_SHORT", "9")))
    ma_long: int = field(default_factory=lambda: int(os.getenv("MA_LONG", "21")))
    # RSI strategy
    rsi_period: int = field(default_factory=lambda: int(os.getenv("RSI_PERIOD", "14")))
    rsi_oversold: float = field(default_factory=lambda: float(os.getenv("RSI_OVERSOLD", "30")))
    rsi_overbought: float = field(default_factory=lambda: float(os.getenv("RSI_OVERBOUGHT", "70")))
    # Risk management
    max_daily_loss: Optional[Decimal] = field(default_factory=lambda: _parse_decimal("MAX_DAILY_LOSS"))
    # Auto mode: задержка перед перезапуском после ошибки (сек.)
    auto_restart_delay: int = field(default_factory=lambda: int(os.getenv("AUTO_RESTART_DELAY", "30")))
    # Интервал вывода статуса риск-менеджера в лог (секунды, 0 = выключено)
    status_interval: int = field(default_factory=lambda: int(os.getenv("STATUS_INTERVAL", "300")))
    # Сколько дней операций брать для восстановления FIFO-базиса риск-менеджера.
    risk_history_days: int = field(default_factory=lambda: int(os.getenv("RISK_HISTORY_DAYS", "365")))
    # LLM trading control
    llm_enabled: bool = field(default_factory=lambda: _parse_bool("LLM_ENABLED"))
    llm_provider: str = field(default_factory=lambda: os.getenv("LLM_PROVIDER", "openai").strip().lower())
    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "").strip())
    llm_session_id: str = field(default_factory=lambda: os.getenv("LLM_SESSION_ID", "t-bot-trading").strip())
    llm_base_url: str = field(default_factory=lambda: os.getenv("LLM_BASE_URL", "").strip())
    llm_api_key: str = field(default_factory=lambda: os.getenv("LLM_API_KEY", "").strip())
    llm_timeout: int = field(default_factory=lambda: int(os.getenv("LLM_TIMEOUT", "30")))
    llm_max_tickers: int = field(default_factory=lambda: int(os.getenv("LLM_MAX_TICKERS", "20")))
    llm_universe_limit: int = field(default_factory=lambda: int(os.getenv("LLM_UNIVERSE_LIMIT", "40")))
    llm_max_lots: int = field(default_factory=lambda: int(os.getenv("LLM_MAX_LOTS", "1")))
    llm_decision_interval: int = field(default_factory=lambda: int(os.getenv("LLM_DECISION_INTERVAL", "300")))
    llm_show_prompts: bool = field(default_factory=lambda: _parse_bool("LLM_SHOW_PROMPTS", "true"))
    llm_mock_response: str = field(default_factory=lambda: os.getenv("LLM_MOCK_RESPONSE", "").strip())
    # Runtime aggression control
    aggression_level: int = field(default_factory=lambda: int(os.getenv("AGGRESSION_LEVEL", "3")))
    aggression_min_interval: int = field(default_factory=lambda: int(os.getenv("AGGRESSION_MIN_INTERVAL", "20")))
    aggression_control_file: str = field(
        default_factory=lambda: os.getenv("AGGRESSION_CONTROL_FILE", ".trading_control.json").strip()
    )

    @property
    def is_sandbox(self) -> bool:
        return self.mode.lower() == "sandbox"

    @property
    def effective_llm_max_lots(self) -> int:
        return max(1, min(self.max_lots, self.llm_max_lots))

    @property
    def resolved_llm_api_key(self) -> str:
        provider_key_env = {
            "openai": "OPENAI_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
            "qwen": "QWEN_API_KEY",
            "gigachat": "GIGACHAT_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "openrouter": "OPENROUTER_API_KEY",
        }.get(self.llm_provider)
        if provider_key_env:
            return os.getenv(provider_key_env, self.llm_api_key).strip()
        return self.llm_api_key
