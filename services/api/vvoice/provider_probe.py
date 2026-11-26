"""Проверка подключения провайдера (кнопка «Проверить» на экране настроек, FR-24).

Человек вводит ключ и хочет понять ДО встречи, что он рабочий. Три состояния:
  - working   — запрос прошёл, всё в порядке;
  - rejected  — ключ отвергнут или провайдер недоступен по адресу/сети;
  - unknown   — сервис ответил кодом, которого нет в таблице: честно говорим «не знаю», не врём.

Сеть снаружи (`send`), поэтому проверка тестируется без ключей. Таблица кодов — наша,
из официальной документации кодов ошибок; здесь нет ни одного запроса к настоящему сервису.
"""

from __future__ import annotations

from dataclasses import dataclass

# код HTTP -> (verdict, сообщение на русском). Проверено по документации каждого сервиса.
CODE_MEANING: dict[int, tuple[str, str]] = {
    200: ("working", "Ключ рабочий, сервис отвечает."),
    201: ("working", "Ключ рабочий, сервис отвечает."),
    400: ("rejected", "Сервис отклонил запрос проверки: вероятно, ключ или регион не совпадают."),
    401: ("rejected", "Ключ неверный или отозван. Проверьте, что скопировали его целиком."),
    402: ("rejected", "Нет оплаченного баланса: сервис не примет запрос, пока не пополните счёт."),
    403: ("rejected", "Доступ запрещён: возможно, ключ без нужного уровня или включается настройкой в кабинете."),
    429: ("rejected", "Превышен лимит запросов. Ключ рабочий, но сейчас сервис просит подождать."),
    500: ("unknown", "Сервис сообщает о внутренней ошибке — повторите проверку позже."),
    503: ("unknown", "Сервис недоступен — повторите проверку позже."),
}


@dataclass
class ProbeResult:
    verdict: str          # working | rejected | unknown
    message: str
    status: int | None = None

    def as_dict(self) -> dict[str, object]:
        return {"verdict": self.verdict, "message": self.message, "status": self.status}

    @property
    def ok(self) -> bool:
        return self.verdict == "working"


def check_key(provider: str, api_key: str) -> ProbeResult:
    """Локальные проверки: пустой ключ, пробелы, короткий обрывок."""
    key = (api_key or "").strip()
    if not key:
        return ProbeResult("rejected", "Ключ не введён.")
    if " " in key or "\n" in key:
        return ProbeResult("rejected", "В ключе есть пробел или перевод строки — скопируйте его заново.")
    if len(key) < 16:
        return ProbeResult("rejected", "Ключ слишком короткий для " + provider + ": похоже, скопирована только часть.")
    return ProbeResult("working", "Ключ прошёл проверку формы; выполняем сетевую проверку.")


def interpret_status(status: int | None, error_text: str = "") -> ProbeResult:
    """Превращает код ответа в человеческое объяснение."""
    if status is None:
        return ProbeResult("rejected", "Нет ответа от сервиса: проверьте интернет или адрес.", None)
    if status in CODE_MEANING:
        verdict, message = CODE_MEANING[status]
        return ProbeResult(verdict, message, status)
    if error_text:
        return ProbeResult("unknown", "Сервис ответил кодом " + str(status) + ": " + error_text[:120], status)
    return ProbeResult("unknown", "Сервис ответил кодом " + str(status) + "; расшифровки нет — сообщите администратору.", status)


def probe(provider: str, api_key: str, send) -> ProbeResult:
    """Полная проверка: форма ключа -> сетевой запрос -> расшифровка ответа.

    `send(provider, key) -> (status, error_text)` передаётся снаружи: так проверку можно прогнать
    тестом без настоящих ключей, и в CI нет ни одного обращения к внешним сервисам.
    """
    local = check_key(provider, api_key)
    if not local.ok:
        return local
    try:
        status, error_text = send(provider, api_key)
    except Exception as exc:  # noqa: BLE001 — любая сетевая беда объясняется человеку, а не падением
        return ProbeResult("rejected", "Не удалось соединиться: " + str(exc)[:120])
    return interpret_status(status, error_text)


def presets() -> dict[str, dict[str, str]]:
    """Пресеты FR-26: «человеческая» настройка вместо десятка параметров."""
    return {
        "точно": {"title": "Точно", "asr": "speechmatics", "llm": "deepseek", "comment": "Лучшее качество: облако, диаризация, пунктуация."},
        "дёшево": {"title": "Быстро и дёшево", "asr": "assemblyai", "llm": "deepseek", "comment": "Предзапись дешевле стрима, разбор теряет живые подсказки."},
        "приватно": {"title": "Только локально (приватно)", "asr": "gigaam", "llm": "ollama", "comment": "Ни один звук не уходит с вашей машины; нужна GPU."},
    }
