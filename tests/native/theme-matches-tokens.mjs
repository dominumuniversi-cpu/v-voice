// Шаблоны (docs/UI/tokens.css) и приложение (theme.dart) обязаны говорить одними цветами.
// Разъехались один раз: bg, surface, ink и ok отличались в четырёх знаках — приложение выглядело
// иначе, чем показанные владельцу концепты.
import { readFileSync } from 'node:fs';

const css = readFileSync('docs/UI/tokens.css', 'utf8');
const code = readFileSync('apps/mobile/lib/src/theme.dart', 'utf8');

// Тёмная тема — первая группа переменных в файле токенов.
const dark = {};
const body = css.slice(0, css.indexOf('*/') + 2) >= 0 ? css : css;
for (const m of body.matchAll(/--vt-([a-z]+):\s*#([0-9A-Fa-f]{6})/g)) {
  if (!dark[m[1]]) dark[m[1]] = m[2].toUpperCase();
}

let problems = 0;
for (const m of code.matchAll(/Color ([a-zA-Z]+) = Color\(0xFF([0-9A-Fa-f]{6})\)/g)) {
  const name = m[1], value = m[2].toUpperCase();
  if (!dark[name]) continue; // line, warnSoft и прочие — живут только в коде
  if (dark[name] !== value) {
    problems++;
    console.error('FAIL theme.dart: ' + name + ' = ' + value + ', а в шаблонах ' + dark[name]);
  }
}
if (problems > 0) process.exit(1);
console.log('OK: цвета приложения совпадают с шаблонами');
