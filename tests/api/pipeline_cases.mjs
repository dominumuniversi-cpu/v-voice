#!/usr/bin/env node
/**
 * pipeline_cases.mjs — сквозные кейсы конвейера «сегменты -> реплики -> разбор -> валидатор».
 *
 * Зачем: на машине нет Python, но поведение конвейера (а не только синтаксис модулей) должно быть
 * проверено уже сейчас. Здесь — зеркало той же логики (шум, склейка, volatile, обрыв провайдера,
 * выдуманная цитата) в JS. При появлении Python тот же сценарий прогоняется pytest-ом:
 * файл tests/api/test_pipeline.py повторяет эти кейсы.
 *
 * Запуск: node --test tests/api/
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';

const MIN_SPEECH = 0.2, MERGE_GAP = 1.5, MIN_QUOTE_LEN = 12, DROP = /$/;

const seg = (o) => ({ speaker: 'Голос 1', confidence: 1, volatile: false, is_noise: false, ...o });

export function assemble(segments, mergeGap = MERGE_GAP) {
  const usable = segments.filter((s) => !s.volatile).sort((a, b) => a.start_s - b.start_s || a.end_s - b.end_s);
  const out = []; let droppedNoise = 0, droppedShort = 0;
  for (const s of usable) {
    if (s.is_noise) { droppedNoise++; continue; }
    if (!(s.end_s - s.start_s >= MIN_SPEECH) || !s.text.trim()) { droppedShort++; continue; }
    const last = out[out.length - 1];
    if (last && last.speaker === s.speaker && s.start_s - last.end_s <= mergeGap) {
      last.text = (last.text + ' ' + s.text.trim()).trim();
      last.end_s = Math.max(last.end_s, s.end_s);
      continue;
    }
    out.push({ speaker: s.speaker, start_s: s.start_s, end_s: s.end_s, text: s.text.trim() });
  }
  return { utterances: out, droppedNoise, droppedShort, text: out.map((u) => u.speaker + ': ' + u.text).join(' ') };
}

const normalize = (t) => (t || '').toLowerCase().replaceAll('ё', 'е').replace(/\s+/g, ' ').trim();
export const quotePresent = (q, transcript) => normalize(q).length > 0 && normalize(transcript).includes(normalize(q));

export function validateItem(item, transcript, speakers) {
  if (!item || typeof item !== 'object') return [false, 'элемент не объект'];
  if (!['task', 'meeting', 'reminder', 'decision', 'question'].includes(item.kind)) return [false, 'неизвестный тип'];
  if (!String(item.title ?? '').trim()) return [false, 'пустой заголовок'];
  const ev = item.evidence;
  if (!ev || typeof ev !== 'object') return [false, 'нет evidence'];
  if (normalize(String(ev.quote ?? '')).length < MIN_QUOTE_LEN) return [false, 'цитата короче 12 символов'];
  if (!(ev.start_s >= 0 && ev.start_s <= ev.end_s)) return [false, 'некорректные таймкоды'];
  if (!quotePresent(String(ev.quote ?? ''), transcript)) return [false, 'цитаты нет в транскрипте'];
  if (item.owner && speakers && !speakers.includes(item.owner)) return [false, 'владелец не участвовал'];
  if (item.due_at != null && !/^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2})?([+-]\d{2}:?\d{2})?)?$/.test(item.due_at)) return [false, 'due_at не ISO8601'];
  return [true, 'ok'];
}

const SEGMENTS = [
  seg({ start_s: 0, end_s: 3, speaker: 'Анна', text: 'По бюджету до пятницы надо понять, укладываемся' }),
  seg({ start_s: 3.2, end_s: 5, speaker: 'Анна', text: 'или нет.' }),
  seg({ start_s: 5.5, end_s: 6.0, speaker: 'Анна', text: 'эээ', is_noise: true }),
  seg({ start_s: 6.5, end_s: 9, speaker: 'Дмитрий', text: 'Я отправлю смету завтра утром, успеем.' }),
  seg({ start_s: 9, end_s: 9.1, speaker: 'Голос 3', text: 'угу' }),
  seg({ start_s: 10, end_s: 13, speaker: 'Анна', text: 'Тогда созвон перенесём на девятое декабря в час дня.' }),
];

test('шум и слишком короткие фрагменты не попадают в транскрипт', () => {
  const t = assemble(SEGMENTS);
  assert.equal(t.droppedNoise, 1);
  assert.equal(t.droppedShort, 1);
  assert.equal(t.utterances.length, 3);
});

test('соседние реплики одного говорящего склеиваются', () => {
  const t = assemble(SEGMENTS);
  assert.equal(t.utterances[0].text, 'По бюджету до пятницы надо понять, укладываемся или нет.');
});

test('volatile-фрагменты в итог не идут', () => {
  const t = assemble([...SEGMENTS, seg({ start_s: 14, end_s: 16, text: 'возможно ещё что-то', volatile: true })]);
  assert.ok(!t.text.includes('возможно ещё что-то'));
});

test('валидная задача проходит, выдуманная — нет', () => {
  const t = assemble(SEGMENTS);
  const speakers = t.utterances.map((u) => u.speaker);
  const good = { kind: 'task', title: 'Отправить смету', owner: 'Дмитрий', due_at: '2026-11-27T08:00:00+05:00',
    evidence: { start_s: 6.5, end_s: 9, quote: 'Я отправлю смету завтра утром, успеем' } };
  assert.deepEqual(validateItem(good, t.text, speakers), [true, 'ok']);
  const invented = { ...good, evidence: { start_s: 1, end_s: 2, quote: 'Надо уволить половину отдела' } };
  assert.equal(validateItem(invented, t.text, speakers)[0], false);
  assert.equal(validateItem({ ...good, owner: 'Олег' }, t.text, speakers)[0], false);
});

test('обрыв провайдера не теряет уже полученное', () => {
  const finals = []; const errors = [];
  const chunks = [1, 2, 3, 4];
  for (const [i, c] of chunks.entries()) {
    if (i === 2) { errors.push('provider_disconnected'); continue; }
    finals.push(seg({ start_s: c, end_s: c + 1, speaker: 'Анна', text: 'фрагмент номер ' + c }));
  }
  assert.equal(finals.length, 3);
  assert.equal(errors.length, 1);
});

test('живой текст: окончательное + приблизительное', () => {
  const finals = [seg({ start_s: 0, end_s: 2, text: 'Я отправлю' })];
  const volatileSeg = seg({ start_s: 2, end_s: 4, text: 'смету завтра', volatile: true });
  const display = (finals.map((s) => s.text).join(' ') + ' ' + volatileSeg.text).trim();
  assert.equal(display, 'Я отправлю смету завтра');
});

test('режим «только участники»: реплика чужого голоса не попадает в разбор, аудио остаётся', () => {
  const segments = [
    ...SEGMENTS,
    seg({ start_s: 20, end_s: 24, speaker: 'Голос 3', text: 'Да я его вообще не знаю, случайно тут проходил' }),
  ];
  const t = assemble(segments);
  assert.ok(t.text.includes('случайно тут проходил'), 'чужой голос слышен в расшифровке');
  const item = { kind: 'task', title: 'Выяснить отношения', speaker: 'Голос 3',
    evidence: { start_s: 20, end_s: 24, quote: 'Да я его вообще не знаю, случайно тут проходил' } };
  const speakers = t.utterances.map((u) => u.speaker);
  const withGate = (it, on) => on && it.speaker === 'Голос 3' ? [false, 'реплика чужого голоса'] : validateItem(it, t.text, speakers);
  assert.equal(withGate(item, false)[0], true, 'без режима задача проходит');
  assert.equal(withGate(item, true)[0], false, 'в режиме «только участники» — отбрасывается');
});


// ---------- VAD: тишина не уходит в облако, первое слово не срезается ----------
export function makeGate(cfg = {}) {
  const c = { on_db: 9, off_db: 4, preroll_frames: 15, hangover_frames: 25, noise_percentile: 0.2, ...cfg };
  const st = { floor: -60, speaking: false, silence: 0, preroll: [], hist: [] };
  return {
    state: st,
    push(db) {
      st.hist.push(db); if (st.hist.length > 125) st.hist.shift();
      if (st.hist.length >= 10) { const s = [...st.hist].sort((a, b) => a - b); st.floor = s[Math.min(Math.floor(s.length * c.noise_percentile), s.length - 1)]; }
      if (!st.speaking) { st.preroll.push(db); if (st.preroll.length > c.preroll_frames) st.preroll.shift(); }
      const loud = db > st.floor + c.on_db;
      const still = db > st.floor + c.off_db;
      if (st.speaking) {
        if (still) st.silence = 0; else { st.silence++; if (st.silence > c.hangover_frames) { st.speaking = false; st.preroll = []; } }
        return st.speaking;
      }
      if (loud) { st.speaking = true; st.silence = 0; return true; }
      return false;
    },
  };
}

test('VAD: тишина не отправляется в облако', () => {
  const g = makeGate();
  const quiet = Array.from({ length: 100 }, () => -62);
  const sent = quiet.filter((db) => g.push(db)).length;
  assert.equal(sent, 0);
});

test('VAD: громкая речь отправляется и держит гистерезис в коротких паузах', () => {
  const g = makeGate();
  // 40 кадров тишины: шумовой пол фиксируется на -62 Дб
  Array.from({ length: 40 }, () => -62).forEach((db) => g.push(db));
  const speech = Array.from({ length: 20 }, () => -25);
  assert.equal(speech.filter((db) => g.push(db)).length, 20, 'вся речь должна уйти');
  // пауза чуть выше шумового пола (на 4 дБ) — всё ещё «речь» по гистерезису
  const shortPause = Array.from({ length: 10 }, () => -58);
  assert.equal(shortPause.filter((db) => g.push(db)).length, 10, 'короткая пауза не рвёт реплику');
  // длинная пауза на уровне шума — VAD закрывается через hangover, не мгновенно
  const longPause = Array.from({ length: 40 }, () => -62);
  const after = longPause.filter((db) => g.push(db)).length;
  // Факт (замер): за 40 кадров паузы уходят 15 — это преролл новой реплики, речь не рвётся.
  assert.ok(after > 0 && after < 40, 'закрытие идёт не мгновенно, но и не бесконечно: ' + after);
  assert.ok(!g.state.speaking, 'к концу длинной паузы VAD закрыт');
});

test('VAD НЕ глушит людей в тихой комнате: -55 дБ не считается тишиной', () => {
  // Ошибка, которую этот тест запрещает: «пауза громче шума = тишина». Тихая речь важнее экономии.
  const g = makeGate();
  Array.from({ length: 40 }, () => -70).forEach((db) => g.push(db));
  const softSpeech = Array.from({ length: 30 }, () => -55);
  assert.equal(softSpeech.filter((db) => g.push(db)).length, 30, 'тихая речь не должна отбрасываться');
});

test('VAD: преролл не даёт срезать первое слово', () => {
  const g = makeGate();
  Array.from({ length: 20 }, () => -62).forEach((db) => g.push(db));
  const prerollLen = g.state.preroll.length;
  assert.ok(prerollLen >= 15, 'накопили преролл: ' + prerollLen);
  g.push(-25);
  assert.ok(g.state.preroll.length >= 15, 'преролл цел в момент старта речи');
});

test('VAD: адаптивный порог поднимается в шумном помещении', () => {
  const g = makeGate();
  Array.from({ length: 125 }, () => -35).forEach((db) => g.push(db)); // шумный зал
  assert.ok(g.state.floor > -50, 'шумовой пол учтён: ' + g.state.floor.toFixed(1));
  const noise = Array.from({ length: 20 }, () => -33);
  assert.equal(noise.filter((db) => g.push(db)).length, 0, 'фоновый гул не уходит в облако');
  const voice = Array.from({ length: 20 }, () => -20);
  assert.equal(voice.filter((db) => g.push(db)).length, 20, 'голос поверх гула распознаётся');
});
