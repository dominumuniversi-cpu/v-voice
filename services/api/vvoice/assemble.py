"""Сборка расшифровки: фрагменты ASR -> реплики по говорящим -> текст для разбора.

Три задачи:
  1. убрать шум/тишину (фрагменты с is_noise не попадают в реплики и в разбор);
  2. склеить соседние фрагменты одного говорящего в реплику (так читаемо и дешевле для LLM);
  3. соблюсти порядок и не потерять таймкоды — они нужны для цитат (evidence).

Правило «всё, что нельзя объяснить цитатой, не попадает в разбор» опирается на то,
что этот модуль даёт стабильные start_s/end_s и точный текст.
"""

from __future__ import annotations

from .hallucination import is_hallucination

from dataclasses import dataclass, field
from typing import Iterable

from .providers.fake_asr import Segment

MIN_SPEECH_SEC = 0.2
MERGE_GAP_SEC = 1.5
VOLATILE_OVERLAP_SEC = 3.0


@dataclass
class Utterance:
    speaker: str
    start_s: float
    end_s: float
    text: str

    def render(self) -> str:
        return f"{self.speaker}: {self.text.strip()}"


@dataclass
class Transcript:
    utterances: list[Utterance] = field(default_factory=list)
    dropped_noise: int = 0
    dropped_short: int = 0
    # Строки, которые придумало распознавание (в тишине и шуме). Считаем отдельно от шума:
    # это не звуки комнаты, а выдуманные слова, и человеку полезно знать их число.
    dropped_invented: int = 0

    @property
    def text(self) -> str:
        """Текст для LLM и для поиска цитат. Говорящий с двоеточием, дальше реплика."""
        return " ".join(u.render() for u in self.utterances)

    @property
    def speakers(self) -> set[str]:
        """Кто участвовал. Пустая метка — «говорящий не распознан», а не участник по имени ''."""
        return {u.speaker for u in self.utterances if u.speaker}


def _is_meaningful(seg: Segment) -> bool:
    return (not seg.is_noise) and (seg.end_s - seg.start_s) >= MIN_SPEECH_SEC and bool(seg.text.strip())


def assemble(segments: Iterable[Segment], *, merge_gap_s: float = MERGE_GAP_SEC) -> Transcript:
    """Собирает реплики. Volatile-фрагменты не попадают в итог: они могут измениться."""
    usable = sorted(
        (s for s in segments if not s.volatile),
        key=lambda s: (s.start_s, s.end_s),
    )
    result = Transcript()
    for seg in usable:
        if seg.is_noise:
            result.dropped_noise += 1
            continue
        if not _is_meaningful(seg):
            result.dropped_short += 1
            continue
        if is_hallucination(seg.text):
            result.dropped_invented += 1
            continue

        # Без диаризации спикера НЕТ. Выдуманная метка «Голос 1» попадала в каждую строку файла
        # и в список участников выжимки: человек читал про участника, которого в разговоре не было.
        speaker = seg.speaker or ""
        if result.utterances:
            last = result.utterances[-1]
            if last.speaker == speaker and seg.start_s - last.end_s <= merge_gap_s:
                last.text = (last.text + " " + seg.text.strip()).strip()
                last.end_s = max(last.end_s, seg.end_s)
                continue
        result.utterances.append(Utterance(speaker=speaker, start_s=seg.start_s, end_s=seg.end_s, text=seg.text.strip()))
    return result
