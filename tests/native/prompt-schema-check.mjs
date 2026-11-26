#!/usr/bin/env node
/**
 * Гайд: схема ответа в промпте совпадает с тем, что читает валидатор.
 *
 * Зачем: в prompts/digest_ru.md лежали ДВЕ разные схемы ответа. Одна просила
 * evidence = {quote, start_s, end_s}, другая — плоское поле evidence_quote. Модель,
 * послушав вторую, вернула бы пункты, которые валидатор отбрасывает целиком:
 * разбор выглядел бы пустым, и виноватой выглядела бы модель.
 * Такое расхождение не ловится ни сборкой, ни тестами — только сверкой двух файлов.
 */
import fs from 'node:fs';
import path from 'node:path';

const promptPath = path.join(process.cwd(), 'services', 'api', 'vvoice', 'prompts', 'digest_ru.md');
const validatorPath = path.join(process.cwd(), 'services', 'api', 'vvoice', 'evidence.py');
if (!fs.existsSync(promptPath) || !fs.existsSync(validatorPath)) {
  console.log('OK: промпта или валидатора нет, сверять нечего');
  process.exit(0);
}
const prompt = fs.readFileSync(promptPath, 'utf8');
const validator = fs.readFileSync(validatorPath, 'utf8');
const problems = [];

// 1) Одна схема: два заголовка «Формат ответа» — это две разные правды для модели.
const schemas = (prompt.match(/## Формат ответа/g) || []).length;
if (schemas > 1) problems.push('в промпте ' + schemas + ' блока «Формат ответа» — модель получит противоречивые схемы');

// 2) Цитата: валидатор читает evidence.quote, промпт обязан просить её там же.
if (validator.includes('.get("quote")') && !prompt.includes('evidence.quote')) {
  problems.push('валидатор читает evidence.quote, а промпт просит цитату в другом месте');
}
if (prompt.includes('evidence_quote')) {
  problems.push('промпт просит плоское поле evidence_quote, которого валидатор не читает');
}

// 3) Таймкоды: без них валидатор отбрасывает пункт как некорректный.
if (validator.includes('.get("start_s")') && !prompt.includes('start_s')) {
  problems.push('валидатор требует start_s, а промпт о нём молчит');
}

// 4) Приоритеты: валидатор может знать одно слово, промпт — другое.
const validatorPriorities = ['low', 'normal', 'high', 'medium'].filter((p) => validator.includes('"' + p + '"'));
if (validatorPriorities.length && prompt.includes('priority')) {
  const tooHigh = prompt.includes('medium') && !validator.includes('"medium"');
  if (tooHigh) problems.push('промпт разрешает priority=medium, валидатор такого значения не знает');
}

// 5) Участники: валидатор читает dict (speaker/verdict), промпт не должен просить список строк.
if (validator.includes('.get("verdict")') && prompt.includes('participants') && !prompt.includes('"verdict"')) {
  problems.push('валидатор ждёт у участников verdict, промпт его не просит');
}

if (problems.length) {
  console.error('❌ промпт и валидатор расходятся:');
  for (const p of problems) console.error('  ' + p);
  process.exit(1);
}
console.log('OK: схема в промпте совпадает с валидатором');
