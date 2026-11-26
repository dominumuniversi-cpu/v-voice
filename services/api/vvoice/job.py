"""Запуск разбора сохранённой записи.

Зачем отдельно от маршрута: маршрут только принимает байты, а здесь — вся последовательность
(найти запись, распознать, разобрать, сохранить). Так проверки могут подставить заранее
записанный звук и синтетический ответ модели, не обращаясь ни к одному внешнему сервису.

Правила:
  1. Нет записи — понятный отказ, а не пустой разбор.
  2. Провайдер упал — разбор не сохраняется частично.
  3. Успех — разбор сохраняется и сразу доступен по тому же идентификатору.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .digest_store import DigestStore
from .pipeline import run_session
from .storage import AudioStore


@dataclass
class JobResult:
    status: int
    body: dict[str, Any]


def analyze(
    session_id: str,
    *,
    store: AudioStore | None,
    digests: DigestStore | None,
    provider_factory: Callable[[Path], Any],
    call_llm: Callable[[str, str], dict],
    gate: Any = None,
) -> JobResult:
    """Полный разбор записи: запись -> конвейер -> сохранённый разбор."""
    if store is None or digests is None:
        return JobResult(503, {"error": "storage_unavailable",
                                "message": "Сервер не настроен хранить записи и разборы."})
    stored = store.find(session_id)
    if stored is None:
        return JobResult(404, {"error": "session_not_found",
                                "message": "Записи с таким идентификатором нет."})
    ready = digests.load(session_id)
    if ready is not None:
        # Повторный разбор стоит денег: уже посчитанное отдаём как есть.
        return JobResult(200, dict(ready, cached=True))
    try:
        provider = provider_factory(stored.path)
        result = run_session(provider, [], call_llm, gate=gate)
    except Exception as exc:  # разбор не должен ронять сервер и не должен сохраняться частично
        return JobResult(502, {"error": "digest_failed", "message": str(exc)})
    digests.save(session_id, result)
    return JobResult(200, result)
