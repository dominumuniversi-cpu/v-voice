"""Настройки: «всё должно настраиваться для человеческого использования».

Принципы:
  1. Каждое значение имеет безопасное значение по умолчанию — приложение стартует без единой переменной.
  2. Каждая переменная документирована по-русски: что это, допустимые значения, что будет, если не задать.
  3. Секреты не хранятся в репозитории: только имена переменных, а сами значения — в `secrets/.env` вне git.
  4. Проверка перед запуском: если выбран провайдер, а ключа нет — понятная ошибка, а не падение в середине встречи.

Модуль намеренно не импортирует FastAPI/pydantic: его можно прогнать простым `python -c` без зависимостей.


СОВЕТ ЧЕЛОВЕКУ: сервер читает переменные с префиксом VV_ (VV_ASR_PROVIDER, VV_LLM_PROVIDER,
VV_LLM_MODEL, VV_LLM_BASE_URL, VV_ASR_MODEL и т.д. — полный список в .env.example). Имена без
префикса из этого файла (ASR_PROVIDER, LLM_API_KEY…) остались от первых набросков: сервер их
НЕ читает. Здесь они полезны как описание смысла и проверки значений, но настраивать проект
по ним — ошибка.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, fields

# --- каталог описаний: имя переменной -> (описание, значение по умолчанию, допустимые значения) ---------------
DESCRIPTIONS: dict[str, tuple[str, str, str]] = {
    "ASR_PROVIDER": ("Сервис распознавания речи: fake (тесты), speechmatics, deepgram, assemblyai, gigaam", "fake", "fake|speechmatics|deepgram|assemblyai|gigaam"),
    "ASR_LANGUAGE": ("Язык распознавания; auto — определять по речи (дороже и медленнее)", "ru", "код ISO, например ru или auto"),
    "SPEECHMATICS_API_KEY": ("Ключ Speechmatics (realtime, 0.20-0.40 $/час)", "", "секрет, в репозиторий не писать"),
    "DEEPGRAM_API_KEY": ("Ключ Deepgram (Nova-3 streaming, 0.29-0.35 $/час)", "", "секрет"),
    "ASSEMBLYAI_API_KEY": ("Ключ AssemblyAI (предзапись, 0.21 $/час, без стрима)", "", "секрет"),
    "GIGAAM_MODEL": ("Веса GigaAM-v3: ai-sage/GigaAM-v3", "ai-sage/GigaAM-v3", "путь к локальной модели"),
    "GIGAAM_REVISION": ("Вариант GigaAM: ssl|ctc|rnnt|e2e_ctc|e2e_rnnt (e2e_rnnt — с пунктуацией)", "e2e_rnnt", "см. карточку модели"),
    "LLM_PROVIDER": ("Модель разбора: deepseek, anthropic, ollama (gigachat описан, но не подключён)", "deepseek", "deepseek|anthropic|ollama"),
    "LLM_MODEL": ("Конкретная модель (для deepseek — deepseek-chat, для ollama — qwen3:8b)", "deepseek-chat", "любая модель провайдера"),
    "LLM_API_KEY": ("Ключ LLM", "", "секрет"),
    "MEMBERS_ONLY": ("Слышим всех, но в задачи берём только реплики участников", "true", "true|false"),
    "REQUIRE_QUOTE": ("Требовать цитату для каждой задачи (нет цитаты — нет задачи)", "true", "true|false; выключать не рекомендуется"),
    "VAD_ADAPTIVE": ("Адаптивный шумовой пол VAD", "true", "true|false"),
    "DATA_RETENTION_DAYS": ("Сколько дней хранить аудио (0 — не удалять)", "90", "целое >= 0"),
    "API_PORT": ("Порт API на машине", "8900", "кроме 8000 (занят другими проектами)"),
}


@dataclass
class Settings:
    ASR_PROVIDER: str = "fake"
    ASR_LANGUAGE: str = "ru"
    SPEECHMATICS_API_KEY: str = ""
    DEEPGRAM_API_KEY: str = ""
    ASSEMBLYAI_API_KEY: str = ""
    GIGAAM_MODEL: str = "ai-sage/GigaAM-v3"
    GIGAAM_REVISION: str = "e2e_rnnt"
    LLM_PROVIDER: str = "deepseek"
    LLM_MODEL: str = "deepseek-chat"
    LLM_API_KEY: str = ""
    MEMBERS_ONLY: bool = True
    REQUIRE_QUOTE: bool = True
    VAD_ADAPTIVE: bool = True
    DATA_RETENTION_DAYS: int = 90
    API_PORT: int = 8900
    # служебное: какие переменные реально приходили из окружения (для понятных проверок ниже)
    provided: set[str] = field(default_factory=set, compare=False)

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "Settings":
        env = env if env is not None else dict(os.environ)  # type: ignore[arg-type]
        values: dict[str, object] = {}
        provided: set[str] = set()
        for f in fields(cls):
            if f.name == "provided":
                continue
            raw = env.get(f.name)
            if raw:
                provided.add(f.name)
            if raw is None or raw == "":
                continue
            default = f.default
            if isinstance(default, bool):
                values[f.name] = raw.strip().lower() in {"1", "true", "yes", "да", "on"}
            elif isinstance(default, int):
                try:
                    values[f.name] = int(raw)
                except ValueError:
                    raise ValueError("Переменная " + f.name + " должна быть числом, а получено: " + raw)
            else:
                values[f.name] = raw.strip()
        return cls(provided=provided, **values)  # type: ignore[arg-type]


# какие ключи обязательны для выбранного внешнего провайдера
KEY_OF_PROVIDER = {
    "speechmatics": "SPEECHMATICS_API_KEY",
    "deepgram": "DEEPGRAM_API_KEY",
    "assemblyai": "ASSEMBLYAI_API_KEY",
}
KEY_OF_LLM = {"deepseek": "LLM_API_KEY", "gigachat": "LLM_API_KEY", "anthropic": "LLM_API_KEY", "ollama": ""}


def validate(settings: Settings) -> list[str]:
    """Возвращает список проблем по-русски. Пустой список = можно запускать.

    Проверяем ровно то, что ломает встречу на половине: нет ключа, опечатка в имени провайдера,
    неверный порт. «Не настроено» лучше, чем «упало в середине записи».
    """
    problems: list[str] = []
    allowed_asr = {"fake", "speechmatics", "deepgram", "assemblyai", "gigaam"}
    if settings.ASR_PROVIDER not in allowed_asr:
        problems.append("ASR_PROVIDER = " + settings.ASR_PROVIDER + "; допустимо: " + ", ".join(sorted(allowed_asr)))
    key_field = KEY_OF_PROVIDER.get(settings.ASR_PROVIDER, "")
    if key_field and not getattr(settings, key_field):
        problems.append("Выбран " + settings.ASR_PROVIDER + ", но не задан " + key_field)
    if settings.ASR_PROVIDER == "gigaam" and not settings.GIGAAM_MODEL:
        problems.append("Для gigaam нужен GIGAAM_MODEL (путь к весам)")

    allowed_llm = {"deepseek", "gigachat", "anthropic", "ollama"}
    if settings.LLM_PROVIDER not in allowed_llm:
        problems.append("LLM_PROVIDER = " + settings.LLM_PROVIDER + "; допустимо: " + ", ".join(sorted(allowed_llm)))
    llm_key = KEY_OF_LLM.get(settings.LLM_PROVIDER, "")
    # Проверяем ключ LLM только если человек ЯВНО выбрал провайдера.
    # Дефолтная конфигурация обязана стартовать без единой настройки (asr=fake, llm выключен).
    llm_explicit = bool({"LLM_PROVIDER", "LLM_API_KEY"} & getattr(settings, "provided", set()))
    if llm_key and llm_explicit and not settings.LLM_API_KEY:
        problems.append("Выбран LLM-провайдер " + settings.LLM_PROVIDER + ", но не задан LLM_API_KEY")

    if settings.API_PORT == 8000:
        problems.append("API_PORT 8000 занят другими проектами на машине; возьмите 8900")
    if settings.DATA_RETENTION_DAYS < 0:
        problems.append("DATA_RETENTION_DAYS не может быть отрицательным")
    return problems


def describe() -> str:
    """Текст для экрана «Настройки» и для `python -m vvoice.settings`."""
    lines = ["# Настройки VoiceTranscribator", ""]
    for f in fields(Settings):
        info = DESCRIPTIONS.get(f.name)
        lines.append("- **" + f.name + "** = " + str(f.default))
        if info:
            lines.append("  " + info[0] + " (по умолчанию: " + info[1] + ")" + ("; " + info[2] if info[2] else ""))
    lines += ["", "Пример настройки: скопируйте .env.example в secrets/.env и заполните ключи.", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    import sys

    try:
        current = Settings.from_env()
    except ValueError as exc:
        print("Ошибка настройки: " + str(exc))
        sys.exit(2)
    problems = validate(current)
    if problems:
        print("Проверка не пройдена:")
        for p in problems:
            print(" - " + p)
        print("")
        print(describe())
        sys.exit(1)
    print("Настройки в порядке: ASR=" + current.ASR_PROVIDER + ", LLM=" + current.LLM_PROVIDER)
