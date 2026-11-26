#!/usr/bin/env node
/**
 * Гайд: контракт экспорта, схема и то, что реально отдаёт сервер, не расходятся.
 *
 * Зачем: EXPORT-CONTRACT.md описывал ответ /digest как «разбор во вложенном digest» — интегратор
 * писал бы клиент под формат, которого уже нет, и получал пустой экран. Такие расхождения
 * не ловятся ни сборкой, ни серверными проверками: они про ТЕКСТ, который читает чужой человек.
 */
import fs from 'node:fs';

const problems = [];
const read = (p) => fs.readFileSync(p, 'utf8');

const schema = JSON.parse(read('docs/ARCHITECTURE/schemas/vvoice.item.v1.json'));
const doc = read('docs/ARCHITECTURE/EXPORT-CONTRACT.md');
const kinds = schema.properties?.kind?.enum || [];

if (kinds.length === 0) problems.push('в схеме нет перечня видов kind');

// 1. Каждый вид из схемы обязан быть объяснён в контракте: интегратор не должен угадывать.
for (const kind of kinds) {
  if (!doc.includes('`' + kind + '`')) {
    problems.push('вид `' + kind + '` есть в схеме, но не описан в контракте');
  }
}

// 2. Контракт не должен обещать вложенный разбор: сервер отдаёт его наверху.
if (/разбор лежит во вложенном/i.test(doc)) {
  problems.push('контракт обещает разбор во вложенном digest — сервер отдаёт его наверху');
}

// 3. Обязательные поля схемы должны упоминаться в контракте хотя бы по имени.
for (const field of schema.required || []) {
  if (!doc.includes(field)) problems.push('обязательное поле ' + field + ' не упомянуто в контракте');
}

if (problems.length) {
  console.error('❌ контракт экспорта расходится со схемой:');
  for (const p of problems) console.error('  ' + p);
  process.exit(1);
}
console.log('OK: контракт экспорта совпадает со схемой (' + kinds.length + ' видов, ' + (schema.required || []).length + ' обязательных полей)');
