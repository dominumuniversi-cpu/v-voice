"""Общий разбор WAV для облачных провайдеров, которые принимают запись файлом.

Зачем отдельный модуль: Deepgram, AssemblyAI, OpenAI и Gladia принимают запись одним
файлом и отдают готовую расшифровку. Снять заголовок, проверить формат и сказать
человеку по-русски, почему файл не принят, должен один код, а не четыре копии.

Продакшн-записи приходят с нашего же сервера: 16 кГц, 16 бит, моно. Из этого и исходим,
но чужой файл (стерео, другая частота) не ломаем: сказано, что делать.
"""

from __future__ import annotations

import io
import wave
from dataclasses import dataclass

# Предел файла до похода в сеть: самый строгий из вендорских (OpenAI — 25 МБ на запрос).
LIMIT_BYTES = 24 * 1024 * 1024


class WavRejected(ValueError):
    """Файл не годится для отправки. Текст — для человека, а не для лога."""


def too_big(size: int, limit: int = LIMIT_BYTES) -> bool:
    """Проверка размера до чтения: заведомо большой файл не тянем в память."""
    return size > limit


@dataclass
class WavInfo:
    """Что внутри записи — этого достаточно, чтобы облако приняло файл."""

    pcm: bytes
    sample_rate: int
    channels: int
    width: int
    duration_s: float


def read_wav(data: bytes, limit: int = LIMIT_BYTES) -> WavInfo:
    """Разбирает WAV целиком. Ошибка — понятная человеку строка, а не IndexError."""
    if too_big(len(data), limit):
        # Предел в мегабайтах; у маленьких пределов (тесты) десятичная дробь честнее нуля.
        mbytes = limit / (1024 * 1024)
        shown = str(int(mbytes)) if mbytes >= 1 else '%.3f' % mbytes
        raise WavRejected('запись больше ' + shown + ' МБ: провайдер такой файл не примет')
    if len(data) < 12 or data[0:4] != b'RIFF' or data[8:12] != b'WAVE':
        raise WavRejected('это не WAV-запись: провайдер принимает наш формат .wav')
    try:
        with wave.open(io.BytesIO(data), 'rb') as handle:
            channels = handle.getnchannels()
            rate = handle.getframerate()
            width = handle.getsampwidth()
            frames = handle.getnframes()
            pcm = handle.readframes(frames)
    except (wave.Error, EOFError) as exc:
        raise WavRejected('WAV не читается: ' + str(exc)) from exc
    if not pcm:
        raise WavRejected('в записи нет звука: файл пустой')
    return WavInfo(pcm=pcm, sample_rate=rate, channels=channels, width=width,
                   duration_s=round(frames / float(rate or 1), 3))


def minutes(info: WavInfo) -> float:
    """Длительность в минутах — по ней считается цена, но не размер."""
    return round(info.duration_s / 60.0, 4)
