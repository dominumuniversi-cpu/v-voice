"""test_evidence.py без pytest — прогон на чистом Python.

Импортирует ровно те же функции валидатора, что и pytest-файл, и проверяет те же утверждения,
чтобы поведение было проверено уже сейчас. Запуск: python tests/api/run_checks.py
"""
import json
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


# ---------- выгрузка во внешние продукты (задачник/CRM) ----------
from vvoice.exporters import ApprovedItem, build_plan, export_all, to_payload  # noqa: E402

ITEM = ApprovedItem(
    id="item-1", kind="task", title="Отправить смету Анне",
    evidence_quote="Я отправлю смету завтра утром, успеем", start_s=742.0, end_s=746.5,
    owner="Дмитрий", due_at="2026-11-27T08:00:00+05:00", priority="high",
    approved_by="Анна", session_id="sess-9",
)
helper_req = to_payload(ITEM, "helper", "https://helper.vernadsky-npc.ru")
check("helper_priority_lower", helper_req.body["priority"] == "high")
check("helper_keeps_quote", "Я отправлю смету" in helper_req.body["description"], helper_req.body["description"][:60])
check("helper_keeps_timecode", "742.0" in helper_req.body["description"])
check("helper_url", helper_req.url.endswith("/api/v1/tasks"))
jira = to_payload(ITEM, "jira", "https://x.atlassian.net")
check("jira_duedate_date", jira.body["fields"]["duedate"] == "2026-11-27")
check("jira_summary", jira.body["fields"]["summary"] == ITEM.title)
bx = to_payload(ITEM, "bitrix24", "https://b24.local")
check("bitrix_deadline", bx.body["fields"]["DEADLINE"] == ITEM.due_at)
wh = to_payload(ITEM, "webhook", "https://crm.local/hook")
check("webhook_schema", wh.body["schema"] == "vvoice.item.v1")
check("webhook_evidence", wh.body["evidence"]["quote"] == ITEM.evidence_quote)
try:
    to_payload(ITEM, "telegram", "https://x")
    check("unknown_target_rejected", False)
except ValueError:
    check("unknown_target_rejected", True)
plan = build_plan([ITEM, ITEM], {"helper": "https://a", "jira": "https://b"})
check("plan_two_targets_two_items", len(plan) == 4, str(len(plan)))
results = export_all([(helper_req, ITEM)], lambda r: (True, "201"))
check("export_success", results[0].ok and results[0].target == "helper")
results_bad = export_all([(helper_req, ITEM)], lambda r: (_ for _ in ()).throw(RuntimeError("нет сети")))
check("export_failure_reported", (not results_bad[0].ok) and "нет сети" in results_bad[0].detail)


# ---------- адаптер Speechmatics: протокол без сети ----------
from vvoice.providers.speechmatics import (  # noqa: E402
    add_audio_message, end_of_stream_message, parse_response, start_recognition_message, wav_to_pcm,
)

WAV_HEADER = b"RIFF" + (36).to_bytes(4, "little") + b"WAVE" + b"fmt " + (16).to_bytes(4, "little") + b"\x01\x00\x01\x00" + \
    (16000).to_bytes(4, "little") + (32000).to_bytes(4, "little") + b"\x02\x00\x10\x00" + b"data" + (8).to_bytes(4, "little")
PCM = b"\x01\x02\x03\x04\x05\x06\x07\x08"

check("wav_header_stripped", wav_to_pcm(WAV_HEADER + PCM) == PCM)
check("pcm_passthrough", wav_to_pcm(PCM) == PCM)
msg = json.loads(add_audio_message(PCM, 7))
check("audio_message_kind", msg["message"] == "AddAudio")
check("audio_message_base64", msg["audio"] == "AQIDBAUGBwg=", msg["audio"])
check("audio_message_seq", msg["seq_no"] == 7)
start = json.loads(start_recognition_message("ru"))
check("start_format_pcm16", start["audio_format"]["encoding"] == "pcm_s16le")
check("start_diarization_on", start["transcription_config"]["diarization"] == "speaker")
check("end_of_stream", json.loads(end_of_stream_message(9))["last_seq_no"] == 9)

