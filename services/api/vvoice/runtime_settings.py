"""Настройки моделей, которые человек меняет из браузера, без перезапуска сервера.

Три принципа, из-за которых этот модуль выглядит именно так:

1. **Ключ — не подключение.** Ключ без адреса, модели и библиотеки ничего не подключает.
   Поэтому здесь хранится вся пара «куда и как», а не одна строка с секретом.
2. **Ключ не выходит наружу.** Он живёт в памяти процесса, не пишется на диск, не возвращается
   в ответе — наружу идёт только отпечаток (4 последних символа), чтобы человек узнал свой ключ.
3. **Настройка без пресета — это викторина.** Человек должен выбрать «DeepSeek» или «бесплатный
   локальный Ollama» из готового списка, а не искать в интернете, какой у провайдера адрес.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

from .provider_factory import IMPLEMENTED_ASR, IMPLEMENTED_LLM
from .providers.llm import DEFAULT_MODELS, ENDPOINTS


@dataclass(frozen=True)
class Preset:
    """Готовая связка «провайдер + адрес + модель», которую человек узнаёт по названию."""

    id: str
    kind: str
    provider: str
    title: str
    url: str
    model: str
    cost: str
    note: str


# Пресеты LLM. Бесплатные отличаем явно: владелец просил и их, а «бесплатно» без оговорки —
# это реклама, поэтому в note пишем цену честно.
LLM_PRESETS: tuple[Preset, ...] = (
    Preset('deepseek-chat', 'llm', 'deepseek', 'DeepSeek (дешёвый, по ключу)',
           ENDPOINTS['deepseek'], DEFAULT_MODELS['deepseek'], 'платно, копейки за встречу',
           'Ключ — на platform.deepseek.com. Хорошо разбирает русскую речь в задачи.'),
    Preset('anthropic-sonnet', 'llm', 'anthropic', 'Claude Sonnet (лучше всех держит формат)',
           ENDPOINTS['anthropic'], DEFAULT_MODELS['anthropic'], 'платно',
           'Ключ — на console.anthropic.com. Аккуратно отдаёт JSON, реже врёт структурой.'),
    Preset('ollama-local', 'llm', 'ollama', 'Ollama на своём сервере (бесплатно)',
           ENDPOINTS['ollama'], DEFAULT_MODELS['ollama'], 'бесплатно, работает на вашем железе',
           'Нужен запущенный ollama и скачанная модель. Адрес — тот, где ollama слушает; '
           'из контейнера 127.0.0.1 значит «внутри контейнера», поэтому адрес обязателен.'),
    Preset('fake-demo', 'llm', 'fake', 'Демо-заглушка (без сети)',
           '', '', 'бесплатно', 'Показывает весь путь, но текст выдуман. Для проверки экранов.'),
)

# Пресеты ASR. Пока в коде есть только Speechmatics и заглушка — и это записано честно.
ASR_PRESETS: tuple[Preset, ...] = (
    Preset('speechmatics', 'asr', 'speechmatics', 'Speechmatics (русский, по ключу)',
           '', '', 'платно, есть пробный период',
           'Ключ — в личном кабинете portal.speechmatics.com. Понимает русский потоково.'),
    Preset('fake-demo', 'asr', 'fake', 'Демо-заглушка (без сети)',
           '', '', 'бесплатно', 'Расшифровка выдумана, но весь путь проходит целиком.'),
)


def presets() -> dict[str, list[dict[str, str]]]:
    """Что показать на форме. Наружу — только безопасные поля, без ключей."""
    return {
        'llm': [p.__dict__ for p in LLM_PRESETS],
        'asr': [p.__dict__ for p in ASR_PRESETS],
    }


def _fingerprint(key: str) -> str:
    """Хвост ключа для опознания. Полный ключ не отдаём никогда, даже владельцу страницы."""
    key = (key or '').strip()
    if len(key) < 6:
        return ''
    return '…' + key[-4:]


@dataclass
class RuntimeSettings:
    """Что человек выбрал на странице. Пустое поле значит «как в окружении»."""

    asr_provider: str = ''
    asr_key: str = ''
    asr_model: str = ''
    llm_provider: str = ''
    llm_key: str = ''
    llm_model: str = ''
    llm_base_url: str = ''
    _lock: Any = field(default_factory=threading.Lock, repr=False)

    def asr(self) -> dict[str, str]:
        with self._lock:
            return {'provider': self.asr_provider, 'key': self.asr_key, 'model': self.asr_model}

    def llm(self) -> dict[str, str]:
        with self._lock:
            return {'provider': self.llm_provider, 'key': self.llm_key,
                    'model': self.llm_model, 'base_url': self.llm_base_url}

    def update(self, raw: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Применяет присланное. Всё, что нельзя использовать, отклоняется с объяснением."""
        provider_asr = str(raw.get('asr_provider') or '').strip().lower()
        provider_llm = str(raw.get('llm_provider') or '').strip().lower()
        if provider_asr and provider_asr not in IMPLEMENTED_ASR:
            return 400, {'error': 'provider_not_implemented',
                         'message': 'Распознавание «' + provider_asr + '» ещё не подключено. Доступно: '
                                    + ', '.join(IMPLEMENTED_ASR) + '.'}
        if provider_llm and provider_llm not in IMPLEMENTED_LLM:
            return 400, {'error': 'provider_not_implemented',
                         'message': 'Понимание «' + provider_llm + '» ещё не подключено. Доступно: '
                                    + ', '.join(IMPLEMENTED_LLM) + '.'}

        key_asr = str(raw.get('asr_key') or '').strip()
        key_llm = str(raw.get('llm_key') or '').strip()
        model_llm = str(raw.get('llm_model') or '').strip()
        model_asr = str(raw.get('asr_model') or '').strip()
        base_url = str(raw.get('llm_base_url') or '').strip()

        with self._lock:
            if provider_asr:
                self.asr_provider, self.asr_key = provider_asr, key_asr
            elif key_asr:
                self.asr_key = key_asr
            if model_asr:
                self.asr_model = model_asr
            if provider_llm:
                self.llm_provider, self.llm_key = provider_llm, key_llm
            elif key_llm:
                self.llm_key = key_llm
            if model_llm:
                self.llm_model = model_llm
            if base_url:
                self.llm_base_url = base_url

        # Проверка после сохранения: «сохранено» без «работает» — это обещание, а не факт.
        problems = self.problems()
        return (400 if problems else 200), {'settings': self.view(), 'problems': problems}

    def problems(self) -> list[str]:
        """Что мешает работать прямо сейчас. Пустой список — можно пользоваться."""
        out: list[str] = []
        asr, llm = self.asr(), self.llm()
        if not asr['provider']:
            out.append('Распознавание не выбрано: сервер берёт значение из окружения.')
        elif asr['provider'] != 'fake' and not asr['key']:
            out.append('Для распознавания «' + asr['provider'] + '» не введён ключ — расшифровки не будет.')
        if not llm['provider']:
            out.append('Понимание не выбрано: сервер берёт значение из окружения.')
        elif llm['provider'] == 'fake':
            pass
        elif not llm['key'] and llm['provider'] != 'ollama':
            out.append('Для понимания «' + llm['provider'] + '» не введён ключ.')
        if llm['provider'] == 'ollama' and not llm['base_url']:
            out.append('Ollama требует адрес сервера: 127.0.0.1 внутри контейнера — это сам контейнер.')
        return out

    def view(self, *, asr_env: str = '', llm_env: str = '') -> dict[str, Any]:
        """Что показать человеку. Ключи — только отпечатком."""
        with self._lock:
            return {
                'asr': {'provider': self.asr_provider or asr_env,
                        'from_env': not self.asr_provider and bool(asr_env),
                        'key_set': bool(self.asr_key), 'key_hint': _fingerprint(self.asr_key),
                        'model': self.asr_model, 'available': list(IMPLEMENTED_ASR)},
                'llm': {'provider': self.llm_provider or llm_env,
                        'from_env': not self.llm_provider and bool(llm_env),
                        'key_set': bool(self.llm_key), 'key_hint': _fingerprint(self.llm_key),
                        'model': self.llm_model, 'base_url': self.llm_base_url,
                        'available': list(IMPLEMENTED_LLM)},
            }
