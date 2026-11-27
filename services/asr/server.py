"""Микросервис своего распознавания речи — бесплатно и на своём железе.

Зачем он отдельным контейнером, а не кодом внутри API: модель Whisper весит сотни мегабайт
и держит память при загрузке. В одном процессе с API она забирала бы память у записей и разбора.

Решение по модели (владелец 27.11.2026): хотели GigaAM-v3 от Сбера — по исследованию он лучше
для русского. На нашем сервере это невозможно: у него нет GPU с нужной памятью, а код GigaAM
рассчитан на CUDA. Поэтому взят faster-whisper: та же идея «открытая модель у нас», но работает
на процессоре. Это ОСОЗНАННАЯ замена, а не выбор «что проще»: русский у Whisper слабее GigaAM.

Контракт — как у прочих провайдеров речи, только по сети:
  POST /v1/transcribe  {audio_base64, language?}  ->  {segments: [{start_s,end_s,text}], model}
  GET  /v1/health                                  ->  {ok, model, device}
"""

from __future__ import annotations

import base64
import binascii
import json
import os
import tempfile
import threading
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

MODEL_NAME = os.environ.get('ASR_MODEL', 'small')
DEVICE = os.environ.get('ASR_DEVICE', 'cpu')
COMPUTE = os.environ.get('ASR_COMPUTE', 'int8')
LANGUAGE = os.environ.get('ASR_LANGUAGE', 'ru') or None
MODEL_DIR = os.environ.get('ASR_MODEL_DIR', '/models')
PORT = int(os.environ.get('ASR_PORT', '8090'))

_model: Any = None
_model_lock = threading.Lock()


def _load_model() -> Any:
    """Модель грузим один раз и держим: загрузка с диска занимает десятки секунд."""
    global _model
    with _model_lock:
        if _model is None:
            from faster_whisper import WhisperModel

            _model = WhisperModel(MODEL_NAME, device=DEVICE, compute_type=COMPUTE, download_root=MODEL_DIR)
        return _model


def _pcm_from_wav(data: bytes) -> tuple[Any, int]:
    """WAV -> массив float32 в диапазоне [-1, 1]. Без ffmpeg: наш API присылает именно WAV."""
    import numpy as np

    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as handle:
        handle.write(data)
        path = handle.name
    try:
        with wave.open(path, 'rb') as wav:
            channels = wav.getnchannels()
            width = wav.getsampwidth()
            rate = wav.getframerate()
            frames = wav.readframes(wav.getnframes())
    finally:
        os.unlink(path)
    if width != 2:
        raise ValueError('ожидается 16-битный WAV, получено ' + str(width * 8) + ' бит')
    samples = np.frombuffer(frames, dtype=np.int16).astype('float32') / 32768.0
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    return samples, rate


def transcribe(audio: bytes, language: str | None) -> dict[str, Any]:
    """Распознаёт запись целиком. Возвращает сегменты в общем формате провайдеров."""
    samples, rate = _pcm_from_wav(audio)
    model = _load_model()
    segments, info = model.transcribe(samples, language=language or LANGUAGE, vad_filter=True)
    out = []
    for seg in segments:
        text = (seg.text or '').strip()
        if text:
            out.append({'start_s': round(float(seg.start), 2), 'end_s': round(float(seg.end), 2), 'text': text})
    return {'segments': out, 'model': MODEL_NAME, 'language': getattr(info, 'language', None),
            'duration_s': round(len(samples) / float(rate), 2) if rate else 0.0}


class Handler(BaseHTTPRequestHandler):
    """Два пути и всё: проверка живости и распознавание."""

    def log_message(self, fmt: str, *args: Any) -> None:  # тише в логах контейнера
        return

    def _send(self, code: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 — имя задано http.server
        if self.path.rstrip('/') == '/v1/health':
            self._send(200, {'ok': True, 'model': MODEL_NAME, 'device': DEVICE, 'loaded': _model is not None})
            return
        self._send(404, {'error': 'not_found', 'message': 'Нет такого пути: ' + self.path})

    def do_POST(self) -> None:  # noqa: N802 — имя задано http.server
        if self.path.rstrip('/') != '/v1/transcribe':
            self._send(404, {'error': 'not_found', 'message': 'Нет такого пути: ' + self.path})
            return
        length = int(self.headers.get('Content-Length') or '0')
        try:
            payload = json.loads(self.rfile.read(length) or b'{}')
        except json.JSONDecodeError as exc:
            self._send(400, {'error': 'bad_json', 'message': 'Тело запроса не JSON: ' + exc.msg})
            return
        raw = payload.get('audio_base64') or ''
        try:
            audio = base64.b64decode(raw, validate=True)
        except (binascii.Error, ValueError):
            self._send(400, {'error': 'bad_audio', 'message': 'Звук не в base64.'})
            return
        if not audio:
            self._send(400, {'error': 'empty_audio', 'message': 'Пустой звук.'})
            return
        try:
            result = transcribe(audio, payload.get('language'))
        except ValueError as exc:
            self._send(400, {'error': 'bad_wav', 'message': str(exc)})
            return
        except Exception as exc:  # noqa: BLE001 — наружу отдаём причину, а не падение
            self._send(500, {'error': 'asr_failed', 'message': str(exc)[:300]})
            return
        self._send(200, result)


def main() -> None:
    """Поднимает сервер. Модель грузится лениво, чтобы /health отвечал сразу после старта."""
    server = ThreadingHTTPServer(('0.0.0.0', PORT), Handler)
    server.serve_forever()


if __name__ == '__main__':
    main()
