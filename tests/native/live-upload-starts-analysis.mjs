#!/usr/bin/env node
/**
 * live-upload-starts-analysis.mjs — после загрузки живой встречи сервер обязан начать разбор.
 *
 * Зачем: разбор не запускается сам ни после загрузки, ни по живому тексту. Пропущенный вызов
 * startAnalysis оставлял живую встречу в состоянии «ещё не готов» навсегда — без единой ошибки.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, '..', '..');
const main = readFileSync(join(root, 'apps/mobile/lib/main.dart'), 'utf8');

const liveBranch = main.slice(main.indexOf('sessionId: _sessionId'));
const tail = liveBranch.slice(0, liveBranch.indexOf('if (_sessionId == null)'));
const ok = tail.includes('startAnalysis(');
if (!ok) {
  console.log('FAIL: после загрузки живой встречи не запускается разбор');
  process.exit(1);
}
console.log('OK: живая встреча после загрузки сама уходит в разбор');
