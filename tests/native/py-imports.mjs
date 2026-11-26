// Ловит NameError, который иначе находится только в CI. Так уже было: 317 проверок зелёные,
// а CI красный на "name 're' is not defined" — import re отсутствовал, и файл умирал на 870-й строке.
//
// Модель: для каждого использования модуля M.x( ищем ЛЮБОЙ импорт M ВЫШЕ по тексту (на уровне модуля
// или локально в функции). Локальный импорт честно покрывает своё использование ниже — так Python
// и работает. Ошибкой считается использование модуля, которому ни один импорт не предшествует.
import { readFileSync } from 'node:fs';

const files = process.argv.slice(2);
const MODULES = ['re', 'json', 'sys', 'os', 'math', 'hashlib', 'hmac', 'base64', 'datetime',
  'collections', 'itertools', 'time', 'tempfile', 'shutil', 'subprocess', 'urllib', 'io', 'uuid',
  'string', 'traceback', 'argparse', 'logging', 'unicodedata', 'struct', 'inspect', 'threading'];

let problems = 0;
for (const file of files) {
  const lines = readFileSync(file, 'utf8').split('\n');
  // Для каждого модуля — номера строк, где он импортирован.
  const importedAt = new Map();
  const add = (name, index) => {
    if (!importedAt.has(name)) importedAt.set(name, []);
    importedAt.get(name).push(index);
  };
  lines.forEach((line, index) => {
    const top = line.match(/^\s*import\s+(.+?)(?:\s*#.*)?$/);
    if (top) {
      for (const part of top[1].split(',')) {
        const name = part.trim().split(/\s+as\s+/)[0].split('.')[0];
        if (name) add(name, index);
      }
    }
    const from = line.match(/^\s*from\s+([\w.]+)\s+import/);
    if (from) add(from[1].split('.')[0], index);
  });

  let inDoc = false;
  lines.forEach((line, index) => {
    const t = line.trim();
    if (t.startsWith('"""') || t.startsWith("'''")) inDoc = !inDoc;
    if (inDoc || t.startsWith('#')) return;
    for (const m of line.matchAll(/\b([a-z][a-z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)\s*\(/g)) {
      const name = m[1];
      if (!MODULES.includes(name)) continue;
      const at = importedAt.get(name) || [];
      if (!at.some((i) => i <= index)) {
        problems++;
        console.error('FAIL ' + file + ':' + (index + 1) + ': используется ' + name + '.*, но импорта ' + name + ' выше нет');
      }
    }
  });
}

if (problems > 0) process.exit(1);
console.log('OK: каждый модуль импортирован до использования');
