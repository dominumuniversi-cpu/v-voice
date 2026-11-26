"""Конвейер одной сессии: запись -> транскрипт -> разбор.

Здесь собраны все шаги, которые до сих пор описывались словами:
сегменты ASR (стрим и финальный проход) -> сборка реплик -> отчёт -> разбор LLM с валидатором цитат.
Сеть не трогаем: ASR и LLM передаются снаружи, поэтому конвейер полностью покрывается тестами.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .assemble import Transcript, assemble
from .digest import make_digest
from .live import LiveBuffer
from .providers.fake_asr import Segment


@dataclass
class SessionState:
    live: LiveBuffer = field(default_factory=LiveBuffer)
    errors: list[str] = field(default_factory=list)


def run_live(provider, state: SessionState, chunks: list[bytes]) -> LiveBuffer:
    """Прогон стрима. Обрыв провайдера не теряет уже полученное — это важнее полноты."""
    for chunk in chunks:
        try:
            state.live.push(provider.stream(chunk))
        except ConnectionError as exc:
            state.errors.append("provider_disconnected: " + str(exc))
    return state.live


def run_session(provider, chunks: list[bytes], call_llm: Callable[[str, str], dict]) -> dict:
    """Полный проход: живой текст + финальный транскрипт + разбор. Возвращает отчёт-сводку."""
    state = SessionState()
    run_live(provider, state, chunks)
    final_segments: list[Segment] = provider.transcribe_file("segment.wav")
    transcript: Transcript = assemble(final_segments)
    digest = make_digest(transcript, call_llm)
    return {
        "live_text": state.live.display_text(),
        "transcript": transcript.text,
        "speakers": sorted(transcript.speakers),
        "dropped_noise": transcript.dropped_noise,
        "dropped_short": transcript.dropped_short,
        "errors": state.errors,
        "digest": digest,
    }
