"""Конвейер одной сессии: запись -> транскрипт -> разбор.

Здесь собраны все шаги, которые до сих пор описывались словами:
сегменты ASR (стрим и финальный проход) -> сборка реплик -> отчёт -> разбор LLM с валидатором цитат.
Сеть не трогаем: ASR и LLM передаются снаружи, поэтому конвейер полностью покрывается тестами.
"""

from __future__ import annotations

import wave
from dataclasses import dataclass, field
from typing import Callable

from .assemble import Transcript, assemble
from .digest import make_digest
from .live import LiveBuffer, gate_chunks
from .providers.fake_asr import Segment
from .vad import FRAME_MS, VadGate


class AsrFailure(RuntimeError):
    """Распознавание речи не состоялось: звук есть, текста нет.

    Отдельный тип нужен, чтобы экран не путал «не услышали» и «не поняли»: первое — про ключ
    распознавания или связь с ним, второе — про модель, которая читает готовый текст.
    """


@dataclass
class SessionState:
    live: LiveBuffer = field(default_factory=LiveBuffer)
    errors: list[str] = field(default_factory=list)


def run_live(provider, state: SessionState, chunks: list[bytes], *, gate: VadGate | None = None) -> LiveBuffer:
    """Прогон стрима. Обрыв провайдера не теряет уже полученное — это важнее полноты.

    gate — тот же VAD, что и на записи: без него шум и тишина живой встречи уходили в облако
    целиком, и «глушить шум» было обещанием, которого не выполняли.
    """
    if gate is not None:
        chunks, dropped = gate_chunks(chunks, gate)
        if dropped:
            state.errors.append("noise_dropped: " + str(dropped))
    for chunk in chunks:
        try:
            state.live.push(provider.stream(chunk))
        except ConnectionError as exc:
            state.errors.append("provider_disconnected: " + str(exc))
    return state.live


def _wav_seconds(path: str) -> float:
    """Длительность записи в секундах. Не читается — 0, а не выдуманное число."""
    try:
        with wave.open(str(path), 'rb') as handle:
            rate = handle.getframerate() or 1
            return round(handle.getnframes() / float(rate), 1)
    except (OSError, wave.Error):
        return 0.0


def run_session(
    provider,
    chunks: list[bytes],
    call_llm: Callable[[str, str], dict],
    *,
    gate: VadGate | None = None,
    members_only: bool = False,
    audio_path: str | None = None,
) -> dict:
    """Полный проход: VAD -> живой текст -> финальный транскрипт -> разбор.

    gate=None означает «прогнать всё как есть» (так делают тесты с заранее записанным звуком).
    audio_path — где лежит сама запись. Без него файл провайдеру не отдать: раньше здесь стояла
    строка "segment.wav", которой на диске нет, и любой файловый провайдер падал на «нет файла».
    """
    # Звук отдаётся распознаванию РОВНО ОДИН РАЗ. Фабрика провайдера уже могла получить
    # расшифровку (она зовёт transcribe_file при сборке), и тогда второй поход в сеть был бы
    # двойной оплатой и обрывом: облако второй раз тот же файл не принимает.
    # Если провайдер пришёл без расшифровки — просим её здесь, и это единственный поход.
    state = SessionState()
    final_segments: list[Segment] = list(getattr(provider, "segments", None) or [])
    if not final_segments:
        try:
            final_segments = list(provider.transcribe_file(audio_path or "segment.wav"))
        except Exception as exc:  # провайдер речи упал: у нас нет ни одной реплики
            raise AsrFailure(str(exc)) from exc
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
        # Файловый проход отдаёт запись целиком, а не куски через отсечение шума: отсечения
        # здесь нет, и считать его нулём честнее, чем числами из ниоткуда.
        "dropped_by_vad": 0,
        "sent_chunks": 1,
        # Сколько секунд аудио реально ушло провайдеру — по длине самой записи, а не по числу кусков.
        "sent_seconds": _wav_seconds(audio_path or ""),
        "dropped_short": transcript.dropped_short,
        # Сколько строк распознавание придумало в тишине. Нужно человеку как мера шума в зале.
        "dropped_invented": transcript.dropped_invented,
        "errors": state.errors,
        "digest": digest,
    }
