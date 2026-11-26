"""Исполнение запроса к модели понимания. Единственное место, где разговор уходит в LLM.

Почему отдельный модуль: `llm.build_request` собирает запрос (и покрыт тестами без сети), но до
появления этого файла никто его не отправлял — `IMPLEMENTED_LLM` был пуст, и «осмысленный разбор»
оставался обещанием. Здесь ровно один POST, таймаут и понятная причина отказа.

Правила:
  - ключ уходит заголовком, а не в адресе: адреса попадают в журналы;
  - тело ответа модели человеку не показываем, но причину отказа — обязательно;
  - исключение сюда не пробрасывается наружу: вызывающий получает (ok, текст или причина).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from .llm import LlmRequest, build_request

TIMEOUT_S = 60


def send_llm(request: LlmRequest, *, timeout_s: int = TIMEOUT_S) -> tuple[bool, str]:
    """Отправляет запрос модели и возвращает (получилось, ответ или причина отказа)."""
    body = json.dumps(request.body, ensure_ascii=False).encode("utf-8")
    headers = dict(request.headers or {})
    # HTTP-заголовки — только latin-1: русский ключ иначе падает невнятным UnicodeEncodeError.
    for name, value in list(headers.items()):
        try:
            str(value).encode("latin-1")
        except UnicodeEncodeError:
            return False, "заголовок " + name + " содержит недопустимые символы (нужна латиница)"
    req = urllib.request.Request(request.url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as response:
            text = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", "replace")[:300]
        except Exception:
            pass
        return False, "модель ответила " + str(exc.code) + (": " + detail if detail else "")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return False, "не удалось связаться с моделью: " + str(exc)
    return True, text


def answer_text(raw: str) -> str:
    """Достаёт текст ответа из разных форматов провайдеров.

    Anthropic отвечает content-списком, OpenAI-совместимые — choices. Понимать оба — дешевле,
    чем требовать от человека одного провайдера.
    """
    try:
        data: Any = json.loads(raw)
    except (ValueError, TypeError):
        return ""
    if not isinstance(data, dict):
        return ""
    content = data.get("content")
    if isinstance(content, list):
        return " ".join(str(part.get("text", "")) for part in content if isinstance(part, dict)).strip()
    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message")
            if isinstance(message, dict):
                return str(message.get("content", "")).strip()
    answer = data.get("answer") or data.get("response")
    return str(answer).strip() if answer else ""


def make_call_llm(provider: str, model: str, api_key: str):
    """Функция, которую ждёт разбор: (системная инструкция, вопрос) -> разобранный JSON.

    Разбор получает словарь, а не сырой текст: модель обязана ответить JSON, и разбирать его
    должен один модуль, а не каждый вызывающий по своему.
    """

    def call(system: str, user: str) -> dict:
        request = build_request(provider, model, system, user, api_key)
        ok, raw = send_llm(request)
        if not ok:
            raise RuntimeError(raw)
        text = answer_text(raw) or raw
        try:
            data = json.loads(text)
        except (ValueError, TypeError) as exc:
            # Модель ответила не JSON — это её ошибка, но человеку нужен понятный текст.
            raise RuntimeError("модель ответила не JSON: " + str(exc)) from exc
        return data if isinstance(data, dict) else {"items": data}

    return call
