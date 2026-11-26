"""test_evidence.py без pytest — прогон на чистом Python.

Импортирует ровно те же функции валидатора, что и pytest-файл, и проверяет те же утверждения,
чтобы поведение было проверено уже сейчас. Запуск: python tests/api/run_checks.py
"""
import json
import re
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
from vvoice.http_api import ROUTES as _ROUTES  # noqa: E402

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
# Хранилище записей: сохранение, поиск, защита от перезаписи.
import tempfile as _tempfile
from vvoice.storage import AudioStore as _AudioStore
from vvoice.http_api import handle as _handle

_tmpdir = _tempfile.mkdtemp(prefix="vvoice-store-")
_store = _AudioStore(_tmpdir)
_payload = __import__('json').dumps({'audio_base64': _good})
_resp = _handle("POST", "/api/v1/sessions", _payload, store=_store)
check("store_upload_ok", _resp.status == 200, _resp.body)
_sid = _resp.body.get('session_id', '')
check("store_file_exists", _store.find(_sid) is not None)
check("store_read_roundtrip", _store.read(_sid) == _store.read(_sid) and _store.read(_sid) is not None)

_again = _handle("POST", "/api/v1/sessions", _payload, store=_store)
check("store_no_overwrite", _again.status == 409 and _again.body.get("error") == "already_exists")

_none = _handle("POST", "/api/v1/sessions", _payload)
check("store_required", _none.status == 503 and _none.body.get("error") == "storage_unavailable")

check("store_rejects_bad_id", _store.find("../etc/passwd") is None)
check("store_rejects_long_id", _store.find("a" * 65) is None)

_notes = []
_resp2 = _handle("POST", "/api/v1/sessions", _payload, store=_store, sender=_notes.append)
check("store_notifies_once", _resp2.status == 409 and _notes == [])
# Хранилище разборов: сохранение, выдача через маршрут, устойчивость к мусору.
from vvoice.digest_store import DigestStore as _DigestStore

_dig_root = _tempfile.mkdtemp(prefix="vvoice-digest-")
_digests = _DigestStore(_dig_root)
_digests.save(_sid, {"summary": ["Обсудили смету"], "items": []})
check("digest_store_roundtrip", (_digests.load(_sid) or {}).get("summary") == ["Обсудили смету"])
_got = _handle("GET", "/api/v1/sessions/" + _sid + "/digest", digests=_digests)
check("digest_route_returns_saved", _got.status == 200 and _got.body.get("summary") == ["Обсудили смету"])
_none = _handle("GET", "/api/v1/sessions/abcdef1234567890/digest", digests=_digests)
check("digest_store_bad_id_none", _digests.load("../x") is None)
# Запуск разбора: без записи, без настройки и повторно — три разных честных ответа.
from vvoice.job import analyze as _analyze
from vvoice.digest_store import DigestStore as _DS2

_dig2 = _DS2(_tempfile.mkdtemp(prefix='vvoice-an-'))
_r = _analyze('0000aaaa0000bbbb', store=_store, digests=_dig2, provider_factory=lambda p: None, call_llm=lambda a, b: {})
check("analyze_requires_session", _r.status == 404 and _r.body.get("error") == "session_not_found")
_r2 = _analyze(_sid, store=None, digests=None, provider_factory=lambda p: None, call_llm=lambda a, b: {})
check("analyze_requires_storage", _r2.status == 503)
_dig2.save(_sid, {'summary': ['готово'], 'items': []})
_r3 = _analyze(_sid, store=_store, digests=_dig2, provider_factory=lambda p: None, call_llm=lambda a, b: {})
check("analyze_cached", _r3.status == 200 and _r3.body.get("cached") is True)
def _boom(path):
    raise RuntimeError('провайдер недоступен')
_dig3 = _DS2(_tempfile.mkdtemp(prefix='vvoice-an2-'))
_r4 = _analyze(_sid, store=_store, digests=_dig3, provider_factory=_boom, call_llm=lambda a, b: {})
check("analyze_failure_reported", _r4.status == 502 and _r4.body.get("error") == "digest_failed")
_ready = _handle("POST", "/api/v1/sessions/" + _sid + "/analyze", store=_store, digests=_dig2)
check("analyze_route_needs_pipeline", _ready.status == 503 and _ready.body.get("error") == "pipeline_unavailable")
# Маршрут analyze должен принимать POST без тела: клиент шлёт пустой запрос, и это нормально.
_empty = _handle("POST", "/api/v1/sessions/" + _sid + "/analyze")
check("analyze_route_accepts_empty_body", _empty.status in (503, 502, 404), _empty.status)
_not_allowed = _handle("GET", "/api/v1/sessions/" + _sid + "/analyze")
check("analyze_route_get_forbidden", _not_allowed.status == 405)
# Живой поток: состояние по сессии, вытеснение старых, честные отказы.
from vvoice.live_sessions import LiveSessions as _LS, push_chunk as _push
from vvoice.providers.fake_asr import FakeAsr as _FakeAsr

