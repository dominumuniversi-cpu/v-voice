"""Адаптеры облачного распознавания, которые принимают запись одним файлом.

Здесь четыре сервиса с разными протоколами и один общий смысл: отдать готовую запись,
получить список фраз с временами. Живого потока у них нет (не нужен: наш конвейер
сначала пишет файл, потом разбирает), поэтому `stream` возвращает пустой список.

Почему это в одном модуле: у всех четырёх три шага (отправить -> дождаться -> разобрать),
различия только в путях и полях JSON. Одна реализация лучше четырёх копий с разными ошибками.

Сеть не проверяется тестами: разбор ответов вынесен в чистые функции, их и проверяем.
"""

from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable

from .fake_asr import Segment
from .wav_tools import LIMIT_BYTES, WavRejected, read_wav

TIMEOUT_S = 300.0
POLL_S = 3.0
POLL_LIMIT_S = 900.0
class CloudError(RuntimeError):
    """Отказ облака с кодом. Отличаем свой отказ от чужого: по коду экран выбирает слова."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


def _post_json(url: str, payload: dict[str, Any] | None, headers: dict[str, str]) -> dict[str, Any]:
    """POST JSON -> JSON. Ошибку облака переводим в одну строку, пригодную для экрана."""
    body = json.dumps(payload).encode('utf-8') if payload is not None else b'{}'
    request = urllib.request.Request(url, data=body, headers={'Content-Type': 'application/json', **headers})
    return _read(request)


def _get_json(url: str, headers: dict[str, str]) -> dict[str, Any]:
    return _read(urllib.request.Request(url, headers=headers))


def _read(request: urllib.request.Request) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_S) as resp:
            raw = resp.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as exc:
        detail = ''
        try:
            data = json.loads(exc.read().decode('utf-8', 'replace'))
            detail = str(data.get('message') or data.get('error') or data.get('detail') or '')
        except Exception:  # noqa: BLE001 — тело ошибки не обязано быть JSON
            detail = ''
        raise CloudError(exc.code, 'облако отказало (' + str(exc.code) + ')'
                         + (': ' + detail if detail else '')) from exc
    except urllib.error.URLError as exc:
        raise CloudError(0, 'облако недоступно: ' + str(exc.reason)) from exc
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CloudError(0, 'облако ответило не JSON вместо расшифровки') from exc


def _speaker(value: Any) -> str | None:
    """Номер голоса -> «Голос 1». Пустой номер — автор неизвестен, и это честнее выдумки."""
    if value is None or value == '':
        return None
    digits = ''.join(ch for ch in str(value) if ch.isdigit())
    return 'Голос ' + (digits or '1')


# --- Deepgram -----------------------------------------------------------------------------

def deepgram_segments(data: dict[str, Any]) -> list[Segment]:
    """Ответ Deepgram -> наши фрагменты. Пустые фразы пропускаем."""
    out: list[Segment] = []
    channels = (data.get('results') or {}).get('channels') or []
    for channel in channels:
        for alt in channel.get('alternatives') or []:
            for word in alt.get('words') or []:
                if not str(word.get('punctuated_word') or word.get('word') or '').strip():
                    continue
                out.append(Segment(start_s=float(word.get('start') or 0.0),
                                   end_s=float(word.get('end') or word.get('start') or 0.0),
                                   text=str(word.get('punctuated_word') or word.get('word')).strip(),
                                   speaker=_speaker(word.get('speaker'))))
    return merge_words(out)


def merge_words(words: list[Segment], gap_s: float = 1.2) -> list[Segment]:
    """Слова склеиваем в фразы: разбор читает фразы, а не отдельные слова.

    Пауза длиннее gap_s или смена голоса начинает новую фразу — иначе границы теряются,
    и цитата из разбора занимает пол-записи.
    """
    out: list[Segment] = []
    for word in words:
        if out and word.start_s - out[-1].end_s <= gap_s and word.speaker == out[-1].speaker:
            last = out[-1]
            last.text = (last.text + ' ' + word.text).strip()
            last.end_s = max(last.end_s, word.end_s)
        else:
            out.append(Segment(start_s=word.start_s, end_s=word.end_s, text=word.text, speaker=word.speaker))
    return out


@dataclass
class DeepgramAsr:
    """POST https://api.deepgram.com/v1/listen — прежний протокол потоковых моделей."""

    api_key: str
    language: str = 'ru'
    model: str = 'nova-3'
    base_url: str = 'https://api.deepgram.com/v1'
    segments: list[Segment] = field(default_factory=list)
    model_name: str = ''

    def stream(self, chunk: bytes) -> list[Segment]:
        return []

    def transcribe_file(self, path: str) -> list[Segment]:
        with open(path, 'rb') as handle:
            audio = handle.read(LIMIT_BYTES + 1)
        read_wav(audio)  # понятная ошибка до похода в сеть
        url = (self.base_url.rstrip('/') + '/listen?model=' + urllib.parse.quote(self.model)
               + '&language=' + urllib.parse.quote(self.language) + '&smart_format=true&diarize=true&punctuate=true')
        request = urllib.request.Request(url, data=audio, headers={
            'Authorization': 'Token ' + self.api_key, 'Content-Type': 'audio/wav'})
        data = _read(request)
        self.model_name = str((data.get('metadata') or {}).get('model_info', {}).get('name') or self.model)
        self.segments = deepgram_segments(data)
        return self.segments


