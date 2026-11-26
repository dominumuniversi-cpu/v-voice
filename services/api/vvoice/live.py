"""Живой текст: склейка стрима и порядок «приблизительно -> окончательно».

Пользователь видит серый приблизительный текст, который потом «оседает» в итоговый.
Для разбора LLM берём ТОЛЬКО окончательный текст: volatile может измениться и породить
цитату, которой в итоге не будет (и валидатор её справедливо отбракует).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .providers.fake_asr import Segment
from .vad import VadGate


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


def gate_chunks(chunks: list[bytes], gate: VadGate) -> tuple[list[bytes], int]:
    """Прогоняет звук через VAD ДО отправки в облако.

    Возвращает (что отправить, сколько кадров отброшено). Главный результат здесь не деньги,
    а приватность и батарея: тишина и шум не уходят с телефона вообще.
    """
    sent: list[bytes] = []
    dropped = 0
    started = False
    for chunk in chunks:
        if gate.push(chunk):
            if not started:
                sent.extend(gate.flush_preroll())
                started = True
            sent.append(chunk)
        else:
            dropped += 1
            started = False
    return sent, dropped
