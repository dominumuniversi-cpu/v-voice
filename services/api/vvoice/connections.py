"""Список подключений: провайдеры моделей, которые человек добавил сам, и какое из них активно.

Зачем это отдельно от настроек: раньше выбор провайдера был «одно поле на весь сервер».
Человек не мог держать рядом DeepSeek и Mistral, не мог добавить свой шлюз и не видел, что уже
добавлено. Теперь есть СПИСОК: добавил запись один раз, потом только выбираешь активную.

Правила, за которые этот файл отвечает:
  - связки живут в памяти процесса: ключ никогда не ложится на диск;
  - безымянный ключ не отправляем: у шлюзов с Cookie это проверка типа «есть ли ключ»;
  - адрес шлюза обязан быть http(s): иначе запрос уйдёт неизвестно куда;
  - встроенные связки (дальше — «встроенные») не удаляются: иначе человек останется без выбора.
"""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any

# Виды записей. `llm` — разбор разговора, `asr` — распознавание речи.
KINDS = ('llm', 'asr')

# Протоколы запросов. Встроенные шлюзы на OpenAI-совместимом протоколе добавляются как `openai`.
PROTOCOLS: dict[str, str] = {
    'openai': 'OpenAI-совместимый (chat/completions)',
    'anthropic': 'Anthropic Messages',
    'ollama': 'Ollama (свой сервер)',
    'deepseek': 'DeepSeek',
    'zai': 'Z.AI (GLM)',
    'mistral': 'Mistral',
    'speechmatics': 'Speechmatics (облако)',
    'whisper': 'Своя модель на нашем сервере',
    'fake': 'Заглушка (без сети)',
}

# Какие протоколы бывают у какого вида связи. Экран «Добавить» берёт выпадающий список отсюда:
# человек выбирает провайдера для разбора или для речи, а не угадывает по общему списку.
PROTOCOLS_BY_KIND: dict[str, tuple[tuple[str, str], ...]] = {
    'llm': (
        ('mistral', 'Mistral'),
        ('zai', 'Z.AI (GLM)'),
        ('deepseek', 'DeepSeek'),
        ('anthropic', 'Claude (Anthropic)'),
        ('openai', 'Свой шлюз (OpenAI-совместимый)'),
        ('ollama', 'Ollama (свой сервер)'),
        ('fake', 'Демо-заглушка (без сети)'),
    ),
    'asr': (
        ('whisper', 'Своя модель на нашем сервере (бесплатно)'),
        ('speechmatics', 'Speechmatics (облако)'),
        ('fake', 'Демо-заглушка (расшифровка выдумана)'),
    ),
}

_ID_RE = re.compile(r'^[a-z0-9][a-z0-9_-]{0,31}$')


