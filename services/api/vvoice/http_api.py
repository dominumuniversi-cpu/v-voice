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
from .conversations import list_conversations
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

    # Список подключений: добавить провайдера, выбрать активного, удалить.
    "/api/v1/connections": ("GET", "POST"),
    "/api/v1/connections/{conn_id}": ("PATCH", "DELETE"),
    "/api/v1/connections/{conn_id}/activate": ("POST",),
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
    # Журнал разговоров: что было, когда и что из этого получилось. Без него «Готово» на экране
    # означало «разбор где-то есть»: вернуться к нему было нечем.
    "/api/v1/conversations": ("GET",),
    # Сам звук записи: человек хочет переслушать разговор, а не только прочитать его.
    "/api/v1/sessions/{session_id}/audio": ("GET",),
    # Удаление разговора целиком: запись и разбор. Человек — хозяин своего архива.
    "/api/v1/sessions/{session_id}": ("DELETE",),
}

# Шаблонные пути: клиент обращается к /api/v1/sessions/<id>/digest, поэтому точного совпадения мало.
_TEMPLATED: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^/api/v1/sessions/([A-Za-z0-9_-]{1,64})/digest$"), "/api/v1/sessions/{session_id}/digest"),
    (re.compile(r"^/api/v1/sessions/([A-Za-z0-9_-]{1,64})/analyze$"), "/api/v1/sessions/{session_id}/analyze"),
    (re.compile(r"^/api/v1/sessions/([A-Za-z0-9_-]{1,64})/stream$"), "/api/v1/sessions/{session_id}/stream"),
    (re.compile(r"^/api/v1/sessions/([A-Za-z0-9_-]{1,64})/export$"), "/api/v1/sessions/{session_id}/export"),
    # Без этой строки скачивание расшифровки (TXT/SRT/JSON) отвечало 404 на любой запрос.
    (re.compile(r"^/api/v1/sessions/([A-Za-z0-9_-]{1,64})/transcript$"), "/api/v1/sessions/{session_id}/transcript"),
    (re.compile(r"^/api/v1/sessions/([A-Za-z0-9_-]{1,64})/audio$"), "/api/v1/sessions/{session_id}/audio"),
    (re.compile(r"^/api/v1/sessions/([A-Za-z0-9_-]{1,64})$"), "/api/v1/sessions/{session_id}"),
    # Подключения: одна запись по имени. Без этих строк «Удалить» и «Включить» отвечали бы 404.
    (re.compile(r"^/api/v1/connections/([A-Za-z0-9_-]{1,32})$"), "/api/v1/connections/{conn_id}"),
    (re.compile(r"^/api/v1/connections/([A-Za-z0-9_-]{1,32})/activate$"), "/api/v1/connections/{conn_id}/activate"),
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


# Протокол связки -> провайдер в терминах настроек. Держим рядом с /health: там это и нужно.
_CHOSEN_PROTOCOL = {
    'deepseek': 'deepseek', 'anthropic': 'anthropic', 'ollama': 'ollama', 'fake': 'fake',
    'zai': 'zai', 'mistral': 'mistral', 'openai': 'openai',
    'speechmatics': 'speechmatics', 'whisper': 'whisper',
}


def _apply_chosen(live: Any, connections: Any) -> None:
    """Подставляет в ответ /health ту связку, которой сервер работает на самом деле.

    Мутирует уже собранный словарь: copy.deepcopy здесь не нужен, а лишний слой скрыл бы,
    что /health и фабрики провайдеров смотрят на один и тот же выбор.
    """
    if not isinstance(live, dict):
        return
    if connections is not None:
        view = connections.view()
        chosen = view.get('in_work') or {}
        by_id = {item.get('id'): item for item in view.get('items') or []}
        for kind in ('llm', 'asr'):
            conn = by_id.get(chosen.get(kind))
            block = live.get(kind)
            if conn is None or not isinstance(block, dict):
                continue
            protocol = str(conn.get('protocol') or '')
            block['provider'] = _CHOSEN_PROTOCOL.get(protocol, protocol)
            block['model'] = conn.get('model') or ''
            if kind == 'llm':
                block['base_url'] = conn.get('base_url') or ''
            block['from_env'] = False
            # Сам ключ не показываем никогда: только «есть/нет», как и у настроек из окружения.
            block['key_set'] = bool(conn.get('key_set'))
            block['ready'] = bool(conn.get('key_set')) or block['provider'] in ('fake', 'whisper')
            block['connection'] = conn.get('title') or ''
    # Рабочего подключения нет — модель тоже не настроена. Показывать провайдера из окружения
    # значит обещать работу, которой не будет: связку выбирает человек кнопкой «Работать этой».
    for kind in ('llm', 'asr'):
        block = live.get(kind)
        if isinstance(block, dict) and not block.get('connection'):
            block['ready'] = False


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


