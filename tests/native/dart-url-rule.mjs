// Согласованность правила адреса: значит ли «адрес без схемы» ошибку или нет.
// Нужен потому, что смена правила в коде обрушила сборку три раза подряд — тесты в трёх файлах
// держали старое поведение. Правило живёт в одном месте кода, тесты обязаны говорить то же самое.
import { readFileSync } from 'node:fs';

const settings = readFileSync('apps/mobile/lib/src/server_settings.dart', 'utf8');
// Правило: нормализация дописывает схему, если её нет.
const addsScheme = settings.includes("text = 'https://' + text");
if (!addsScheme) {
  console.error('FAIL: нормализация больше не дописывает схему — правило изменилось, проверить все тесты адреса');
  process.exit(1);
}

const tests = ['apps/mobile/test/server_settings_test.dart', 'apps/mobile/test/server_store_test.dart', 'apps/mobile/test/app_config_test.dart'];
let problems = 0;
for (const file of tests) {
  const text = readFileSync(file, 'utf8');
  // адрес без схемы не должен считаться ошибкой проблемы.
  // Значение имеет не аргумент, а ОЖИДАНИЕ теста: адрес без схемы не должен ждать ошибку.
  const lines = text.split('\n');
  lines.forEach((line, index) => {
    for (const m of line.matchAll(/(problem|addressProblem)\(([^)]*)\)|save\(([^)]*)\)/g)) {
      const arg = (m[2] || m[3] || '').trim();
      const isAddress = /'[^']+'/.test(arg) && !/^\s*(true|false|null|[0-9a-z()._ ]*\baccept|new\b)/.test(arg);
      if (!isAddress) continue;
      const literal = arg.match(/'([^']+)'/)[1];
      const schemeLess = !/^https?:\/\//.test(literal);
      if (!schemeLess) continue;
      // «плохо»/«мусор» — намеренная проверка отказа, а не домен без схемы.
      if (/^(плохо|мусор|слово|слово-мусор)$/.test(literal)) continue;
      // Ожидание может быть на этой строке или следующей.
      const window = (line + ' ' + (lines[index + 1] || '')).trim();
      if (/(isNotNull|contains\('домен'\))/.test(window)) {
        problems++;
        console.error('FAIL ' + file + ':' + (index + 1) + ': адрес без схемы ожидают как ошибку → ' + literal);
      }
    }
  });
}
if (problems > 0) process.exit(1);
console.log('OK: тесты адреса согласованы с правилом «схему дописываем сами»');