final = parse_response(json.dumps({
    "message": "AddTranscript", "start_time": 3.0, "end_time": 5.5,
    "metadata": {"transcript": "Отправим смету завтра утром."},
    "results": [{"alternatives": [{"speaker": "S2", "content": "Отправим"}], "start_time": 3.0, "end_time": 5.5}],
}))
check("transcript_final_parsed", final is not None and not final.volatile and final.text.startswith("Отправим"), str(final))
check("transcript_speaker", final.speaker == "Голос 2", str(final.speaker))
partial = parse_response(json.dumps({"message": "AddPartialTranscript", "start_time": 1.0, "end_time": 2.0,
                                     "metadata": {"transcript": "Отпра"}}))
check("partial_is_volatile", partial.volatile is True)
check("service_messages_ignored", parse_response(json.dumps({"message": "AudioAdded", "seq_no": 1})) is None)
check("broken_json_ignored", parse_response("не json") is None)
try:
    parse_response(json.dumps({"message": "Error", "type": "quota"}))
    check("error_raises", False)
except ConnectionError:
    check("error_raises", True)


# ---------- кнопка «Проверить» на экране настроек (FR-24) ----------
from vvoice.provider_probe import check_key, interpret_status, presets, probe  # noqa: E402

check("empty_key_rejected", check_key("speechmatics", "   ").verdict == "rejected")
check("space_in_key_rejected", "пробел" in check_key("deepgram", "abcd efgh ijkl mnop").message)
check("short_key_rejected", check_key("deepgram", "abcdef").verdict == "rejected")
check("good_shape_key", check_key("deepgram", "a" * 32).ok)

check("status_200_working", interpret_status(200).ok)
check("status_401_names_key", "Ключ неверный" in interpret_status(401).message)
check("status_402_balance", "баланс" in interpret_status(402).message)
check("status_429_limit", "лимит" in interpret_status(429).message.lower())
check("status_unknown_honest", interpret_status(418).verdict == "unknown")
check("no_response_explained", "Нет ответа" in interpret_status(None).message)

ok = probe("deepgram", "b" * 32, lambda p, k: (200, ""))
check("probe_success", ok.ok, str(ok.as_dict()))
bad = probe("deepgram", "b" * 32, lambda p, k: (401, "bad token"))
check("probe_rejected", not bad.ok and bad.status == 401)
net = probe("deepgram", "b" * 32, lambda p, k: (_ for _ in ()).throw(OSError("timeout")))
check("probe_network_error", "Не удалось соединиться" in net.message)
short_circuit = probe("deepgram", "", lambda p, k: (_ for _ in ()).throw(AssertionError("сеть не должна вызываться")))
check("probe_skips_network_for_bad_key", short_circuit.verdict == "rejected")

ps = presets()
check("presets_three", len(ps) == 3, str(list(ps)))
check("presets_private_local", ps["приватно"]["asr"] == "gigaam" and ps["приватно"]["llm"] == "ollama")
check("presets_have_titles", all(p.get("title") for p in ps.values()))


# ---------- горячий путь: задержка, досыл, индикатор ----------
from vvoice.hotpath import (  # noqa: E402
    CHUNK_MS, NetworkBudget, ResendQueue, chunk_bytes, estimate_first_text_ms,
)

check("chunk_200ms_bytes", chunk_bytes() == 6400, str(chunk_bytes()))
check("chunk_size_scales", chunk_bytes(100) == 3200)
budget = NetworkBudget()
check("budget_live_initially", budget.state() == "live")
check("budget_lagging", budget.cursor(2000) == "lagging")
check("budget_offline", budget.cursor(3000) == "offline")
budget.recovered(6000)
check("budget_recovered", budget.state() == "live", budget.state())
budget.recovered(999999)
check("budget_never_negative", budget.lag_ms == 0, str(budget.lag_ms))

q = ResendQueue(max_ms=3000)
for _ in range(20):
    q.push(b"x" * 10)