# --- AssemblyAI ---------------------------------------------------------------------------

def assemblyai_segments(data: dict[str, Any]) -> list[Segment]:
    """Ответ AssemblyAI: реплики (utterances) или слова с временем в миллисекундах -> фразы."""
    # Если задачник просил разметку говорящих, вендор отдаёт готовые utterances — берём их:
    # так границы фраз и голоса приходят от сервиса, а не из нашего склеивания по паузам.
    utterances = data.get('utterances') or []
    if utterances:
        out: list[Segment] = []
        for utter in utterances:
            if not isinstance(utter, dict):
                continue
            text = str(utter.get('text') or '').strip()
            if not text:
                continue
            out.append(Segment(start_s=float(utter.get('start') or 0) / 1000.0,
                               end_s=float(utter.get('end') or 0) / 1000.0,
                               text=text, speaker=_speaker(utter.get('speaker'))))
        if out:
            return out
    words: list[Segment] = []
    for word in data.get('words') or []:
        text = str(word.get('text') or '').strip()
        if not text:
            continue
        words.append(Segment(start_s=float(word.get('start') or 0) / 1000.0,
                             end_s=float(word.get('end') or 0) / 1000.0,
                             text=text, speaker=_speaker(word.get('speaker'))))
    return merge_words(words)


@dataclass
class AssemblyAiAsr:
    """Загрузить (upload) -> заказать (transcript) -> ждать (poll) -> забрать слова."""

    api_key: str
    language: str = 'ru'
    base_url: str = 'https://api.assemblyai.com/v2'
    segments: list[Segment] = field(default_factory=list)
    model_name: str = 'universal'
    poll_limit_s: float = POLL_LIMIT_S
    sleep: Callable[[float], None] = time.sleep

    def stream(self, chunk: bytes) -> list[Segment]:
        return []

    def transcribe_file(self, path: str) -> list[Segment]:
        with open(path, 'rb') as handle:
            audio = handle.read(LIMIT_BYTES + 1)
        read_wav(audio)
        headers = {'Authorization': self.api_key}
        upload = urllib.request.Request(self.base_url.rstrip('/') + '/upload', data=audio,
                                        headers={'Authorization': self.api_key, 'Content-Type': 'audio/wav'})
        uploaded = _read(upload)
        audio_url = str(uploaded.get('upload_url') or '')
        if not audio_url:
            raise RuntimeError('AssemblyAI не принял файл: нет адреса загрузки')
        ordered = _post_json(self.base_url.rstrip('/') + '/transcript', {
            'audio_url': audio_url, 'speech_model': self.model_name,
            'language_code': self.language, 'speaker_labels': True, 'punctuate': True}, headers)
        job_id = str(ordered.get('id') or '')
        if not job_id:
            raise RuntimeError('AssemblyAI не выдал номер задачи: ' + str(ordered)[:120])
        deadline = time.monotonic() + self.poll_limit_s
        while time.monotonic() < deadline:
            job = _get_json(self.base_url.rstrip('/') + '/transcript/' + job_id, headers)
            status = str(job.get('status') or '')
            if status == 'completed':
                self.segments = assemblyai_segments(job)
                return self.segments
            if status == 'error':
                raise RuntimeError('AssemblyAI не распознал запись: ' + str(job.get('error') or 'без причины'))
            self.sleep(POLL_S)
        raise RuntimeError('AssemblyAI не ответил за ' + str(int(self.poll_limit_s)) + ' с')


# --- OpenAI Whisper API -------------------------------------------------------------------

def openai_segments(data: dict[str, Any]) -> list[Segment]:
    """OpenAI отдаёт текст без времён на каждый сегмент — времена берём как есть."""
    out: list[Segment] = []
    for seg in data.get('segments') or []:
        text = str(seg.get('text') or '').strip()
        if text:
            out.append(Segment(start_s=float(seg.get('start') or 0.0), end_s=float(seg.get('end') or 0.0), text=text))
    if not out:
        text = str(data.get('text') or '').strip()
        if text:
            out.append(Segment(start_s=0.0, end_s=0.0, text=text))
    return out


