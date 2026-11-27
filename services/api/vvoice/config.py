"""Настройка сервера из окружения.

Почему так: человек должен настраивать ОДИН файл на сервере, а не вводить ключи на каждом
телефоне. Здесь — единственное место, где имена переменных превращаются в настройки.

Правила:
  1. Отсутствие ключа — не падение. Сервер поднимается и честно говорит, что разбор недоступен:
     диагностика без сервера невозможна, а красный старт заставляет людей отключать проверки.
  2. Ключи никогда не попадают в ответы и логи: наружу уходит только «настроено/нет» и отпечаток.
  3. Имена переменных совпадают с документацией (AI-PROVIDERS.md), иначе документация врёт.
"""

from __future__ import annotations

from dataclasses import field

import hashlib
import os
from pathlib import Path
from dataclasses import dataclass
from typing import Mapping

# fake — заглушка для сквозных проверок. Допустима только по явному имени и никогда по умолчанию:
# так выдуманный текст не может случайно оказаться на месте настоящего.
# Только то, что действительно собрано в provider_factory. Остальные (gigaam, deepgram, assemblyai) —
# кандидаты на будущее; держать их здесь значит обещать подключение, которого нет.
# whisper — своя модель на нашем сервере (services/asr), без ключей и оплаты за минуты.
ASR_PROVIDERS = ('speechmatics', 'whisper', 'deepgram', 'assemblyai', 'openai_asr', 'gladia', 'fake')
LLM_PROVIDERS = ('deepseek', 'anthropic', 'ollama', 'fake')


@dataclass(frozen=True)
class Settings:
    """Настройки сервера. Секреты хранятся только здесь и наружу не выходят."""

    asr_provider: str
    llm_provider: str
    asr_key: str
    llm_key: str
    export_targets: dict[str, str]
    # Токен приёмника задач (задачник, CRM). Пусто — отправляем без заголовка: свой приёмник может
    # быть открыт внутри сети; чужой откажет и скажет об этом, а не потеряет задачу молча.
    export_token: str = ''
    # Свой токен на каждую цель: Helper принимает Bearer Прохора, Jira — свой, Bitrix24 — свой.
    # Один общий токен позволял подключить реально только один приёмник.
    export_tokens: dict[str, str] = field(default_factory=dict)
    # Тариф распознавания в рублях за час аудио. 0 — тариф не задан, и тогда стоимость не выдумываем.
    asr_price_per_hour: float = 0.0
    # Предел расходов на одну встречу, рубли. 0 — предел не задан, предупреждать не о чем.
    budget_per_meeting: float = 0.0
    # Какую модель зовём и куда. Пусто — модель провайдера по умолчанию и его же адрес.
    llm_model: str = ''
    llm_base_url: str = ''
    asr_model: str = ''
    # Свой адрес сервиса распознавания: у облаков он свой у каждого, у своей модели — voice-asr.
    asr_base_url: str = ''

    def token_for(self, target: str) -> str:
        """Токен именно для этой цели, иначе общий."""
        return self.export_tokens.get(target) or self.export_token
    # Отсечение шума и тишины. Человек может выключить, но по умолчанию — включено:
    # в записанном разговоре шум мешает модели сильнее, чем редкая потерянная пауза.
    noise_gate: bool = True
    # Список разрешённых токенов устройств через запятую. Пусто — сервер никого не проверяет
    # (режим разработки); на боевом сервере это должно быть заполнено, иначе разговор
    # может прочитать любой, кто знает адрес.
    device_tokens: tuple[str, ...] = ()

    @property
    def asr_ready(self) -> bool:
        """Готов ли разбор речи: есть провайдер и ключ к нему."""
        return bool(self.asr_provider and self.asr_key)

    @property
    def llm_ready(self) -> bool:
        """Готов ли осмысленный разбор: без модели задачи не появятся.

        Заглушка ключа не требует: она не ходит в сеть, и требовать с неё ключ — значит
        показывать «не готово» там, где разбор на самом деле работает.
        """
        if (self.llm_provider or '').strip().lower() == 'fake':
            return True
        return bool(self.llm_provider and self.llm_key)

    def public_health(self) -> dict[str, object]:
        """Что показать в /health. Ключей здесь нет и быть не может."""
        # Готово — значит «этим можно пользоваться», а не «человек вписал ключ». Иначе экран говорит
        # «готово» о провайдере, которого ещё нет в коде, и человек ищет ошибку у себя.
        from .provider_factory import IMPLEMENTED_ASR, IMPLEMENTED_LLM
        asr_usable = self.asr_ready and self.asr_provider in IMPLEMENTED_ASR
        llm_usable = self.llm_ready and self.llm_provider in IMPLEMENTED_LLM
        # Есть ли чем открыть соединение с сервисом распознавания. Настройки могут быть полными,
        # а библиотеки — не быть; тогда это видно здесь, а не по пустой расшифровке.
        from .provider_factory import _ws_available
        return {
            # ready — «настроено и реализовано», но НЕ «ключ рабочий»: проверку ключа
            # делает только живой запрос. Раньше ready читалось как «всё хорошо», и это вводило в заблуждение.
            'asr': {'provider': self.asr_provider, 'ready': asr_usable,
                    'key_checked': False,
                    'ws_client': _ws_available(),
                    'configured': self.asr_ready, 'implemented': self.asr_provider in IMPLEMENTED_ASR,
                    'key_fingerprint': _fingerprint(self.asr_key)},
            'llm': {'provider': self.llm_provider, 'ready': llm_usable,
                    'configured': self.llm_ready, 'implemented': self.llm_provider in IMPLEMENTED_LLM,
                    'key_fingerprint': _fingerprint(self.llm_key)},
            'export': sorted(self.export_targets),
            'can_transcribe': asr_usable,
            'can_understand': llm_usable,
        }


