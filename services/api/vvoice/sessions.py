"""Сессии записи: приём аудио с телефона и выдача разбора.

Зачем отдельный модуль: маршрут приёма — единственное место, где с телефона приходят сотни
килобайт двоичных данных. Здесь проверяется всё, что можно проверить без базы и без сети:
формат, размер, длительность, а сам файл отдаётся наружу чистыми байтами.

Правила (проверяются тестами):
  1. Принимаем только WAV PCM — иначе распознавание получит мусор и вернёт пустоту,
     а человек решит, что приложение не слышит.
  2. Слишком маленькая запись — не сессия, а обрывок: честный отказ с причиной.
  3. Слишком большая — отказ до записи в память, а не после.
  4. Каждая созданная сессия получает идентификатор, который можно передать в разбор.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import re
from dataclasses import dataclass
from typing import Any

# Границы по реальному использованию: 0.2 с короче любой осмысленной фразы,
# 500 МБ — дольше, чем телефон проживёт на одной зарядке в фоновом режиме.
MIN_AUDIO_BYTES = 8_000
MAX_AUDIO_BYTES = 500 * 1024 * 1024

# PCM 16 бит 16 кГц: те же параметры, что пишет натив на обеих платформах.
BYTES_PER_MS = 32

_SESSION_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


@dataclass
class Session:
    session_id: str
    duration_ms: int
    audio_bytes: int
    sha256: str


def _read_wav_header(data: bytes) -> tuple[int, int, int] | None:
    """Возвращает (каналы, частота, биты на отсчёт) или None, если это не WAV."""
    if len(data) < 44:
        return None
    if data[0:4] != b"RIFF" or data[8:12] != b"WAVE":
        return None
    offset = 12
    channels = rate = bits = None
    while offset + 8 <= len(data):
        chunk_id = data[offset:offset + 4]
        chunk_size = int.from_bytes(data[offset + 4:offset + 8], "little")
        if chunk_id == b"fmt " and offset + 24 <= len(data):
            channels = int.from_bytes(data[offset + 10:offset + 12], "little")
            rate = int.from_bytes(data[offset + 12:offset + 16], "little")
            bits = int.from_bytes(data[offset + 22:offset + 24], "little")
            break
        offset += 8 + chunk_size + (chunk_size % 2)
    if channels is None or rate is None or bits is None:
        return None
    return channels, rate, bits


def create_session(raw: dict[str, Any]) -> tuple[int, dict[str, Any], bytes | None]:
    """Принимает тело запроса и возвращает (код, ответ, аудио).

    Аудио отдаётся отдельно: слой хранения решает, куда его положить,
    а правила приёма остаются здесь и проверяются без базы.
    """
    encoded = raw.get("audio_base64")
    if not isinstance(encoded, str) or not encoded.strip():
        return 400, {"error": "bad_request", "message": "Нужен audio_base64: запись в base64"}, None
    try:
        data = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        return 400, {"error": "bad_request", "message": "audio_base64 не является корректным base64"}, None

    if len(data) < MIN_AUDIO_BYTES:
        return 400, {"error": "audio_too_short",
                     "message": "Запись слишком короткая: " + str(len(data)) + " байт."}, None
    if len(data) > MAX_AUDIO_BYTES:
        return 413, {"error": "audio_too_large",
                     "message": "Запись слишком большая."}, None

    header = _read_wav_header(data)
    if header is None:
        return 415, {"error": "not_wav", "message": "Нужен файл WAV: заголовок не распознан."}, None
    channels, rate, bits = header
    if bits != 16:
        return 415, {"error": "unsupported_format",
                     "message": "Нужен PCM 16 бит, а пришло " + str(bits) + " бит."}, None
    if channels not in (1, 2):
        return 415, {"error": "unsupported_format",
                     "message": "Нужен 1 или 2 канала, а пришло " + str(channels) + "."}, None

    digest = hashlib.sha256(data).hexdigest()
    session = Session(
        session_id=digest[:16],
        duration_ms=(len(data) - 44) // (BYTES_PER_MS * channels),
        audio_bytes=len(data),
        sha256=digest,
    )
    return 200, {"session_id": session.session_id, "duration_ms": session.duration_ms,
                 "audio_bytes": session.audio_bytes}, data


def is_session_id(value: Any) -> bool:
    """Идентификатор сессии пришёл от клиента — проверяем форму, а не доверяем строке."""
    return isinstance(value, str) and bool(_SESSION_ID.match(value))
