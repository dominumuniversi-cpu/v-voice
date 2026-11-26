"""Хранилище записей на диске.

Зачем файлы, а не база: на этом этапе нужно одно — чтобы после загрузки запись можно было
найти по идентификатору и отдать в распознавание. База подключится в M4, и переезд должен
быть заменой этого модуля, а не переделкой всего сервера.

Правила (проверяются тестами):
  1. Идентификатор сессии — только из формы, проверенной при приёме; имя файла собирается здесь.
  2. Запись нельзя перезаписать загрузкой: две разные записи с одним id — ошибка, а не молчаливая потеря.
  3. Отсутствие записи — понятный ответ, а не исключение наружу.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .sessions import is_session_id


@dataclass
class Stored:
    path: Path
    size: int


class AudioStore:
    """Каталог записей: одна сессия — один файл."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.root = Path(root)

    def _path(self, session_id: str) -> Path:
        if not is_session_id(session_id):
            raise ValueError("Неверный идентификатор сессии")
        return self.root / (session_id + ".wav")

    def save(self, session_id: str, audio: bytes) -> Stored:
        """Сохраняет запись целиком или ничего: частичный файл не должен появиться."""
        target = self._path(session_id)
        if target.exists():
            raise FileExistsError("Такая сессия уже есть: " + session_id)
        self.root.mkdir(parents=True, exist_ok=True)
        temp = target.with_suffix(".part")
        with open(temp, "wb") as handle:
            handle.write(audio)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, target)
        return Stored(path=target, size=len(audio))

    def find(self, session_id: str) -> Stored | None:
        """Возвращает запись или None, если её нет (и если id негодный)."""
        try:
            path = self._path(session_id)
        except ValueError:
            return None
        if not path.exists():
            return None
        return Stored(path=path, size=path.stat().st_size)

    def read(self, session_id: str) -> bytes | None:
        stored = self.find(session_id)
        if stored is None:
            return None
        return stored.path.read_bytes()
