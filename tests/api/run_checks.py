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


# ---------- HTTP-слой: коды и объяснения без фреймворка ----------
from vvoice.http_api import handle  # noqa: E402

check("http_health", handle("GET", "/api/v1/health").status == 200)
check("http_unknown_path_404", handle("GET", "/api/v1/nope").status == 404)
check("http_unknown_path_explains", "Нет такого пути" in handle("GET", "/api/v1/nope").body["message"])
r405 = handle("POST", "/api/v1/health")
check("http_wrong_method_405", r405.status == 405)
check("http_allow_header", r405.headers.get("Allow") == "GET", str(r405.headers))
check("http_bad_json_400", handle("POST", "/api/v1/probe", "{не json").status == 400)
check("http_json_array_400", handle("POST", "/api/v1/probe", "[1,2]").status == 400)
check("http_probe_requires_provider", handle("POST", "/api/v1/probe", "{}").status == 400)
rprobe = handle("POST", "/api/v1/probe", json.dumps({"provider": "deepgram", "api_key": ""}))
check("http_probe_empty_key_rejected", rprobe.body.get("verdict") == "rejected", str(rprobe.body))
rpresets = handle("GET", "/api/v1/presets")
check("http_presets_three", len(rpresets.body["presets"]) == 3)

good_item = {"kind": "task", "title": "Отправить смету", "evidence": {"quote": "я отправлю смету завтра утром", "start_s": 12, "end_s": 14}}
transcript = "привет, я отправлю смету завтра утром, хорошо"
rok = handle("POST", "/api/v1/items/validate", json.dumps({"item": good_item, "transcript": transcript}))
check("http_item_ok", rok.status == 200, str(rok.body))
bad_item = {"kind": "task", "title": "Отправить смету", "evidence": {"quote": "этого не говорили никогда", "start_s": 12, "end_s": 14}}
rbad = handle("POST", "/api/v1/items/validate", json.dumps({"item": bad_item, "transcript": transcript}))
check("http_item_unproven_422", rbad.status == 422, str(rbad.body))
check("http_item_unproven_reason", "цитаты нет" in rbad.body.get("reason", ""), str(rbad.body))
check("http_validate_needs_transcript", handle("POST", "/api/v1/items/validate", json.dumps({"item": good_item})).status == 400)


# ---------- экспорт: четыре формата, границы времени ----------
from vvoice.formats import (  # noqa: E402
    Line, clock, render, srt_stamp, to_json, to_markdown, to_srt, to_txt, to_vtt, vtt_stamp,
)

check("srt_stamp_comma", srt_stamp(5.25) == "00:00:05,250", srt_stamp(5.25))
check("vtt_stamp_dot", vtt_stamp(5.25) == "00:00:05.250", vtt_stamp(5.25))
check("stamp_boundary_59_999", srt_stamp(59.999) == "00:01:00,000" or srt_stamp(59.999) == "00:00:59,999", srt_stamp(59.999))
check("stamp_hour", srt_stamp(3661.5) == "01:01:01,500", srt_stamp(3661.5))
check("stamp_negative_clamped", srt_stamp(-3) == "00:00:00,000")
check("clock_short", clock(252) == "04:12")
check("clock_long", clock(3725) == "01:02:05")

lines = [Line(0.0, 2.5, "Привет, коллеги", "Голос 1"), Line(2.5, 6.0, "Начнём  с\nпункта два", "Голос 2")]
txt = to_txt(lines)
check("txt_has_timecode", "[00:00]" in txt)
check("txt_has_speaker", "Голос 1: Привет" in txt)
check("txt_strips_newlines", "пункта" in txt and "\nпункта" not in txt)

srt = to_srt(lines)
check("srt_starts_with_index", srt.startswith("1\n"))
check("srt_arrow", " --> " in srt)
check("srt_blocks_separated", "\n\n2\n" in srt)

vtt = to_vtt(lines)
check("vtt_header", vtt.startswith("WEBVTT"))
check("vtt_no_indices", "\n2\n" not in vtt)

