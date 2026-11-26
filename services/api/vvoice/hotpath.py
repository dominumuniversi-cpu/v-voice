"""Горячий путь: что происходит в первые секунды разговора на телефоне.

Требование «голос транскрибировался онлайн» — это не «рано или поздно текст появится»,
а «человек видит слова за доли секунды». Здесь собраны правила, которые определяют задержку,
и они проверяемы без телефона:

  1. Размер чанка. Маленький — больше запросов и накладных расходов; большой — задержка.
     200 мс — компромисс: при пропуске одного чанка задержка ещё незаметна.
  2. Досыл. Если сеть пропала, чанки не теряются, а копятся и уходят пачкой при восстановлении.
     3. Бюджет. Пока мы в бюджете, показываем «слушаю»; вышли — честно показываем «связь плохая».
"""

from __future__ import annotations

from dataclasses import dataclass, field

CHUNK_MS = 200
SAMPLE_RATE = 16_000
BYTES_PER_SAMPLE = 2


def chunk_bytes(chunk_ms: int = CHUNK_MS) -> int:
    """Сколько байт PCM16 в одном чанке."""
    return SAMPLE_RATE * BYTES_PER_SAMPLE * chunk_ms // 1000


@dataclass
class NetworkBudget:
    """Насколько отстаёт живой текст. Задаёт, что видит человек в индикаторе."""

    healthy_ms: int = 1500
    degraded_ms: int = 4000
    lag_ms: int = 0

    def cursor(self, delta_ms: int) -> str:
        """Сообщает, насколько выросло отставание, и возвращает состояние индикатора."""
        self.lag_ms = max(0, self.lag_ms + delta_ms)
        return self.state()

    def recovered(self, sent_ms: int) -> None:
        """Успешная отправка уменьшает отставание."""
        self.lag_ms = max(0, self.lag_ms - sent_ms)

    def state(self) -> str:
        if self.lag_ms <= self.healthy_ms:
            return "live"
        if self.lag_ms <= self.degraded_ms:
            return "lagging"
        return "offline"


@dataclass
class ResendQueue:
    """Буфер неотправленного: ограничен по времени, чтобы не съесть память бесконечной записью."""

    max_ms: int = 60_000
    pending: list[bytes] = field(default_factory=list)
    pending_ms: int = 0
    dropped_ms: int = 0

    def push(self, chunk: bytes, chunk_ms: int = CHUNK_MS) -> None:
        self.pending.append(chunk)
        self.pending_ms += chunk_ms
        while self.pending_ms > self.max_ms and self.pending:
            self.pending.pop(0)
            self.pending_ms -= chunk_ms
            self.dropped_ms += chunk_ms

    def drain(self) -> list[bytes]:
        out, self.pending, self.pending_ms = self.pending, [], 0
        return out


def estimate_first_text_ms(network_rtt_ms: int, chunk_ms: int = CHUNK_MS, asr_final_ms: int = 400) -> int:
    """Когда человек увидит первое осмысленное слово.

    Складываем накопление одного чанка, дорогу до сервиса в одну сторону, обработку и дорогу обратно.
    Это оценка снизу: в ней нет очередей и повторных попыток — их проверяем живым прогоном.
    """
    return chunk_ms + network_rtt_ms // 2 + asr_final_ms + network_rtt_ms // 2