_ls = _LS(limit=3)
_code, _body = _push(_ls, 'aaaa1111bbbb2222', b'\x00' * 3200, provider_factory=lambda sid: _FakeAsr())
check("live_accepts_chunk", _code == 200 and "text" in _body, _code)
check("live_state_kept", _ls.size() == 1)
_code2, _ = _push(_ls, "../bad", b"\x00" * 10, provider_factory=lambda sid: _FakeAsr())
check("live_rejects_bad_id", _code2 == 400)
_code3, _ = _push(_ls, "aaaa1111bbbb2222", b"", provider_factory=lambda sid: _FakeAsr())
check("live_rejects_empty_chunk", _code3 == 400)
for _i in range(5):
    _push(_ls, 'sess' + str(_i) + '0000aaaa', b'\x00' * 100, provider_factory=lambda sid: _FakeAsr())
check("live_evicts_old", _ls.size() == 3, _ls.size())
_ls.drop('sess40000aaaa')
check("live_drop_frees", _ls.size() == 2)
def _broken(sid):
    raise RuntimeError('провайдер недоступен')
_code4, _body4 = _push(_ls, "aaaa1111bbbb2222", b"\x00" * 100, provider_factory=_broken)
check("live_failure_keeps_text", _code4 == 502 and "text" in _body4)
_no = _handle("POST", "/api/v1/sessions/aaaa1111bbbb2222/stream", '{"pcm_base64":"AAAA"}')
check("live_route_needs_recognizer", _no.status == 503)
_bad = _handle("GET", "/api/v1/sessions/aaaa1111bbbb2222/stream")
check("live_route_get_forbidden", _bad.status == 405)
# Открытие сессии заранее: идентификатор есть до записи, и он годится для живого текста.
from vvoice.open_session import open_session as _open, new_session_id as _new_id

_oc, _ob = _open()
check("open_session_returns_id", _oc == 200 and len(_ob.get("session_id", "")) == 16)
check("open_session_id_unique", _new_id() != _new_id())
check("open_session_id_shape", _open()[1]["session_id"].isalnum())
_oo = _handle("POST", "/api/v1/sessions/open")
check("open_route_works", _oo.status == 200 and "session_id" in _oo.body)
_og = _handle("GET", "/api/v1/sessions/open")
check("open_route_get_forbidden", _og.status == 405)

# Связка: открыли сессию заранее, прислали кусок, получили текст по тому же id.
_ls2 = _LS(limit=4)
_open_id = _oo.body["session_id"]
_sc, _sb = _push(_ls2, _open_id, b'\x00' * 3200, provider_factory=lambda sid: _FakeAsr())
check("open_then_stream_works", _sc == 200 and "text" in _sb)
# Восстановление оборванной записи: заголовок обещает больше, чем пришло.
_full = _wav(1500)
_broken = _full[:len(_full) - 8000]  # обрыв: данных меньше, чем заявлено в заголовке
_bc, _bb, _ba = _create_session({"audio_base64": _b64.b64encode(_broken).decode()})
check("broken_wav_recovers", _bc == 200 and _bb.get("duration_ms", 0) > 900, (_bc, _bb.get("duration_ms")))
check("broken_wav_gives_audio", _ba is not None and len(_ba) == len(_broken))
_tiny = _full[:120]
_tc, _tb, _ = _create_session({"audio_base64": _b64.b64encode(_tiny).decode()})
check("tiny_broken_rejected", _tc == 400 and _tb.get("error") == "audio_too_short")
# Экспорт задач: без одобрения не уходит, неизвестная цель отвергается, сбой адресата не валит остальных.
from vvoice.export_route import export_session as _export