BUILTIN_CONNECTIONS: tuple[dict[str, Any], ...] = (
    # Продавать «бесплатно» без оговорки нельзя, поэтому в каждого встроенного — цена и правда.
    {'id': 'deepseek', 'kind': 'llm', 'protocol': 'deepseek', 'title': 'DeepSeek',
     'model': 'deepseek-chat', 'cost': 'платно, копейки за встречу',
     'note': 'Ключ — на platform.deepseek.com. Хорошо разбирает русскую речь в задачи.'},
    {'id': 'zai', 'kind': 'llm', 'protocol': 'zai', 'title': 'Z.AI (GLM)',
     'model': 'glm-4.6', 'cost': 'платно, есть дешёвые модели',
     'note': 'Ключ — на z.ai. Адрес api.z.ai/api/paas/v4, модели GLM.'},
    {'id': 'mistral', 'kind': 'llm', 'protocol': 'mistral', 'title': 'Mistral',
     'model': 'mistral-small-latest', 'cost': 'платно, есть бесплатный уровень с лимитом',
     'note': 'Ключ — на console.mistral.ai. Русский понимает, но слабее DeepSeek.'},
    {'id': 'anthropic', 'kind': 'llm', 'protocol': 'anthropic', 'title': 'Claude Sonnet',
     'model': 'claude-sonnet-4-5', 'cost': 'платно',
     'note': 'Ключ — на console.anthropic.com. Аккуратно отдаёт JSON.'},
    {'id': 'ollama-local', 'kind': 'llm', 'protocol': 'ollama', 'title': 'Ollama на своём сервере',
     'base_url': 'http://127.0.0.1:11434', 'model': 'qwen3:8b',
     'cost': 'бесплатно, работает на вашем железе',
     'note': 'Нужен запущенный ollama и скачанная модель. Адрес обязателен: из контейнера '
             '127.0.0.1 — это сам контейнер.'},
    {'id': 'fake-demo', 'kind': 'llm', 'protocol': 'fake', 'title': 'Демо-заглушка (разбор)',
     'cost': 'бесплатно', 'note': 'Показывает весь путь, но текст выдуман. Для проверки экранов.'},
    {'id': 'speechmatics', 'kind': 'asr', 'protocol': 'speechmatics', 'title': 'Speechmatics',
     'cost': 'платно, есть пробный период',
     'note': 'Ключ — на portal.speechmatics.com. Бесплатного режима нет, после пробного — оплата.'},
    {'id': 'whisper-local', 'kind': 'asr', 'protocol': 'whisper', 'title': 'Своё распознавание (Whisper)',
     'cost': 'бесплатно, работает на нашем железе',
     'note': 'Открытая модель на процессоре рядом с сервером: ни ключа, ни оплаты за минуты. '
             'Качество ниже, чем у GigaAM-v3 (ему нужна видеокарта, которой у нас нет).'},
    {'id': 'fake-asr', 'kind': 'asr', 'protocol': 'fake', 'title': 'Демо-заглушка (распознавание)',
     'cost': 'бесплатно', 'note': 'Расшифровка выдумана, но весь путь проходит целиком.'},
)


@dataclass
class Connection:
    """Одна добавленная связка: где звать, чем платить, какой моделью."""

    id: str
    kind: str
    protocol: str
    title: str
    base_url: str = ''
    model: str = ''
    key: str = ''
    builtin: bool = False
    note: str = ''
    cost: str = ''
    added: float = 0.0
    _touch: float = field(default=0.0, repr=False)

    def public(self) -> dict[str, Any]:
        """Что можно показать: ключ — только фактом «есть» и последними четырьмя символами."""
        return {
            'id': self.id, 'kind': self.kind, 'protocol': self.protocol, 'title': self.title,
            'base_url': self.base_url, 'model': self.model, 'builtin': self.builtin,
            'note': self.note, 'cost': self.cost,
            'key_set': bool(self.key), 'key_hint': _hint(self.key),
        }


def _hint(key: str) -> str:
    """Хвост ключа: по нему человек узнаёт «тот ли ключ», но восстановить ключ нельзя."""
    if not key:
        return ''
    return '…' + key[-4:] if len(key) > 4 else 'задан'


def _check_url(url: str) -> str:
    """Адрес шлюза: пустой допустим только у встроенных без сети, иначе обязан быть http(s)."""
    url = (url or '').strip()
    if not url:
        return ''
    if '://' not in url:
        url = 'https://' + url
    if not (url.startswith('http://') or url.startswith('https://')):
        raise ValueError('адрес должен начинаться с http:// или https://')
    return url


