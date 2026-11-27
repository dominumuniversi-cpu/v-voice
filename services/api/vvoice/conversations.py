"""Журнал разговоров для экрана «Разговоры».

Зачем это отдельный модуль: список собирается из двух каталогов на диске (звук и разбор),
а не из базы, — и правило «что считать разговором» должно быть в одном месте, чтобы экран,
скачивание и разбор не разошлись во мнениях о том, что существует.

Правила:
  1. Один идентификатор — один разговор, даже если запись и разбор лежат файлами отдельно.
  2. Показываем и «есть только звук»: разбор мог не запускаться, и человеку нужно видеть,
     что запись цела и разбор можно запустить.
  3. Время берётся с диска: другого источника правды о том, когда говорили, у нас нет.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .digest_store import DigestStore
from .sessions import is_session_id
from .storage import AudioStore


def _files(root: Path, suffix: str) -> dict[str, Path]:
    """Идентификатор -> файл. Мусорные имена пропускаем: id приходит из адреса, а не с диска."""
    found: dict[str, Path] = {}
    try:
        entries = list(root.iterdir())
    except OSError:
        return found
    for path in entries:
        if path.suffix != suffix or not path.is_file():
            continue
        session_id = path.stem
        if is_session_id(session_id):
            found[session_id] = path
    return found


def _title(digest: dict[str, Any] | None, session_id: str) -> str:
    """Название разговора: своё заголовок из разбора, иначе дата и время начала."""
    if digest:
        for key in ("title", "topic", "subject"):
            value = digest.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:120]
    return "Разговор " + session_id[:6]


def list_conversations(audio: AudioStore | None, digests: DigestStore | None) -> dict[str, Any]:
    """Список разговоров, свежие сверху, и счётчики для подписи на экране."""
    by_id: dict[str, dict[str, Any]] = {}
    audio_files = _files(audio.root, ".wav") if audio is not None else {}
    digest_files = _files(digests.root, ".json") if digests is not None else {}

    for session_id, path in audio_files.items():
        try:
            size = path.stat().st_size
            started = path.stat().st_mtime
        except OSError:
            continue
        # 44 байта — заголовок WAV; длительность считаем по 16 кГц моно 16 бит, как пишет экран.
        seconds = max(0, (size - 44) // 32000) if size > 44 else 0
        by_id[session_id] = {"session_id": session_id, "started": started, "size": size,
                             "duration_s": seconds, "has_audio": True, "ready": False}

    for session_id, path in digest_files.items():
        digest = digests.load(session_id) if digests is not None else None
        try:
            when = path.stat().st_mtime
        except OSError:
            continue
        entry = by_id.setdefault(session_id, {"session_id": session_id, "started": when, "size": 0,
                                              "duration_s": 0, "has_audio": False, "ready": False})
        entry["ready"] = digest is not None
        # Есть ли что показать текстом. Разбор без реплик — это «разбор готов», но исходного
        # текста нет, и кнопки скачивания вели в 409: экран должен знать разницу заранее.
        entry["has_transcript"] = bool(digest) and bool(str(digest.get("transcript") or "").strip())
        entry["title"] = _title(digest, session_id)
        if digest:
            entry["items"] = len(digest.get("items") or [])
            entry["summary_count"] = len(digest.get("summary") or [])
            if not entry.get("started"):
                entry["started"] = when

    items = []
    for entry in by_id.values():
        entry.setdefault("title", "Разговор " + entry["session_id"][:6])
        entry["url"] = "?session=" + entry["session_id"]
        items.append(entry)
    items.sort(key=lambda e: e.get("started") or 0, reverse=True)
    return {"items": items, "total": len(items),
            "ready": sum(1 for e in items if e.get("ready")),
            "now": time.time()}
