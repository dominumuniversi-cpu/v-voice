"""Человеческие причины сбоев разбора.

Зачем отдельный модуль: текст исключения (str(exc)) не годится для экрана. В нём бывает
URL с ключом в query, «'NoneType' object is not subscriptable» и трейсбек обёртки.
Человек либо не понимает, либо — хуже — видит чужой ключ в сообщении об ошибке.

Правило: наружу уходит короткая фраза «что случилось и что делать», а техническое
описание остаётся в логах сервера.
"""

import re

# Всё, что похоже на ключ в URL или в заголовке: ?key=..., api_key=..., Bearer ....
_SECRET_PATTERN = re.compile(
    r"(?i)(api[_-]?key|access[_-]?token|token|key|authorization|bearer)(\s*[=:]\s*|\s+)([A-Za-z0-9\-._~+/]{6,})"
)


# Отдельно: «Authorization: Bearer <токен>» — после первой замены остаётся голый токен,
# поэтому второй проход ищет сам заголовок целиком и затирает его до конца строки.
# Заголовок может стоять как «Authorization: Bearer <токен>», так и голым «Bearer <токен>».
# Ловим оба вида ДО общей замены: общая замена превращает «Bearer sk-...» в «Bearer ***»,
# после чего шаблон заголовка уже не находит себе пару и токен остаётся открытым.
_BEARER_PATTERN = re.compile(r"(?i)authorization\s*[=:]\s*bearer\s+\S+")
_BEARER_ONLY_PATTERN = re.compile(r"(?i)(?<=\bbearer)\s+\S+")

def scrub(text: str) -> str:
    """Убирает из текста всё, похожее на секрет. Пустая строка остаётся пустой."""
    if not text:
        return ""
    headers_gone = _BEARER_ONLY_PATTERN.sub(" ***", _BEARER_PATTERN.sub("***", text))
    return _SECRET_PATTERN.sub(lambda m: m.group(1) + m.group(2) + "***", headers_gone)


def explain_digest_failure(exc: BaseException) -> dict[str, str]:
    """Причина сбоя разбора словами человека.

    Кроме текста отдаём вид сбоя: по нему экран решает, звать ли человека что-то менять.
    network — нет связи с моделью/распознаванием; provider — сервис ответил отказом;
    internal — ошибка на нашей стороне, человеку делать нечего.
    """
    raw = scrub(str(exc))
    low = raw.lower()
    if any(w in low for w in ("timeout", "timed out", "connection", "connect", "dns", "unreachable")):
        kind = "network"
        message = (
            "Не удалось связаться с моделью или сервисом распознавания. "
            "Проверьте интернет; запись сохранена, разбор можно повторить."
        )
    elif any(w in low for w in ("unauthorized", "401", "403", "invalid api key", "authentication")):
        kind = "provider"
        message = (
            "Сервис отклонил ключ. Запись сохранена; ключ задаётся на сервере, "
            "проверьте его на экране настроек."
        )
    else:
        kind = "internal"
        message = (
            "Разбор не удался на нашей стороне. Запись сохранена — звук не потерян, "
            "разбор можно повторить."
        )
    # Техническое описание тоже отдаём, но уже вычищенное: оно помогает в задаче-баге.
    return {"message": message, "kind": kind, "detail": raw[:300]}