@dataclass
class ConnectionList:
    """Список связок с активной записью для каждого вида. Потокобезопасен простым замком."""

    items: list[Connection] = field(default_factory=list)
    active: dict[str, str] = field(default_factory=dict)
    _lock: Any = field(default_factory=threading.Lock, repr=False)

    # --- чтение -------------------------------------------------------------

    def all(self) -> list[dict[str, Any]]:
        with self._lock:
            return [c.public() for c in self.items]

    def find(self, conn_id: str) -> Connection | None:
        with self._lock:
            for c in self.items:
                if c.id == conn_id:
                    return c
        return None

    def active_for(self, kind: str) -> Connection | None:
        """Связка вида, которой сервер работает сейчас. Нет выбранной — None, а не «какая-нибудь».

        Раньше здесь отдавалась первая связка вида. Это давало работу без выбора человека:
        достаточно было открыть список, и сервер уже звал незаказанного провайдера.
        """
        with self._lock:
            want = self.active.get(kind)
            if not want:
                return None
            for c in self.items:
                if c.id == want and c.kind == kind:
                    return c
        return None

    def view(self) -> dict[str, Any]:
        """Всё, что нужно экрану: список, активные и что из этого работает без ключа."""
        with self._lock:
            # «Активная» — та, которой сервер РАБОТАЕТ, а не только имя выбранной строки.
            # active_for отдаёт первую связку вида, если выбор сбросился (удалили активную) —
            # экран должен показывать то же, что идёт в работу, иначе человек видит одну,
            # а работает другая. Считаем по self.items напрямую: active_for берёт тот же замок,
            # и RLock из фонового потока дал бы дедлок на запросе /health.
            in_work: dict[str, str] = {}
            # Активных подключений по умолчанию НЕТ: пока человек сам не нажал «Работать этой»,
            # сервер не берёт ни провайдера по привычке, ни «первую попавшуюся» связку.
            # Иначе панель обещает работу, которой человек не выбирал.
            for kind in ('llm', 'asr'):
                want = self.active.get(kind)
                if want and any(c.id == want and c.kind == kind for c in self.items):
                    in_work[kind] = want
            return {'items': [c.public() for c in self.items],
                    'active': dict(self.active),
                    'in_work': in_work,
                    'protocols': {kind: [{'value': v, 'title': t} for v, t in pairs]
                                  for kind, pairs in PROTOCOLS_BY_KIND.items()}}

    # --- изменение ----------------------------------------------------------

    def seed(self, connection: Connection) -> None:
        """Добавляет встроенную связку или обновляет её, но НЕ трогает уже введённый ключ."""
        with self._lock:
            for c in self.items:
                if c.id == connection.id:
                    c.title, c.protocol, c.base_url = connection.title, connection.protocol, connection.base_url
                    c.model = c.model or connection.model
                    c.note, c.cost = connection.note, connection.cost
                    return
            connection.builtin = True
            connection.added = time.time()
            self.items.append(connection)

    def add(self, raw: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Добавляет связку. Ошибка — код и текст, который человек может понять без программиста."""
        kind = str(raw.get('kind') or '').strip().lower()
        if kind not in KINDS:
            return 400, {'error': 'bad_kind', 'message': 'Неизвестный вид связи: ' + (kind or 'пусто')
                                    + '. Ожидается llm (разбор) или asr (распознавание).'}
        protocol = str(raw.get('protocol') or '').strip().lower()
        if protocol not in PROTOCOLS:
            return 400, {'error': 'bad_protocol',
                         'message': 'Неизвестный протокол «' + (protocol or 'пусто') + '». Доступно: '
                                    + ', '.join(sorted(PROTOCOLS)) + '.'}
        title = str(raw.get('title') or '').strip()
        if not title:
            return 400, {'error': 'bad_title', 'message': 'Дайте связке имя — по нему вы будете её узнавать. '
                                                         'Например: «Mistral (мой ключ)».'}
        conn_id = str(raw.get('id') or '').strip().lower()
        if not conn_id:
            conn_id = self._slug(title)
        if not _ID_RE.match(conn_id):
            return 400, {'error': 'bad_id',
                         'message': 'Имя для ссылки («' + conn_id + '») может содержать только латинские буквы, '
                                    'цифры, дефис и подчёркивание.'}
        try:
            base_url = _check_url(str(raw.get('base_url') or ''))
        except ValueError as exc:
            return 400, {'error': 'bad_url', 'message': 'Адрес не принят: ' + str(exc) + '.'}
        if protocol in ('openai', 'anthropic') and not base_url:
            return 400, {'error': 'need_url',
                         'message': 'Для своего шлюза нужен адрес: без него непонятно, куда отправлять запрос.'}
        with self._lock:
            if any(c.id == conn_id for c in self.items):
                return 409, {'error': 'already_exists', 'id': conn_id,
                             'message': 'Связка с таким именем уже есть. Выберите другое имя.'}
            conn = Connection(id=conn_id, kind=kind, protocol=protocol, title=title, base_url=base_url,
                              model=str(raw.get('model') or '').strip(), key=str(raw.get('key') or '').strip(),
                              note='добавлено вами', cost=str(raw.get('cost') or 'условия у провайдера').strip(),
                              added=time.time())
            self.items.append(conn)
            # Первая связка вида сразу становится рабочей: иначе человек добавил и «ничего не произошло».
            if not self.active.get(kind):
                self.active[kind] = conn_id
            return 201, {'connection': conn.public(), 'active': dict(self.active),
                         'message': 'Связка «' + title + '» добавлена.'}

    def update_key(self, conn_id: str, key: str, model: str | None = None,
                   base_url: str | None = None, title: str | None = None) -> tuple[int, dict[str, Any]]:
        """Меняет ключ/модель/адрес/имя у записи. Пустой ключ значит «стереть прежний»."""
        with self._lock:
            conn = next((c for c in self.items if c.id == conn_id), None)
            if conn is None:
                return 404, {'error': 'not_found', 'message': 'Такой связки нет.'}
            if key:
                conn.key = key.strip()
            else:
                # Пустой ключ — «уберите прежний»: человек не должен остаться с чужим ключом,
                # который он не может увидеть и потому не может проверить.
                conn.key = ''
            if model is not None:
                conn.model = model.strip()
            if title is not None:
                conn.title = title.strip() or conn.title
            if base_url is not None:
                try:
                    conn.base_url = _check_url(base_url)
                except ValueError as exc:
                    return 400, {'error': 'bad_url', 'message': 'Адрес не принят: ' + str(exc) + '.'}
            return 200, {'connection': conn.public(), 'message': 'Сохранено.'}

    def remove(self, conn_id: str) -> tuple[int, dict[str, Any]]:
        """Удаляет связку. Встроенную — нельзя: экран без выбора оставит человека без пути назад."""
        with self._lock:
            conn = next((c for c in self.items if c.id == conn_id), None)
            if conn is None:
                return 404, {'error': 'not_found', 'message': 'Такой связки нет.'}
            if conn.builtin:
                return 409, {'error': 'builtin', 'message': 'Встроенную связку удалить нельзя — иначе не из чего выбирать.'}
            self.items = [c for c in self.items if c.id != conn_id]
            if self.active.get(conn.kind) == conn_id:
                # Удалили рабочую — вид остаётся без рабочей связки. Подставлять первую попавшуюся
                # нельзя: человек не выбирал её, и сервер молча пошёл бы звать чужого провайдера.
                self.active[conn.kind] = ''
            return 200, {'removed': conn_id, 'active': dict(self.active),
                         'message': 'Связка «' + conn.title + '» удалена.'}

    def activate(self, kind: str, conn_id: str) -> tuple[int, dict[str, Any]]:
        """Делает связку активной — то есть именно ею сервер будет работать."""
        with self._lock:
            conn = next((c for c in self.items if c.id == conn_id), None)
            if conn is None or conn.kind != kind:
                return 404, {'error': 'not_found',
                             'message': 'Такой связки для ' + ('разбора' if kind == 'llm' else 'распознавания')
                                        + ' нет.'}
            self.active[kind] = conn_id
            return 200, {'active': dict(self.active),
                         'message': 'Активная связка: «' + conn.title + '».'}

    def _slug(self, title: str) -> str:
        """Имя для ссылок из названия: латиница и цифры, остальное — дефис."""
        table = str.maketrans({'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e', 'ж': 'zh',
                               'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o',
                               'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'h', 'ц': 'c',
                               'ч': 'ch', 'ш': 'sh', 'щ': 'sch', 'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu',
                               'я': 'ya'})
        slug = title.lower().translate(table)
        slug = re.sub(r'[^a-z0-9]+', '-', slug).strip('-')[:32]
        if slug and _ID_RE.match(slug) and not any(c.id == slug for c in self.items):
            return slug
        return 'conn-' + str(int(time.time() * 1000))[-8:]
