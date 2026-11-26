"""Сборка разбора: контекст из транскрипта -> ответ модели -> валидатор цитат.

Модуль намеренно не зовёт сеть: он принимает функцию-вызов LLM. Так тесты конвейера не зависят
от ключа и не тратят деньги, а реальный адаптер (deepseek/gigachat/claude/ollama) подключается снаружи.
"""

from __future__ import annotations

from typing import Callable

from .assemble import Transcript
from .evidence import validate_digest

MAX_TRANSCRIPT_CHARS = 90_000

SYSTEM_PROMPT = (
    "Ты разбираешь расшифровку делового разговора на русском языке. "
    "Верни СТРОГО JSON без пояснений по схеме: "
    '{"summary": [строка], "participants": [{"speaker": "S1", "name": "Анна", "verdict": "owner|member|foreign"}], '
    '"items": [{"kind": "task|meeting|reminder|decision|question", "title": строка, '
    '"owner": строка|null, "due_at": ISO8601|null, "priority": "low|medium|high", '
    '"evidence": {"start_s": число, "end_s": число, "quote": строка}}], "open_questions": [строка]}. '
    "Правила: не придумывай факты; для каждого элемента items evidence.quote обязан дословно "
    "присутствовать в расшифровке и быть не короче 12 символов; сроки бери только из речи; "
    "если сказано «подумать», это не задача, а открытый вопрос."
)


def build_prompt(transcript: Transcript, *, previous_summary: list[str] | None = None) -> str:
    """Промпт для одного прохода разбора. previous_summary нужен для добавочного разбора."""
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
        "summary": [str(s) for s in (raw.get("summary") or [])],
        "participants": raw.get("participants") or [],
        "open_questions": [str(s) for s in (raw.get("open_questions") or [])],
        "items": checked["items"],
        "rejected": checked["rejected"],
    }
