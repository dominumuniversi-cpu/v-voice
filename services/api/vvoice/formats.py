"""Экспорт расшифровки (FR-11): TXT, Markdown, SRT, VTT.

Форматы кажутся скучной частью, пока не попробуешь импортировать файл в плеер или в таймкод
видеоредактора. Тогда вылезает всё сразу:
  - SRT требует запятую в долях секунды, VTT — точку и заголовок WEBVTT;
  - в SRT/VTT нельзя пустую строку внутри текста (она режет субтитр на два);
  - время в SRT округляется вниз или вверх — от этого субтитр «съезжает».
Поэтому форматирование времени — отдельная функция с тестами на границы (59.999 c, 3600 c).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Line:
    start_s: float
    end_s: float
    text: str
    speaker: str = ""


def _stamp(seconds: float, sep: str) -> str:
    """Время в формате чч:мм:сс<sep>мс, без накопления ошибок округления."""
    if seconds < 0:
        seconds = 0.0
    total_ms = int(round(seconds * 1000))
    hours, rest = divmod(total_ms, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    secs, ms = divmod(rest, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{sep}{ms:03d}"


def srt_stamp(seconds: float) -> str:
    return _stamp(seconds, ",")


def vtt_stamp(seconds: float) -> str:
    return _stamp(seconds, ".")


def clock(seconds: float) -> str:
    """05:12 — для человеческого чтения в TXT и Markdown."""
    total = int(seconds)
    minutes, secs = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _clean(text: str) -> str:
    """Однострочный текст: пустая строка внутри субтитра ломает разметку файла."""
    return " ".join(text.split())


def to_txt(lines: list[Line], title: str = "Расшифровка") -> str:
    out = [title, ""]
    for line in lines:
        who = (line.speaker + ": ") if line.speaker else ""
        out.append(f"[{clock(line.start_s)}] {who}{_clean(line.text)}")
    return "\n".join(out) + "\n"


def to_markdown(lines: list[Line], title: str = "Расшифровка") -> str:
    out = [f"# {title}", ""]
    for line in lines:
        who = f"**{line.speaker}** · " if line.speaker else ""
        out.append(f"- `{clock(line.start_s)}` {who}{_clean(line.text)}")
    return "\n".join(out) + "\n"


def to_srt(lines: list[Line]) -> str:
    blocks = []
    for index, line in enumerate(lines, start=1):
        who = (line.speaker + ": ") if line.speaker else ""
        blocks.append(f"{index}\n{srt_stamp(line.start_s)} --> {srt_stamp(line.end_s)}\n{who}{_clean(line.text)}")
    return "\n\n".join(blocks) + "\n"


def to_vtt(lines: list[Line]) -> str:
    blocks = ["WEBVTT", ""]
    for line in lines:
        who = (line.speaker + ": ") if line.speaker else ""
        blocks.append(f"{vtt_stamp(line.start_s)} --> {vtt_stamp(line.end_s)}\n{who}{_clean(line.text)}")
    return "\n\n".join(blocks) + "\n"


def to_json(lines: list[Line]) -> list[dict]:
    return [
        {"start_s": round(line.start_s, 3), "end_s": round(line.end_s, 3), "text": _clean(line.text), "speaker": line.speaker}
        for line in lines
    ]


FORMATS = {"txt": to_txt, "md": to_markdown, "srt": to_srt, "vtt": to_vtt}


def render(fmt: str, lines: list[Line], title: str = "Расшифровка"):
    if fmt == "json":
        return to_json(lines)
    if fmt not in FORMATS:
        raise ValueError("Неизвестный формат: " + fmt + "; доступно: " + ", ".join(list(FORMATS) + ["json"]))
    if fmt in ("txt", "md"):
        return FORMATS[fmt](lines, title)
    return FORMATS[fmt](lines)