def _price(raw: object) -> float:
    """Тариф из окружения. Мусор — это 0 (тариф не задан), а не падение старта."""
    try:
        value = float(str(raw or '0').replace(',', '.').strip() or 0)
    except (TypeError, ValueError):
        return 0.0
    return value if value > 0 else 0.0


def _fingerprint(key: str) -> str:
    """Короткий отпечаток ключа, чтобы человек мог сверить, тот ли ключ подхвачен.

    Сам ключ не возвращается никогда: отпечаток не позволяет восстановить значение,
    но отличает «ключ от другого проекта» от «ключ тот самый».
    """
    if not key:
        return ''
    return hashlib.sha256(key.encode('utf-8')).hexdigest()[:8]


def load_env_file(path: str | Path) -> dict[str, str]:
    """Читает .env и возвращает пары ключ-значение.

    Зачем свой разбор вместо библиотеки: зависимостей у сервиса нет намеренно. Формат простой —
    строки ИМЯ=значение, решётка начинает комментарий, кавычки по краям снимаются.
    Если файла нет — пустой словарь: отсутствие .env не должно валить запуск.
    """
    file = Path(path)
    if not file.exists():
        return {}
    parsed: dict[str, str] = {}
    for raw in file.read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        if '=' not in line:
            continue
        name, _, value = line.partition('=')
        name = name.strip()
        value = value.strip().strip('"').strip("'")
        if name:
            parsed[name] = value
    return parsed


def load(env: Mapping[str, str] | None = None) -> Settings:
    """Собирает настройки из окружения. Неизвестный провайдер — пустая строка, а не догадка."""
    source: Mapping[str, str]
    if env is None:
        from_file = load_env_file(os.environ.get('VV_ENV_FILE') or Path(__file__).resolve().parents[1] / '.env')
        # Окружение важнее файла: так переменную можно переопределить на конкретной машине,
        # не трогая общий файл.
        source = {**from_file, **os.environ}
    else:
        source = env

    def picked(name: str, allowed: tuple[str, ...]) -> str:
        value = (source.get(name) or '').strip().lower()
        return value if value in allowed else ''

    targets: dict[str, str] = {}
    for name, key in (('helper', 'VV_EXPORT_HELPER_URL'), ('jira', 'VV_EXPORT_JIRA_URL'),
                      ('bitrix24', 'VV_EXPORT_BITRIX_URL'), ('webhook', 'VV_EXPORT_WEBHOOK_URL')):
        value = (source.get(key) or '').strip()
        if value:
            targets[name] = value

    # Токены устройств: через запятую. Пробелы и пустые куски отбрасываем, чтобы
    # «токен1, токен2» не превращался в токен с пробелом внутри и не переставал подходить.
    device_tokens = tuple(t.strip() for t in (source.get('VV_DEVICE_TOKENS') or '').split(',') if t.strip())

    return Settings(
        asr_provider=picked('VV_ASR_PROVIDER', ASR_PROVIDERS),
        llm_provider=picked('VV_LLM_PROVIDER', LLM_PROVIDERS),
        asr_key=(source.get('VV_ASR_KEY') or '').strip(),
        llm_key=(source.get('VV_LLM_KEY') or '').strip(),
        llm_model=(source.get('VV_LLM_MODEL') or '').strip(),
        llm_base_url=(source.get('VV_LLM_BASE_URL') or '').strip(),
        asr_model=(source.get('VV_ASR_MODEL') or '').strip(),
        asr_base_url=(source.get('VV_ASR_BASE_URL') or '').strip(),
        # Тариф — настройка, а не константа: цены меняются, и вписанная в код цифра однажды станет ложью.
        asr_price_per_hour=_price(source.get('VV_ASR_PRICE_PER_HOUR')),
        budget_per_meeting=_price(source.get('VV_BUDGET_PER_MEETING')),
        export_targets=targets,
        export_token=(source.get('VV_EXPORT_TOKEN') or '').strip(),
        # Свой токен на цель: VV_EXPORT_HELPER_TOKEN, VV_EXPORT_JIRA_TOKEN, VV_EXPORT_BITRIX_TOKEN.
        # Имена целей — те же, что у адресов (VV_EXPORT_<ЦЕЛЬ>_URL), чтобы искать один раз и не гадать.
        export_tokens={t: (source.get('VV_EXPORT_' + t.upper() + '_TOKEN') or '').strip()
                       for t in targets if (source.get('VV_EXPORT_' + t.upper() + '_TOKEN') or '').strip()},
        device_tokens=device_tokens,
        noise_gate=(source.get('VV_NOISE_GATE') or 'on').strip().lower() not in ('off', '0', 'false', 'нет'),
    )
