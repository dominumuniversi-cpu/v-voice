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
import os
from pathlib import Path
from typing import Any

from vvoice.config import Settings, load as load_settings, load_env_file
from vvoice.connections import ConnectionList
from vvoice.connections_file import ConnectionFiles
from vvoice.settings_file import SettingsFile
from vvoice.runtime_settings import RuntimeSettings
from vvoice.digest_store import DigestStore
from vvoice.http_api import handle
from vvoice.live_sessions import LiveSessions
from vvoice.export_sender import send_request
from vvoice.provider_factory import (IMPLEMENTED_LLM, PROTOCOL_TO_ASR, PROTOCOL_TO_LLM,
                                     describe as describe_providers, make_asr_factory)
from vvoice.providers.llm_send import make_call_llm
from vvoice.storage import AudioStore
from vvoice.vad import VadConfig, VadGate

MAX_BODY_BYTES = 12 * 1024 * 1024  # запись приходит base64, запас на JSON-обёртку


class _SilentStream:
    """Провайдер живого потока, который честно ничего не слышит.

    Нужен для своего распознавания: Whisper принимает только целый файл. Молчать в живом
    тексте лучше, чем показывать выдуманные слова; запись всё равно разберётся после «Стоп».
    """

    def stream(self, chunk: bytes) -> list:
        return []

    def transcribe_file(self, path: str) -> list:
        raise RuntimeError('своё распознавание работает по целому файлу, а не по кускам')