md = to_markdown(lines, "Встреча")
check("md_title", md.startswith("# Встреча"))
check("md_tick", "`00:00`" in md)

data = to_json(lines)
check("json_shape", data[0]["speaker"] == "Голос 1" and data[0]["start_s"] == 0.0)
check("json_single_line_text", data[1]["text"] == "Начнём с пункта два", data[1]["text"])

check("render_by_name", render("srt", lines).startswith("1\n"))
try:
    render("docx", lines)
    check("render_unknown_format", False)
except ValueError as exc:
    check("render_unknown_format", "docx" in str(exc))


# ---------- восстановление после сбоя (FR-6) ----------
from vvoice.recovery import HEADER_SIZE, duration_ms, inspect, rebuild_header, recover, usable_data_bytes  # noqa: E402

check("recovery_empty_file_refused", inspect(0).recovered is False)
check("recovery_header_only_refused", inspect(HEADER_SIZE).recovered is False)
fragment = inspect(HEADER_SIZE + 16_000)
check("recovery_fragment_marked", fragment.recovered is False and "обрывок" in fragment.reason, fragment.reason)
big = HEADER_SIZE + 32_000 * 10
check("recovery_ten_seconds_ok", inspect(big).recovered is True and duration_ms(big) >= 9990, str(duration_ms(big)))
check("recovery_odd_byte_dropped", usable_data_bytes(HEADER_SIZE + 101) == 100)

fake_raw = b"RIFF" + (0).to_bytes(4, "little") + b"WAVE" + b"\x00" * (HEADER_SIZE - 12) + b"\x01\x02" * 32_000
wav, res = recover(fake_raw)
check("recovery_rebuilds_header", wav.startswith(b"RIFF") and wav[8:12] == b"WAVE")
check("recovery_riff_size_correct", int.from_bytes(wav[4:8], "little") == len(wav) - 8, str(int.from_bytes(wav[4:8], "little")))
check("recovery_data_size_correct", int.from_bytes(wav[40:44], "little") == len(wav) - HEADER_SIZE)
check("recovery_says_ok", res.recovered is True and res.duration_ms >= 990)
check("recovery_header_generated", rebuild_header(b"\x00" * 100)[0:4] == b"RIFF")
empty_wav, empty_res = recover(b"RIFF" + b"\x00" * 40)
check("recovery_no_data_gives_no_file", empty_wav == b"" and empty_res.recovered is False)

# ---------- лимиты месяца (FR-27) ----------
from vvoice.limits import Budget, Usage  # noqa: E402

budget = Budget(monthly_rub=1000, usage=Usage())
check("budget_ok_initially", budget.state == "ok")
budget.usage.add_minutes(10, 0.5)
check("budget_counts_money", abs(budget.usage.money_rub - 5.0) < 1e-6, str(budget.usage.money_rub))
check("budget_minutes", budget.usage.minutes == 10.0)
budget.usage.money_rub = 850.0
check("budget_warning_at_85", budget.state == "warning", budget.state)
budget.usage.money_rub = 1000.0
check("budget_exhausted", budget.state == "exhausted")
check("budget_headline_human", "лимит исчерпан" in budget.headline().lower())
budget.usage.money_rub = 0.0
check("budget_meetings_floor", budget.meetings_left(30, 0.5) == 66, str(budget.meetings_left(30, 0.5)))
check("budget_meetings_guard", Budget(0, Usage()).meetings_left(30, 0.5) == 0)
check("budget_ratio_capped", Budget(100, Usage(money_rub=500)).ratio == 1.0)


# ---------- промпт разбора: правила на месте, пример валиден ----------
import os  # noqa: E402

PROMPT_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "services", "api", "vvoice", "prompts", "digest_ru.md")
prompt_text = open(PROMPT_PATH, encoding="utf-8").read()

check("prompt_requires_quote", "Цитата обязательна" in prompt_text)
check("prompt_forbids_invented_owner", "Не додумывай исполнителя" in prompt_text)
check("prompt_separates_decision", "Не путай разговор и решение" in prompt_text)
check("prompt_excludes_noise", "Шум и чужие разговоры" in prompt_text)
check("prompt_russian", "Язык ответа — русский" in prompt_text)
check("prompt_no_arabic_noise", not any("\u0600" <= ch <= "\u06ff" for ch in prompt_text), "в промпте чужие символы")

