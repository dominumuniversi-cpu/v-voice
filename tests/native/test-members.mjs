// Проверяет, что тесты не зовут несуществующих статических методов классов.
import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

const problems = [];
const libFiles = readdirSync('apps/mobile/lib/src').filter(f => f.endsWith('.dart'));
const libText = libFiles.map(f => readFileSync(join('apps/mobile/lib/src', f), 'utf8')).join('\n');

const testFiles = readdirSync('apps/mobile/test').filter(f => f.endsWith('.dart'));
for (const file of testFiles) {
  const text = readFileSync(join('apps/mobile/test', file), 'utf8');
  // Вид вызова: ClassName.member( — проверяем, что member объявлен в lib.
  for (const m of text.matchAll(/\b([A-Z][A-Za-z0-9_]*)\.([a-z][A-Za-z0-9_]*)\s*\(/g)) {
    const member = m[2];
    // Пропускаем обращения к типам из flutter (tester, expect и пр. не подходят под \(...)\) класс).
    if (/^(pumpAndSettle|pumpWidget)$/.test(member)) continue;
    const declared = new RegExp('\\b' + member + '\\s*\\(').test(libText);
    if (!declared) problems.push(file + ': ' + m[1] + '.' + member + ' не найден в lib');
  }
}
if (problems.length) {
  for (const p of [...new Set(problems)]) console.log('FAIL ' + p);
  process.exit(1);
}
console.log('OK: тесты не зовут несуществующих членов');
