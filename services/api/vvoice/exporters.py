"""Встраивание в другие продукты: перенос задач из штучной выжимки в чужой задачник или CRM.

Требование владельца: «в дальнейшем приложение можно будет встроить в другие продукты (задачник/CRM)».
Поэтому граница интеграции описана явно, в одном модуле, и проверяется тем же валидатором цитат:

  1. Наш объект (`ApprovedItem`) — итог разбора, который человек подтвердил.
  2. `to_payload(item, target)` — приведение к контракту конкретной цели
     (helper.vernadsky-npc.ru, Jira, Битрикс24, Бумеранг, свой вебхук).
  3. `ExportPlan` — заранее собранный список запросов: что и куда уйдёт. Его можно показать
     человеку ДО отправки и проверить тестом без сети.

Правила, которые нельзя ослаблять:
  - в чужую систему уходит только подтверждённый человеком элемент;
  - у каждой задачи остаётся ссылка на фрагмент звука и цитату (иначе через месяц никто не поймёт откуда);
  - сбой одной цели не отменяет остальные: отчёт собирается по каждому пункту.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

SUPPORTED_TARGETS = ("helper", "jira", "bitrix24", "webhook")

PRIORITY_MAP = {"high": "high", "medium": "medium", "low": "low"}


@dataclass
class ApprovedItem:
    """Подтверждённый человеком элемент разбора. Только такие уходят наружу."""

    id: str
    kind: str
    title: str
    evidence_quote: str
    start_s: float
    end_s: float
    owner: str | None = None
    due_at: str | None = None
    priority: str = "medium"
    approved_by: str = ""
    session_id: str = ""

    def as_note(self) -> str:
        """Человекочитаемый хвост: откуда задача и что звучало."""
        who = self.owner or "не назначен"
        when = self.due_at or "без срока"
        return (
            f"[{self.kind}] {self.title}\n"
            f"Исполнитель: {who}; срок: {when}\n"
            f"Цитата: «{self.evidence_quote}» ({self.start_s:.1f}-{self.end_s:.1f} с)\n"
            f"Сессия: {self.session_id}; подтвердил: {self.approved_by}"
        )


@dataclass
class ExportRequest:
    """Один будущий сетевой запрос. Сети здесь нет — только описание."""

    target: str
    method: str
    url: str
    body: dict[str, Any] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _helper(item: ApprovedItem, base: str) -> ExportRequest:
    """Задачник NPC (наш эталон): POST /api/v1/tasks, priority строго в нижнем регистре."""
    body = {
        "title": item.title,
        "description": item.as_note(),
        "acceptance_criteria": "Подтверждено в прослушанной встрече; цитата и таймкод в описании.",
        "priority": PRIORITY_MAP.get(item.priority, "medium"),
    }
    if item.due_at:
        body["due_at"] = item.due_at
    return ExportRequest(target="helper", method="POST", url=base.rstrip("/") + "/api/v1/tasks", body=body,
                         headers={"Authorization": "Bearer <HELPER_TOKEN>", "Content-Type": "application/json"})


def _jira(item: ApprovedItem, base: str) -> ExportRequest:
    body = {
        "fields": {
            "summary": item.title,
            "description": item.as_note(),
            "issuetype": {"name": "Task"},
            "labels": ["v-voice", "from-meeting"],
        }
    }
    if item.due_at:
        body["fields"]["duedate"] = item.due_at[:10]
    return ExportRequest(target="jira", method="POST", url=base.rstrip("/") + "/rest/api/3/issue", body=body,
                         headers={"Content-Type": "application/json"})


def _bitrix24(item: ApprovedItem, base: str) -> ExportRequest:
    body = {
        "fields": {
            "TITLE": item.title,
            "DESCRIPTION": item.as_note(),
            "RESPONSIBLE_ID": item.owner or "",
        }
    }
    if item.due_at:
        body["fields"]["DEADLINE"] = item.due_at
    return ExportRequest(target="bitrix24", method="POST", url=base.rstrip("/") + "/rest/tasks.task.add.json", body=body,
                         headers={"Content-Type": "application/json"})


def _webhook(item: ApprovedItem, base: str) -> ExportRequest:
    """Свой продукт: единый плоский контракт — его легко принять любой CRM."""
    return ExportRequest(
        target="webhook", method="POST", url=base,
        body={
            "schema": "vvoice.item.v1",
            "item_id": item.id,
            "session_id": item.session_id,
            "kind": item.kind,
            "title": item.title,
            "owner": item.owner,
            "due_at": item.due_at,
            "priority": PRIORITY_MAP.get(item.priority, "medium"),
            "evidence": {"quote": item.evidence_quote, "start_s": item.start_s, "end_s": item.end_s},
            "approved_by": item.approved_by,
        },
        headers={"Content-Type": "application/json"},
    )


_BUILDERS = {"helper": _helper, "jira": _jira, "bitrix24": _bitrix24, "webhook": _webhook}


def to_payload(item: ApprovedItem, target: str, base_url: str) -> ExportRequest:
    """Один элемент -> запрос для конкретной цели. Неизвестная цель = понятная ошибка."""
    if target not in _BUILDERS:
        raise ValueError("Неизвестная цель выгрузки: " + target + "; допустимо: " + ", ".join(SUPPORTED_TARGETS))
    return _BUILDERS[target](item, base_url)


def build_plan(items: list[ApprovedItem], targets: dict[str, str]) -> list[ExportRequest]:
    """План выгрузки: каждый элемент по каждой цели. Показывается человеку перед отправкой."""
    return [to_payload(item, target, base) for item in items for target, base in targets.items()]


def dry_run_json(plan: list[ExportRequest]) -> str:
    """Текст плана для экрана «Проверить перед отправкой» (и для тестов)."""
    return json.dumps([req.as_dict() for req in plan], ensure_ascii=False, indent=2)


@dataclass
class ExportResult:
    target: str
    item_id: str
    ok: bool
    detail: str = ""


def export_all(plan_items: list[tuple[ExportRequest, ApprovedItem]], send) -> list[ExportResult]:
    """Выполняет план через переданную функцию `send(request) -> (ok, detail)`.

    Сеть снаружи: поэтому сбой одного запроса виден по-пунктно и не валит остальные.
    """
    results: list[ExportResult] = []
    for req, item in plan_items:
        try:
            ok, detail = send(req)
        except Exception as exc:  # noqa: BLE001 — одна упавшая цель не должна ронять весь экспорт
            ok, detail = False, str(exc)
        results.append(ExportResult(target=req.target, item_id=item.id, ok=ok, detail=detail))
    return results
