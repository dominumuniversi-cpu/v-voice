"""Запуск сервера: единственное место, где модули связываются в рабочую службу.

Почему на стандартной библиотеке: в CI есть только Python 3.12 без пакетов, а точка запуска
обязана проверяться там же, где всё остальное. Иначе ошибка старта всплывает на боевом сервере.

Что делает сборка:
  * читает настройки из окружения (ключи моделей живут только здесь);
  * готовит хранилища записей и разборов в каталоге данных;
  * отдаёт маршруты через http_api.handle — ни одного второго списка путей;
  * честно отвечает /health, даже если модели не настроены.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from vvoice.config import Settings, load as load_settings
from vvoice.digest_store import DigestStore
from vvoice.http_api import handle
from vvoice.live_sessions import LiveSessions
from vvoice.storage import AudioStore

MAX_BODY_BYTES = 12 * 1024 * 1024  # запись приходит base64, запас на JSON-обёртку


def build_dependencies(settings: Settings, data_dir: Path) -> dict[str, Any]:
    """Собирает всё, что нужно маршрутам. Ключи остаются в settings и наружу не передаются."""
    data_dir.mkdir(parents=True, exist_ok=True)
    return {
        'store': AudioStore(data_dir / 'audio'),
        'digests': DigestStore(data_dir / 'digests'),
        'live_sessions': LiveSessions(),
        # Отправка задач наружу появится, когда будут ключи интеграций; пока None —
        # маршрут отвечает 503 и говорит правду, вместо того чтобы делать вид.
        'exporter': None,
    }


class Handler(BaseHTTPRequestHandler):
    """Переводит HTTP-запрос в вызов handle() и обратно."""

    server_version = 'v-voice/1'
    deps: dict[str, Any] = {}
    settings: Settings | None = None

    def _respond(self, status: int, body: dict[str, Any], headers: dict[str, str] | None = None) -> None:
        raw = json.dumps(body, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(raw)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(raw)

    def _read_body(self) -> str:
        length = int(self.headers.get('Content-Length') or 0)
        if length <= 0:
            return ''
        if length > MAX_BODY_BYTES:
            raise ValueError('too_large')
        return self.rfile.read(length).decode('utf-8', errors='replace')

    def _dispatch(self, method: str) -> None:
        try:
            raw = self._read_body()
        except ValueError:
            self._respond(413, {'error': 'too_large',
                               'message': 'Запись больше допустимого размера.'})
            return
        response = handle(method, self.path, raw, **self.deps)
        self._respond(response.status, response.body, response.headers)

    def do_GET(self) -> None:  # noqa: N802 — имена заданы http.server
        self._dispatch('GET')

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch('POST')

    def log_message(self, fmt: str, *args: Any) -> None:
        # Тело запроса в лог не попадает никогда: там аудио и ключи.
        print('%s %s' % (self.command, self.path))


def make_server(host: str, port: int, settings: Settings, data_dir: Path) -> ThreadingHTTPServer:
    """Поднимает сервер, но не запускает его: так его можно проверить в тестах."""
    deps = build_dependencies(settings, data_dir)
    handler = type('BoundHandler', (Handler,), {'deps': deps, 'settings': settings})
    return ThreadingHTTPServer((host, port), handler)


def main() -> int:
    """Точка входа службы: настройки из окружения, данные рядом, порт из VV_PORT."""
    import os

    settings = load_settings()
    data_dir = Path(os.environ.get('VV_DATA_DIR') or './data')
    host = os.environ.get('VV_HOST') or '0.0.0.0'
    port = int(os.environ.get('VV_PORT') or '8080')
    health = settings.public_health()
    print('v-voice: трансляция %s, понимание %s'
          % ('готово' if health['can_transcribe'] else 'НЕ настроено',
             'готово' if health['can_understand'] else 'НЕ настроено'))
    make_server(host, port, settings, data_dir).serve_forever()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