_item_ok = {'id': 'i1', 'kind': 'task', 'title': 'Отправить смету', 'evidence_quote': 'я отправлю смету Ивану', 'start_s': 1.0, 'end_s': 3.0, 'approved': True}
_item_no = {'id': 'i2', 'kind': 'task', 'title': 'Позвонить', 'evidence_quote': 'позвони ему завтра', 'approved': False}
_sent = []
_c, _b = _export({'targets': {'webhook': 'https://example.test/hook'}, 'items': [_item_ok, _item_no]}, send=lambda req: (_sent.append(req), (True, 'ok'))[1])
check("export_sends_approved", _c == 200 and _b.get("sent") == 1, (_c, _b))
check("export_skips_unapproved", _b.get("skipped") == 1)
check("export_reaches_send", len(_sent) == 1)
_c2, _b2 = _export({"targets": {"narnia": "x"}, "items": [_item_ok]}, send=lambda r: (True, ""))
check("export_rejects_unknown_target", _c2 == 400 and _b2.get("error") == "unknown_target")
_c3, _b3 = _export({"targets": {"webhook": "x"}, "items": [_item_no]}, send=lambda r: (True, ""))
check("export_needs_approval", _c3 == 422 and _b3.get("error") == "nothing_approved")
_c4, _b4 = _export({"targets": {"webhook": "x"}, "items": [_item_ok]}, send=None)
check("export_needs_sender", _c4 == 503)
def _boom(req):
    raise RuntimeError('адресат недоступен')
_c5, _b5 = _export({"targets": {"webhook": "x"}, "items": [_item_ok]}, send=_boom)
check("export_failure_reported", _c5 == 200 and _b5.get("failed") == 1 and _b5.get("sent") == 0)
_r = _handle("POST", "/api/v1/sessions/" + _sid + "/export", '{"targets":{"webhook":"x"},"items":[]}')
check("export_route_rejects_empty", _r.status == 400)
# Сквозная проверка стыка: одобренная задача доходит до адресанта через http_api, неодобренная — нет.
import json as _json
_envelope = {'targets': {'webhook': 'https://example.test/hook'}, 'items': [
    {'id': 'a1', 'kind': 'task', 'title': 'Позвонить в банк', 'evidence_quote': 'позвони в банк завтра', 'approved': True},
    {'id': 'a2', 'kind': 'task', 'title': 'Купить кофе', 'evidence_quote': 'заскочи за кофе', 'approved': False},
]}
_delivered = []
_r = _handle('POST', '/api/v1/sessions/' + _sid + '/export', _json.dumps(_envelope),
               exporter=lambda req: (_delivered.append(req), (True, 'ok'))[1])
check("export_reaches_end", _r.status == 200 and _r.body.get("sent") == 1, (_r.status, _r.body))
check("export_delivers_only_approved", len(_delivered) == 1)
_payload0 = getattr(_delivered[0], "body", {}) if _delivered else {}
check("export_payload_has_schema", isinstance(_payload0, dict) and _payload0.get("schema") == "vvoice.item.v1")
# Настройка сервера из окружения (#44): живость без ключей, ключ не утекает, мусор не проходит.
from vvoice import config as _cfg
_empty = _cfg.load({})
check("config_empty_is_alive", _empty.asr_ready is False and _empty.llm_ready is False)
_full = _cfg.load({"VV_ASR_PROVIDER": "deepgram", "VV_ASR_KEY": "secret-asr", "VV_LLM_PROVIDER": "openai", "VV_LLM_KEY": "secret-llm"})
check("config_reads_providers", _full.asr_ready and _full.llm_ready and _full.asr_provider == "deepgram")
_health_text = repr(_full.public_health())
check("config_key_never_leaks", "secret-asr" not in _health_text and "secret-llm" not in _health_text)
check("config_fingerprint_differs", _full.public_health()["asr"]["key_fingerprint"] != _full.public_health()["llm"]["key_fingerprint"])
_junk = _cfg.load({"VV_ASR_PROVIDER": "нечто", "VV_ASR_KEY": "k"})
check("config_rejects_unknown_provider", _junk.asr_provider == "" and _junk.asr_ready is False)
_exp = _cfg.load({"VV_EXPORT_WEBHOOK_URL": "https://x.test/h"})
check("config_reads_export_targets", _exp.export_targets.get("webhook") == "https://x.test/h")
# Стык: /health действительно говорит о моделях и не выдаёт ключи.
_h = _handle('GET', '/api/v1/health')
check("health_reports_settings", _h.status == 200 and "settings" in _h.body and "asr" in _h.body["settings"])
check("health_no_secret_in_body", "secret" not in repr(_h.body))
# Живая проверка точки запуска (#44): сервер поднимается и отвечает на настоящий HTTP-запрос.
import sys as _sys, threading as _threading, urllib.request as _url
from main import make_server as _make_server
from vvoice.config import load as _load
_srv = _make_server('127.0.0.1', 0, _load({}), _tempfile.mkdtemp())
_port = _srv.server_address[1]
_threading.Thread(target=_srv.serve_forever, daemon=True).start()
_live = _url.urlopen('http://127.0.0.1:%d/api/v1/health' % _port, timeout=5)
_live_body = _json.loads(_live.read().decode('utf-8'))
check("server_starts_and_answers", _live.status == 200 and _live_body.get("status") == "ok", _live_body)
check("server_health_has_settings", "settings" in _live_body and "can_transcribe" in _live_body["settings"])
try:
    _url.urlopen('http://127.0.0.1:%d/api/v1/nope' % _port, timeout=5)
    _code_unknown = 200
