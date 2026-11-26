// Проверка дублей импортов: Kotlin и Swift падают на них только на сборке, спустя минуты ожидания.
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, extname } from 'node:path';

const ROOT = process.argv[2] || '.';
const problems = [];

/// Обходит каталог и проверяет каждый исходник на повторные импорты.
function walk(dir) {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) { walk(full); continue; }
    const ext = extname(full);
    if (ext !== '.kt' && ext !== '.swift') continue;
    const lines = readFileSync(full, 'utf8').split(/\r?\n/);
    const seen = new Map();
    for (const line of lines) {
      const t = line.trim();
      if (!t.startsWith('import ')) continue;
      const count = (seen.get(t) || 0) + 1;
      seen.set(t, count);
      if (count === 2) problems.push({ file: full, import: t });
    }
  }
}

walk(join(ROOT, 'apps', 'mobile'));
if (problems.length) {
  for (const p of problems) console.log('FAIL ' + p.file + ': повторный импорт ' + p.import);
  process.exit(1);
}
console.log('OK: дублей импортов нет');
