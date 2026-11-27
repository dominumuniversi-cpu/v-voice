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
from .models_check import check_models, list_models
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
    "/api/v1/models": ("GET",),
    "/api/v1/models/check": ("POST",),
    # Настройка моделей из браузера: меняет работающий сервер, ключ живёт в памяти.
    "/api/v1/settings": ("GET", "POST"),
    # Настройка моделей из браузера. Отдельная ручка, потому что меняет работающий сервер.

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
    # Без этой строки скачивание расшифровки (TXT/SRT/JSON) отвечало 404 на любой запрос.
    (re.compile(r"^/api/v1/sessions/([A-Za-z0-9_-]{1,64})/transcript$"), "/api/v1/sessions/{session_id}/transcript"),
]


def _route(path: str) -> tuple[str | None, str | None]:
    """Возвращает (шаблон маршрута, параметр) или (None, None), если пути нет.

    Строка запроса (?format=srt) — это параметры, а не часть пути: без отсечения
    скачивание расшифровки в любом формате отвечало бы 404.
    """
    path = path.split('?', 1)[0]
    if path in ROUTES:
        return path, None
    for pattern, template in _TEMPLATED:
        match = pattern.match(path)
        if match:
            return template, match.group(1)
    return None, None


def _bad_request(reason: str) -> Response:
    return Response(400, {"error": "bad_request", "message": reason})


def _with_cost(body: Any, price_per_hour: float, budget: float = 0.0) -> Any:
    """Добавляет стоимость к разбору — и только если тариф задан.

    Ноль означает «тариф неизвестен». Показывать «0 ₽» в этом случае — значит соврать человеку,
    который начнёт думать, что встреча ничего не стоила.
    """
    if not isinstance(body, dict) or price_per_hour <= 0:
        return body
    seconds = body.get('sent_seconds')
    if not isinstance(seconds, (int, float)):
        return body
    body = dict(body)
    cost = round(seconds / 3600.0 * price_per_hour, 2)
    body['cost_rub'] = cost
    # Предел задан и превышен — говорим прямо. Узнать о перерасходе из счёта в конце месяца
    # поздно: встреча уже записана.
    if budget > 0 and cost > budget:
        body['budget_exceeded'] = True
        body['budget_rub'] = budget
    return body


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
           asr_price_per_hour: float = 0.0,
           budget_per_meeting: float = 0.0,
           device_tokens: Any = None,
           settings: Any = None,
           asr_env: str = '',
           llm_env: str = '') -> Response:
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
        # Человек чаще всего путает две вещи: токен устройства (пускает в сервис) и ключ модели
        # (платит провайдеру). Пишем это прямо, иначе он ищет ошибку не там, где она есть.
        hint = "Нужен токен устройства. Он выдаётся при настройке приложения."
        given = (auth_token or "").strip()
        if given.startswith(("sk-", "ghp_", "ghs_")):
            hint += " Похоже, вставлен ключ модели: он нужен ниже, в поле «Ключ» у выбранной связки, а не в токене."
        elif given:
            hint += " Токен не совпал с тем, что знает сервер."
        return Response(401, {"error": "unauthorized", "message": hint},
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
            # Раньше здесь читался только .env, и после сохранения на экране health продолжал
            # показывать старую связку — экран не отражал то, что человек настроил. Берём живое
            # состояние, когда оно есть, и .env только если сервер собран без него.
            from .config import load as _load_settings
            live = settings.view() if settings is not None else _load_settings().public_health()
            return Response(200, {"status": "ok", "service": "v-voice", "version": "1",
                                  "settings": live})
        if path == "/api/v1/presets":
            # Старые пресеты (шаблоны задач) и новые (связки моделей) в одном ответе: два разных
            # пути к одному понятию — это две правды, и одна из них обязательно отстанет.
            from .runtime_settings import presets as model_presets
            data = {"presets": presets()}
            data.update(model_presets())
            return Response(200, data)

    if path == "/api/v1/models":
        # Что можно выбрать для уже сохранённой связки. Для Ollama — живой запрос к серверу человека.
        if settings is None:
            return Response(503, {"error": "settings_unavailable"})
        return Response(200, list_models(settings))

    if path == "/api/v1/models/check":
        # Настоящий пробный вызов: «ключ вписан» и «ключ работает» — разные вещи, и человеку
        # нужен ответ на второй вопрос, а не зелёная галочка за сохранение строки.
        if settings is None:
            return Response(503, {"error": "settings_unavailable", "message": "Нечего проверять."})
        return Response(200, check_models(settings))


    if path == "/api/v1/settings":
        if settings is None:
            return Response(503, {"error": "settings_unavailable",
                                  "message": "Сервер не хранит настроек в памяти."})
        if method.upper() == "GET":
            return Response(200, settings.view(asr_env=asr_env, llm_env=llm_env))
        payload: dict[str, Any] = {}
        if raw_body.strip():
            try:
                payload = json.loads(raw_body)
            except json.JSONDecodeError as exc:
                return _bad_request("Тело запроса не JSON: " + exc.msg)
            if not isinstance(payload, dict):
                return _bad_request("Нужен объект с полями asr_provider, asr_key, llm_provider, llm_key")
        code, body = settings.update(payload)
        if code != 200:
            body["message"] = str(body.get("message", ""))
        return Response(code, body)

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
            # Заменить запись можно ТОЛЬКО у сессии, открытой заранее под живой текст: её звук
            # приходит после «Стоп». Для обычной записи защита «второй файл не затирает первый» сильна.
            _live_state = live_sessions.peek(body["session_id"]) if live_sessions is not None else None
            opened_live = _live_state is not None and (
                bool(_live_state.live.finals) or _live_state.live.volatile is not None)
            store.save(body["session_id"], audio, replace=opened_live)
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
        return Response(outcome.status, _with_cost(outcome.body, asr_price_per_hour, budget_per_meeting))

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
        code, body = push_chunk(live_sessions, param, pcm, provider_factory=recognizer, gate=gate)
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