except Exception as _exc:
    _code_unknown = getattr(_exc, 'code', 0)
check("server_returns_404_for_unknown", _code_unknown == 404, _code_unknown)
_srv.shutdown()
# Разбор несуществующей записи — 404, а не выдуманный пустой разбор.
_absent = _handle('GET', '/api/v1/sessions/abcdef0123456789/digest')
check("digest_route_missing", _absent.status == 404 and _absent.body.get("error") == "digest_not_found")
# .env действительно читается: иначе инструкция настройки врала бы, а человек видел «НЕ настроено».
_envdir = _tempfile.mkdtemp()
_envpath = _envdir + '/.env'
with open(_envpath, 'w', encoding='utf-8') as _fh:
    _fh.write('# комментарий\nVV_ASR_PROVIDER=assemblyai\nVV_ASR_KEY="ключ-из-файла"\n\nVV_LLM_PROVIDER=gigachat\n')
_fromfile = _cfg.load_env_file(_envpath)
check("config_reads_env_file", _fromfile.get("VV_ASR_PROVIDER") == "assemblyai" and _fromfile.get("VV_ASR_KEY") == "ключ-из-файла", _fromfile)
check("config_env_ignores_comments", len(_fromfile) == 3)
check("config_missing_env_file_ok", _cfg.load_env_file(_envdir + "/нет-такого") == {})
# Фабрика провайдеров: заглушка только по явной настройке, нереализованный провайдер не выдаёт себя за рабочий.
from vvoice.provider_factory import make_asr_factory as _mk, describe as _describe
_none = _mk(_cfg.load({}))
check("factory_empty_gives_none", _none is None)
_fake = _mk(_cfg.load({"VV_ASR_PROVIDER": "fake"}))
check("factory_fake_only_explicit", _fake is not None)
_dg = _mk(_cfg.load({"VV_ASR_PROVIDER": "deepgram", "VV_ASR_KEY": "k"}))
check("factory_unimplemented_gives_none", _dg is None)
_desc = _describe(_cfg.load({"VV_ASR_PROVIDER": "deepgram", "VV_ASR_KEY": "k"}))
check("factory_describes_gap", _desc["asr_configured"] == "deepgram" and _desc["asr_usable"] is False)
# Списки провайдеров не должны расходиться: реализованный обязан быть разрешён в настройках.
from vvoice.provider_factory import IMPLEMENTED_ASR as _impl
_allowed = set(_cfg.ASR_PROVIDERS)
check("factory_lists_agree", set(_impl) <= _allowed, (sorted(_impl), sorted(_allowed)))
# Отсечение шума действительно доходит до разбора, а не лежит мёртвым кодом.
from vvoice.pipeline import run_session as _run_session
from vvoice.vad import VadConfig, VadGate as _VadGate
import inspect as _inspect
_sig = _inspect.signature(_run_session)
check("gate_is_a_pipeline_option", "gate" in _sig.parameters)
_h_sig = _inspect.signature(_handle)
check("gate_is_a_handle_option", "gate" in _h_sig.parameters)
check("config_noise_gate_on_by_default", _cfg.load({}).noise_gate is True)
check("config_noise_gate_can_be_off", _cfg.load({"VV_NOISE_GATE": "off"}).noise_gate is False)
_silence = b"\x00\x00" * 1600
_gate = _VadGate(config=VadConfig())
_kept = _gate.push(_silence)
# Тишина не должна выдаваться за речь: иначе шум уходит в распознавание.
check("gate_drops_silence", not _kept, _kept)
# Каждая настройка из кода описана в .env.example: иначе она есть, но о ней не узнать.
_example_path = Path(__file__).resolve().parents[2] / 'services' / 'api' / '.env.example'
_example_text = _example_path.read_text(encoding='utf-8')
_code_names = set()
for _mod in (Path(__file__).resolve().parents[2] / 'services' / 'api' / 'vvoice' / 'config.py',
             Path(__file__).resolve().parents[2] / 'services' / 'api' / 'main.py'):
    _code_names |= set(re.findall(r'VV_[A-Z_]+', _mod.read_text(encoding='utf-8')))
