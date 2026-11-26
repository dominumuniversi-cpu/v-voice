// Ловит "missing_required_argument": ApiClient в этом проекте собирается только именованными
// параметрами (transport:, baseUrl:). Позиционный вызов падает в CI, а локально Dart нет.
import { readFileSync } from 'node:fs';

const files = process.argv.slice(2);
const NAMED = new Set(['transport', 'baseUrl', 'deviceToken']);
let problems = 0;
for (const file of files) {
  const lines = readFileSync(file, 'utf8').split('\n');
  lines.forEach((line, index) => {
    for (const m of line.matchAll(/ApiClient\(([^)]*)\)/g)) {
      const args = m[1].trim();
      if (!args) continue;
      // Объявление конструктора (ApiClient({required this.transport ...})) — не вызов.
      if (/\bthis\.|\brequired\b/.test(args)) continue;
      // Всё, что до первого ":" вне кавычек, позиционное — а значит ошибка.
      const first = args.split(',')[0].trim();
      // Именованный аргумент — это всегда "имя: значение". Без двоеточия аргумент позиционный,
      // даже если его текст совпадает с именем параметра (ApiClient(transport) — та самая ошибка).
      const name = first.split(':')[0].trim();
      if (!first.includes(':') || !NAMED.has(name)) {
        problems++;
        console.error('FAIL ' + file + ':' + (index + 1) + ': ApiClient с позиционным аргументом → ' + first.slice(0, 50));
      }
    }
  });
}
if (problems > 0) process.exit(1);
console.log('OK: ApiClient собирается именованными параметрами');
