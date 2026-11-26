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

import base64
import binascii
import json
from dataclasses import dataclass, field
from typing import Any

from .evidence import validate_item
from .sessions import create_session, is_session_id
from .digest_store import DigestStore
from .export_route import export_session
from .transcript_route import transcript_file
from .job import analyze
from .live_sessions import LiveSessions, push_chunk
from .open_session import open_session
from .storage import AudioStore
from .provider_probe import presets


@dataclass
class Response:
    status: int
    body: dict[str, Any]
    headers: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"status": self.status, "body": self.body, "headers": self.headers}


import re

ROUTES: dict[str, tuple[str, ...]] = {
    "/api/v1/health": ("GET",),
    "/api/v1/presets": ("GET",),
    "/api/v1/probe": ("POST",),
    "/api/v1/items/validate": ("POST",),
    # Приём записи с телефона. Ответ содержит идентификатор сессии для разбора.
    "/api/v1/sessions": ("POST",),
    # Открыть сессию заранее — до того, как появится запись (для живого текста).
    "/api/v1/sessions/open": ("POST",),
    # Готовый разбор сессии. Путь шаблонный: id приходит от клиента.
    "/api/v1/sessions/{session_id}/digest": ("GET",),
    # Запуск разбора сохранённой записи. Отдельный путь, потому что действие меняет состояние.
    "/api/v1/sessions/{session_id}/analyze": ("POST",),
    # Кусок звука для живого текста. Отдельный путь: ответ содержит только текст, без разбора.
    "/api/v1/sessions/{session_id}/stream": ("POST",),
    # Отправка одобренных задач наружу (Helper, Jira, Bitrix24, webhook).
    "/api/v1/sessions/{session_id}/export": ("POST",),
    # Скачивание расшифровки в привычном формате: человек уносит разговор с собой.
    "/api/v1/sessions/{session_id}/transcript": ("GET",),
}

# Шаблонные пути: клиент обращается к /api/v1/sessions/<id>/digest, поэтому точного совпадения мало.
_TEMPLATED: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^/api/v1/sessions/([A-Za-z0-9_-]{1,64})/digest$"), "/api/v1/sessions/{session_id}/digest"),
    (re.compile(r"^/api/v1/sessions/([A-Za-z0-9_-]{1,64})/analyze$"), "/api/v1/sessions/{session_id}/analyze"),
    (re.compile(r"^/api/v1/sessions/([A-Za-z0-9_-]{1,64})/stream$"), "/api/v1/sessions/{session_id}/stream"),
    (re.compile(r"^/api/v1/sessions/([A-Za-z0-9_-]{1,64})/export$"), "/api/v1/sessions/{session_id}/export"),
]


def _route(path: str) -> tuple[str | None, str | None]:
    """Возвращает (шаблон маршрута, параметр) или (None, None), если пути нет."""
    if path in ROUTES:
        return path, None
    for pattern, template in _TEMPLATED:
        match = pattern.match(path)
        if match:
            return template, match.group(1)
    return None, None


def _bad_request(reason: str) -> Response:
    return Response(400, {"error": "bad_request", "message": reason})


