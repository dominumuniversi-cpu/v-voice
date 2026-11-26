"""Заглушка модели понимания: разбор без ключей и без сети.

Зачем: без неё демо-режим не проходил разбор — `/analyze` отвечал 503 при любых настройках,
и показать приложение человеку без платных ключей было нельзя.

Правила, без которых заглушка вредна:
  - включается ТОЛЬКО явным `VV_LLM_PROVIDER=fake`, а не пустой строкой;
  - пункты строятся ИЗ ТЕКСТА расшифровки, а не из заготовки: цитата обязана быть в тексте,
    иначе валидатор справедливо отбросит пункт, и разбор окажется пустым — а виноват будет не текст;
  - `/health` видит провайдера `fake` и может сказать человеку, что ответы выдуманы.
"""

from __future__ import annotations

import json
import re
from typing import Callable

# Слова, по которым фраза похожа на задачу. Список короткий нарочно: заглушка не должна
# притворяться умной — она показывает, что путь работает, а не что модель хороша.
_TASK_MARKERS = ("надо", "нужно", "сделаю", "отправлю", "позвоню", "проверю", "подготовлю")

# Решение — это когда договорились, а не когда предложили. Без этих маркеров «Договорились: ...»
# пропадало из разбора, и экран показывал пустой раздел решений на встрече, где решали.
_DECISION_MARKERS = ("договорились", "решили", "приняли", "утвердили", "согласовали", "выходит в")

# Открытый вопрос — то, что ещё не решили. Иначе «нужен ли созвон?» уходил в задачи как действие.
_QUESTION_MARKERS = ("?", "нужен ли", "стоит ли", "пока не решили", "неясно")

# Служебная разметка расшифровки: «S2 [4.5-9.2] ». Человеку она не нужна, а в заголовке задачи
# выглядела как часть фразы.
_SPEAKER_TAG = re.compile(r"^\s*S\d+\s*\[[\d.]+\s*-\s*[\d.]+\]\s*")


def _sentences(text: str) -> list[str]:
    """Делит расшифровку на фразы. Точка в конце — тоже граница."""
    parts = re.split(r'(?<=[.!?])\s+|\n+', text.strip())
    return [p.strip() for p in parts if p.strip()]


def fake_understanding(system: str, user: str) -> dict:
    """Ответ в форме, которую ждёт разбор: выжимка, пункты, решения.

    `user` — промпт с расшифровкой. Вытаскиваем фразы из него: так цитата в пункте
    совпадает с текстом, и валидатор не отбросит всё подряд.
    """
    sentences = [_SPEAKER_TAG.sub("", p) for p in _sentences(_transcript_from_prompt(user))]
    sentences = [p for p in sentences if p]
    items = []
    decisions = []
    questions = []
    for phrase in sentences:
        low = phrase.lower()
        # Вопрос проверяем ПЕРВЫМ: «нужно ли ...?» содержит «нужно», но это не задача.
        if any(marker in low for marker in _QUESTION_MARKERS):
            questions.append({"text": phrase[:200]})
            continue
        if any(marker in low for marker in _DECISION_MARKERS):
            decisions.append({"text": phrase[:200]})
            continue
        if any(marker in low for marker in _TASK_MARKERS):
            # Таймкоды обязательны: без них валидатор отбросит пункт как «некорректные таймкоды».
            # Заглушка не знает реальных времён, поэтому ставит диапазон по порядку фразы.
            index = sentences.index(phrase)
            items.append({
                "kind": "task",
                "title": phrase[:80],
                "evidence": {"start_s": float(index * 3), "end_s": float(index * 3 + 3), "quote": phrase},
            })
    # summary — СПИСОК пунктов, как у настоящей модели: строка здесь превратилась бы в список букв.
    summary = [phrase[:200] for phrase in sentences[:3]] or ["Речь не распознана."]
    return {
        "summary": summary,
        "items": items,
        "decisions": decisions,
        "open_questions": questions,
    }


def _transcript_from_prompt(prompt: str) -> str:
    """Достаёт расшифровку из промпта. Если разметки нет — возвращает весь текст."""
    # Промпт начинается со служебных строк ("Расшифровка разговора:", инструкции схемы).
    # Ищем последнюю такую строку и берём всё ПОСЛЕ неё — там и есть речь.
    lines = prompt.split("\n")
    service: list[int] = []
    for number, line in enumerate(lines):
        low = line.strip().lower()
        if low.startswith("расшифровка") or low.startswith("разбери") or low.startswith("верни json"):
            service.append(number)
    if not service:
        return prompt
    # Речь лежит МЕЖДУ заголовком и финальной инструкцией: только так, иначе промпт целиком.
    start = service[0] + 1
    finish = service[-1] if len(service) > 1 else len(lines)
    return "\n".join(lines[start:finish]).strip() or prompt


def make_fake_llm() -> Callable[[str, str], dict]:
    """Функция в том же виде, что и настоящая: (системная инструкция, вопрос) -> разбор."""
    return fake_understanding


def as_json(data: dict) -> str:
    """Полезно в тестах: сравнить ответ с ожидаемой формой."""
    return json.dumps(data, ensure_ascii=False)
