"""Адаптер Speechmatics (realtime WebSocket).

Почему этот сервис в MVP первым: заявленная задержка финального результата меньше секунды,
есть диаризация в стриме и 55+ языков, стоимость 0.20-0.40 $/час. Проверено по карточке тарифов
(docs/RESEARCH/RESEARCH-2026-11.md).

Устройство модуля:
  - сетевая часть (class SpeechmaticsAsr) тонкая: только отправка и получение;
  - ВСЯ логика протокола вынесена в чистые функции (`add_audio_message`, `parse_response`),
    поэтому её можно покрыть тестами и она не требует ключа и интернета;
  - вход API ожидает WAV-байты, а в теле WebSocket отправляется только чистый PCM (16 кГц, 16 бит, моно).
    Ошибка «отправили WAV-заголовок как звук» даёт шум в первом слове — поэтому конвертация явная.
"""

from __future__ import annotations

import json
import time

# Отказы распознавания на языке человека. Ключи — ответы сервера (`type`), значение — что делать.
_WHY = {
    'not_authorised': 'сервис не принял ключ: он недействителен или у него нет доступа к распознаванию. '
                      'Проверьте ключ в настройках связки «Speechmatics» на сайте провайдера.',
    'auth_failed': 'сервис не принял ключ: он недействителен или у него нет доступа к распознаванию. '
                   'Проверьте ключ в настройках связки «Speechmatics» на сайте провайдера.',
    'invalid_language': 'сервис не умеет распознавать на выбранном языке. Смените язык в настройках разбора.',
    'quota_exceeded': 'закончился лимит или кредит на счёте провайдера. Пополните счёт и повторите разбор.',
    'not_entitled': 'ключ верный, но у аккаунта не подключён батч-тариф. Включите его в кабинете провайдера.',
    'too_much_audio': 'запись длиннее, чем принимает провайдер. Разбейте её на части.',
}

from dataclasses import dataclass, field
from typing import Any

from .fake_asr import Segment

SAMPLE_RATE = 16_000
WS_URL = "wss://eu2.rt.speechmatics.com/v2/ru"


def wav_to_pcm(chunk: bytes) -> bytes:
    """Снимает RIFF/WAVE-заголовок, если он есть. Поток может прийти как PCM или как WAV."""
    if len(chunk) > 44 and chunk[0:4] == b"RIFF" and chunk[8:12] == b"WAVE":
        return chunk[44:]
    return chunk


def add_audio_message(pcm: bytes, seq: int) -> str:
    """Сообщение `AddAudio` с base64-аудио — ровно такой формат ждёт сервер."""
    import base64

    return json.dumps({"message": "AddAudio", "audio": base64.b64encode(pcm).decode("ascii"), "seq_no": seq})


def start_recognition_message(language: str, diarization: bool = True) -> str:
    """Первое сообщение после подключения: язык, формат аудио, включение диаризации."""
    return json.dumps({
        "message": "StartRecognition",
        "audio_format": {"type": "raw", "encoding": "pcm_s16le", "sample_rate": SAMPLE_RATE},
        "transcription_config": {
            "language": language,
            "enable_entities": False,
            "diarization": "speaker" if diarization else "none",
        },
    })


def end_of_stream_message(seq: int) -> str:
    return json.dumps({"message": "EndOfStream", "last_seq_no": seq})


def parse_response(raw: str) -> Segment | None:
    """Ответ сервера -> наш Segment. Неизвестные/служебные сообщения игнорируем (None)."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    kind = data.get("message")
    if kind in ("AudioAdded", "RecognitionStarted", "Info"):
        return None
    if kind == "AddPartialTranscript":
        words = (data.get("metadata") or {}).get("transcript") or ""
        if not words.strip():
            return None
        start = float(data.get("start_time") or 0.0)
        end = float(data.get("end_time") or start)
        return Segment(start_s=start, end_s=end, text=words, speaker=_speaker(data), volatile=True)
    if kind == "AddTranscript":
        text = (data.get("metadata") or {}).get("transcript") or ""
        if not text.strip():
            return None
        start = float(data.get("start_time") or 0.0)
        end = float(data.get("end_time") or start)
        return Segment(start_s=start, end_s=end, text=text, speaker=_speaker(data))
    if kind == "Error":
        raise ConnectionError(why_error(data))
    return None


def _speaker(data: dict) -> str | None:
    results = data.get("results") or []
    for r in results:
        speaker = (r.get("alternatives") or [{}])[0].get("speaker")
        if speaker:
            return "Голос " + str(speaker).replace("S", "")
    return None


def why_error(data: dict) -> str:
    """Причина отказа сервера словами человека, с техническим кодом в скобках."""
    code = str(data.get("type") or "unknown")
    return ("Speechmatics: " + _WHY.get(code, str(data.get("reason") or code))
            + " (ответ сервера: " + code + ")")


def check_key(connect: Any, api_key: str, language: str = "ru") -> tuple[bool, str]:
    """Проверка ключа без звука: открыть сеанс и дождаться подтверждения или отказа.

    Отдельный короткий сеанс нужен потому, что разбор идёт минутами, а «ключ не принят»
    человек должен увидеть сразу после его вставки, а не на середине разговора.
    """
    sock = None
    try:
        sock = connect(WS_URL + "?" + "jwt=" + api_key, {})
        sock.send(start_recognition_message(language, False))
        for _ in range(5):
            raw = sock.recv()
            try:
                data = json.loads(raw)
            except (TypeError, ValueError):
                continue
            if data.get("message") == "RecognitionStarted":
                return True, "ключ принят, распознавание готово"
            if data.get("message") == "Error":
                return False, why_error(data)
        return False, "сервис не подтвердил сеанс — попробуйте ещё раз через минуту"
    except Exception as exc:  # сеть, TLS, рукопожатие — всё это «нет связи», а не падение сервера
        return False, "не удалось связаться: " + str(exc)[:200]
    finally:
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass

@dataclass
class SpeechmaticsAsr:
    """Сетевой адаптер. Ожидает объект подключения (`connect`) — так тестируется без сети."""

    connect: Any  # (url, headers) -> объект с send(str), recv() -> str, close()
    api_key: str
    language: str = "ru"
    diarization: bool = True
    seq: int = 0
    buffer: list[Segment] = field(default_factory=list)

    def open(self) -> None:
        self.sock = self.connect(WS_URL + "?" + "jwt=" + self.api_key, {})
        self.sock.send(start_recognition_message(self.language, self.diarization))

    def stream(self, chunk: bytes) -> list[Segment]:
        self.seq += 1
        self.sock.send(add_audio_message(wav_to_pcm(chunk), self.seq))
        out: list[Segment] = []
        while True:
            seg = parse_response(self.sock.recv())
            if seg is None:
                break
            out.append(seg)
        return out

    def close(self) -> None:
        self.sock.send(end_of_stream_message(self.seq))
        self.sock.close()

    def transcribe_file(self, path: str) -> list[Segment]:
        """Финальный проход: ждём AddTranscript после EndOfStream в пределах таймаута."""
        self.close()
        out: list[Segment] = []
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            seg = parse_response(self.sock.recv())
            if seg is not None and not seg.volatile:
                out.append(seg)
            if seg is None:
                break
        return out