def build_dependencies(settings: Settings, data_dir: Path) -> dict[str, Any]:
    """Собирает всё, что нужно маршрутам. Ключи остаются в settings и наружу не передаются."""
    data_dir.mkdir(parents=True, exist_ok=True)
    # Стартуем с того, что задано в окружении: иначе сервер запускается с пустыми настройками
    # и первое же открытие экрана стирает рабочую связку из .env. Что человек поменял в браузере,
    # живёт дольше одного запроса, но не дольше процесса: ключ никто не сохраняет на диск.
    # Значения из файла важнее окружения: окружение — точка старта, а ключ человек ввёл на
    # экране настроек, и перезапуск контейнера не должен его стирать.
    saved = SettingsFile(data_dir / "settings.json").load()
    runtime = RuntimeSettings(**{
        'asr_provider': settings.asr_provider, 'asr_key': settings.asr_key,
        'asr_model': settings.asr_model, 'llm_provider': settings.llm_provider,
        'llm_key': settings.llm_key, 'llm_model': settings.llm_model,
        'llm_base_url': settings.llm_base_url, **saved})

    # Список подключений: только то, что человек завёл сам, и связка, которую он выбрал рабочей.
    # Пустых заготовок провайдеров здесь нет — они живут в каталоге (BUILTIN_CONNECTIONS) и
    # попадают в список, лишь когда человек нажмёт «Добавить».
    connections = ConnectionList()
    # Заведённые ранее связки возвращаем с диска: пересборка контейнера не должна стирать ключи,
    # которые человек ввёл в настройках приложения.
    conn_files = ConnectionFiles(data_dir / "connections.json")
    connections.restore(conn_files.load(), conn_files.load_active())

    def asr_factory(path: str) -> Any:
        """Собирает распознавание на момент вызова: ключ мог поменяться только что."""
        # Живой текст приходит кусками и зовёт фабрику на каждый кусок. Распознавание файла там
        # не нужно вовсе: раньше whisper-клиент на каждый кусок гнал в модель пустой путь, сервис
        # отвечал «нет такого файла», и живой текст не работал никогда. Для живого потока отдаём
        # провайдера без файла; файловый проход пошлёт звук ровно один раз.
        if not path or not os.path.exists(path):
            return _live_asr(settings, connections)
        conn = connections.active_for('asr')
        if conn is not None:
            provider = PROTOCOL_TO_ASR.get(conn.protocol, conn.protocol)
            live = _with(settings, asr_provider=provider, asr_key=conn.key or settings.asr_key,
                         asr_model=conn.model or settings.asr_model,
                         asr_base_url=conn.base_url or _own_asr_url(settings, provider))
            return make_asr_factory(live)(path)
        chosen = runtime.asr()
        provider = chosen['provider']
        live = (settings if not provider else
                _with(settings, asr_provider=provider, asr_key=chosen['key'] or settings.asr_key,
                      asr_model=chosen['model'] or settings.asr_model,
                      asr_base_url=chosen.get('base_url') or _own_asr_url(settings, provider)))
        return make_asr_factory(live)(path)

    def _live_asr(settings: Settings, connections: Any) -> Any:
        """Распознавание для живого потока: умеет куски, но не файл.

        Настоящий стриминг сегодня есть у Speechmatics. Своё распознавание (Whisper) и
        провайдеры «загрузим файл целиком» в живом потоке честно молчат: придуманный текст
        хуже отсутствия текста, а запись всё равно разберётся после «Стоп».
        """
        conn = connections.active_for('asr')
        protocol = conn.protocol if conn is not None else (settings.asr_provider or '').strip().lower()
        key = (conn.key if conn is not None else '') or settings.asr_key
        if protocol == 'speechmatics' and (key or '').strip():
            from .vvoice.providers.speechmatics import SpeechmaticsAsr
            from .vvoice.providers.ws_connect import connect_websocket
            client = SpeechmaticsAsr(connect=connect_websocket, api_key=key.strip())
            client.open()
            return client
        return _SilentStream()

    def _call_understanding(system: str, user: str) -> dict:
        """Вызов модели так, как его ждёт разбор. Нечем звать — говорим причину, а не падаем TypeError."""
        understanding = llm_factory()
        if understanding is None:
            raise RuntimeError('модель разбора не настроена: выберите связку и введите ключ '
                               'на экране «Подключить модели»')
        if not callable(understanding):
            raise RuntimeError('внутренняя ошибка: понимание собрано не как функция вызова')
        return understanding(system, user)

    def llm_factory() -> Any:
        """Понимание собирается в момент разбора: человек мог сменить модель минуту назад."""
        conn = connections.active_for('llm')
        if conn is not None:
            provider = PROTOCOL_TO_LLM.get(conn.protocol, conn.protocol)
            live = _with(settings, llm_provider=provider, llm_key=conn.key,
                         llm_model=conn.model or settings.llm_model,
                         llm_base_url=conn.base_url or settings.llm_base_url)
            return _make_understanding(live)
        chosen = runtime.llm()
        provider = chosen['provider']
        live = (settings if not provider else
                _with(settings, llm_provider=provider, llm_key=chosen['key'] or settings.llm_key,
                      llm_model=chosen['model'] or settings.llm_model,
                      llm_base_url=chosen['base_url'] or settings.llm_base_url))
        return _make_understanding(live)

    return {
        'settings': runtime,
        'settings_file': SettingsFile(data_dir / "settings.json"),
        'connections_file': conn_files,
        'asr_env': (settings.asr_provider or '').strip().lower(),
        'llm_env': (settings.llm_provider or '').strip().lower(),
        'connections': connections,
        'store': AudioStore(data_dir / 'audio'),
        'digests': DigestStore(data_dir / 'digests'),
        'live_sessions': LiveSessions(),
        # Распознавание речи: раньше сюда ничего не передавалось, и разбор не мог работать даже
        # с заполненным ключом. Теперь фабрика собирается из настроек, а отсутствие реализации
        # видно в /health, а не в молчаливом «ничего не произошло».
        'recognizer': asr_factory,
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
        # Понимание разговора: без модели задачи из встречи не появятся. Раньше сюда ничего
        # не передавалось, и «осмысленный разбор» не мог работать даже с заполненным ключом.
        # Заглушка включается только явным VV_LLM_PROVIDER=fake и не требует ключа: иначе демо
        # без ключей невозможно, и человек видит «сервер не настроен» вместо работы пути.
        # Конвейер зовёт это как call_llm(system, user) -> dict. Раньше сюда клали саму фабрику
        # без вызова, и разбор падал TypeError у ЛЮБОГО провайдера: экран настраивал модель,
        # а разбор не мог её позвать. Обёртка собирает понимание в момент запроса.
        'call_llm': _call_understanding,
        # Пусто — сервер открыт (режим разработки). Задан — без токена не пустим.
        'device_tokens': settings.device_tokens,
        # Тариф для расчёта стоимости встречи. 0 — цена не считается и не выдумывается.
        'asr_price_per_hour': settings.asr_price_per_hour,
        'budget_per_meeting': settings.budget_per_meeting,
    }


def _own_asr_url(settings: Settings, provider: str) -> str:
    """Адрес распознавания из окружения — только своему провайдеру.

    VV_ASR_BASE_URL описывает ОДИН сервис. Раньше он подставлялся любому провайдеру, и связка
    Deepgram уходила на адрес Speechmatics: звук не туда, деньги мимо. Чужой адрес не берём.
    """
    stored = (getattr(settings, 'asr_base_url', '') or '').strip()
    owner = (getattr(settings, 'asr_provider', '') or '').strip().lower()
    if stored and provider and owner == provider:
        return stored
    return ''


def _make_understanding(settings: Any) -> Any:
    """Что зовёт разбор: настоящая модель или явно включённая заглушка."""
    provider = (settings.llm_provider or '').strip().lower()
    if provider == 'fake':
        from vvoice.providers.fake_llm import make_fake_llm
        return make_fake_llm()
    if provider in IMPLEMENTED_LLM and settings.llm_key:
        # Модель и адрес — из настроек: пустая строка значит «как у провайдера по умолчанию»,
        # а выбор модели на странице должен долетать до самого запроса, иначе это надпись.
        return make_call_llm(provider, getattr(settings, 'llm_model', '') or '',
                             settings.llm_key, getattr(settings, 'llm_base_url', '') or '')
    return None


