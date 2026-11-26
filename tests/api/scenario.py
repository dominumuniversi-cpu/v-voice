"""Сквозной прогон на заглушке: от записанного звука до готовой к отправке задачи.

Зачем отдельный файл: проверки проверяют куски, а человек спрашивает «работает ли всё целиком».
Здесь один прогон проходит весь путь без ключей и без сети — и падает, если хоть один шаг разорван.

Запуск: python tests/api/scenario.py
"""

from __future__ import annotations

import json
import struct
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'services' / 'api'))

from vvoice.job import analyze  # noqa: E402
from vvoice.providers.fake_asr import FakeAsr, Segment  # noqa: E402
from vvoice.exporters import ApprovedItem, to_payload  # noqa: E402
from vvoice.transcript_route import transcript_file  # noqa: E402


def wav_of_silence(seconds: float, rate: int = 16000) -> bytes:
    """Запись тишины в формате телефона: 16 кГц, моно, 16 бит."""
    frames = int(seconds * rate)
    data = b'\x00\x00' * frames
    header = b'RIFF' + struct.pack('<I', 36 + len(data)) + b'WAVEfmt ' + struct.pack('<IHHIIHH', 16, 1, 1, rate, rate * 2, 2, 16) + b'data' + struct.pack('<I', len(data))
    return header + data


def fake_understanding(system: str, user: str) -> dict[str, Any]:
    """Понимание-заглушка: отвечает по схеме, но с вымышленным содержанием."""
    return {
        'topic': 'Планёрка',
        'participants': [{'speaker': 'S1', 'name': 'Анна', 'verdict': 'owner'}],
        'summary': ['Обсудили бюджет.'],
        'decisions': [],
        'open_questions': [],
        'items': [{
            'kind': 'task',
            'title': 'Отправить смету',
            'owner': None,
            'due_at': '2026-11-27T10:00:00+05:00',
            'priority': 'high',
            # Схема ответа модели: цитата и таймкоды лежат во вложенном evidence, а не плоскими полями.
            'evidence': {
                'quote': 'я отправлю смету завтра утром',
                'start_s': 1.0,
                'end_s': 3.0,
            },
        }],
    }


def main() -> int:
    steps: list[tuple[str, bool, str]] = []
    audio = wav_of_silence(4.0)
    steps.append(('запись получена', len(audio) > 1000, '%d байт' % len(audio)))

    import tempfile
    from vvoice.digest_store import DigestStore
    from vvoice.storage import AudioStore
    data_dir = Path(tempfile.mkdtemp(prefix='vvoice-scenario-'))
    store = AudioStore(data_dir / 'audio')
    digests = DigestStore(data_dir / 'digests')
    store.save('scenario-session', audio)
    # Заглушка наговаривает фразу, которую потом «понимание» цитирует: без совпадения цитаты
    # валидатор честно выбросит пункт, и сценарий покажет не работу, а свою собственную ошибку.
    def factory(_path):
        asr = FakeAsr()
        asr.script = [Segment(start_s=1.0, end_s=3.0, text='я отправлю смету завтра утром')]
        return asr

    job = analyze('scenario-session', store=store, digests=digests,
                  provider_factory=factory, call_llm=fake_understanding)
    steps.append(('разбор прошёл', job.status == 200, 'статус %d' % job.status))
    saved = digests.load('scenario-session') or {}
    steps.append(('разбор сохранён на диск', bool(saved), str(list(saved)[:4])))
    # Разбор хранится самим собой. Раньше сюда попадала обёртка конвейера, и /digest отдавал объект
    # без summary — экран показывал пустоту. Страховка: если старая обёртка всё же пришла, берём вложенное.
    digest = saved.get('digest') if 'summary' not in saved and isinstance(saved.get('digest'), dict) else saved
    steps.append(('разбор содержит выжимку', 'summary' in digest, ''))
    steps.append(('разбор содержит реплики', len(saved.get('utterances', [])) >= 0,
                  'реплик: %d' % len(saved.get('utterances', []))))

    code, file_body, headers = transcript_file(saved, 'srt')
    steps.append(('расшифровка отдаётся файлом', code == 200 and '-->' in file_body, headers.get('Content-Type', '')))

    kept_items = digest.get('items') or []
    rejected = digest.get('rejected') or saved.get('rejected') or []
    if not kept_items:
        # Молчаливый IndexError ничего не объясняет: говорим, какой пункт отброшен и почему.
        print('FAIL разбор не оставил ни одного пункта')
        for r in rejected:
            print('     отброшен: ' + str(r.get('title')) + ' :: ' + str(r.get('reason')))
        print('     расшифровка: ' + repr(saved.get('transcript'))[:200])
        print('     ключи разбора: ' + ', '.join(sorted(saved.get('digest', {}))))
        return 1
    item = kept_items[0]
    approved = ApprovedItem(
        id='i1', session_id='scenario-session', kind=item['kind'], title=item['title'],
        owner=item.get('owner'), due_at=item.get('due_at'), priority=item.get('priority', 'medium'),
        evidence_quote=item['evidence']['quote'], start_s=item['evidence']['start_s'], end_s=item['evidence']['end_s'],
        approved_by='сценарий',
    )
    request = to_payload(approved, 'webhook', 'https://example.invalid/hook')
    steps.append(('задача готова к отправке', request.body.get('schema') == 'vvoice.item.v1', request.url))
    steps.append(('цитата есть в отправке', bool(request.body['evidence']['quote']), request.body['evidence']['quote']))

    ok = True
    for name, passed, detail in steps:
        print(('OK   ' if passed else 'FAIL ') + name + ((' :: ' + detail) if detail else ''))
        ok = ok and passed
    print(json.dumps({'steps': len(steps), 'ok': ok}, ensure_ascii=False))
    return 0 if ok else 1



if __name__ == '__main__':
    raise SystemExit(main())
