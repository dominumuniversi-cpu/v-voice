"""Фабрики провайдеров из настроек.

Зачем отдельный модуль: настроить провайдера в .env — половина дела, вторая половина —
создать рабочий объект. Раньше эту работу делал «кто-то снаружи», и в собранном сервере
её не делал никто: разбор молча не работал, хотя ключи были заполнены.

Правило: если провайдер не подключён по-настоящему, честнее вернуть None и сказать об этом,
чем отдать заглушку и показать выдуманный текст.
"""

from __future__ import annotations

from typing import Any, Callable

from .config import Settings
from .providers.fake_asr import FakeAsr

# Провайдеры, для которых есть настоящая реализация в коде. Остальные — настройка есть,
# реализации нет: сюда добавлять только после того, как она написана и проверена.
IMPLEMENTED_ASR = ('fake', 'speechmatics')


def make_asr_factory(settings: Settings) -> Callable[[str], Any] | None:
    """Возвращает функцию «путь к записи или id живой сессии → провайдер речи» либо None.

    Оба места (разбор файла и живой поток) зовут фабрику ровно с одним аргументом — путь или id.

    None — это не ошибка старта, а правда о конфигурации: /health её уже показывает,
    а разбор ответит «недоступно» вместо падения.
    """
    provider = (settings.asr_provider or '').strip().lower()
    if provider == 'fake':
        # Заглушка разрешена только явной настройкой VV_ASR_PROVIDER=fake: она нужна для
        # сквозных прогонов и не должна включаться от пустой строки.
        return lambda path: FakeAsr()
    if provider == 'speechmatics':
        key = (settings.asr_key or '').strip()
        if not key:
            # Без ключа не выдаём «почти работающий» объект: человек заполнил половину настроек,
            # и /health честно скажет, что не хватает ключа.
            return None
        from .providers.speechmatics import SpeechmaticsAsr
        from .providers.ws_connect import connect_websocket

        def _make_speechmatics(path: str) -> Any:
            client = SpeechmaticsAsr(connect=connect_websocket, api_key=key)
            client.open()
            return client

        return _make_speechmatics
    return None


IMPLEMENTED_LLM: tuple[str, ...] = ('deepseek', 'anthropic', 'ollama')


def _ws_available() -> bool:
    """Есть ли библиотека для WebSocket. Проверка импортом: не падает, если нет."""
    try:
        import websocket  # type: ignore[import-not-found]  # noqa: F401
        return True
    except ImportError:
        return False


def describe(settings: Settings) -> dict[str, Any]:
    """Что из настроенного реально можно подключить. Для /health и для журнала старта."""
    provider = (settings.asr_provider or '').strip().lower()
    llm = (settings.llm_provider or '').strip().lower()
    return {
        'asr_configured': provider,
        'asr_implemented': provider in IMPLEMENTED_ASR,
        'asr_usable': make_asr_factory(settings) is not None,
        # Отдельно от «ключ есть»: человек заполнил настройки, но без библиотеки распознавание
        # не поднимется, и лучше узнать это в /health, чем по пустой расшифровке.
        'asr_ws_client': _ws_available(),
        'llm_configured': llm,
        'llm_implemented': llm in IMPLEMENTED_LLM,
        'llm_usable': llm in IMPLEMENTED_LLM,
    }
