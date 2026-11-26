#!/usr/bin/env node
/**
 * Гайд: экран не обещает «готово», если сервер не проверял ключ.
 *
 * Зачем: /health отдаёт key_checked: false — живой запрос к провайдеру не делался.
 * Экран настроек показывал «готово» по полю ready (которое означает лишь «настроено»),
 * и человек был уверен, что ключ рабочий, хотя ключ мог быть опечаткой.
 * Такая ошибка не падает и не видна в тестах — только в момент, когда расшифровка пустая.
 */
import fs from 'node:fs';
import path from 'node:path';

const file = path.join(process.cwd(), 'apps', 'mobile', 'lib', 'src', 'settings_screen.dart');
if (!fs.existsSync(file)) {
  console.log('OK: экрана настроек нет, проверять нечего');
  process.exit(0);
}
const src = fs.readFileSync(file, 'utf8');
const problems = [];

// 1) Читаем ли мы вообще key_checked — иначе фраза про «проверен» будет всегда ложной.
if (!src.includes('key_checked')) {
  problems.push('settings_screen.dart не читает key_checked: подпись про ключ обещает проверку, которой нет');
}
// 2) Слово «готово» не должно появляться как подпись состояния провайдера.
if (/' — готово'/.test(src) || /" — готово"/.test(src)) {
  problems.push('подпись «готово» осталась: ready означает «настроено», а не «ключ работает»');
}
// 3) Если читаем key_checked — должна быть ветка на «не проверен».
if (src.includes('key_checked') && !src.includes('не проверен') && !src.includes('проверится')) {
  problems.push('key_checked читается, но человеку не сказано, что ключ ещё не проверен');
}

// 4) Упавшая сеть — это «неизвестно», а не «ключ плохой»: иначе человек меняет рабочий ключ.
if (src.includes("'Не удалось соединиться")) {
  problems.push('сетевая ошибка помечена как отказ ключа: это разные вещи и разные действия человека');
}

if (problems.length) {
  console.error('❌ подписи о готовности моделей вводят в заблуждение:');
  for (const p of problems) console.error('  ' + p);
  process.exit(1);
}
console.log('OK: подписи о моделях не обещают проверку, которой не было');
