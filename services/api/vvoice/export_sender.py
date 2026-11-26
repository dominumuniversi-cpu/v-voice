"""Отправка одного запроса наружу. Единственное место, где задача покидает сервер.

Почему отдельный модуль: exporters.py собирает запросы, но сам ничего не шлёт — и до появления этого
файла отправка была нечем: маршрут отдавал 503, хотя код «есть». Здесь ровно один HTTP-вызов,
таймаут и понятная причина отказа, чтобы человек видел, куда и почему не ушло.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from .exporters import ExportRequest

TIMEOUT_S = 15


def send_request(request: ExportRequest, *, token: str = '', timeout_s: int = TIMEOUT_S) -> tuple[bool, str]:
    """Шлёт request и возвращает (получилось, объяснение для человека).

    Токен передаётся заголовком, а не в адресе: адреса попадают в журналы, заголовки — нет.
    Ответ читаем только ради объяснения: тело задачника человеку не нужно, а память расходует.
    """
    body = json.dumps(request.body, ensure_ascii=False).encode('utf-8') if request.body is not None else None
    headers = dict(request.headers or {})
    headers.setdefault('Content-Type', 'application/json; charset=utf-8')
    if token:
        headers['Authorization'] = 'Bearer ' + token
    # Заголовки в HTTP — только latin-1. Русский токен/адрес иначе падал бы невнятным UnicodeEncodeError,
    # и человек не понял бы, что не так с ключом.
    for name, value in list(headers.items()):
        try:
            str(value).encode('latin-1')
        except UnicodeEncodeError:
            return False, 'заголовок %s содержит недопустимые символы (нужна латиница)' % name
    req = urllib.request.Request(request.url, data=body, headers=headers, method=request.method)
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            status = getattr(resp, 'status', 200)
            if 200 <= status < 300:
                return True, 'принято (%d)' % status
            return False, 'отказ %d' % status
    except urllib.error.HTTPError as exc:  # ответ пришёл, но с ошибкой — самое частое
        try:
            detail = exc.read(200).decode('utf-8', 'replace')
        except Exception:  # noqa: BLE001 — тело ошибки может быть чем угодно
            detail = ''
        return False, 'отказ %s: %s' % (exc.code, detail.strip()[:120])
    except urllib.error.URLError as exc:  # сеть: нет маршрута, нет DNS, таймаут
        return False, 'не дозвонились: %s' % (exc.reason,)
    except Exception as exc:  # noqa: BLE001 — одна цель не должна ронять весь экспорт
        return False, str(exc)
