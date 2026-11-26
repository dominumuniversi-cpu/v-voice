// Ловит ошибку "Expected 'else' or comma": в списке аргументов после закрывающей скобки
// блока-условия должен идти else или запятая, иначе следующий элемент списка ломает разбор.
// Так уже было: if (d.summary.isEmpty) Padding(...) и сразу _section(...) — CI красный.
import { readFileSync } from 'node:fs';

const files = process.argv.slice(2);
let problems = 0;
for (const file of files) {
  const lines = readFileSync(file, 'utf8').split('\n');
  for (let i = 0; i < lines.length - 1; i++) {
    const close = lines[i].trim();
    if (close !== ')' && close !== '),') continue;
    const next = lines[i + 1].trim();
    // Следующая строка — вызов или условие в том же списке, а между ними ни else, ни запятой.
    if (/^[A-Za-z_][A-Za-z0-9_]*[.(]/.test(next) && !close.endsWith(',')) {
      problems++;
      console.error('FAIL ' + file + ':' + (i + 2) + ': после ")" идёт элемент списка без else и без запятой → ' + next.slice(0, 60));
    }
    if (/^if \(/.test(next) && !close.endsWith(',')) {
      problems++;
      console.error('FAIL ' + file + ':' + (i + 2) + ': после ")" идёт if без else и без запятой → ' + next.slice(0, 60));
    }
  }
}
if (problems > 0) process.exit(1);
console.log('OK: скобки в списках аргументов закрыты по правилам Dart');
