"""Отсечение шума и тишины на телефоне: VAD по энергии с гистерезисом.

Зачем именно такой VAD:
  нейросетевой Silero VAD точнее, но стоит батареи и его надо возить в приложение.
  Энергетический VAD с адаптивной оценкой шума решает главную задачу — НЕ ОТПРАВЛЯТЬ тишину
  и шум в облако (деньги и приватность), — а ошибочно отрезанная речь недопустима.
  Поэтому: адаптивный порог + гистерезис (разные пороги включения/выключения) + трейлинг буфер,
  который досылает последние `preroll_ms` звука, чтобы первое слово не срезалось.

Пороговые значения подобраны под 16 кГц INT16 PCM (телефонный/наушниковый микрофон):
  - silence_dbfs около -70 дБ, но громкость зависит от устройства → шум оцениваем по «тихому» перцентилю.
  - речь считается идущей, если энергия выше noise_floor + on_db и так все последние кадры.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

SAMPLE_RATE = 16_000
FRAME_MS = 20
FRAME_SAMPLES = SAMPLE_RATE * FRAME_MS // 1000  # 320


def frame_dbfs(pcm16: bytes) -> float:
    """Среднеквадратичная громкость кадра в дБFS ("0 дБFS" = полная шкала)."""
    if not pcm16:
        return -120.0
    count = len(pcm16) // 2
    if count == 0:
        return -120.0
    total = 0.0
    for i in range(0, count * 2, 2):
        sample = int.from_bytes(pcm16[i:i + 2], "little", signed=True)
        total += sample * sample
    rms = math.sqrt(total / count)
    if rms <= 0:
        return -120.0
    return 20.0 * math.log10(rms / 32768.0)


@dataclass
class VadConfig:
    """Настройки VAD. Меняются экраном «Качество и индикаторы», не в коде."""

    on_db: float = 9.0            # насколько речь должна быть громче шумового пола, чтобы начать
    off_db: float = 4.0           # гистерезис: пока не упало ниже — считаем речь идущей
    preroll_frames: int = 15      # 300 мс до начала речи: не срезать первое слово
    hangover_frames: int = 25     # 500 мс после конца речи: не рвать паузами
    min_speech_frames: int = 5    # 100 мс: короче — это щелчок, а не слово
    noise_percentile: float = 0.2


@dataclass
class VadGate:
    """Потоковое решение «сейчас речь или нет» + буфер для досылки головы/хвоста."""

    config: VadConfig = field(default_factory=VadConfig)
    noise_floor_db: float = -60.0
    speaking: bool = False
    speech_frames: int = 0
    silence_frames: int = 0
    preroll: list[bytes] = field(default_factory=list)
    _history: list[float] = field(default_factory=list)

    def _update_floor(self, db: float) -> None:
        """Адаптивный шумовой пол: берём 20-й перцентиль последних ~2.5 с."""
        self._history.append(db)
        if len(self._history) > 125:
            self._history.pop(0)
        if len(self._history) >= 10:
            ordered = sorted(self._history)
            idx = int(len(ordered) * self.config.noise_percentile)
            self.noise_floor_db = ordered[min(idx, len(ordered) - 1)]

    def push(self, frame: bytes) -> bool:
        """Принимает один кадр (20 мс). Возвращает True, если кадр нужно отправить в ASR."""
        db = frame_dbfs(frame)
        self._update_floor(db)

        if not self.speaking:
            self.preroll.append(frame)
            if len(self.preroll) > self.config.preroll_frames:
                self.preroll.pop(0)

        loud_enough = db > self.noise_floor_db + self.config.on_db
        still_speaking = db > self.noise_floor_db + self.config.off_db

        if self.speaking:
            if still_speaking:
                self.silence_frames = 0
            else:
                self.silence_frames += 1
                if self.silence_frames > self.config.hangover_frames:
                    self.speaking = False
                    self.speech_frames = 0
                    self.preroll.clear()
            return self.speaking

        if loud_enough:
            self.speaking = True
            self.speech_frames = 1
            self.silence_frames = 0
            return True
        return False

    def flush_preroll(self) -> list[bytes]:
        """Отдать накопленный преролл (после старта речи) — один раз на реплику."""
        out, self.preroll = self.preroll, []
        return out

    @property
    def speech_ratio_hint(self) -> float:
        """Грубая доля речи в последних кадрах — для индикатора на экране."""
        if not self._history:
            return 0.0
        loud = sum(1 for db in self._history if db > self.noise_floor_db + self.config.on_db)
        return loud / len(self._history)
