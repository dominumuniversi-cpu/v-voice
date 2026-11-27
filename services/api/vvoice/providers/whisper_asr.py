"""Whisper через сеть: своё распознавание на нашем сервере, без ключей и облака.

Почему отдельный сервис, а не модель внутри API: модель держит сотни мегабайт памяти,
и в одном процессе с записями она мешала бы всему остальному.

Честная граница: качество Whisper на русском ниже, чем у GigaAM-v3, но GigaAM требует CUDA,
а на нашем сервере видеокарты для него нет. Поэтому здесь Whisper — рабочая замена, а не идеал.
"""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from .fake_asr import Segment

DEFAULT_URL = os.environ.get('VV_ASR_URL', 'http://voice-asr:8090')
TIMEOUT_S = float(os.environ.get('VV_ASR_TIMEOUT', '600'))


@dataclass
class WhisperAsr:
    """Клиент к микросервису распознавания. Контракт — как у остальных провайдеров речи."""

    base_url: str = DEFAULT_URL
    language: str = 'ru'
    segments: list[Segment] = field(default_factory=list)

    def transcribe_file(self, path: str) -> list[Segment]:
        """Отправляет запись целиком и получает сегменты с временами."""
        with open(path, 'rb') as handle:
            audio = handle.read()
        payload = json.dumps({'audio_base64': base64.b64encode(audio).decode('ascii'),
                              'language': self.language}).encode('utf-8')
        request = urllib.request.Request(self.base_url.rstrip('/') + '/v1/transcribe', data=payload,
                                         headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_S) as resp:
                data = json.loads(resp.read().decode('utf-8'))
        except urllib.error.HTTPError as exc:
            detail = ''
            try:
                detail = json.loads(exc.read().decode('utf-8')).get('message', '')
            except Exception:  # noqa: BLE001 — сообщение уже есть кодом ошибки
                pass
            raise RuntimeError('распознавание не удалось: ' + (detail or str(exc.code))) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError('сервис распознавания недоступен: ' + str(exc.reason)) from exc
        self.segments = [Segment(start_s=float(s.get('start_s', 0.0)), end_s=float(s.get('end_s', 0.0)),
                                 text=str(s.get('text', '')).strip())
                         for s in data.get('segments', []) if str(s.get('text', '')).strip()]
        return self.segments
