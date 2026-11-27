"""Сборка разбора: контекст из транскрипта -> ответ модели -> валидатор цитат.

Модуль намеренно не зовёт сеть: он принимает функцию-вызов LLM. Так тесты конвейера не зависят
от ключа и не тратят деньги, а реальный адаптер (deepseek/gigachat/claude/ollama) подключается снаружи.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

from .assemble import Transcript
from .evidence import normalize, validate_digest

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


def _utterance_pairs(transcript: Transcript) -> list[tuple[str, str]]:
    """Реплики как пары «говорящий, текст» — основа для проверки, чей это пункт."""
    return [(u.speaker, u.text) for u in transcript.utterances]


def _drop_foreign_only(
    lines: list[str],
    utterances: list[tuple[str, str]],
    foreign: set[str],
) -> list[str]:
    """Убирает строки, которые целиком взяты из реплик чужих голосов.

    Зачем: режим «только участники» раньше резал лишь пункты задач. Выжимка, решения и вопросы —
    это и есть «суть разговора», и чужие голоса (сосед, телевизор, попутчик) оставались в ней.
    Строка считается своей, если хоть часть её опирается на своего говорящего: половина правды
    лучше, чем потеря всего сказанного рядом.
    """
    if not foreign or not utterances:
        return lines
    kept: list[str] = []
    for line in lines:
        normalized = normalize(line)
        if not normalized:
            continue
        own = any(
            normalize(text) and normalize(text) in normalized and speaker not in foreign
            for speaker, text in utterances
        )
        if own:
            kept.append(line)
    return kept


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


def _question_text(value) -> str:
    """Вопрос из ответа модели. Модель шлёт и строку, и объект {text}: str(dict) дал бы
    "{'text': ...}" прямо на экране — так и случилось на живой записи."""
    if isinstance(value, dict):
        return str(value.get("text") or value.get("question") or value.get("title") or "")
    return str(value or "")


def _lead_colon(value) -> str:
    """Убирает ведущее двоеточие: «: текст» — остаток от пустого автора, а не начало фразы."""
    return re.sub(r"^\s*:\s*", "", str(value or "")).strip()


def _clean_item(item: dict) -> dict:
    """Пункт разбора без ведущего двоеточия: и заголовок, и цитата."""
    clean = dict(item)
    clean["title"] = _lead_colon(clean.get("title"))
    evidence = clean.get("evidence")
    if isinstance(evidence, dict):
        clean["evidence"] = dict(evidence, quote=_lead_colon(evidence.get("quote")))
    return clean


def make_digest(
    transcript: Transcript,
    call_llm: Callable[[str, str], dict],
    *,
    previous_summary: list[str] | None = None,
    members_only: bool = False,
) -> dict:
    """Один проход: промпт -> ответ модели -> фильтр цитат. Возвращает безопасный разбор."""
    # Пустую расшифровку модели не отдаём: она честно «разбирает» служебные строки промпта,
    # и человек получает выжимку из инструкции («Разбери разговор и верни JSON») вместо отказа.
    if not str(transcript.text or "").strip():
        return {"topic": "", "summary": [], "items": [], "decisions": [], "open_questions": [],
                "truncated": False, "summary_missing": True, "empty_transcript": True,
                "rejected": [], "participants": []}
    raw = call_llm(SYSTEM_PROMPT, build_prompt(transcript, previous_summary=previous_summary))
    foreign, seen_foreign = members_only_flag(raw.get("participants") or [])
    # Действует только когда человек включил режим «только участники»: иначе чужой голос —
    # такое же свидетельство, как и свой.
    active_foreign = foreign if members_only else set()
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
        # Двоеточие без автора модель иногда оставляет в начале строки — «: я отправлю смету».
        # Это обрывок, а не ответ; на сервере вычищаем, чтобы экран и экспорт не расходились.
        "topic": _lead_colon(raw.get("topic")),
        # True — разобрана только часть разговора. Молчать об этом значит выдать половину за целое.
        "truncated": prompt_is_truncated(transcript),
        "summary": [_lead_colon(s) for s in _drop_foreign_only(_summary_points(raw), _utterance_pairs(transcript), active_foreign) if _lead_colon(s)],
        # Сколько пунктов не показано. Молчаливая обрезка заставила бы человека думать, что он
        # увидел всё главное.
        "summary_hidden": max(0, len(raw.get("summary") or []) - MAX_SUMMARY_ITEMS),
        # Модель ничего не выделила — это факт о разборе, а не пустое место.
        # Тот, кто строит интеграцию, должен уметь отличить «нечего сказать» от «не справилась».
        "summary_missing": not (raw.get("summary") or []),
        "participants": raw.get("participants") or [],
        "open_questions": [_lead_colon(s) for s in _drop_foreign_only(
        [_question_text(q) for q in (raw.get("open_questions") or []) if _question_text(q)],
        _utterance_pairs(transcript), active_foreign) if _lead_colon(s)],
        # Решения читает приложение, а не только экспорт: без фильтра чужая реплика становилась
        # «тем, о чём договорились».
        "decisions": [_lead_colon(s) for s in _drop_foreign_only([str(s) for s in (raw.get("decisions") or [])], _utterance_pairs(transcript), active_foreign) if _lead_colon(s)],
        # Пункты тоже чистятся: «: я отправлю смету» во главе задачи читается как сбой модели.
        "items": [_clean_item(it) for it in checked["items"]],
        "rejected": checked["rejected"],
    }