check("queue_keeps_within_budget", q.pending_ms <= 3000, str(q.pending_ms))
check("queue_drops_reported", q.dropped_ms > 0, str(q.dropped_ms))
drained = q.drain()
check("queue_drain_returns_kept", len(drained) == q.pending_ms // CHUNK_MS if q.pending_ms else len(drained) >= 1)
check("queue_empty_after_drain", q.pending == [] and q.pending_ms == 0)

fast = estimate_first_text_ms(60)
slow = estimate_first_text_ms(400)
check("first_text_fast_network", fast < 900, str(fast))
check("first_text_slow_network_slower", slow > fast, str((fast, slow)))
check("first_text_below_one_second_good_network", estimate_first_text_ms(80) <= 1000, str(estimate_first_text_ms(80)))


# ---------- LLM-адаптер: четыре провайдера, один вызов ----------
from vvoice.providers.llm import (  # noqa: E402
    build_request, extract_text, make_caller, parse_json_answer,
)

ds = build_request("deepseek", "", "sys", "usr", "k")
check("deepseek_url", ds.url.endswith("/chat/completions"))
check("deepseek_system_message", ds.body["messages"][0]["role"] == "system")
check("deepseek_json_mode", ds.body["response_format"]["type"] == "json_object")
check("deepseek_default_model", ds.body["model"] == "deepseek-chat")
an = build_request("anthropic", "", "sys", "usr", "k")
check("anthropic_system_top_level", an.body["system"] == "sys" and len(an.body["messages"]) == 1)
check("anthropic_version_header", an.headers.get("anthropic-version") == "2023-06-01")
check("anthropic_key_header", an.headers.get("x-api-key") == "k")
ol = build_request("ollama", "", "sys", "usr", "")
check("ollama_no_key", "Authorization" not in ol.headers)
check("ollama_json_format", ol.body["format"] == "json")
check("ollama_local_url", "127.0.0.1" in ol.url)
try:
    build_request("openai", "m", "s", "u", "k")
    check("unknown_llm_rejected", False)
except ValueError:
    check("unknown_llm_rejected", True)

check("extract_openai_style", extract_text("deepseek", {"choices": [{"message": {"content": "{}"}}]}) == "{}")
check("extract_anthropic_blocks", extract_text("anthropic", {"content": [{"type": "text", "text": "{}"}]}) == "{}")
check("extract_ollama", extract_text("ollama", {"message": {"content": "{}"}}) == "{}")
try:
    extract_text("deepseek", {"error": {"message": "quota exceeded"}})
    check("llm_error_raises", False)
except ConnectionError as exc:
    check("llm_error_raises", "quota" in str(exc), str(exc))

check("json_plain", parse_json_answer('{"a": 1}') == {"a": 1})
check("json_wrapped_in_text", parse_json_answer('Вот ответ: {"a": 2} Спасибо') == {"a": 2})
try:
    parse_json_answer("никакого json тут нет")
    check("json_missing_raises", False)
except ValueError:
    check("json_missing_raises", True)
try:
    parse_json_answer('[1, 2]')
    check("json_array_rejected", False)
except ValueError:
    check("json_array_rejected", True)

calls = []
def fake_send(req):
    calls.append(req)
    return {"choices": [{"message": {"content": '{"summary": ["ок"], "items": []}'}}]}

call = make_caller("deepseek", "deepseek-chat", "k", fake_send)
answer = call("система", "пользователь")
check("caller_returns_dict", answer["summary"] == ["ок"])
check("caller_sent_once", len(calls) == 1)
check("caller_model_passed", calls[0]["body"]["model"] == "deepseek-chat")

for name, passed, detail in checks:
    if not passed:
        sys.stderr.write("FAILED: " + name + " :: " + str(detail) + "\n")

failed2 = [c for c in checks if not c[1]]
sys.stderr.write("total=%d passed=%d failed=%d\n" % (len(checks), len(checks) - len(failed2), len(failed2)))
sys.exit(1 if failed2 else 0)
