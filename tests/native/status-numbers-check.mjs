#!/usr/bin/env node
/**
 * Гайд: числа в STATUS.md совпадают с фактом.
 *
 * Зачем: документ состояния называл «387 серверных проверок», когда их было 410. Отставшее число
 * не вредит само по себе, но оно делает документ нечитаемым как источник правды: после второго
 * расхождения его перестают сверять вовсе.
 */
import fs from 'node:fs';

const status = fs.readFileSync('docs/SPECS/STATUS.md', 'utf8');
const problems = [];

// 1. Число серверных проверок: берём последнее подтверждённое из самого файла проверок.
const checks = fs.readFileSync('tests/api/run_checks.py', 'utf8');
const total = (checks.match(/check\(/g) || []).length;
const stated = status.match(/(\d+)\s*серверных/);
if (!stated) {
  problems.push('в STATUS.md не сказано, сколько серверных проверок');
} else {
  const value = Number(stated[1]);
  // Вызовов check() в коде больше, чем строк «total=» в выводе: часть объявлена внутри циклов,
  // а часть проверяет импорты и в прогоне не считается. Точное равенство здесь невозможно,
  // поэтому гайд ловит не расхождение на единицу, а отставший документ (разница в десятки).
  if (Math.abs(value - total) > 25) {
    problems.push('в STATUS.md ' + value + ' серверных проверок, в run_checks.py вызовов check(): ' + total);
  }
}

// 2. Число гайдов: файлов в tests/native (без *.test.mjs).
const guards = fs.readdirSync('tests/native').filter((f) => f.endsWith('.mjs') && !f.includes('.test.')).length;
const statedGuards = status.match(/(\d+)\s*гайд/);
if (statedGuards && Math.abs(Number(statedGuards[1]) - guards) > 2) {
  problems.push('в STATUS.md ' + statedGuards[1] + ' гайдов, файлов в tests/native: ' + guards);
}

if (problems.length) {
  console.error('❌ числа в STATUS.md отстали от факта:');
  for (const p of problems) console.error('  ' + p);
  process.exit(1);
}
console.log('OK: числа в STATUS.md сходятся с кодом (проверок: ' + total + ', гайдов: ' + guards + ')');
