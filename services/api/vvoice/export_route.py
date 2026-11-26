"""Маршрут экспорта: превращает одобренные задачи в отправку наружу.

Зачем отдельный модуль: контракт и отправка уже есть в exporters.py, но к ним не было пути.
Здесь — только проверки, которые обязаны стоять на входе, и пересказ результата человеку.

Правила:
  1. Без одобрения человека ничего не уходит: разбор предлагает, человек решает.
  2. Неизвестная цель — отказ с перечнем доступных, а не молчаливая потеря задачи.
  3. Один упавший адресат не отменяет остальных: результат по каждому.
"""

from __future__ import annotations

from typing import Any, Callable

from .exporters import ApprovedItem, export_all, to_payload

KNOWN_TARGETS = ('helper', 'jira', 'bitrix24', 'webhook')


def _item(raw: dict[str, Any]) -> ApprovedItem | None:
    """Собирает элемент или None, если он не годится для отправки наружу."""
    if not isinstance(raw, dict):
        return None
    if not raw.get('approved'):
        return None  # человек не подтверждал — наружу не уходит, даже если просят
    item_id = str(raw.get('id') or '').strip()
    title = str(raw.get('title') or '').strip()
    quote = str(raw.get('evidence_quote') or '').strip()
    if not item_id or not title or not quote:
        return None
    return ApprovedItem(
        id=item_id,
        kind=str(raw.get('kind') or 'task'),
        title=title,
        evidence_quote=quote,
        start_s=float(raw.get('start_s') or 0),
        end_s=float(raw.get('end_s') or 0),
        owner=raw.get('owner'),
        due_at=raw.get('due_at'),
        priority=str(raw.get('priority') or 'medium'),
    )


def export_session(
    raw: dict[str, Any],
    *,
    send: Callable[[Any], tuple[bool, str]] | None,
) -> tuple[int, dict[str, Any]]:
    """Отправляет одобренные задачи в указанные цели. Возвращает (код, ответ)."""
    targets_raw = raw.get('targets');
    if not isinstance(targets_raw, dict) or not targets_raw:
        return 400, {'error': 'bad_request', 'message': 'Нужны targets: адреса, куда отправлять.'}
    unknown = [name for name in targets_raw if name not in KNOWN_TARGETS]
    if unknown:
        return 400, {'error': 'unknown_target',
                     'message': 'Неизвестная цель: ' + ', '.join(unknown) + '. Доступны: ' + ', '.join(KNOWN_TARGETS)}
    raw_items = raw.get('items');
    if not isinstance(raw_items, list) or not raw_items:
        return 400, {'error': 'bad_request', 'message': 'Нужны items: задачи после одобрения.'}
    approved = [item for item in (_item(x) for x in raw_items) if item is not None]
    skipped = len(raw_items) - len(approved)
    if not approved:
        return 422, {'error': 'nothing_approved',
                      'message': 'Ни одна задача не одобрена человеком — отправлять нечего.'}
    if send is None:
        return 503, {'error': 'export_unavailable',
                      'message': 'Сервер не настроен отправлять задачи наружу.'}
    # build_plan выдаёт пары «элемент × цель» в порядке: все цели для первого элемента, все для второго.
    targets = {k: str(v) for k, v in targets_raw.items()}
    pairs = [(to_payload(item, target, base), item) for item in approved for target, base in targets.items()]
    results = export_all(pairs, send)
    ok_count = sum(1 for r in results if getattr(r, 'ok', False))
    return 200, {'sent': ok_count, 'failed': len(results) - ok_count, 'skipped': skipped,
                 'results': [{'target': r.target, 'ok': bool(getattr(r, 'ok', False)),
                              'detail': getattr(r, 'detail', '')} for r in results]}
