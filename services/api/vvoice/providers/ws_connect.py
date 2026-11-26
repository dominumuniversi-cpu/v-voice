"""Соединение с внешним сервисом распознавания по WebSocket.

Зачем отдельный файл: адаптер [SpeechmaticsAsr] принимает функцию `connect`, чтобы его можно было
проверять без сети. В настоящем прогоне соединение создаётся здесь, и если нужной библиотеки нет,
человек получает объяснение по-русски, а не трассировку импорта.
"""

from __future__ import annotations

from typing import Any


class ConnectError(RuntimeError):
    """Соединение нельзя открыть. Текст исключения показывает человеку в /health и в ответе."""


def connect_websocket(url: str, headers: dict[str, str]) -> Any:
    """Открывает WebSocket. Возвращает объект с send(str), recv() и close()."""
    try:
        import websocket  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover — зависит от окружения
        raise ConnectError(
            "для живого распознавания нужна библиотека websocket-client "
            "(pip install websocket-client); без неё работает только разбор через файл"
        ) from exc
    try:
        sock = websocket.create_connection(url, header=_as_header_lines(headers), timeout=30)
    except Exception as exc:  # сеть и ключ: причина важнее типа исключения
        raise ConnectError("не удалось подключиться к сервису распознавания: " + str(exc)) from exc
    return _Sock(sock)


def _as_header_lines(headers: dict[str, str]) -> list[str]:
    """websocket-client ждёт список строк «Имя: значение», а не словарь."""
    return [str(name) + ": " + str(value) for name, value in (headers or {}).items()]


class _Sock:
    """Тонкая обёртка: адаптер не должен знать про особенности библиотеки."""

    def __init__(self, sock: Any) -> None:
        self._sock = sock

    def send(self, text: str) -> None:
        self._sock.send(text)

    def recv(self) -> str:
        data = self._sock.recv()
        return data if isinstance(data, str) else data.decode("utf-8", "replace")

    def close(self) -> None:
        try:
            self._sock.close()
        except Exception:
            pass
