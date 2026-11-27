"""Хранилище готовых разборов: одна сессия — один JSON рядом с её записью.

Зачем отдельно от аудио: разбор нужен, чтобы экран открывался без повторного распознавания,
а повторное распознавание стоит денег и времени. Правила те же, что у записей: имя файла
собирается только из проверенного идентификатора, отсутствие — понятный ответ, а не исключение.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .sessions import is_session_id


class DigestStore:
    """Каталог разборов: session_id + ".json"."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.root = Path(root)

    def _path(self, session_id: str) -> Path:
        if not is_session_id(session_id):
            raise ValueError("Неверный идентификатор сессии")
        return self.root / (session_id + ".json")

    def save(self, session_id: str, digest: dict[str, Any]) -> Path:
        """Пишет разбор атомарно: недописанный JSON не попадёт в выдачу."""
        target = self._path(session_id)
        self.root.mkdir(parents=True, exist_ok=True)
        temp = target.with_suffix(".part")
        with open(temp, "w", encoding="utf-8") as handle:
            json.dump(digest, handle, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, target)
        return target

    def remove(self, session_id: str) -> bool:
        """Удаляет разбор. False — файла не было."""
        try:
            path = self._path(session_id)
        except ValueError:
            return False
        if not path.exists():
            return False
        path.unlink()
        return True

    def load(self, session_id: str) -> dict[str, Any] | None:
        """Возвращает разбор или None; битый файл тоже None, а не падение сервера."""
        try:
            path = self._path(session_id)
        except ValueError:
            return None
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return None
        return data if isinstance(data, dict) else None
