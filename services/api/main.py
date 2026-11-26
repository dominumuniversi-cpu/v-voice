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

from vvoice.config import Settings, load as load_settings, load_env_file
from vvoice.digest_store import DigestStore
from vvoice.http_api import handle
from vvoice.live_sessions import LiveSessions
from vvoice.export_sender import send_request
from vvoice.provider_factory import describe as describe_providers, make_asr_factory
from vvoice.storage import AudioStore
from vvoice.vad import VadConfig, VadGate

MAX_BODY_BYTES = 12 * 1024 * 1024  # запись приходит base64, запас на JSON-обёртку


def build_dependencies(settings: Settings, data_dir: Path) -> dict[str, Any]:
    """Собирает всё, что нужно маршрутам. Ключи остаются в settings и наружу не передаются."""
    data_dir.mkdir(parents=True, exist_ok=True)
    return {
        'store': AudioStore(data_dir / 'audio'),
        'digests': DigestStore(data_dir / 'digests'),
        'live_sessions': LiveSessions(),
        # Распознавание речи: раньше сюда ничего не передавалось, и разбор не мог работать даже
        # с заполненным ключом. Теперь фабрика собирается из настроек, а отсутствие реализации
        # видно в /health, а не в молчаливом «ничего не произошло».
        'recognizer': make_asr_factory(settings),
        # Отсечение шума: без этого шум шёл в распознавание целиком, и код vad.py существовал,
        # но ни один запрос через него не проходил. None — только если человек сам выключил.
        'gate': VadGate(config=VadConfig()) if settings.noise_gate else None,
        # Отправка задач наружу. Без ключей интеграций маршрут честно отвечает 503:
        # настроек нет — значит и цели нет. С ключом задача уходит тем же отправителем.
        # Токен — по цели запроса: Helper, Jira и Bitrix24 разные сервисы и ждут разные ключи.
        'exporter': (lambda request: send_request(request, token=settings.token_for(request.target)))
                     if settings.export_targets else None,
        # Адреса целей — из настроек: телефон не должен знать, где живёт задачник.
        'export_targets': settings.export_targets,
        # Пусто — сервер открыт (режим разработки). Задан — без токена не пустим.
        'device_tokens': settings.device_tokens,
    }


def _safe_path(path: str) -> str:
    """Путь для лога без query-строки.

    Сейчас секретов в адресе нет, но одна привычка «положить токен в ссылку» — и он окажется
    в журнале навсегда: журналы копируют, пересылают и хранят дольше, чем сам токен живёт.
    """
    return path.split('?', 1)[0]


class Handler(BaseHTTPRequestHandler):
    """Переводит HTTP-запрос в вызов handle() и обратно."""

    server_version = 'v-voice/1'
    deps: dict[str, Any] = {}
    settings: Settings | None = None

    def _respond(self, status: int, body: Any, headers: dict[str, str] | None = None) -> None:
        # Строка — это файл (расшифровка в TXT/SRT): отдаём байты как есть, иначе человек вместо
        # субтитров получит JSON-обёртку с тем же текстом внутри. Всё остальное — JSON, как раньше.
        if isinstance(body, str):
            raw = body.encode('utf-8')
            default_type = 'text/plain; charset=utf-8'
        else:
            raw = json.dumps(body, ensure_ascii=False).encode('utf-8')
            default_type = 'application/json; charset=utf-8'
        self.send_response(status)
        self.send_header('Content-Type', (headers or {}).get('Content-Type', default_type))
        self.send_header('Content-Length', str(len(raw)))
        for name, value in (headers or {}).items():
            if name.lower() == 'content-type':
                continue  # уже отправлен выше с правильным значением
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
        # Токен устройства приходит заголовком, а не в теле: тело — это звук, и лишний разбор
        # большого запроса ради одного поля нам не нужен.
        token = (self.headers.get('Authorization') or '').removeprefix('Bearer ').strip() or None
        response = handle(method, self.path, raw, auth_token=token, **self.deps)
        self._respond(response.status, response.body, response.headers)

    def do_GET(self) -> None:  # noqa: N802 — имена заданы http.server
        self._dispatch('GET')

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch('POST')

    def log_message(self, fmt: str, *args: Any) -> None:
        # Тело запроса в лог не попадает никогда: там аудио и ключи.
        print('%s %s' % (self.command, _safe_path(self.path)))


def make_server(host: str, port: int, settings: Settings, data_dir: str | Path) -> ThreadingHTTPServer:
    """Поднимает сервер, но не запускает его: так его можно проверить в тестах.

    data_dir принимает и строку, и Path: вызывающий код приходит разный (в тестах mkdtemp
    отдаёт строку), и отказываться от неё из-за типа — ловушка для того, кто просто хочет запустить.
    """
    deps = build_dependencies(settings, Path(data_dir))
    handler = type('BoundHandler', (Handler,), {'deps': deps, 'settings': settings})
    return ThreadingHTTPServer((host, port), handler)


def main() -> int:
    """Точка входа службы: настройки из окружения, данные рядом, порт из VV_PORT."""
    import os

    # Человек заполняет .env, а не выставляет переменные руками: файл обязан применяться при запуске,
    # иначе все его правки молча игнорируются. Окружение сильнее файла — это позволяет CI подменить значение.
    env_file = os.environ.get('VV_ENV_FILE') or '.env'
    if os.path.exists(env_file):
        for key, value in load_env_file(env_file).items():
            os.environ.setdefault(key, value)
        print('v-voice: настройки прочитаны из %s' % env_file)

    settings = load_settings()
    data_dir = Path(os.environ.get('VV_DATA_DIR') or './data')
    # Дефолт — только свой компьютер: сервис записывает чужие разговоры, и «слушать везде»
    # должен быть осознанным выбором человека, а не следствием умолчания.
    host = os.environ.get('VV_HOST') or '127.0.0.1'
    port = int(os.environ.get('VV_PORT') or '8080')
    health = settings.public_health()
    providers = describe_providers(settings)
    if providers['asr_configured'] and not providers['asr_usable']:
        print('v-voice: провайдер %s настроен, но реализации нет — разбор речи не заработает'
              % providers['asr_configured'])
    if providers['llm_configured'] and not providers['llm_usable']:
        print('v-voice: понимание настроено на %s, но реализации нет — задачи из разговора не появятся'
              % providers['llm_configured'])
    print('v-voice: трансляция %s, понимание %s'
          % ('готово' if health['can_transcribe'] else 'НЕ настроено',
             'готово' if health['can_understand'] else 'НЕ настроено'))
    # Одна строка, которую человек прочитает в консоли: он должен видеть, открыт сервер или нет.
    if host in ('127.0.0.1', 'localhost'):
        print('v-voice: слушаю %s:%d — только этот компьютер' % (host, port))
    else:
        print('v-voice: слушаю %s:%d — доступен из сети' % (host, port))
        # Сервер хранит чужие разговоры. Пускать в сеть без замка нельзя: любой в той же Wi-Fi
        # прочитает расшифровки. Лучше не подняться и объяснить, чем работать открытым.
        if not settings.device_tokens:
            print('v-voice: ОТКАЗ — сервер открыт в сеть, но замка нет. Задайте VV_DEVICE_TOKENS '
                  '(список ключей устройств через запятую) или слушайте только свой компьютер '
                  '(VV_HOST=127.0.0.1).')
            return 2
    make_server(host, port, settings, data_dir).serve_forever()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
