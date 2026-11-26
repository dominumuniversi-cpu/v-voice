"""Живой текст: склейка стрима и порядок «приблизительно -> окончательно».

Пользователь видит серый приблизительный текст, который потом «оседает» в итоговый.
Для разбора LLM берём ТОЛЬКО окончательный текст: volatile может измениться и породить
цитату, которой в итоге не будет (и валидатор её справедливо отбракует).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .providers.fake_asr import Segment


@dataclass
class LiveBuffer:
    finals: list[Segment] = field(default_factory=list)
    volatile: Segment | None = None
    last_update_s: float = 0.0

    def push(self, segments: list[Segment]) -> None:
        for seg in segments:
            if seg.volatile:
                self.volatile = seg
            else:
                self.finals.append(seg)
                self.volatile = None
            self.last_update_s = max(self.last_update_s, seg.end_s)

    def display_text(self) -> str:
        """Текст для экрана «Слушаю»: окончательное + (приблизительное в кавычках)."""
        final = " ".join(s.text.strip() for s in self.finals).strip()
        approx = (self.volatile.text.strip() if self.volatile else "")
        return (final + " " + approx).strip()
