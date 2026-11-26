"""HTTP-слой: разбор запросов и сборка ответов без веб-фреймворка.

Зачем без FastAPI: чтобы поведение (коды, тела, валидация) проверялось в CI без установки
фреймворка и без базы. Роуты — чистые функции `handle(method, path, body)`, а тонкая обёртка
(ASGI/FastAPI) добавляется в M4, когда появится БД. Логика не переезжает — переезжает только обвязка.

Полнота важна здесь, а не в фреймворке:
  1. Неизвестный путь -> 404 с человеческим текстом, а не пустое тело.
  2. Неверный метод -> 405 и заголовок Allow.
  3. Плохой JSON -> 400 с указанием места, а не 500.
  4. Элемент без цитаты -> 422 и объяснение, что именно не так.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .evidence import validate_item
from .provider_probe import presets


@dataclass
class Response:
    status: int
    body: dict[str, Any]
    headers: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"status": self.status, "body": self.body, "headers": self.headers}


ROUTES: dict[str, tuple[str, ...]] = {
    "/api/v1/health": ("GET",),
    "/api/v1/presets": ("GET",),
    "/api/v1/probe": ("POST",),
    "/api/v1/items/validate": ("POST",),
}


def _bad_request(reason: str) -> Response:
    return Response(400, {"error": "bad_request", "message": reason})


def handle(method: str, path: str, raw_body: str = "", *, sender: Any = None) -> Response:
    """Единственная точка входа: метод, путь, тело. Никаких глобальных состояний."""
    allowed = ROUTES.get(path)
    if allowed is None:
        return Response(404, {"error": "not_found", "message": "Нет такого пути: " + path})
    if method.upper() not in allowed:
        return Response(405, {"error": "method_not_allowed", "message": "Этот путь принимает: " + ", ".join(allowed)},
                        {"Allow": ", ".join(allowed)})

    if method.upper() == "GET":
        if path == "/api/v1/health":
            return Response(200, {"status": "ok", "service": "v-voice", "version": "1"})
        if path == "/api/v1/presets":
            return Response(200, {"presets": presets()})

    payload: dict[str, Any] = {}
    if raw_body.strip():
        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            return _bad_request("Тело запроса не JSON: " + exc.msg + " (позиция " + str(exc.pos) + ")")
        if not isinstance(payload, dict):
            return _bad_request("Тело запроса должно быть JSON-объектом")

    if path == "/api/v1/probe":
        provider = payload.get("provider")
        if not isinstance(provider, str) or not provider:
            return _bad_request("Укажите provider")
        api_key = payload.get("api_key") or ""
        if not isinstance(api_key, str):
            return _bad_request("api_key должен быть строкой")
        from .provider_probe import probe

        result = probe(provider, api_key, sender or (lambda p, k: (None, "проверка отключена в офлайн-режиме")))
        return Response(200, result.as_dict())

    if path == "/api/v1/items/validate":
        item = payload.get("item")
        transcript = payload.get("transcript") or ""
        speakers = payload.get("speakers") or []
        if not isinstance(item, dict):
            return _bad_request("Нужен объект item")
        if not isinstance(transcript, str) or not transcript.strip():
            return _bad_request("Нужен непустой transcript: без расшифровки цитату проверить нельзя")
        ok, reason = validate_item(item, transcript, set(speakers), set(), False)
        if not ok:
            return Response(422, {"error": "unproven_item", "reason": reason})
        return Response(200, {"ok": True})
