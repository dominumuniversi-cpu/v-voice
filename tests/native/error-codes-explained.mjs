#!/usr/bin/env node
/**
 * error-codes-explained.mjs — каждый код ошибки из натива объяснён человеку словами.
 *
 * Зачем: `emitError("mic_unavailable")` без ветки в Dart показывает пользователю сырое
 * слово вместо причины. Человек видит «mic_unavailable» — это не объяснение.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, '..', '..');
const read = (p) => readFileSync(join(root, p), 'utf8');

const natives = [
  'apps/mobile/android/app/src/main/kotlin/ru/vernadsky/vvoice/RecordingService.kt',
  'apps/mobile/ios/Runner/RecordingEngine.swift',
];
const dart = read('apps/mobile/lib/src/recording_controller.dart');
const explained = new Set([...dart.matchAll(/case '([a-z_]+)':/g)].map((m) => m[1]));

const missing = [];
for (const file of natives) {
  for (const m of read(file).matchAll(/emitError\((?:code: )?"([a-z_]+)"/g)) {
    if (!explained.has(m[1])) missing.push(file.split('/').pop() + ': ' + m[1]);
  }
}
if (missing.length) {
  console.log('FAIL коды без объяснения: ' + missing.join(', '));
  process.exit(1);
}
console.log('OK: каждый код ошибки натива объяснён словами');
