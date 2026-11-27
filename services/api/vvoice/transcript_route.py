"""Скачивание расшифровки: один разговор — четыре привычных формата.

Зачем отдельным модулем: генераторы уже есть в formats.py, и второй такой же рядом — это
две разные правды об одном формате. Здесь только достаём реплики и превращаем их в строки.
"""

from __future__ import annotations

from typing import Any

from .formats import Line, render

# Расширения, под которыми файлы ждут на телефоне и в проводнике.
CONTENT_TYPES = {
    "txt": "text/plain; charset=utf-8",
    "md": "text/markdown; charset=utf-8",
    "srt": "application/x-subrip; charset=utf-8",
    "vtt": "text/vtt; charset=utf-8",
    "json": "application/json; charset=utf-8",
}


def to_lines(digest: dict[str, Any]) -> list[Line]:
    """Реплики разбора в строки формата. Разбор без реплик — пустой список, а не падение."""
    raw = digest.get("utterances")
    if not isinstance(raw, list):
        return []
    lines: list[Line] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        lines.append(Line(
            start_s=float(item.get("start_s") or 0.0),
            end_s=float(item.get("end_s") or 0.0),
            text=text,
            speaker=str(item.get("speaker") or ""),
        ))
    return lines


def transcript_file(digest: dict[str, Any] | None, fmt: str, session_id: str = "") -> tuple[int, Any, dict[str, str]]:
    """Ответ маршрута: статус, тело и заголовки. Тело — текст файла или описание ошибки."""
    if fmt not in CONTENT_TYPES:
        return 400, {"error": "unknown_format", "format": fmt,
                     "message": "Такого формата нет. Доступно: " + ", ".join(sorted(CONTENT_TYPES))}, {}
    if digest is None:
        return 404, {"error": "digest_not_found",
                     "message": "Разбор этой записи ещё не готов, расшифровки пока нет."}, {}
    lines = to_lines(digest)
    if not lines:
        # Пустой файл человек прочитает как «сломалось». Говорим словами, что распознавать было нечего.
        return 409, {"error": "transcript_empty",
                     "message": "В разборе нет расшифровки: распознано не было ни одной реплики."}, {}
    body = render(fmt, lines, title="Расшифровка")
    # Имя файла в заголовке: без него браузер открывает расшифровку вкладкой, и человек ждёт
    # скачивания, а получает текст на экране. Имя — из идентификатора сессии, а не из текста.
    name = (session_id or "transcript") + "." + fmt
    return 200, body, {"Content-Type": CONTENT_TYPES[fmt],
                       "Content-Disposition": 'attachment; filename="' + name + '"'}
