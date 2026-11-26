"""Лимиты расхода и предупреждения (FR-27).

Человеку не нужны токены и минуты — ему нужно знать: «денег хватит ещё на две встречи».
Поэтому модуль отвечает на два вопроса: сколько истрачено в этом месяце и на сколько ещё хватит.

Округление вверх — сознательно: обещать «хватит ещё на 3 встречи», когда хватит на 2.5,
хуже, чем сказать «на 2». Ошибка в свою пользу недопустима в прогнозе бюджета.
"""

from __future__ import annotations

from dataclasses import dataclass, field

WARN_RATIO = 0.8


@dataclass
class Usage:
    asr_seconds: float = 0.0
    llm_tokens: int = 0
    money_rub: float = 0.0

    def add_minutes(self, minutes: float, rub_per_minute: float) -> None:
        self.asr_seconds += minutes * 60
        self.money_rub += minutes * rub_per_minute

    @property
    def minutes(self) -> float:
        return round(self.asr_seconds / 60, 1)


@dataclass
class Budget:
    monthly_rub: float
    usage: Usage = field(default_factory=Usage)

    @property
    def ratio(self) -> float:
        if self.monthly_rub <= 0:
            return 0.0
        return min(1.0, self.usage.money_rub / self.monthly_rub)

    @property
    def state(self) -> str:
        if self.usage.money_rub >= self.monthly_rub > 0:
            return "exhausted"
        if self.ratio >= WARN_RATIO:
            return "warning"
        return "ok"

    def headline(self) -> str:
        """Одна строка для экрана настроек."""
        if self.state == "exhausted":
            return "Месячный лимит исчерпан. Новые записи расшифровываться не будут до следующего месяца."
        if self.state == "warning":
            return "Израсходовано " + str(int(self.ratio * 100)) + "% месячного лимита."
        return "Израсходовано " + str(int(self.ratio * 100)) + "% месячного лимита."

    def meetings_left(self, avg_meeting_minutes: float, rub_per_minute: float) -> int:
        """Сколько ещё встреч уместится в остаток. Округление вниз: обещать больше — плохо."""
        if avg_meeting_minutes <= 0 or rub_per_minute <= 0:
            return 0
        left = max(0.0, self.monthly_rub - self.usage.money_rub)
        return int(left // (avg_meeting_minutes * rub_per_minute))
