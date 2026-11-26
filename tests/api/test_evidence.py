"""Тесты правила «нет цитаты — нет задачи».

Запуск: python -m pytest tests/api -q
Кейсы написаны так, что проверяют не «счастливый путь», а именно то, ради чего правило введено:
выдуманная моделью задача, укороченная цитата, цитата из другой встречи, несуществующий владелец.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services" / "api"))

from vvoice.evidence import (  # noqa: E402
    MIN_QUOTE_LEN,
    normalize,
    quote_is_present,
    validate_digest,
    validate_item,
)

TRANSCRIPT = (
    "Анна: По бюджету до пятницы надо понять, укладываемся или нет. "
    "Дмитрий: Я отправлю смету завтра утром, успеем. "
    "Анна: Тогда созвон перенесём на девятое декабря в час дня."
)

TASK = {
    "kind": "task",
    "title": "Отправить смету Анне",
    "owner": "Дмитрий",
    "due_at": "2026-11-27T08:00:00+05:00",
    "evidence": {"start_s": 742.0, "end_s": 746.5, "quote": "Я отправлю смету завтра утром, успеем"},
}


def test_normalize_collapses_whitespace_and_case():
    assert normalize("  Я   ОТПРАВЛЮ\nсмету ") == "я отправлю смету"


def test_quote_present_tolerates_case_and_spaces():
    assert quote_is_present("я отправлю  смету завтра", TRANSCRIPT)


def test_valid_task_passes():
    ok, reason = validate_item(TASK, TRANSCRIPT, speakers={"Анна", "Дмитрий"})
    assert ok, reason


def test_task_without_evidence_rejected():
    broken = {k: v for k, v in TASK.items() if k != "evidence"}
    ok, reason = validate_item(broken, TRANSCRIPT)
    assert not ok and "evidence" in reason


def test_short_quote_rejected():
    broken = dict(TASK, evidence={"start_s": 1, "end_s": 2, "quote": "успеем"})
    ok, reason = validate_item(broken, TRANSCRIPT)
    assert not ok and str(MIN_QUOTE_LEN) in reason


def test_invented_quote_rejected():
    """Главный кейс: модель придумала задачу, которой в разговоре не было."""
    broken = dict(TASK, evidence={"start_s": 10, "end_s": 12, "quote": "Давай закроем контракт с новым клиентом завтра"})
    ok, reason = validate_item(broken, TRANSCRIPT)
    assert not ok and "нет в транскрипте" in reason


def test_quote_from_another_meeting_rejected():
    ok, reason = validate_item(TASK, "Анна: добрый день, начнём")
    assert not ok


def test_owner_not_in_conversation_rejected():
    broken = dict(TASK, owner="Олег")
    ok, reason = validate_item(broken, TRANSCRIPT, speakers={"Анна", "Дмитрий"})
    assert not ok and "Олег" in reason


def test_bad_due_at_rejected():
    broken = dict(TASK, due_at="завтра утром")
    ok, reason = validate_item(broken, TRANSCRIPT)
    assert not ok and "ISO8601" in reason


def test_due_at_may_be_null():
    item = dict(TASK, due_at=None)
    ok, reason = validate_item(item, TRANSCRIPT, speakers={"Анна", "Дмитрий"})
    assert ok, reason


def test_reversed_timestamps_rejected():
    broken = dict(TASK, evidence={"start_s": 20, "end_s": 10, "quote": TASK["evidence"]["quote"]})
    ok, reason = validate_item(broken, TRANSCRIPT)
    assert not ok


def test_validate_digest_reports_rejections():
    digest = {
        "summary": ["Свели бюджет"],
        "items": [
            TASK,
            {"kind": "task", "title": "Придуманная задача", "evidence": {"start_s": 1, "end_s": 2, "quote": "поговорим об этом когда-нибудь позже"}},
            {"kind": "meeting", "title": "Созвон 9 декабря 13:00", "evidence": {"start_s": 900, "end_s": 905, "quote": "созвон перенесём на девятое декабря в час дня"}},
        ],
    }
    result = validate_digest(digest, TRANSCRIPT, speakers={"Анна", "Дмитрий"})
    assert len(result["items"]) == 2
    assert len(result["rejected"]) == 1
    assert result["rejected"][0]["index"] == 1


@pytest.mark.parametrize("kind", ["task", "meeting", "reminder", "decision", "question"])
def test_all_supported_kinds(kind):
    ok, reason = validate_item(dict(TASK, kind=kind), TRANSCRIPT, speakers={"Анна", "Дмитрий"})
    assert ok, reason


def test_unknown_kind_rejected():
    ok, reason = validate_item(dict(TASK, kind="note"), TRANSCRIPT)
    assert not ok and "неизвестный тип" in reason
