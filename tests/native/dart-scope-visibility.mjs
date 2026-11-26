#!/usr/bin/env node
// Страж: `scope` существует только внутри build(). Обращение к нему из других методов класса
// даёт ошибку flutter analyze, которую локальные проверки до сих пор пропускали (3 раза подряд).
// Здесь ловим заранее: вне build() допустим только ServerScope.maybeOf(context) или widget.*.
import { readFileSync } from 'node:fs';

const files = process.argv.slice(2);
const HEAD = /^\s{2}(?:Future<[^>]*>|void|Widget|String|bool|int|double|List<[^>]*>)\s+\w+\(/;

let bad = 0;
for (const path of files) {
  const lines = readFileSync(path, 'utf8').split('\n');
  let current = '(верх файла)';
  // Локальная переменная scope внутри метода — законная: тогда обращение к ней допустимо.
  let declaredLocally = false;
  lines.forEach((line, index) => {
    if (/\bWidget build\(BuildContext/.test(line)) { current = 'build'; declaredLocally = false; }
    else if (HEAD.test(line)) { current = line.trim(); declaredLocally = false; }
    if (/\bfinal\s+scope\s*=/.test(line) || /\bvar\s+scope\s*=/.test(line)) declaredLocally = true;
    if (declaredLocally && current !== 'build') return;
    // Обращение к scope вне build: `scope.` не считается, если рядом ServerScope (другой токен).
    if (current !== 'build' && /\bscope\./.test(line) && !/ServerScope/.test(line)) {
      console.log('FAIL: строка ' + (index + 1) + ' в «' + current + '»: scope виден только в build() → '
        + 'передайте api параметром или возьмите ServerScope.maybeOf(context)');
      bad++;
    }
  });
}
if (bad === 0) console.log('OK: scope используется только там, где он определён');
process.exit(bad === 0 ? 0 : 1);
