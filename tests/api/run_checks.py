"""test_evidence.py без pytest — прогон на чистом Python.

Импортирует ровно те же функции валидатора, что и pytest-файл, и проверяет те же утверждения,
чтобы поведение было проверено уже сейчас. Запуск: python tests/api/run_checks.py
"""
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / "services" / "api"))

from vvoice.evidence import MIN_QUOTE_LEN, normalize, quote_is_present, validate_digest, validate_item  # noqa: E402

TRANSCRIPT = (
    "Анна: По бюджету до пятницы надо понять, укладываемся или нет. "
    "Дмитрий: Я отправлю смету завтра утром, успеем. "
    "Анна: Тогда созвон перенесём на девятое декабря в час дня."
)
TASK = {
    "kind": "task",
    "title": "Отправить смету Анне",
    "owner": "Дмитрий",
    "due_at": "2026-11-27T08:00:00+05:00",
    "evidence": {"start_s": 742.0, "end_s": 746.5, "quote": "Я отправлю смету завтра утром, успеем"},
}
SPEAKERS = {"Анна", "Дмитрий"}
checks = []


def check(name, cond, detail=""):
    checks.append((name, bool(cond), detail))


check("normalize", normalize("  Я   ОТПРАВЛЮ\nсмету ") == "я отправлю смету")
check("quote_present", quote_is_present("я отправлю  смету завтра", TRANSCRIPT))
check("valid_task", validate_item(TASK, TRANSCRIPT, speakers=SPEAKERS)[0])
broken = {k: v for k, v in TASK.items() if k != "evidence"}
check("no_evidence", not validate_item(broken, TRANSCRIPT)[0])
short = dict(TASK, evidence={"start_s": 1, "end_s": 2, "quote": "успеем"})
ok, reason = validate_item(short, TRANSCRIPT)
check("short_quote", not ok and str(MIN_QUOTE_LEN) in reason, reason)
invented = dict(TASK, evidence={"start_s": 10, "end_s": 12, "quote": "Давай закроем контракт с новым клиентом завтра"})
ok, reason = validate_item(invented, TRANSCRIPT)
check("invented_quote", not ok and "нет в транскрипте" in reason, reason)
check("other_meeting", not validate_item(TASK, "Анна: добрый день, начнём")[0])
ok, reason = validate_item(dict(TASK, owner="Олег"), TRANSCRIPT, speakers=SPEAKERS)
check("owner_absent", not ok and "Олег" in reason, reason)
ok, reason = validate_item(dict(TASK, due_at="завтра утром"), TRANSCRIPT)
check("bad_due", not ok and "ISO8601" in reason, reason)
check("due_null_ok", validate_item(dict(TASK, due_at=None), TRANSCRIPT, speakers=SPEAKERS)[0])
check("reversed_ts", not validate_item(dict(TASK, evidence={"start_s": 20, "end_s": 10, "quote": TASK["evidence"]["quote"]}), TRANSCRIPT)[0])

digest = {
    "summary": ["Свели бюджет"],
    "items": [
        TASK,
        {"kind": "task", "title": "Придуманная задача",
         "evidence": {"start_s": 1, "end_s": 2, "quote": "поговорим об этом когда-нибудь позже"}},
        {"kind": "meeting", "title": "Созвон 9 декабря 13:00",
         "evidence": {"start_s": 900, "end_s": 905, "quote": "созвон перенесём на девятое декабря в час дня"}},
    ],
}
res = validate_digest(digest, TRANSCRIPT, speakers=SPEAKERS)
check("digest_kept_2", len(res["items"]) == 2, str(len(res["items"])))
check("digest_rejected_1", len(res["rejected"]) == 1 and res["rejected"][0]["index"] == 1, str(res["rejected"]))
for kind in ("task", "meeting", "reminder", "decision", "question"):
    check("kind_" + kind, validate_item(dict(TASK, kind=kind), TRANSCRIPT, speakers=SPEAKERS)[0])
ok, reason = validate_item(dict(TASK, kind="note"), TRANSCRIPT)
check("unknown_kind", not ok and "неизвестный тип" in reason, reason)

# ---------- настройки: понятные сообщения, безопасные значения по умолчанию ----------
from vvoice.settings import Settings, describe, validate  # noqa: E402

defaults = Settings.from_env({})
check("defaults_valid", validate(defaults) == [], str(validate(defaults)))
check("defaults_asr_fake", defaults.ASR_PROVIDER == "fake")
check("bool_parsing_yes", Settings.from_env({"MEMBERS_ONLY": "да"}).MEMBERS_ONLY is True)
check("bool_parsing_off", Settings.from_env({"MEMBERS_ONLY": "false"}).MEMBERS_ONLY is False)
try:
    Settings.from_env({"DATA_RETENTION_DAYS": "много"})
    check("int_rejects_words", False)
except ValueError:
    check("int_rejects_words", True)

cloud = Settings.from_env({"ASR_PROVIDER": "speechmatics"})
check("missing_key_reported", any("SPEECHMATICS_API_KEY" in p for p in validate(cloud)), str(validate(cloud)))
check("zero_config_starts", validate(Settings.from_env({})) == [], "дефолт должен работать без настроек")
llm = Settings.from_env({"LLM_PROVIDER": "anthropic"})
check("missing_llm_key_reported", any("LLM_API_KEY" in p for p in validate(llm)), str(validate(llm)))
bad = Settings.from_env({"API_PORT": "8000"})
check("port_8000_rejected", any("8000" in p for p in validate(bad)))
typo = Settings.from_env({"ASR_PROVIDER": "speechmatic"})
check("typo_reported", any("ASR_PROVIDER" in p for p in validate(typo)))
check("describe_mentions_keys", "SPEECHMATICS_API_KEY" in describe())

for name, passed, detail in checks:
    if not passed:
        sys.stderr.write("FAILED: " + name + " :: " + str(detail) + "\n")

failed2 = [c for c in checks if not c[1]]
sys.stderr.write("total=%d passed=%d failed=%d\n" % (len(checks), len(checks) - len(failed2), len(failed2)))
sys.exit(1 if failed2 else 0)