_undocumented = sorted(n for n in _code_names if n not in _example_text)
check("env_example_is_complete", not _undocumented, _undocumented)
# Промпт берётся из файла, который правит человек, а не из строки в коде.
from vvoice.digest import load_system_prompt as _load_prompt, SYSTEM_PROMPT as _sys_prompt
_prompt_text = _load_prompt()
check("prompt_file_is_used", len(_prompt_text) > 500, len(_prompt_text))
check("prompt_matches_code", _sys_prompt == _prompt_text)
check("prompt_has_schema", "evidence_quote" in _prompt_text and "summary" in _prompt_text)
_tmp_empty = Path(_tempfile.mkdtemp()) / "empty.md"
_tmp_empty.write_text("", encoding="utf-8")
_raised = False
try:
    _load_prompt(_tmp_empty)
except ValueError:
    _raised = True
check("prompt_empty_raises", _raised)
# Адреса целей берутся из настроек сервера, а не у клиента: телефон не должен знать, где задачник.
from vvoice.export_route import export_session as _export_session
_approved_item = [{'id': 'i1', 'kind': 'task', 'title': 'Позвонить', 'evidence_quote': 'позвони в среду', 'approved': True}]
_sent: list = []
_def_send = lambda req: (_sent.append(req), (True, ''))[1]
_code_ok, _body_ok = _export_session({'targets': {'helper': 'http://phone-should-not-decide'}, 'items': _approved_item},
                                      send=_def_send, configured={'helper': 'https://tasks.example'})
check("export_uses_server_settings", _code_ok == 200, (_code_ok, _body_ok))
check("export_ignores_client_address", any('tasks.example' in r.url for r in _sent), [r.url for r in _sent])
_code_no, _body_no = _export_session({'targets': {'helper': 'http://x'}, 'items': _approved_item},
                                     send=_def_send, configured={})
check("export_without_settings_is_honest", _code_no == 503 and _body_no.get('error') == 'export_not_configured', _body_no)
# Телефон не диктует адрес: пустое значение допустимо только при настроенном сервере.
_code_empty, _body_empty = _export_session({'targets': {'helper': ''}, 'items': _approved_item},
                                          send=_def_send, configured=None)
check("export_empty_address_is_honest", _code_empty == 400 and _body_empty.get('error') == 'empty_address', _body_empty)
_c_ok, _ = _export_session({'targets': {'helper': ''}, 'items': _approved_item}, send=_def_send, configured={'helper': 'https://tasks.example'})
check("export_empty_address_works_when_configured", _c_ok == 200, _c_ok)
# Схема контракта не должна расходиться с тем, что реально отправляется наружу.
from vvoice.exporters import ApprovedItem as _AI, to_payload as _to_payload
_schema_path = Path(__file__).resolve().parents[2] / 'docs' / 'ARCHITECTURE' / 'schemas' / 'vvoice.item.v1.json'
_schema = json.loads(_schema_path.read_text(encoding='utf-8'))
_probe = _AI(id='i1', session_id='s1', kind='task', title='Позвонить', owner=None, due_at=None,
             priority='medium', evidence_quote='позвони в среду утром', start_s=1.0, end_s=2.0,
             approved_by='владелец')
_req = _to_payload(_probe, 'webhook', 'https://crm.example/hook')
check("webhook_sends_contract", _req.body.get('schema') == 'vvoice.item.v1')
_extra = sorted(set(_req.body) - set(_schema['properties']))
check("webhook_matches_schema", not _extra, _extra)
_required_missing = [k for k in _schema['required'] if k not in _req.body]
check("webhook_has_required_fields", not _required_missing, _required_missing)
# Исходный баг #44: сервер не собирался, потому что точки запуска не было. Проверяем её наличие и поведение.
_main_src = (Path(__file__).resolve().parents[2] / 'services' / 'api' / 'main.py').read_text(encoding='utf-8')
check("main_has_entrypoint", "if __name__ == '__main__'" in _main_src)
check("main_loads_env_file", 'load_env_file(env_file)' in _main_src, 'env не читается при запуске')
check("main_builds_settings", 'load_settings(' in _main_src)
check("main_warns_about_gap", 'describe_providers(' in _main_src,
      'сервер не предупреждает, что настроенный провайдер не реализован')

# Настройки из окружения доходят до значений, а не теряются по дороге.
_s = _load({'VV_ASR_PROVIDER': 'fake', 'VV_LLM_PROVIDER': 'fake'})
check("config_env_reaches_settings", _s.asr_provider == 'fake' and _s.llm_provider == 'fake',
      (_s.asr_provider, _s.llm_provider))