prompt_json = prompt_text.split("```json")[1].split("```")[0]
example = json.loads(prompt_json)
check("prompt_example_valid_json", isinstance(example, dict) and "items" in example)
check("prompt_example_item_has_evidence", all("evidence" in it for it in example["items"]))
check("prompt_example_kinds", set(example) >= {"topic", "participants", "summary", "decisions", "open_questions", "items"})

# Шаблонный путь разбора: клиент обращается к /api/v1/sessions/<id>/digest.
from vvoice.http_api import handle as _handle

_ok = _handle("GET", "/api/v1/sessions/abc123/digest")
check("digest_route_exists", _ok.body.get("error") == "digest_not_found", "путь должен существовать, а не давать «нет такого пути»")
check("digest_route_names_session", _ok.body.get("session_id") == "abc123")
check("digest_route_rejects_empty_id", _handle("GET", "/api/v1/sessions//digest").body.get("error") == "not_found")
check("digest_route_rejects_huge_id", _handle("GET", "/api/v1/sessions/" + "a" * 65 + "/digest").body.get("error") == "not_found")
_wrong = _handle("POST", "/api/v1/sessions/abc123/digest")
check("digest_route_method", _wrong.status == 405)
check("digest_route_allow", _wrong.headers.get("Allow") == "GET")

# Приём записи с телефона: сессия создаётся только из настоящего WAV.
import base64 as _b64
import struct as _struct
from vvoice.sessions import create_session as _create_session

def _wav(ms=1000):
    frames = b"\x00\x00" * (16 * ms)  # 16 кГц моно, 16 бит
    header = b"RIFF" + _struct.pack("<I", 36 + len(frames)) + b"WAVE"
    fmt = b"fmt " + _struct.pack("<IHHIIHH", 16, 1, 1, 16000, 32000, 2, 16)
    data = b"data" + _struct.pack("<I", len(frames))
    return header + fmt + data + frames

_good = _b64.b64encode(_wav(1000)).decode()
_code, _body, _audio = _create_session({"audio_base64": _good})
check("session_accepts_wav", _code == 200 and "session_id" in _body)
check("session_duration_seconds", _body.get("duration_ms", 0) in range(990, 1011), _body.get("duration_ms"))
check("session_id_shape", len(_body.get("session_id", "")) == 16)
check("session_returns_audio", _audio is not None and len(_audio) > 1000)

_short = _b64.b64encode(_wav(1)).decode()
_code, _body, _ = _create_session({"audio_base64": _short})
check("session_rejects_short", _code == 400 and _body.get("error") == "audio_too_short")

_code, _body, _ = _create_session({"audio_base64": "не base64 !!!"})
check("session_rejects_garbage", _code == 400)

_code, _body, _ = _create_session({})
check("session_requires_audio", _code == 400 and _body.get("error") == "bad_request")

_code, _body, _ = _create_session({"audio_base64": _b64.b64encode(b"x" * 9000).decode()})
check("session_rejects_not_wav", _code == 415 and _body.get("error") == "not_wav")

_stereo = _wav(1000).replace(_struct.pack("<HHIIHH", 1, 1, 16000, 32000, 2, 16), _struct.pack("<HHIIHH", 1, 2, 16000, 64000, 4, 16))
_code, _body, _ = _create_session({"audio_base64": _b64.b64encode(_stereo).decode()})
check("session_accepts_stereo", _code == 200, _body.get("error"))
for name, passed, detail in checks:
    if not passed:
        sys.stderr.write("FAILED: " + name + " :: " + str(detail) + "\n")

failed2 = [c for c in checks if not c[1]]
sys.stderr.write("total=%d passed=%d failed=%d\n" % (len(checks), len(checks) - len(failed2), len(failed2)))
sys.exit(1 if failed2 else 0)