def _save_connections(connections: Any, connections_file: Any) -> None:
    """Записывает список связок на диск после правки. Нет файла — молча живём в памяти."""
    if connections_file is None or connections is None:
        return
    snapshot = connections.snapshot()
    connections_file.save(snapshot['items'], snapshot['active'])


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
           connections: Any = None,
           settings_file: Any = None,
           connections_file: Any = None,
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
        if path == "/api/v1/conversations":
            # Список собирается из двух каталогов на диске: звук и разбор лежат файлами рядом
            # с идентификатором сессии. Показываем оба вида — «есть звук» и «готов разбор», —
            # иначе человек не понимает, откуда пропадает разговор, по которому разбор не запускался.
            return Response(200, list_conversations(store, digests))
        if template == "/api/v1/sessions/{session_id}/audio":
            stored = store.find(param) if store is not None else None
            if stored is None:
                return Response(404, {"error": "session_not_found",
                                      "message": "Записи с таким идентификатором нет."})
            try:
                audio = stored.path.read_bytes()
            except OSError:
                return Response(500, {"error": "audio_unreadable", "message": "Запись на диске не читается."})
            return Response(200, audio, {"Content-Type": "audio/wav",
                                         "Content-Disposition": 'inline; filename="' + param + '.wav"',
                                         "Cache-Control": "private, max-age=600"})
        if template == "/api/v1/sessions/{session_id}/transcript":
            # Формат — часть пути для человека (?format=srt), по умолчанию TXT.
            from urllib.parse import parse_qs
            query = parse_qs(path.split("?", 1)[1]) if "?" in path else {}
            fmt = (query.get("format") or ["txt"])[0].strip().lower()
            found = digests.load(param) if digests is not None else None
            code, body, headers = transcript_file(found, fmt, param)
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
            if settings is not None:
                # Настройки (.env) — не приговор: человек выбирает связку в списоке подключений,
                # и в работу идёт именно она (фабрики в main.py берут active_for первым делом).
                # Без этой поправки /health показывал whisper и fake рядом с выбранными
                # «Mistral» и «Speechmatics», и экран говорил одно, а работал другое.
                _apply_chosen(live, connections)
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


    if path == "/api/v1/connections":
        if connections is None:
            return Response(503, {"error": "connections_unavailable",
                                  "message": "Сервер не хранит список подключений."})
        if method.upper() == "GET":
            return Response(200, connections.view())
        payload: dict[str, Any] = {}
        if raw_body.strip():
            try:
                payload = json.loads(raw_body)
            except json.JSONDecodeError as exc:
                return _bad_request("Тело запроса не JSON: " + exc.msg)
            if not isinstance(payload, dict):
                return _bad_request("Нужен объект: kind, protocol, title, base_url, model, key")
        code, body = connections.add(payload)
        if code == 201:
            _save_connections(connections, connections_file)
        return Response(code, body)

    if template == "/api/v1/connections/{conn_id}":
        if connections is None:
            return Response(503, {"error": "connections_unavailable"})
        if method.upper() == "DELETE":
            code, body = connections.remove(param)
            if code == 200:
                _save_connections(connections, connections_file)
            return Response(code, body)
        payload = {}
        if raw_body.strip():
            try:
                payload = json.loads(raw_body)
            except json.JSONDecodeError as exc:
                return _bad_request("Тело запроса не JSON: " + exc.msg)
        code, body = connections.update_key(
            param, str(payload.get("key") or ""),
            None if "model" not in payload else str(payload.get("model") or ""),
            None if "base_url" not in payload else str(payload.get("base_url") or ""),
            None if "title" not in payload else str(payload.get("title") or ""))
        if code == 200:
            _save_connections(connections, connections_file)
        return Response(code, body)

    if template == "/api/v1/connections/{conn_id}/activate":
        if connections is None:
            return Response(503, {"error": "connections_unavailable"})
        payload = {}
        if raw_body.strip():
            try:
                payload = json.loads(raw_body)
            except json.JSONDecodeError as exc:
                return _bad_request("Тело запроса не JSON: " + exc.msg)
        kind = str((payload or {}).get("kind") or "").strip().lower()
        if kind not in ("llm", "asr"):
            return _bad_request("Укажите kind: llm (разбор) или asr (распознавание).")
        code, body = connections.activate(kind, param)
        if code == 200:
            _save_connections(connections, connections_file)
        return Response(code, body)

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
        elif settings_file is not None:
            # Сохраняем СРАЗУ: ключ, введённый в настройках, принадлежит приложению, и первый же
            # перезапуск контейнера не должен его стереть. На диск уходит, наружу — нет.
            settings_file.save(settings.snapshot())
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
            # Повтор той же загрузки — не ошибка человека, а обычный сбой сети. Отдаём идентификатор
            # уже лежащей записи, иначе он не знает, куда идти за расшифровкой.
            return Response(409, {"error": "already_exists",
                                  "session_id": body["session_id"],
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

    if method.upper() == "DELETE" and template == "/api/v1/sessions/{session_id}":
        # Удаляем запись и разбор вместе: оставить разбор от удалённого звука — значит хранить
        # разговор, который человек попросил убрать.
        removed_audio = store.remove(param) if store is not None else False
        removed_digest = digests.remove(param) if digests is not None else False
        if not removed_audio and not removed_digest:
            return Response(404, {"error": "session_not_found", "session_id": param,
                                  "message": "Такого разговора уже нет — возможно, его удалили раньше."})
        return Response(200, {"session_id": param, "deleted": True,
                              "audio": removed_audio, "digest": removed_digest,
                              "message": "Разговор удалён: запись и разбор убраны с сервера."})

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