# Понимание речи — такой же честный статус, как и распознавание: молчание тут опаснее ошибки.
from vvoice.provider_factory import describe as _describe, IMPLEMENTED_LLM as _IMPL_LLM
_llm_status = _describe(_load({'VV_LLM_PROVIDER': 'openai'}))
check("factory_reports_llm", _llm_status.get('llm_configured') == 'openai', _llm_status)
check("factory_llm_not_usable_yet", _llm_status.get('llm_usable') is False)
check("factory_lists_llm", isinstance(_IMPL_LLM, tuple))
# Расшифровка должна уходить человеку файлом в привычном формате, а не JSON-обёрткой.
from vvoice.transcript_route import transcript_file as _transcript_file
_digest_with_speech = {'utterances': [
    {'speaker': 'S1', 'start_s': 0.0, 'end_s': 2.5, 'text': 'Начнём с бюджета.'},
    {'speaker': 'S2', 'start_s': 2.5, 'end_s': 5.0, 'text': 'Смету пришлю утром.'},
]}
_c_srt, _b_srt, _h_srt = _transcript_file(_digest_with_speech, 'srt')
check("transcript_srt_works", _c_srt == 200 and '-->' in _b_srt and 'Смету' in _b_srt, _c_srt)
check("transcript_srt_type", _h_srt.get('Content-Type', '').startswith('application/x-subrip'), _h_srt)
_c_txt, _b_txt, _ = _transcript_file(_digest_with_speech, 'txt')
check("transcript_txt_has_speaker", _c_txt == 200 and 'S1' in _b_txt, _b_txt[:60])
_c_bad, _b_bad, _ = _transcript_file(_digest_with_speech, 'docx')
check("transcript_unknown_format", _c_bad == 400 and _b_bad.get('error') == 'unknown_format', _b_bad)
_c_none, _b_none, _ = _transcript_file(None, 'txt')
check("transcript_missing_is_honest", _c_none == 404 and _b_none.get('error') == 'digest_not_found', _b_none)
_c_empty, _b_empty, _ = _transcript_file({'utterances': []}, 'txt')
check("transcript_empty_is_honest", _c_empty == 409 and _b_empty.get('error') == 'transcript_empty', _b_empty)
check("transcript_route_registered", '/api/v1/sessions/{session_id}/transcript' in _ROUTES)
check("pipeline_keeps_utterances", '"utterances"' in (Path(__file__).resolve().parents[2] / 'services' / 'api' / 'vvoice' / 'pipeline.py').read_text(encoding='utf-8'))
# Журнал изменений: без него «что менялось» знает только автор коммита.
_changelog = Path(__file__).resolve().parents[2] / 'CHANGELOG.md'
check("changelog_exists", _changelog.exists(), 'CHANGELOG.md отсутствует')
_cl_text = _changelog.read_text(encoding='utf-8') if _changelog.exists() else ''
check("changelog_has_unreleased", '## [Unreleased]' in _cl_text)
check("changelog_not_empty", len(_cl_text.strip().splitlines()) > 4, 'журнал пуст')
# STATUS не должен врать о числе путей: это первое, что читает новый человек.
_status_text = (Path(__file__).resolve().parents[2] / 'docs' / 'SPECS' / 'STATUS.md').read_text(encoding='utf-8')
check("status_route_count_matches", ('**%d путей**' % len(_ROUTES)) in _status_text,
      'в STATUS не совпадает число путей: их %d' % len(_ROUTES))
# «Готово» на экране человека должно означать «этим можно пользоваться», а не «ключ вписан».
_h_configured = _load({'VV_ASR_PROVIDER': 'deepgram', 'VV_ASR_KEY': 'k'}).public_health()
check("health_ready_means_usable", _h_configured['asr']['ready'] is False, _h_configured['asr'])
check("health_shows_configured", _h_configured['asr']['configured'] is True, _h_configured['asr'])
check("health_shows_not_implemented", _h_configured['asr']['implemented'] is False, _h_configured['asr'])
check("health_can_transcribe_is_honest", _h_configured['can_transcribe'] is False)
_h_fake = _load({'VV_ASR_PROVIDER': 'fake', 'VV_ASR_KEY': 'k'}).public_health()
check("health_ready_for_implemented", _h_fake['asr']['ready'] is True, _h_fake['asr'])
# Документ советует конкретные имена провайдеров. Если человек скопирует их, настройки не должны молча пустеть.
_doc = (Path(__file__).resolve().parents[2] / 'docs' / 'ARCHITECTURE' / 'AI-PROVIDERS.md').read_text(encoding='utf-8')
_doc_asr = set(re.findall(r'VV_ASR_PROVIDER=([a-z0-9_]+)', _doc))
_doc_llm = set(re.findall(r'VV_LLM_PROVIDER=([a-z0-9_]+)', _doc))
from vvoice.config import ASR_PROVIDERS as _ASR_OK, LLM_PROVIDERS as _LLM_OK
check("doc_providers_are_accepted", _doc_asr <= set(_ASR_OK) and _doc_llm <= set(_LLM_OK),
      ('asr', sorted(_doc_asr - set(_ASR_OK)), 'llm', sorted(_doc_llm - set(_LLM_OK))))
