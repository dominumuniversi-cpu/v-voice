"""Список связок на диске: заведённый провайдер не пропадает после перезапуска.

Ключ в поле настроек — собственность приложения, а не агента: человек вводит его на экране,
и приложение обязано это запомнить. Без файла каждая пересборка контейнера стирала список
связок, и человек заново вводил ключи, считая, что «настройка не работает».

Файл лежит рядом с данными (`/data/connections.json`), пишется атомарно и с правами 0600.
Наружу по-прежнему уходит только `public()` без ключа — эту часть решает ConnectionList.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# Поля связки, которые можно хранить. Ключ хранится: без него связка — просто надпись.
FIELDS = ('id', 'kind', 'protocol', 'title', 'base_url', 'model', 'key', 'preset', 'note', 'cost', 'added')
FILE_NAME = 'connections.json'


class ConnectionFiles:
    """Чтение и запись списка связок. Битый файл — пустой список, а не упавший сервер."""

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path)

    def load(self) -> list[dict[str, Any]]:
        try:
            raw = json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return []
        items = raw.get('items') if isinstance(raw, dict) else raw
        if not isinstance(items, list):
            return []
        out = []
        for item in items:
            if isinstance(item, dict) and isinstance(item.get('id'), str) and isinstance(item.get('kind'), str):
                out.append({name: item[name] for name in FIELDS if name in item})
        return out

    def load_active(self) -> dict[str, str]:
        """Какую связку человек выбрал рабочей. Без этого после перезапуска работал не он."""
        try:
            raw = json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return {}
        active = raw.get('active') if isinstance(raw, dict) else None
        if not isinstance(active, dict):
            return {}
        return {str(k): str(v) for k, v in active.items() if isinstance(v, str)}

    def save(self, items: list[dict[str, Any]], active: dict[str, str]) -> None:
        """Пишет атомарно: недописанный файл не должен стать источником правды."""
        temp = self.path.with_suffix('.part')
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(temp, 'w', encoding='utf-8') as handle:
                json.dump({'items': items, 'active': active}, handle, ensure_ascii=False)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.chmod(temp, 0o600)
            except OSError:
                pass  # на Windows права держит каталог
            os.replace(temp, self.path)
        except OSError:
            # Диск полон или каталог только для чтения: работа продолжается как до правки.
            return
