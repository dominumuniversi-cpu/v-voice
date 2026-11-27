"""Настройки моделей, которые можно менять из браузера без перезапуска сервера.

Зачем отдельный объект, а не переменные окружения: человек ставит ключ на стенде и ждёт
ответа сразу. Перезапуск контейнера на каждую попытку — это лотерея, где ошибку в ключе
видно только после простоя.

Ключи живут ТОЛЬКО в памяти процесса: не пишутся на диск, не попадают в журнал и не
возвращаются в ответе. Перезапуск сервера их сотрёт — это осознанный выбор: подробность,
которая утекает, хуже неудобства, которое исправляется одной формой.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any

from .provider_factory import IMPLEMENTED_ASR, IMPLEMENTED_LLM


@dataclass
class RuntimeSettings:
    """Что сменили из браузера. Пустое поле значит «как в окружении»."""

    asr_provider: str = ''
    asr_key: str = ''
    llm_provider: str = ''
    llm_key: str = ''

    def __post_init__(self) -> None:
        # Один слот записи: две вкладки не должны затирать настройки друг друга посреди записи ключа.
        self._lock = threading.Lock()

    def asr(self) -> tuple[str, str]:
        with self._lock:
            return self.asr_provider, self.asr_key

    def llm(self) -> tuple[str, str]:
        with self._lock:
            return self.llm_provider, self.llm_key

    def update(self, raw: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Применяет присланное. Ошибки объясняются, а не просто отклоняются."""
        provider_asr = str(raw.get('asr_provider') or '').strip().lower()
        provider_llm = str(raw.get('llm_provider') or '').strip().lower()
        key_asr = str(raw.get('asr_key') or '').strip()
        key_llm = str(raw.get('llm_key') or '').strip()

        if provider_asr and provider_asr not in IMPLEMENTED_ASR:
            return 400, {'error': 'provider_not_implemented',
                         'message': 'Распознавание «' + provider_asr + '» ещё не подключено. Доступно: '
                                    + ', '.join(IMPLEMENTED_ASR) + '.'}
        if provider_llm and provider_llm not in IMPLEMENTED_LLM:
            return 400, {'error': 'provider_not_implemented',
                         'message': 'Понимание «' + provider_llm + '» ещё не подключено. Доступно: '
                                    + ', '.join(IMPLEMENTED_LLM) + '.'}
        # Провайдер без ключа — это не «готово», а «настроено наполовину»: говорим сразу,
        # иначе человек сохранит и будет ждать тишины.
        if provider_asr and provider_asr not in ('fake',) and not key_asr:
            return 400, {'error': 'key_required',
                         'message': 'Для распознавания «' + provider_asr + '» нужен ключ.'}
        if provider_llm and provider_llm not in ('fake',) and not key_llm:
            return 400, {'error': 'key_required',
                         'message': 'Для понимания «' + provider_llm + '» нужен ключ.'}

        with self._lock:
            if provider_asr:
                self.asr_provider, self.asr_key = provider_asr, key_asr
            elif key_asr:
                self.asr_key = key_asr
            if provider_llm:
                self.llm_provider, self.llm_key = provider_llm, key_llm
            elif key_llm:
                self.llm_key = key_llm
        return 200, {'settings': self.view()}

    def view(self) -> dict[str, Any]:
        """Что показать человеку. Ключ — никогда, только признак «задан»."""
        with self._lock:
            return {
                'asr': {'provider': self.asr_provider, 'key_set': bool(self.asr_key),
                        'available': list(IMPLEMENTED_ASR)},
                'llm': {'provider': self.llm_provider, 'key_set': bool(self.llm_key),
                        'available': list(IMPLEMENTED_LLM)},
            }
