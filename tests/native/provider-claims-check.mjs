#!/usr/bin/env node
/**
 * Гайд: AI-PROVIDERS.md не выдаёт нереализованных провайдеров за готовые.
 *
 * Зачем: человек покупал ключ Deepgram, ставил его, а сервер отвечал «реализации нет».
 * Документ — это тоже интерфейс: если он обещает то, чего нет, виноват документ.
 */
import fs from 'node:fs';

const factory = fs.readFileSync('services/api/vvoice/provider_factory.py', 'utf8');
const doc = fs.readFileSync('docs/ARCHITECTURE/AI-PROVIDERS.md', 'utf8');
const problems = [];

const asr = /IMPLEMENTED_ASR[^=]*=\s*\(([^)]*)\)/.exec(factory);
const llm = /IMPLEMENTED_LLM[^=]*=\s*\(([^)]*)\)/.exec(factory);
if (!asr || !llm) problems.push('не удалось прочитать реализованные провайдеры из provider_factory.py');

const clean = (s) => s.split(',').map((x) => x.trim().replace(/['"]/g, '')).filter(Boolean);

if (asr) {
  for (const name of clean(asr[1])) {
    if (!doc.includes('`' + name + '`')) problems.push('ASR ' + name + ' реализован, но не упомянут в документе');
  }
}

// Должен быть раздел с честным состоянием, а не только планы.
if (!doc.includes('Что уже подключено в коде')) {
  problems.push('в документе нет раздела о том, что подключено на самом деле');
}

// Нереализованные должны быть названы таковыми явно.
for (const name of ['Deepgram', 'AssemblyAI', 'GigaAM']) {
  const nearby = doc.split('\n').filter((l) => l.toLowerCase().includes(name.toLowerCase())).join(' ');
  const covered = /реализации нет|кода у них пока нет|есть в списке допустимых имён/i.test(doc);
  if (nearby && !covered) problems.push(name + ' описан, но нигде не сказано, что кода нет');
}

if (problems.length) {
  console.error('❌ документ о моделях расходится с кодом:');
  for (const p of problems) console.error('  ' + p);
  process.exit(1);
}
console.log('OK: документ о моделях совпадает с тем, что реализовано');
