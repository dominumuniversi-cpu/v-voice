"""Живой поток: приём кусков звука и накопленный текст по сессии.

Зачем держать состояние здесь, а не в маршруте: распознаватель узнаёт слова по перекрытию
с предыдущим куском. Если каждый запрос начинать с чистого листа, фразы будут рваться на
стыках, и живой текст станет хуже финального. Поэтому состояние живёт в этом модуле,
а маршрут остаётся тонким.

Правила:
  1. Кусок без сессии не принимается — иначе некуда накапливать.
  2. Провайдер упал — отдаём то, что уже услышали, и честную пометку об обрыве.
  3. Старые сессии вытесняются: телефон может не дослать «конец», и память не должна расти.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any, Callable

from .pipeline import SessionState, run_live
from .sessions import is_session_id

# Сколько сессий помним одновременно: длинный разговор идёт одной сессией,
# а забытые телефоном — вылетают по порядку поступления.
MAX_LIVE_SESSIONS = 32


class LiveSessions:
    """Состояние живого распознавания по сессиям, ограниченное по числу."""

    def __init__(self, limit: int = MAX_LIVE_SESSIONS) -> None:
        self._states: OrderedDict[str, SessionState] = OrderedDict()
        self._limit = limit

    def peek(self, session_id: str) -> SessionState | None:
        """Смотрит состояние, НЕ создавая его: проверка не должна плодить пустые сессии."""
        return self._states.get(session_id)

    def state_for(self, session_id: str) -> SessionState:
        """Выдаёт состояние сессии, поднимая её в очередь свежих."""
        state = self._states.get(session_id)
        if state is None:
            state = SessionState()
        else:
            self._states.move_to_end(session_id)
        self._states[session_id] = state
        while len(self._states) > self._limit:
            self._states.popitem(last=False)
        return state

    def drop(self, session_id: str) -> None:
        """Сессия закончилась: освобождаем память сразу, а не когда дойдёт очередь."""
        self._states.pop(session_id, None)

    def size(self) -> int:
        return len(self._states)


def push_chunk(
    sessions: LiveSessions,
    session_id: str,
    pcm: bytes,
    *,
    provider_factory: Callable[[str], Any],
) -> tuple[int, dict[str, Any]]:
    """Отправляет кусок в распознавание и возвращает (код, ответ с накопленным текстом)."""
    if not is_session_id(session_id):
        return 400, {"error": "bad_request", "message": "Неверный идентификатор сессии."}
    if not pcm:
        return 400, {"error": "bad_request", "message": "Пустой кусок звука."}
    state = sessions.state_for(session_id)
    try:
        run_live(provider_factory(session_id), state, [pcm])
    except Exception as exc:  # обрыв провайдера не должен стирать уже услышанное
        return 502, {"error": "stream_failed", "message": str(exc),
                     "text": state.live.display_text()}
    text = state.live.display_text()
    return 200, {"text": text}
