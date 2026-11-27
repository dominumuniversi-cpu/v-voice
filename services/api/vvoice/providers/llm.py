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
from urllib.parse import urlsplit
from dataclasses import dataclass
from typing import Any

SUPPORTED = ("deepseek", "anthropic", "gigachat", "ollama", "openai", "zai", "mistral")

DEFAULT_MODELS = {
    "deepseek": "deepseek-chat",
    "anthropic": "claude-sonnet-4-5",
    "gigachat": "GigaChat-2-Max",
    "ollama": "qwen3:8b",
    # z.ai и Mistral — обычные OpenAI-совместимые чаты, различаются адресом и именем модели.
    "openai": "gpt-4o-mini",
    "zai": "glm-4.6",
    "mistral": "mistral-small-latest",
}

ENDPOINTS = {
    "deepseek": "https://api.deepseek.com/chat/completions",
    "anthropic": "https://api.anthropic.com/v1/messages",
    "gigachat": "https://gigachat.devices.sberbank.ru/api/v1/chat/completions",
    "ollama": "http://127.0.0.1:11434/api/chat",
    "openai": "https://api.openai.com/v1/chat/completions",
    "zai": "https://api.z.ai/api/paas/v4/chat/completions",
    "mistral": "https://api.mistral.ai/v1/chat/completions",
}


@dataclass
class LlmRequest:
    url: str
    headers: dict[str, str]
    body: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {"url": self.url, "headers": self.headers, "body": self.body}


def _endpoint_for(provider: str, base_url: str) -> str:
    """Адрес запроса: базовый адрес из настроек + путь ручки провайдера.

    Пустой адрес — у провайдера по умолчанию. Базовый адрес («http://1.2.3.4:11434» или
    «http://10.0.0.5:8000/v1») дополняем путём ручки. Полный адрес ручки, который уже на неё
    кончается, оставляем как есть: иначе получалось «/api/chat/api/chat» и «/v1/v1/chat».
    """
    default = ENDPOINTS[provider]
    if not base_url:
        return default
    url = base_url
    if '://' not in url:
        url = 'http://' + url
    url = url.rstrip('/')
    base_path = urlsplit(url).path or ''
    path = urlsplit(default).path
    # Человек мог дать адрес «.../v1», и полный путь уже содержит «/v1»: тогда лишний не добавляем.
    if path.startswith(base_path) and base_path:
        return url + path[len(base_path):]
    if url.endswith(path):
        return url
    return url + path


def build_request(provider: str, model: str, system: str, user: str, api_key: str, base_url: str = '') -> LlmRequest:
    """Собирает запрос под конкретного провайдера. Ошибка в имени — понятная, а не KeyError."""
    if provider not in SUPPORTED:
        raise ValueError("Неизвестный LLM-провайдер: " + provider + "; допустимо: " + ", ".join(SUPPORTED))
    model = model or DEFAULT_MODELS[provider]
    # Адрес можно переопределить: «своего сервера» одной модели недостаточно — у локальной сборки
    # свой порт, у прокси своя точка входа. Пустое значение значит «как у провайдера по умолчанию».
    # «Адрес сервера» из настроек — это хост («http://192.168.1.5:11434»), а не готовый URL запроса.
    # Раньше он подставлялся как есть, и Ollama получал POST на корень вместо /api/chat.
    url = _endpoint_for(provider, (base_url or '').strip())

    if provider in ("deepseek", "gigachat", "zai", "mistral"):
        body = {
            "model": model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }
        headers = {"Content-Type": "application/json", "Authorization": "Bearer " + api_key}
        return LlmRequest(url, headers, body)

    if provider == "openai":
        # Свой шлюз: адрес известен только из настроек, поэтому без него — понятная ошибка,
        # а не молчаливый запрос на api.openai.com без ключа и без модели.
        body = {
            "model": model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0.1,
        }
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = "Bearer " + api_key
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

    def call(system: str, user: str, base_url: str = '') -> dict:
        request = build_request(provider, model, system, user, api_key, base_url)
        response = send(request.as_dict())
        return parse_json_answer(extract_text(provider, response))

    return call
