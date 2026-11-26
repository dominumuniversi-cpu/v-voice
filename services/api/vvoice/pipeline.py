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
from .live import LiveBuffer, gate_chunks
from .providers.fake_asr import Segment
from .vad import VadGate


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


def run_session(
    provider,
    chunks: list[bytes],
    call_llm: Callable[[str, str], dict],
    *,
    gate: VadGate | None = None,
    members_only: bool = False,
) -> dict:
    """Полный проход: VAD -> живой текст -> финальный транскрипт -> разбор.

    gate=None означает «прогнать всё как есть» (так делают тесты с заранее записанным звуком).
    """
    state = SessionState()
    sent, dropped_frames = (chunks, 0) if gate is None else gate_chunks(chunks, gate)
    run_live(provider, state, sent)
    final_segments: list[Segment] = provider.transcribe_file("segment.wav")
    transcript: Transcript = assemble(final_segments)
    digest = make_digest(transcript, call_llm, members_only=members_only)
    return {
        "live_text": state.live.display_text(),
        "transcript": transcript.text,
        # Реплики с таймкодами. Без них не собрать субтитры и не вернуться к месту в записи,
        # а разговор — это в первую очередь «кто и когда сказал», а не сплошной текст.
        "utterances": [
            {"speaker": u.speaker, "start_s": u.start_s, "end_s": u.end_s, "text": u.text}
            for u in transcript.utterances
        ],
        "speakers": sorted(transcript.speakers),
        "dropped_noise": transcript.dropped_noise,
        "dropped_by_vad": dropped_frames,
        "sent_chunks": len(sent),
        "dropped_short": transcript.dropped_short,
        "errors": state.errors,
        "digest": digest,
    }