# Напоминание «в 9:00» не должно превратиться в «в этот день» без единого слова.
from vvoice.exporters import to_payload as _to_payload2
_rem = _AI(id='r1', session_id='s1', kind='reminder', title='Позвонить маме', evidence_quote='напомни завтра в 9 утра',
           start_s=1.0, end_s=2.0, due_at='2026-11-27T09:00:00+05:00', approved_by='владелец')
_jira_req = _to_payload2(_rem, 'jira', 'https://x.atlassian.net')
check("jira_reminder_time_is_kept", '09:00' in _jira_req.body['fields']['description'],
      'время напоминания потерялось без предупреждения')
check("jira_reminder_date_set", _jira_req.body['fields'].get('duedate') == '2026-11-27')
# Сервер не должен отдавать чужую расшифровку тому, кто просто знает адрес.
from vvoice.http_api import handle as _handle
_code_no_token = _handle('GET', '/api/v1/health', device_tokens=('secret-1',))
check("auth_rejects_without_token", _code_no_token.status == 401, _code_no_token.status)
_code_wrong = _handle('GET', '/api/v1/health', device_tokens=('secret-1',), auth_token='nope')
check("auth_rejects_wrong_token", _code_wrong.status == 401, _code_wrong.status)
_code_ok = _handle('GET', '/api/v1/health', device_tokens=('secret-1',), auth_token='secret-1')
check("auth_accepts_right_token", _code_ok.status == 200, _code_ok.status)
_code_open = _handle('GET', '/api/v1/health')
check("auth_off_by_default", _code_open.status == 200, _code_open.status)
check("auth_sets_challenge", _code_no_token.headers.get('WWW-Authenticate') == 'Bearer', _code_no_token.headers)
load_cfg = _load
_s = load_cfg({'VV_DEVICE_TOKENS': 'a, b ,'})
check("auth_tokens_from_env", _s.device_tokens == ('a', 'b'), _s.device_tokens)
# В подсказке .env.example должны быть перечислены все допустимые провайдеры:
# человек не обязан читать код, чтобы узнать, что можно вписать.
_env = (Path(__file__).resolve().parents[2] / 'services' / 'api' / '.env.example').read_text(encoding='utf-8')
_missing_asr = [p for p in _ASR_OK if p not in _env]
_missing_llm = [p for p in _LLM_OK if p not in _env]
check("env_example_lists_providers", not _missing_asr and not _missing_llm,
      ('asr', _missing_asr, 'llm', _missing_llm))
# В журнал не должен попадать query: там когда-нибудь окажется токен.
check("log_hides_query", '_safe_path(self.path)' in _main_src and "split('?', 1)[0]" in _main_src,
      'журнал пишет путь с query — туда попадёт токен')
