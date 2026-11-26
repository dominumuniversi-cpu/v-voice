// Один источник цвета. Экран с собственным hex-кодом расходится с остальными экранами,
// и человек видит два разных «жёлтых». Исключение одно — файл темы.
import { readFileSync } from 'node:fs';
import { readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';

function walk(dir, acc = []) {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) walk(full, acc);
    else if (name.endsWith('.dart')) acc.push(full);
  }
  return acc;
}

let problems = 0;
for (const file of walk('apps/mobile/lib')) {
  if (file.endsWith('theme.dart')) continue;
  const lines = readFileSync(file, 'utf8').split('\n');
  lines.forEach((line, index) => {
    if (/Color\(0x[0-9A-Fa-f]{8}\)/.test(line)) {
      problems++;
      console.error('FAIL ' + file + ':' + (index + 1) + ': цвет мимо темы → ' + line.trim().slice(0, 70));
    }
  });
}
if (problems > 0) process.exit(1);
console.log('OK: все цвета экранов берутся из VVTheme');
