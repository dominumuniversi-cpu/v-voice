"""Правило «нет цитаты — нет задачи».

LLM-разбор склонен дописывать то, чего в разговоре не было. Поэтому каждый элемент
(задача, встреча, напоминание, решение) обязан ссылаться на реальный кусок транскрипта:
цитата >= MIN_QUOTE_LEN символов и находится в тексте (с точностью до регистра и лишних пробелов).
Всё, что не прошло проверку, отбрасывается ДО записи в базу и отправки в задачник.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

MIN_QUOTE_LEN = 12
_WS = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Приводим текст к виду, в котором цитату можно искать: нижний регистр, один пробел, ё→е."""
    return _WS.sub(" ", (text or "").lower().replace("ё", "е")).strip()


def quote_is_present(quote: str, transcript: str) -> bool:
    """Цитата есть в транскрипте? Сравнение устойчиво к регистру и пробелам."""
    q = normalize(quote)
    return bool(q) and q in normalize(transcript)


@dataclass(frozen=True)
class Evidence:
    start_s: float
    end_s: float
    quote: str

    @property
    def long_enough(self) -> bool:
        return len(normalize(self.quote)) >= MIN_QUOTE_LEN

    @property
    def ordered(self) -> bool:
        return 0 <= self.start_s <= self.end_s


def parse_evidence(raw: object) -> Evidence | None:
    """Разбираем evidence из ответа модели. Кривая структура = отсутствие evidence."""
    if not isinstance(raw, dict):
        return None
    try:
        start = float(raw.get("start_s", -1))
        end = float(raw.get("end_s", -1))
        quote = str(raw.get("quote", ""))
    except (TypeError, ValueError):
        return None
    return Evidence(start_s=start, end_s=end, quote=quote)


def validate_item(
    item: dict,
    transcript: str,
    speakers: set[str] | None = None,
    foreign_speakers: set[str] | None = None,
    members_only: bool = False,
) -> tuple[bool, str]:
    """Проверка одного элемента разбора. Возвращает (попускать?, причина).

    Причины на русском: они попадают в отчёт и в логи, чтобы было видно, что отрезано и почему.
    """
    if not isinstance(item, dict):
        return False, "элемент не объект"
    kind = item.get("kind")
    if kind not in {"task", "meeting", "reminder", "decision", "question"}:
        return False, f"неизвестный тип: {kind!r}"
    if not str(item.get("title") or "").strip():
        return False, "пустой заголовок"

    ev = parse_evidence(item.get("evidence"))
    if ev is None:
        return False, "нет evidence"
    if not ev.long_enough:
        return False, "цитата короче 12 символов"
    if not ev.ordered:
        return False, "некорректные таймкоды"
    if not quote_is_present(ev.quote, transcript):
        return False, "цитаты нет в транскрипте"

    owner = item.get("owner")
    if owner and speakers is not None and str(owner) not in speakers:
        return False, f"владелец {owner!r} не участвовал в разговоре"

    # Режим «для участников»: элемент с чужим голосом не попадает в задачник.
    if members_only and item.get("speaker") in foreign_speakers:
        return False, f"реплика чужого голоса {item.get('speaker')!r} (режим для участников)"

    due = item.get("due_at")
    if due is not None and not isinstance(due, str):
        return False, "due_at должен быть строкой ISO8601 или null"
    if isinstance(due, str) and due:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2})?([+-]\d{2}:?\d{2})?)?", due):
            return False, "due_at не похож на ISO8601"
    return True, "ok"


def validate_digest(
    digest: dict,
    transcript: str,
    speakers: set[str] | None = None,
    foreign_speakers: set[str] | None = None,
    members_only: bool = False,
) -> dict:
    """Фильтруем разбор целиком. Возвращает только допустимые элементы + отчёт об отсеве.

    members_only=True — «слышим всех, разбираем только участников»: элементы, привязанные
    к реплике чужого голоса, отбрасываются с понятной причиной (не удаляются из аудио).
    """
    items = digest.get("items") or []
    kept: list[dict] = []
    rejected: list[dict] = []
    for idx, item in enumerate(items):
        ok, reason = validate_item(item, transcript, speakers, foreign_speakers, members_only)
        if ok:
            kept.append(item)
        else:
            rejected.append({"index": idx, "title": (item or {}).get("title") if isinstance(item, dict) else None, "reason": reason})
    return {"items": kept, "rejected": rejected}
