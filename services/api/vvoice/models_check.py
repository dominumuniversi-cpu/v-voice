"""Проверка моделей на живом вызове, а не на наличии строки с ключом.

Владелец сказал точно: «ключ — ещё не подключение». Согласен. Ключ может быть просрочен,
адрес — недоступен, модель — переименована. Узнать это в середине встречи — худший момент,
поэтому здесь отдельная короткая проверка по кнопке.

Правила: ответ модели наружу не отдаём (только диагноз), запрос минимальный,
исключение не пробрасываем — человек получает причину словами.
"""

from __future__ import annotations

from typing import Any

# Просим ровно один ключ JSON: проверяем и связь, и способность модели держать формат.
_PROBE_SYSTEM = 'Ты проверка связи. Ответь только JSON: {"ok": true}'
_PROBE_USER = 'Ответь JSON.'


def _probe_llm(runtime: Any) -> dict[str, Any]:
    """Живой вызов выбранной модели. Возвращает диагноз, а не текст ответа."""
    from .providers.llm_send import make_call_llm

    chosen = runtime.llm()
    provider = chosen['provider']
    if not provider:
        return {'ok': False, 'provider': '', 'message': 'Модель понимания не выбрана.'}
    if provider == 'fake':
        return {'ok': False, 'provider': 'fake',
                'message': 'Это демо-заглушка: связи с моделью нет по определению.'}
    if not chosen['key'] and provider != 'ollama':
        return {'ok': False, 'provider': provider, 'message': 'Нет ключа — проверять нечего.'}
    if provider == 'ollama' and not chosen['base_url']:
        return {'ok': False, 'provider': provider,
                'message': 'Не указан адрес Ollama. 127.0.0.1 внутри контейнера — это сам контейнер.'}
    try:
        call = make_call_llm(provider, chosen['model'], chosen['key'], chosen['base_url'])
        call(_PROBE_SYSTEM, _PROBE_USER)
        return {'ok': True, 'provider': provider, 'model': chosen['model'] or '(по умолчанию)',
                'message': 'Модель ответила JSON. Можно разбирать разговоры.'}
    except Exception as exc:
        return {'ok': False, 'provider': provider, 'message': str(exc)[:300]}


# Список моделей, которые провайдер реально предлагает. Человек не должен вписывать имя по памяти:
# ошибка в имени выглядит как «модель не ответила», и это дорого стоит во время встречи.
_KNOWN = {
    'deepseek': ['deepseek-chat', 'deepseek-reasoner'],
    'anthropic': ['claude-sonnet-4-5', 'claude-haiku-4-5', 'claude-opus-4-1'],
    'ollama': [],
    'fake': [],
}


def list_models(runtime: Any) -> dict[str, Any]:
    """Что можно выбрать. Для Ollama — настоящий запрос к серверу: там модели живут у человека."""
    chosen = runtime.llm()
    provider = chosen['provider']
    if provider == 'ollama':
        base = chosen['base_url'].rstrip('/').removesuffix('/api/chat')
        if not base:
            return {'provider': 'ollama', 'models': [], 'source': 'none',
                    'message': 'Укажите адрес Ollama — список моделей берётся с вашего сервера.'}
        try:
            import json as _json
            import urllib.request
            with urllib.request.urlopen(base + '/api/tags', timeout=6) as resp:
                data = _json.loads(resp.read().decode('utf-8'))
            names = [m.get('name', '') for m in data.get('models', []) if m.get('name')]
            return {'provider': 'ollama', 'models': names, 'source': 'live',
                    'message': '' if names else 'Сервер ответил, но моделей в нём нет: скачайте модель на сервере.'}
        except Exception as exc:
            return {'provider': 'ollama', 'models': [], 'source': 'error',
                    'message': 'Не удалось спросить Ollama: ' + str(exc)[:200]}
    models = _KNOWN.get(provider, [])
    return {'provider': provider, 'models': models,
            'source': 'catalog' if models else 'none',
            'message': '' if models else 'Для этой связки список моделей не ведётся — впишите имя вручную.'}


def check_models(runtime: Any) -> dict[str, Any]:
    """Живой диагноз: 200 с ok=true только если модель действительно ответила."""
    return _probe_llm(runtime)
