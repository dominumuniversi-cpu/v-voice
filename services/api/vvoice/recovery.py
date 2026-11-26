"""Восстановление недописанных записей после сбоя (FR-6).

Что происходит на телефоне в реальности: система убила приложение на встрече в 40 минут,
или человек выронил телефон из батареи, или просто выключил экран на морозе. Файл остался,
но WAV-заголовок в нём не финализирован: длина = 0, звук «есть», открыть нельзя.

Правила восстановления:
  1. Заголовок пересобирается по фактическому размеру данных, а не по записанной длине.
  2. Если данных меньше 1 секунды — файл не восстанавливаем, а помечаем как обрывок:
     сессия из щелчка микрофона не нужна ни человеку, ни статистике.
  3. Частичные чанки (обрезанный последний) отбрасываются: непарный байт ломает PCM.
  4. Восстановление никогда не перезаписывает исходник: пишем рядом .recovered.wav.
  5. Никаких «попутных» удалений: что не восстановили — то остаётся лежать для разбора.
"""

from __future__ import annotations

from dataclasses import dataclass

HEADER_SIZE = 44
BYTES_PER_MS_MONO16 = 32  # 16000 * 2 байта в секунду = 32 байта на миллисекунду
MIN_RECOVER_MS = 1000


@dataclass
class RecoveryResult:
    recovered: bool
    reason: str = ""
    duration_ms: int = 0
    data_bytes: int = 0

    def as_dict(self) -> dict:
        return {"recovered": self.recovered, "reason": self.reason, "duration_ms": self.duration_ms, "data_bytes": self.data_bytes}


def _u32(value: int) -> bytes:
    return int(value).to_bytes(4, "little")


def usable_data_bytes(total_size: int) -> int:
    """Сколько звука лежит после заголовка с учётом парности байт (16-бит = по 2 байта)."""
    data = max(0, total_size - HEADER_SIZE)
    return data - (data % 2)


def duration_ms(total_size: int) -> int:
    return usable_data_bytes(total_size) * 1000 // BYTES_PER_MS_MONO16


def rebuild_header(payload: bytes) -> bytes:
    """Собирает честный WAV-заголовок под фактический размер данных."""
    data_size = len(payload)
    header = b"RIFF" + _u32(36 + data_size) + b"WAVE"
    header += b"fmt " + _u32(16) + (1).to_bytes(2, "little") + (1).to_bytes(2, "little")
    header += _u32(16_000) + _u32(32_000) + (2).to_bytes(2, "little") + (16).to_bytes(2, "little")
    header += b"data" + _u32(data_size)
    return header


def inspect(total_size: int) -> RecoveryResult:
    """Решение до чтения файла целиком: берёмся ли за восстановление."""
    data = usable_data_bytes(total_size)
    if total_size <= HEADER_SIZE:
        return RecoveryResult(False, "данных нет: только пустой заголовок", 0, 0)
    if duration_ms(total_size) < MIN_RECOVER_MS:
        return RecoveryResult(False, "меньше секунды звука — это обрывок, не запись", duration_ms(total_size), data)
    return RecoveryResult(True, "", duration_ms(total_size), data)


def recover(raw: bytes) -> tuple[bytes, RecoveryResult]:
    """Возвращает (wav-байты или b"", результат). Файл без данных не выдаём как запись."""
    result = inspect(len(raw))
    if not result.recovered:
        return b"", result
    payload = raw[HEADER_SIZE:HEADER_SIZE + result.data_bytes]
    return rebuild_header(payload) + payload, result
