"""Сборка разбора: контекст из транскрипта -> ответ модели -> валидатор цитат.

Модуль намеренно не зовёт сеть: он принимает функцию-вызов LLM. Так тесты конвейера не зависят
от ключа и не тратят деньги, а реальный адаптер (deepseek/gigachat/claude/ollama) подключается снаружи.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from .assemble import Transcript
from .evidence import validate_digest

MAX_TRANSCRIPT_CHARS = 90_000
# Краткая выжимка — это краткая. Модель иногда отвечает двумя десятками пунктов, и человек такое
# не читает. Показываем первые 7 и честно называем, сколько осталось.
MAX_SUMMARY_ITEMS = 7

# Промпт живёт в prompts/digest_ru.md, потому что его читают и правят люди, а не только модель.
# Встроенная копия — только запас: если файла нет (упаковка), разбор не должен падать молча.
PROMPT_PATH = Path(__file__).parent / 'prompts' / 'digest_ru.md'


def load_system_prompt(path: Path | None = None) -> str:
    """Читает промпт с диска. Пустой или отсутствующий файл — это ошибка, а не повод молчать."""
    target = path or PROMPT_PATH
    text = target.read_text(encoding='utf-8').strip()
    if not text:
        raise ValueError('prompt_empty: ' + str(target))
    return text


SYSTEM_PROMPT = load_system_prompt()



def _summary_points(raw: dict[str, Any]) -> list[str]:
    """Пункты выжимки в пределах краткости. Лишнее не теряется молча: число скрытых отдаёт ответ."""
    points = [str(s).strip() for s in (raw.get("summary") or []) if str(s).strip()]
    return points[:MAX_SUMMARY_ITEMS]


def prompt_is_truncated(transcript: Transcript) -> bool:
    """Поместилась ли расшифровка в один проход целиком."""
    return len(transcript.text) > MAX_TRANSCRIPT_CHARS


def build_prompt(transcript: Transcript, *, previous_summary: list[str] | None = None) -> str:
    """Промпт для одного прохода разбора. previous_summary нужен для добавочного разбора.

    Длинную расшифровку обрезаем по лимиту модели — иначе разбор не пройдёт вовсе. Но факт обрезки
    не теряем: make_digest кладёт его в результат, чтобы человек увидел, что конец разговора
    ещё не разобран, а не думал, что там ничего не говорили.
    """
    text = transcript.text
    if len(text) > MAX_TRANSCRIPT_CHARS:
        text = text[:MAX_TRANSCRIPT_CHARS]
    parts = ["Расшифровка разговора:", text]
    if previous_summary:
        parts += ["", "Уже сказано ранее (не повторяй):", *[f"- {s}" for s in previous_summary]]
    parts += ["", "Разбери разговор и верни JSON по схеме."]
    return "\n".join(parts)


def members_only_flag(participants: list[dict]) -> tuple[set[str], bool]:
    """Из participants ответа модели достаём чужие голоса и включён ли режим «только участники»."""
    foreign = {str(p.get("speaker")) for p in participants if isinstance(p, dict) and p.get("verdict") == "foreign"}
    return foreign, bool(foreign)


def make_digest(
    transcript: Transcript,
    call_llm: Callable[[str, str], dict],
    *,
    previous_summary: list[str] | None = None,
    members_only: bool = False,
) -> dict:
    """Один проход: промпт -> ответ модели -> фильтр цитат. Возвращает безопасный разбор."""
    raw = call_llm(SYSTEM_PROMPT, build_prompt(transcript, previous_summary=previous_summary))
    foreign, seen_foreign = members_only_flag(raw.get("participants") or [])
    checked = validate_digest(
        raw,
        transcript.text,
        speakers=transcript.speakers,
        foreign_speakers=foreign,
        members_only=members_only and seen_foreign,
    )
    return {
        # Одна строка «о чём был разговор». Раньше её теряли: промпт просил, модель отвечала,
        # а в результат она не попадала — и человек видел список, но не видел сути.
        "topic": str(raw.get("topic") or "").strip(),
        # True — разобрана только часть разговора. Молчать об этом значит выдать половину за целое.
        "truncated": prompt_is_truncated(transcript),
        "summary": _summary_points(raw),
        # Сколько пунктов не показано. Молчаливая обрезка заставила бы человека думать, что он
        # увидел всё главное.
        "summary_hidden": max(0, len(raw.get("summary") or []) - MAX_SUMMARY_ITEMS),
        # Модель ничего не выделила — это факт о разборе, а не пустое место.
        # Тот, кто строит интеграцию, должен уметь отличить «нечего сказать» от «не справилась».
        "summary_missing": not (raw.get("summary") or []),
        "participants": raw.get("participants") or [],
        "open_questions": [str(s) for s in (raw.get("open_questions") or [])],
        "items": checked["items"],
        "rejected": checked["rejected"],
    }
