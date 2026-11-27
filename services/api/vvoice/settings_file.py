"""Хранилище настроек на диске: ключ, введённый в настройках, не пропадает после перезапуска.

Зачем это вообще: ключ человек вводит НЕ агенту и не в файл проекта, а в поле настроек экрана.
Значит приложение обязано сохранить его само — иначе первый же перезапуск контейнера стирает
рабочий ключ, и человек ищет ошибку в провайдере вместо того, чтобы просто продолжить.

Правила, без которых такое хранилище хуже отсутствия:
  - файл лежит в каталоге данных (`/data/settings.json`), а не в образе: пересборка его не тронет;
  - наружу ключ не отдаётся никогда — только отпечаток, это решает существующий view();
  - битый файл не валит сервер: читаем, что можем, остальное берём из окружения;
  - запись атомарная (временный файл + rename): недописанный JSON не должен стать источником правды;
  - права 0600: файл с ключом не читает никто, кроме владельца процесса.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# Что из настроек сохраняем. Только то, что человек реально выбирает на экране.
FIELDS = ('asr_provider', 'asr_key', 'asr_model', 'llm_provider', 'llm_key', 'llm_model', 'llm_base_url')
FILE_NAME = 'settings.json'


class SettingsFile:
    """Файл настроек: чтение при старте, запись после каждого изменения человеком."""

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path)

    def load(self) -> dict[str, str]:
        """Сохранённые значения. Нет файла или он битый — пусто, и работаем на окружении."""
        try:
            raw = json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return {}
        if not isinstance(raw, dict):
            return {}
        return {name: str(raw[name]) for name in FIELDS if isinstance(raw.get(name), str)}

    def save(self, values: dict[str, Any]) -> None:
        """Пишет атомарно и закрыто для чужих глаз. Сбой записи не должен ронять запрос."""
        payload = {name: str(values[name]) for name in FIELDS if name in values}
        temp = self.path.with_suffix('.part')
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(temp, 'w', encoding='utf-8') as handle:
                json.dump(payload, handle, ensure_ascii=False)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.chmod(temp, 0o600)
            except OSError:
                pass  # на Windows прав не меняем: там действуют права каталога
            os.replace(temp, self.path)
        except OSError:
            # Диск полон или каталог только для чтения: работа продолжается как до правки.
            return