def handle(method: str, path: str, raw_body: str = "", *, sender: Any = None,
           store: "AudioStore | None" = None,
           digests: "DigestStore | None" = None,
           recognizer: Any = None,
           call_llm: Any = None,
           live_sessions: Any = None,
           exporter: Any = None,
           gate: Any = None,
           export_targets: Any = None,
           auth_token: str | None = None,
           device_tokens: Any = None) -> Response:
    """Единственная точка входа: метод, путь, тело. Никаких глобальных состояний."""
    template, param = _route(path)
    allowed = ROUTES.get(template) if template else None
    if allowed is None:
        return Response(404, {"error": "not_found", "message": "Нет такого пути: " + path})
    if method.upper() not in allowed:
        return Response(405, {"error": "method_not_allowed", "message": "Этот путь принимает: " + ", ".join(allowed)},
                        {"Allow": ", ".join(allowed)})

    # Пускаем только своих. Пустой список токенов — сервер открыт (как было), и это осознанный
    # режим разработки: он не должен тихо превращаться в «открыто» на боевом сервере.
    if device_tokens and not _authorized(auth_token, device_tokens):
        return Response(401, {"error": "unauthorized",
                              "message": "Нужен токен устройства. Он выдаётся при настройке приложения."},
                        {"WWW-Authenticate": "Bearer"})

    if method.upper() == "GET":
        if template == "/api/v1/sessions/{session_id}/transcript":
            # Формат — часть пути для человека (?format=srt), по умолчанию TXT.
            from urllib.parse import parse_qs
            query = parse_qs(path.split("?", 1)[1]) if "?" in path else {}
            fmt = (query.get("format") or ["txt"])[0].strip().lower()
            found = digests.load(param) if digests is not None else None
            code, body, headers = transcript_file(found, fmt)
            return Response(code, body, headers)
        if template == "/api/v1/sessions/{session_id}/digest":
            # Путь есть. Данных может не быть — тогда говорим именно это, а не «нет такого пути».
            found = digests.load(param) if digests is not None else None
            if found is None:
                return Response(404, {"error": "digest_not_found", "session_id": param,
                                      "message": "Разбор этой записи ещё не готов."})
            return Response(200, found)
        if path == "/api/v1/health":
            # Сюда добавляются настройки моделей: человек по этому ответу понимает, работает ли разбор,
            # и видит отпечаток ключа, чтобы сверить, тот ли подхвачен. Значения ключей не выходят никогда.
            from .config import load as _load_settings
            return Response(200, {"status": "ok", "service": "v-voice", "version": "1",
                                  "settings": _load_settings().public_health()})
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

    if path == "/api/v1/sessions/open":
        code, body = open_session()
        return Response(code, body)

    if path == "/api/v1/sessions":
        status, body, audio = create_session(payload)
        if status != 200 or audio is None:
            return Response(status, body)
        if store is None:
            # Нет хранилища — не притворяемся, что запись принята и найдётся потом.
            return Response(503, {"error": "storage_unavailable",
                                  "message": "Сервер не настроен хранить записи."})
        try:
            store.save(body["session_id"], audio)
        except FileExistsError:
            return Response(409, {"error": "already_exists",
                                  "message": "Такая запись уже загружена."})
        if sender is not None:
            # Уведомление для слоя разбора: сам разбор здесь не запускается.
            try:
                sender({"session_id": body["session_id"], "size": len(audio)})
            except Exception:  # pragma: no cover
                pass
        return Response(200, body)

    if template == "/api/v1/sessions/{session_id}/analyze":
        if recognizer is None or call_llm is None:
            return Response(503, {"error": "pipeline_unavailable",
                                  "message": "Сервер не настроен запускать разбор."})
        # «Разбирать только участников» — выбор человека, а не догадка модели. По умолчанию
        # выключено: на командной встрече иначе чужие голоса остались бы без задач.
        outcome = analyze(param, store=store, digests=digests,
                          provider_factory=recognizer, call_llm=call_llm, gate=gate,
                          members_only=payload.get('members_only') is True)
        return Response(outcome.status, outcome.body)

    if template == "/api/v1/sessions/{session_id}/stream":
        if recognizer is None:
            return Response(503, {"error": "pipeline_unavailable",
                                  "message": "Сервер не настроен распознавать на лету."})
        encoded = payload.get("pcm_base64")
        if not isinstance(encoded, str) or not encoded.strip():
            return _bad_request("Нужен pcm_base64: кусок звука в base64")
        try:
            pcm = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError):
            return _bad_request("pcm_base64 не является корректным base64")
        if live_sessions is None:
            return Response(503, {"error": "pipeline_unavailable",
                                  "message": "Сервер не хранит состояние живого потока."})
        code, body = push_chunk(live_sessions, param, pcm, provider_factory=recognizer)
        return Response(code, body)

    if template == "/api/v1/sessions/{session_id}/export":
        code, body = export_session(payload, send=exporter, configured=export_targets)
        return Response(code, body)

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


def _authorized(token: str | None, allowed: Any) -> bool:
    """Сверка токена за постоянное время.

    Обычное == выходит из сравнения на первом несовпавшем символе, и по задержке ответа
    можно подбирать токен посимвольно. compare_digest так не делает.
    """
    import hmac
    if not token:
        return False
    return any(hmac.compare_digest(str(token), str(known)) for known in allowed)
