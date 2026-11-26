"""FakeASR — предсказуемый ASR-провайдер для тестов конвейера.

Зачем: конвейер (сегменты -> спикеры -> разбор) нужно проверять без сети, ключей и денег.
FakeAsr выдаёт заранее заданные сегменты и умеет «сыпать» ошибкой — чтобы проверять реконнект.
Контракт совпадает с настоящими адаптерами (speechmatics/deepgram/gigaam): см. asr.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Segment:
    """Один фрагмент распознанной речи. Единый формат для всех провайдеров."""

    start_s: float
    end_s: float
    text: str
    speaker: str | None = None
    confidence: float = 1.0
    volatile: bool = False
    is_noise: bool = False


@dataclass
class FakeAsr:
    """Сегменты отдаются по одному за вызов stream(); при fail_on переданных байтах — исключение."""

    script: list[Segment] = field(default_factory=list)
    fail_at_call: int | None = None
    calls: int = 0

    def stream(self, chunk: bytes) -> list[Segment]:
        self.calls += 1
        if self.fail_at_call is not None and self.calls == self.fail_at_call:
            raise ConnectionError("provider disconnected")
        return [dict(s) if not isinstance(s, Segment) else s for s in self.script]  # type: ignore[misc]

    def transcribe_file(self, path: str) -> list[Segment]:
        """Финальный проход по всему файлу — у настоящих провайдеров точнее стрима."""
        return [s for s in self.script if not s.volatile]
