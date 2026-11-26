"""Адаптер LLM-разбора: какие модели подключать и как (требование владельца «скажи модели и как»).

Четыре провайдера с разными протоколами, поэтому вся разница собрана здесь, а конвейер
(`digest.make_digest`) видит один вызов `call(system, user) -> dict`.

  - deepseek  — OpenAI-совместимый чат; ответ в `choices[0].message.content`, режим строгого JSON.
  - anthropic — Messages API; системный промпт отдельным полем `system`, ответ в `content[0].text`.
  - gigachat  — OAuth-токен из ключа, сообщения в `messages`, ответ в `choices[0].message.content`.
  - ollama    — локальная модель, `options.temperature` и поле `format: "json"`.

Почему это важно: неверно собранный запрос даёт «модель молчит» или «модель вернула прозу вместо JSON»,
и разбор падает в разгар встречи. Поэтому сборка/разбор — чистые функции с тестами, сеть — тонкая.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

SUPPORTED = ("deepseek", "anthropic", "gigachat", "ollama")

DEFAULT_MODELS = {
    "deepseek": "deepseek-chat",
    "anthropic": "claude-sonnet-4-5",
    "gigachat": "GigaChat-2-Max",
    "ollama": "qwen3:8b",
}

ENDPOINTS = {
    "deepseek": "https://api.deepseek.com/chat/completions",
    "anthropic": "https://api.anthropic.com/v1/messages",
    "gigachat": "https://gigachat.devices.sberbank.ru/api/v1/chat/completions",
    "ollama": "http://127.0.0.1:11434/api/chat",
}


@dataclass
class LlmRequest:
    url: str
    headers: dict[str, str]
    body: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {"url": self.url, "headers": self.headers, "body": self.body}


def build_request(provider: str, model: str, system: str, user: str, api_key: str) -> LlmRequest:
    """Собирает запрос под конкретного провайдера. Ошибка в имени — понятная, а не KeyError."""
    if provider not in SUPPORTED:
        raise ValueError("Неизвестный LLM-провайдер: " + provider + "; допустимо: " + ", ".join(SUPPORTED))
    model = model or DEFAULT_MODELS[provider]
    url = ENDPOINTS[provider]

    if provider in ("deepseek", "gigachat"):
        body = {
            "model": model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }
        headers = {"Content-Type": "application/json", "Authorization": "Bearer " + api_key}
        return LlmRequest(url, headers, body)

    if provider == "anthropic":
        body = {
            "model": model,
            "max_tokens": 4096,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }
        return LlmRequest(url, headers, body)

    # ollama: локальный сервер, ключа нет
    body = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.1},
    }
    return LlmRequest(url, {"Content-Type": "application/json"}, body)


def extract_text(provider: str, response: dict) -> str:
    """Достаёт текст ответа. Если провайдер вернул ошибку — понятная причина."""
    if provider not in SUPPORTED:
        raise ValueError("Неизвестный LLM-провайдер: " + provider)

    if "error" in response and response["error"]:
        err = response["error"]
        message = err.get("message") if isinstance(err, dict) else str(err)
        raise ConnectionError("LLM error (" + provider + "): " + str(message)[:200])

    if provider == "anthropic":
        blocks = response.get("content") or []
        parts = [b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text"]
        return "".join(parts)

    choices = response.get("choices") or []
    if choices:
        message = choices[0].get("message") or {}
        return str(message.get("content") or "")

    # ollama отвечает в поле message
    message = response.get("message") or {}
    return str(message.get("content") or "")


def parse_json_answer(text: str) -> dict:
    """Строгий разбор JSON-ответа модели.

    Модели иногда оборачивают JSON в тройные кавычки или добавляют пояснение.
    Порядок: чистый JSON -> вырезать первый {...} -> ошибка с понятным текстом.
    """
    stripped = (text or "").strip()
    if not stripped:
        raise ValueError("Модель вернула пустой ответ")
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        start, end = stripped.find("{"), stripped.rfind("}")
        if start == -1 or end <= start:
            raise ValueError("В ответе модели нет JSON-объекта: " + stripped[:120])
        data = json.loads(stripped[start:end + 1])
    if not isinstance(data, dict):
        raise ValueError("Ответ модели должен быть JSON-объектом, а пришёл " + type(data).__name__)
    return data


def make_caller(provider: str, model: str, api_key: str, send):
    """Готовая функция `call(system, user) -> dict` для конвейера разбора.

    `send(request) -> response dict` передаётся снаружи: тесты не ходят в сеть и не платят.
    """

    def call(system: str, user: str) -> dict:
        request = build_request(provider, model, system, user, api_key)
        response = send(request.as_dict())
        return parse_json_answer(extract_text(provider, response))

    return call
