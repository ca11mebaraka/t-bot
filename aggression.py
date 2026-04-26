"""
Runtime trading aggression control.

Interactive terminal:
  + then Enter  -> increase level
  - then Enter  -> decrease level

Control file:
  {"aggression": 4}
"""
import json
import logging
import select
import sys
from dataclasses import dataclass
from pathlib import Path

from config import Config

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AggressionProfile:
    level: int
    name: str
    lot_multiplier: float
    interval_multiplier: float
    decision_multiplier: float


_PROFILES = {
    1: AggressionProfile(1, "очень осторожный", 0.25, 2.0, 0.5),
    2: AggressionProfile(2, "осторожный", 0.5, 1.5, 0.75),
    3: AggressionProfile(3, "нормальный", 1.0, 1.0, 1.0),
    4: AggressionProfile(4, "агрессивный", 1.5, 0.75, 1.25),
    5: AggressionProfile(5, "максимальный", 2.0, 0.5, 1.5),
}


class AggressionController:
    def __init__(self, config: Config):
        self.config = config
        self.path = Path(config.aggression_control_file)
        self._level = self._clamp(config.aggression_level)
        self._last_file_level: int | None = None
        self._write_control_file_if_missing()

    @property
    def level(self) -> int:
        return self._level

    @property
    def profile(self) -> AggressionProfile:
        return _PROFILES[self._level]

    def describe(self) -> str:
        profile = self.profile
        return (
            f"агрессивность={profile.level}/5 ({profile.name}), "
            f"lots x{profile.lot_multiplier:g}, interval x{profile.interval_multiplier:g}"
        )

    def max_lots(self, base_lots: int) -> int:
        lots = round(base_lots * self.profile.lot_multiplier)
        return max(1, min(self.config.max_lots, lots))

    def max_llm_decisions(self) -> int:
        # Keep the LLM market review broad at every aggression level. Aggression still
        # controls execution size and polling interval, not how many tickers are audited.
        return max(1, self.config.llm_max_tickers)

    def llm_interval(self) -> int:
        interval = round(self.config.llm_decision_interval * self.profile.interval_multiplier)
        return max(self.config.aggression_min_interval, interval)

    def check_interval(self) -> int:
        interval = round(self.config.check_interval * self.profile.interval_multiplier)
        return max(self.config.aggression_min_interval, interval)

    def poll(self) -> bool:
        """Returns True when the level changed."""
        changed = False
        changed = self._poll_file() or changed
        changed = self._poll_stdin() or changed
        return changed

    def increase(self) -> bool:
        return self._set_level(self._level + 1, "terminal")

    def decrease(self) -> bool:
        return self._set_level(self._level - 1, "terminal")

    def _set_level(self, level: int, source: str) -> bool:
        level = self._clamp(level)
        if level == self._level:
            return False
        self._level = level
        logger.info("Уровень агрессивности изменён (%s): %s", source, self.describe())
        self._write_control_file()
        return True

    def _poll_stdin(self) -> bool:
        if not sys.stdin.isatty():
            return False
        readable, _, _ = select.select([sys.stdin], [], [], 0)
        if not readable:
            return False
        command = sys.stdin.readline().strip()
        if command == "+":
            return self.increase()
        if command == "-":
            return self.decrease()
        if command:
            logger.info("Команда агрессивности не распознана: %s (используйте + или -)", command)
        return False

    def _poll_file(self) -> bool:
        if not self.path.exists():
            return False
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            level = self._clamp(int(data.get("aggression", self._level)))
        except Exception as exc:
            logger.warning("Не удалось прочитать %s: %s", self.path, exc)
            return False
        if level == self._last_file_level:
            return False
        self._last_file_level = level
        return self._set_level(level, str(self.path))

    def _write_control_file_if_missing(self) -> None:
        if not self.path.exists():
            self._write_control_file()

    def _write_control_file(self) -> None:
        try:
            self.path.write_text(
                json.dumps({"aggression": self._level}, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            self._last_file_level = self._level
        except Exception as exc:
            logger.warning("Не удалось записать %s: %s", self.path, exc)

    @staticmethod
    def _clamp(level: int) -> int:
        return max(1, min(5, level))
