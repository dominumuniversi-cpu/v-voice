#!/usr/bin/env node
/**
 * native-drift-check.test.mjs — тесты проверки контракта.
 * Запуск: node --test tests/native/
 * Смысл: доказать, что проверка действительно ЛОВИТ расхождения, а не просто зелёная.
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { checkSource, loadContract, checkPlatform } from './native-drift-check.mjs';
import { normalizeReport, diff } from './jsondiff.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const contract = loadContract();
const read = (p) => readFileSync(join(here, '..', '..', p), 'utf8');

test('реальные исходники соответствуют контракту', () => {
  assert.deepEqual(checkPlatform(join(here, '..', '..'), contract, 'android'), []);
  assert.deepEqual(checkPlatform(join(here, '..', '..'), contract, 'ios'), []);
});

test('манифест Android без типа microphone ловится', () => {
  const src = read('apps/mobile/android/app/src/main/AndroidManifest.xml').replace('foregroundServiceType="microphone"', 'foregroundServiceType="dataSync"');
  const problems = checkSource(contract, src, 'android');
  assert.ok(problems.some((p) => String(p.missing).includes('foregroundServiceType="microphone"')), JSON.stringify(problems));
});

test('iOS без UIBackgroundModes ловится', () => {
  const src = read('apps/mobile/ios/Runner/Info.plist').replace('<key>UIBackgroundModes</key>', '');
  const problems = checkSource(contract, src, 'ios');
  assert.ok(problems.length > 0);
});

test('запрет VOICE_CALL в Android ловится (запись чужих звонков вне MVP)', () => {
  const fake = 'AudioRecord(MediaRecorder.AudioSource.VOICE_CALL)';
  const problems = checkSource(contract, fake, 'android');
  assert.ok(problems.some((p) => String(p.forbidden).includes('VOICE_CALL')));
});

test('пустая платформа даёт список недостающего, а не молчание', () => {
  const problems = checkSource(contract, '', 'android');
  assert.ok(problems.length >= contract.android.requiredSymbols.length);
});

test('jsondiff: одинаковые отчёты (без времени) не дают шума', () => {
  const a = { contractVersion: '1.0', problems: [], generatedAt: 'x', pid: 1 };
  const b = { problems: [], contractVersion: '1.0', generatedAt: 'y', pid: 2 };
  assert.deepEqual(diff(normalizeReport(a), normalizeReport(b)), []);
});

test('jsondiff: разные проблемы видны', () => {
  const a = { contractVersion: '1.0', problems: [] };
  const b = { contractVersion: '1.0', problems: [{ platform: 'ios' }] };
  assert.ok(diff(normalizeReport(a), normalizeReport(b)).length > 0);
});


test('UI: запрет блокирующих подтверждений ловится', () => {
  const fake = 'void ask() { showDialog(context: c); }';
  const problems = checkSource(contract, fake, 'mobile_ui');
  assert.ok(problems.some((p) => String(p.forbidden).includes('showDialog')), JSON.stringify(problems));
});

test('UI: обязательные символы экрана на месте', () => {
  const real = read('apps/mobile/lib/main.dart') + read('apps/mobile/lib/src/recording_controller.dart');
  assert.deepEqual(checkSource(contract, real, 'mobile_ui'), []);
});


test('Android: событийный канал объявлен как EventChannel', () => {
  const src = read('apps/mobile/android/app/src/main/kotlin/ru/vernadsky/vvoice/RecordingChannel.kt');
  assert.ok(src.includes('EventChannel.StreamHandler'), 'ожидался EventChannel.StreamHandler');
  assert.ok(!/MethodChannel\(messenger, CHANNEL \+ \"\/events\"\)/.test(src), 'событийный канал не должен быть MethodChannel');
});
