// Проверка прототипов: ни одна var(--x) не должна остаться без объявления.
// Найдено на живом макете: concept-a ссылался на четыре переменные и не объявлял ни одной —
// браузер подставлял пустоту, часть текста могла стать невидимой, а макет «открывался».
import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

const dir = 'docs/UI/prototypes';
let problems = 0;
let checked = 0;

for (const name of readdirSync(dir)) {
  if (!name.endsWith('.html')) continue;
  checked++;
  const text = readFileSync(join(dir, name), 'utf8');
  const used = new Set([...text.matchAll(/var\((--[\w-]+)\)/g)].map((m) => m[1]));
  const declared = new Set([...text.matchAll(/(--[\w-]+)\s*:/g)].map((m) => m[1]));
  const missing = [...used].filter((v) => !declared.has(v));
  if (missing.length > 0) {
    problems++;
    console.error('FAIL ' + name + ': не объявлены ' + missing.join(', '));
  }
}

if (checked === 0) {
  console.error('FAIL: в ' + dir + ' нет ни одного прототипа');
  process.exit(1);
}
if (problems > 0) process.exit(1);
console.log('OK: переменные CSS в прототипах объявлены (' + checked + ' файлов)');