def _strip_prefix(path: str) -> str:
    """Снимает префикс стенда /voice, чтобы маршруты не зависели от того, где живёт сервис.

    Локально сервер отвечает на /api/v1/health, за nginx — на /voice/api/v1/health.
    Один и тот же код не должен знать, куда его поставили.
    """
    for prefix in ('/voice',):
        if path == prefix:
            return '/'
        if path.startswith(prefix + '/'):
            return path[len(prefix):]
    return path


def _with(settings: Settings, **changes: Any) -> Settings:
    """Копия настроек с заменой полей: работающий процесс не должен переписывать сам себя.

    dataclasses.replace здесь не подходит: Settings из другого модуля и собирается своим
    загрузчиком, а копирование через copy с явными полями оставляет один источник правды.
    """
    import copy
    clone = copy.copy(settings)
    for name, value in changes.items():
        object.__setattr__(clone, name, value)
    return clone


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
        # субтитров получит JSON-обёртку с тем же текстом внутри. Байты — это звук записи.
        # Всё остальное — JSON, как раньше.
        if isinstance(body, bytes):
            raw = body
            default_type = (headers or {}).get('Content-Type', 'application/octet-stream')
        elif isinstance(body, str):
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
        """Тело запроса строкой. Длина берётся из заголовка: потоковое чтение до конца здесь не нужно."""
        length = int(self.headers.get('Content-Length') or 0)
        if length <= 0:
            return ''
        if length > MAX_BODY_BYTES:
            raise ValueError('too_large')
        return self.rfile.read(length).decode('utf-8', errors='replace')

    def _serve_page(self) -> bool:
        """Отдаёт веб-экран стенда на /voice/ и /voice.

        Токен здесь не проверяется намеренно: страница — это поле ввода, без неё человек
        не сможет ввести токен вовсе. Защищены только данные, то есть /api/v1/*.
        """
        path = _safe_path(self.path)
        if path not in ('/voice', '/voice/', '/voice/index.html'):
            return False
        page = Path(__file__).resolve().parent / 'web' / 'index.html'
        if not page.exists():
            self._respond(404, {'error': 'no_page', 'message': 'Веб-экран не найден в образе.'})
            return True
        body = page.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        # Страницу не кэшируем: стенд обновляется, и старый экран путает больше, чем экономит.
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)
        return True

    def _dispatch(self, method: str) -> None:
        if method == 'GET' and self._serve_page():
            return
        # Стенд живёт под /voice/ за nginx, и префикс приходит внутри пути. Без снятия
        # /voice/api/v1/health превратится в 404, хотя сервер здоров.
        self.path = _strip_prefix(self.path)
        try:
            raw = self._read_body()
        except ValueError:
            self._respond(413, {'error': 'too_large',
                               'message': 'Запись больше допустимого размера.'})
            return
        # Токен устройства приходит заголовком, а не в теле: тело — это звук, и лишний разбор
        # большого запроса ради одного поля нам не нужен. Для ссылок (прослушать запись, скачать
        # расшифровку) токен допустим и в строке запроса: браузер не умеет слать заголовок
        # на <audio> и на обычное скачивание. Открытого пути это не создаёт — токен всё тот же.
        token = (self.headers.get('Authorization') or '').removeprefix('Bearer ').strip()
        if not token and '?' in self.path:
            from urllib.parse import parse_qs
            token = (parse_qs(self.path.split('?', 1)[1]).get('token') or [''])[0].strip()
        response = handle(method, self.path, raw, auth_token=token or None, **self.deps)
        self._respond(response.status, response.body, response.headers)

    def do_GET(self) -> None:  # noqa: N802 — имена заданы http.server
        self._dispatch('GET')

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch('POST')

    # Список подключений меняется по-настоящему: ключ, адрес и удаление — это PATCH и DELETE.
    # Без этих двух методов сервер отвечал 501, и кнопки «Сменить ключ» и «Удалить» не работали бы.
    def do_PATCH(self) -> None:  # noqa: N802
        self._dispatch('PATCH')

    def do_DELETE(self) -> None:  # noqa: N802
        self._dispatch('DELETE')

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
        if providers['asr_implemented']:
            # Провайдер реализован, значит мешает не он. Самая частая причина — не установлена
            # библиотека; говорить «реализации нет» в этом случае значит отправлять человека
            # искать ошибку в коде, которого нет.
            print('v-voice: провайдер %s настроен, но не может запуститься — проверьте установку '
                  'зависимостей (pip install -r requirements.txt)' % providers['asr_configured'])
        else:
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
