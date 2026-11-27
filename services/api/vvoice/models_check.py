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

def _live(runtime: Any, kind: str) -> Any:
    """Связка из списка подключений, если она есть: она и работает. Иначе — файл настроек.

    Так проверка говорит правду о том, чем сервер разбирает прямо сейчас, а не о том, что
    когда-то лежало в настройках.
    """
    conn = getattr(runtime, "active_for", None)
    conn = conn(kind) if callable(conn) else None
    if conn is None:
        return runtime
    provider = getattr(conn, "protocol", "") or ""
    fields = {"llm": dict(llm_provider=provider, llm_key=conn.key or "",
                         llm_model=conn.model or "", llm_base_url=conn.base_url or ""),
              "asr": dict(asr_provider=provider, asr_key=conn.key or "",
                         asr_model=conn.model or "")}[kind]
    return _Overridden(runtime, fields)


class _Overridden:
    """Подменённый вид: чтение связки идёт из списка подключений, остальное — из настроек."""

    def __init__(self, base: Any, fields: dict) -> None:
        self._base = base
        self._fields = fields

    def asr(self) -> dict:
        data = dict(self._base.asr())
        if "asr_provider" in self._fields:
            data["provider"] = self._fields["asr_provider"]
            data["key"] = self._fields["asr_key"]
            data["model"] = self._fields["asr_model"]
        return data

    def llm(self) -> dict:
        data = dict(self._base.llm())
        if "llm_provider" in self._fields:
            data["provider"] = self._fields["llm_provider"]
            data["key"] = self._fields["llm_key"]
            data["model"] = self._fields["llm_model"]
            data["base_url"] = self._fields["llm_base_url"]
        return data

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
                    'message': 'Укажите адрес Ollama — список моделей берётся с вашего сервера. '
                               'Скачивания моделей здесь нет: это делается на вашем сервере командой '
                               'ollama pull <модель>, после чего модель появится в списке.'}
        try:
            import json as _json
            import urllib.request
            with urllib.request.urlopen(base + '/api/tags', timeout=6) as resp:
                data = _json.loads(resp.read().decode('utf-8'))
            names = [m.get('name', '') for m in data.get('models', []) if m.get('name')]
            return {'provider': 'ollama', 'models': names, 'source': 'live',
                    'message': '' if names else ('Сервер ответил, но моделей в нём нет: скачайте модель на сервере '
                                                 'командой ollama pull <модель> — здесь её не скачать.')}
        except Exception as exc:
            return {'provider': 'ollama', 'models': [], 'source': 'error',
                    'message': 'Не удалось спросить Ollama: ' + str(exc)[:200]}
    models = _KNOWN.get(provider, [])
    return {'provider': provider, 'models': models,
            'source': 'catalog' if models else 'none',
            'message': '' if models else 'Для этой связки список моделей не ведётся — впишите имя вручную.'}


def _probe_asr(runtime: Any) -> dict[str, Any]:
    """Распознавание проверяем своим живым запросом: у него свой ключ, своя служба и свой отказ."""
    from .providers.speechmatics import check_key
    from .providers.ws_connect import connect_websocket

    chosen = runtime.asr()
    provider = chosen["provider"]
    if not provider or provider == "fake":
        return {"ok": False, "provider": provider or "",
                "message": "распознавание не выбрано: разговор не во что превращать в текст."}
    if provider == "whisper":
        return {"ok": True, "provider": provider,
                "message": "своя модель работает на этом же сервере, ключ ей не нужен."}
    if not chosen["key"]:
        return {"ok": False, "provider": provider, "message": "ключ не вписан."}
    if provider == "speechmatics":
        ok, why = check_key(connect_websocket, chosen["key"])
        return {"ok": ok, "provider": provider, "message": why + "."}
    return {"ok": False, "provider": provider,
            "message": "проверить заранее можно только у Speechmatics: у остальных облачных сервисов "
                       "нет пробного вызова без звука. Короткая запись покажет, работает ли ключ."}

def check_models(runtime: Any) -> dict[str, Any]:
    """Живой диагноз: 200 с ok=true только если модель действительно ответила.

    Понимание и распознавание проверяются по отдельности: разные ключи, разные службы, и «разбор
    не идёт» у половины людей — это именно отказ распознавания.
    """
    guess = _probe_llm(_live(runtime, "llm"))
    heard = _probe_asr(_live(runtime, "asr"))
    parts = [str(guess.get("message") or "").strip()]
    if heard.get("message"):
        parts.append("Распознавание: " + str(heard["message"]).strip())
    return {"ok": bool(guess.get("ok")), "provider": guess.get("provider", ""),
            "model": guess.get("model", ""), "asr": heard,
            "message": " ".join(p for p in parts if p)}