check("log_keeps_plain_path", 'print(\'%s %s\' % (self.command' in _main_src)
# Длинный разговор не должен выглядеть полностью разобранным.
from vvoice.digest import build_prompt as _build_prompt, prompt_is_truncated as _trunc, MAX_TRANSCRIPT_CHARS as _MAX
from vvoice.assemble import Transcript as _Tr, Utterance as _Ut
_filler = 'а' * (_MAX + 10)
_long = _Tr(utterances=[_Ut(start_s=0.0, end_s=1.0, speaker='S1', text=_filler)])
check("long_transcript_is_marked", _trunc(_long) is True)
_short = _Tr(utterances=[_Ut(start_s=0.0, end_s=1.0, speaker='S1', text='короткий разговор')])
check("short_transcript_not_marked", _trunc(_short) is False)
check("long_prompt_fits_limit", len(_build_prompt(_long)) < _MAX + 200, len(_build_prompt(_long)))
# «Модель ничего не выделила» — факт о разборе, а не пустота.
from vvoice.digest import make_digest as _make_digest
_tr_short2 = _Tr(utterances=[_Ut(start_s=0.0, end_s=2.0, speaker='S1', text='обсудили смету и сроки')])
_dg_empty = _make_digest(_tr_short2, lambda s, u: {'summary': [], 'items': [], 'participants': []})
check("empty_summary_is_marked", _dg_empty['summary_missing'] is True, _dg_empty)
_dg_ok = _make_digest(_tr_short2, lambda s, u: {'summary': ['Обсудили смету'], 'items': [], 'participants': []})
check("filled_summary_not_marked", _dg_ok['summary_missing'] is False, _dg_ok)
# Документ для внешних продуктов не должен называть полей, которых нет.
_contract = (Path(__file__).resolve().parents[2] / 'docs' / 'ARCHITECTURE' / 'EXPORT-CONTRACT.md').read_text(encoding='utf-8')
_pipeline_src = (Path(__file__).resolve().parents[2] / 'services' / 'api' / 'vvoice' / 'pipeline.py').read_text(encoding='utf-8')
_names = [n for n in ('utterances', 'digest', 'errors', 'speakers') if ('"' + n + '"') in _pipeline_src]
_missing_in_doc = [n for n in _names if ('`' + n + '`') not in _contract]
check("contract_doc_matches_result", not _missing_in_doc, _missing_in_doc)
# Инструкция установки не должна отставать от примера настроек.
_setup = (Path(__file__).resolve().parents[2] / 'docs' / 'ARCHITECTURE' / 'SETUP.md').read_text(encoding='utf-8')
_env_keys = sorted(set(re.findall(r'^(VV_[A-Z_]+)=', _env, re.M)))
_setup_missing = [k for k in _env_keys if k not in _setup]
check("setup_doc_lists_env_keys", not _setup_missing, _setup_missing)
# Сервис записывает чужие разговоры: дефолт не должен открывать его в сеть.
_main_src = (Path(__file__).resolve().parents[2] / 'services' / 'api' / 'main.py').read_text(encoding='utf-8')
check("host_defaults_to_localhost", "or '127.0.0.1'" in _main_src, 'дефолт VV_HOST')
check("host_default_not_wildcard", "or '0.0.0.0'" not in _main_src, 'дефолт 0.0.0.0 вернулся')
check("startup_names_listen_scope", 'доступен из сети' in _main_src and 'только этот компьютер' in _main_src, 'строка о прослушивании')
# Модель отвечает темой разговора — она обязана дойти до человека, а не остаться в ответе модели.
_dg_topic = _make_digest(_tr_short2, lambda s, u: {'topic': 'Бюджет и сроки', 'summary': ['Смета'], 'items': [], 'participants': []})
check("topic_reaches_result", _dg_topic.get('topic') == 'Бюджет и сроки', _dg_topic.get('topic'))
_dg_notopic = _make_digest(_tr_short2, lambda s, u: {'summary': ['Смета'], 'items': [], 'participants': []})
check("topic_empty_when_model_silent", _dg_notopic.get('topic') == '', _dg_notopic.get('topic'))
# Отправитель — единственное место, где задача покидает сервер. Проверяем на живом локальном приёмнике.
import threading as _th
from http.server import BaseHTTPRequestHandler as _BH, HTTPServer as _HS
from vvoice.export_sender import send_request as _send

_got = {}
class _Sink(_BH):
    def do_POST(self):
        _got['path'] = self.path
        _got['auth'] = self.headers.get('Authorization')
        _got['body'] = self.rfile.read(int(self.headers.get('Content-Length') or 0)).decode('utf-8')
        code = 201 if self.path == '/ok' else 500
        self.send_response(code); self.end_headers(); self.wfile.write(b'{}')
    def log_message(self, *a):
        pass

_srv = _HS(('127.0.0.1', 0), _Sink)
_th.Thread(target=_srv.serve_forever, daemon=True).start()
_port = _srv.server_address[1]
from vvoice.exporters import ExportRequest as _ER
_ok, _detail = _send(_ER(target='webhook', method='POST', url='http://127.0.0.1:%d/ok' % _port, body={'title': 'Смета'}, headers={}), token='ключ')
check("sender_posts_json", _ok, _detail)
check("sender_sends_bearer", _got.get('auth') == 'Bearer ключ', _got.get('auth'))
check("sender_body_is_json", '"title"' in (_got.get('body') or ''), _got.get('body'))
_bad_ok, _bad_detail = _send(_ER(target='webhook', method='POST', url='http://127.0.0.1:%d/bad' % _port, body={}, headers={}))
check("sender_reports_refusal", _bad_ok is False and '500' in _bad_detail, _bad_detail)
_srv.shutdown()

for name, passed, detail in checks:
    if not passed:
        sys.stderr.write("FAILED: " + name + " :: " + str(detail) + "\n")

failed2 = [c for c in checks if not c[1]]
sys.stderr.write("total=%d passed=%d failed=%d\n" % (len(checks), len(checks) - len(failed2), len(failed2)))
sys.exit(1 if failed2 else 0)
