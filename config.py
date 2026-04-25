import os
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


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
    check_interval: int = field(
        default_factory=lambda: int(os.getenv("CHECK_INTERVAL", "60"))
    )
    reports_dir: Path = field(
        default_factory=lambda: Path(os.getenv("REPORTS_DIR", "reports"))
    )
    # MA strategy
    ma_short: int = field(default_factory=lambda: int(os.getenv("MA_SHORT", "9")))
    ma_long: int = field(default_factory=lambda: int(os.getenv("MA_LONG", "21")))
    # RSI strategy
    rsi_period: int = field(default_factory=lambda: int(os.getenv("RSI_PERIOD", "14")))
    rsi_oversold: float = field(
        default_factory=lambda: float(os.getenv("RSI_OVERSOLD", "30"))
    )
    rsi_overbought: float = field(
        default_factory=lambda: float(os.getenv("RSI_OVERBOUGHT", "70"))
    )

    @property
    def is_sandbox(self) -> bool:
        return self.mode.lower() == "sandbox"