@dataclass
class OpenAiWhisperAsr:
    """multipart/form-data на /audio/transcriptions: имя файла и поля — вручную, без библиотек."""

    api_key: str
    language: str = 'ru'
    model: str = 'whisper-1'
    base_url: str = 'https://api.openai.com/v1'
    segments: list[Segment] = field(default_factory=list)
    model_name: str = ''

    def stream(self, chunk: bytes) -> list[Segment]:
        return []

    def transcribe_file(self, path: str) -> list[Segment]:
        with open(path, 'rb') as handle:
            audio = handle.read(LIMIT_BYTES + 1)
        read_wav(audio)
        boundary = '----vvoice' + base64.b16encode(str(time.time()).encode())[:12].decode()
        parts: list[bytes] = []
        for name, value in (('model', self.model), ('language', self.language),
                            ('response_format', 'verbose_json'), ('temperature', '0')):
            parts.append(('--' + boundary + '\r\nContent-Disposition: form-data; name="' + name + '"\r\n\r\n'
                          + value + '\r\n').encode('utf-8'))
        head = ('--' + boundary + '\r\nContent-Disposition: form-data; name="file"; filename="record.wav"\r\n'
                'Content-Type: audio/wav\r\n\r\n').encode('utf-8')
        body = b''.join(parts) + head + audio + ('\r\n--' + boundary + '--\r\n').encode('utf-8')
        request = urllib.request.Request(self.base_url.rstrip('/') + '/audio/transcriptions', data=body, headers={
            'Authorization': 'Bearer ' + self.api_key,
            'Content-Type': 'multipart/form-data; boundary=' + boundary})
        data = _read(request)
        self.model_name = self.model
        self.segments = openai_segments(data)
        return self.segments


# --- Gladia -------------------------------------------------------------------------------


def gladia_segments(data: dict[str, Any]) -> list[Segment]:
    """Gladia: transcription.utterances со временем в миллисекундах и номером голоса."""
    out: list[Segment] = []
    result = data.get('result') or {}
    transcription = result.get('transcription') or {}
    # Полный ответ несёт объект transcription, упрощённый — только перечень utterances.
    utterances = (transcription.get('utterances') if isinstance(transcription, dict) else None) \
        or result.get('utterances') or []
    for utter in utterances:
        if not isinstance(utter, dict):
            continue
        # Время у Gladia в миллисекундах, у остальных — в секундах: приводим к секундам сразу.
        text = str(utter.get('text') or '').strip()
        if not text:
            continue
        out.append(Segment(start_s=_ms(utter.get('start')), end_s=_ms(utter.get('end')),
                           text=text, speaker=_speaker(utter.get('speaker'))))
    return out


def _ms(value: Any) -> float:
    """Миллисекунды Gladia -> секунды. Число меньше минуты считаем секундами, чтобы не терять старые ответы."""
    number = float(value or 0.0)
    return number / 1000.0 if number > 60 else number


@dataclass
class GladiaAsr:
    """POST /v2/pre-recorded -> адрес результата; ждём готовности по нему."""

    api_key: str
    language: str = 'ru'
    base_url: str = 'https://api.gladia.io/v2'
    segments: list[Segment] = field(default_factory=list)
    model_name: str = 'default'
    poll_limit_s: float = POLL_LIMIT_S
    sleep: Callable[[float], None] = time.sleep

    def stream(self, chunk: bytes) -> list[Segment]:
        return []

    def transcribe_file(self, path: str) -> list[Segment]:
        with open(path, 'rb') as handle:
            audio = handle.read(LIMIT_BYTES + 1)
        read_wav(audio)
        headers = {'x-gladia-key': self.api_key}
        started = _post_json(self.base_url.rstrip('/') + '/pre-recorded', {
            'audio': 'data:audio/wav;base64,' + base64.b64encode(audio).decode('ascii'),
            'language_config': {'languages': [self.language], 'code_switching': False}}, headers)
        # Документация Gladia: POST возвращает id и status=queued, готовый результат — по
        # /pre-recorded/{id}. Поле result_url оставляем запасным: если вендор его пришлёт, он главнее.
        job_id = str(started.get('id') or '')
        poll_url = str(started.get('result_url') or (self.base_url.rstrip('/') + '/pre-recorded/' + job_id
                                                    if job_id else ''))
        if not poll_url:
            raise CloudError(0, 'Gladia не выдала номер задачи распознавания')
        deadline = time.monotonic() + self.poll_limit_s
        while time.monotonic() < deadline:
            job = _get_json(poll_url, headers)
            status = str(job.get('status') or '')
            if status == 'done':
                self.segments = gladia_segments(job)
                return self.segments
            if status == 'error':
                raise RuntimeError('Gladia не распознала запись: ' + str(job.get('error') or 'без причины'))
            self.sleep(POLL_S)
        raise RuntimeError('Gladia не ответила за ' + str(int(self.poll_limit_s)) + ' с')
