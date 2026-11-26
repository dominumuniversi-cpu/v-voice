// Проверка «сделано, но не подключено».
//
// Причина: в этом проекте систематически появлялся код, который работает и покрыт тестами,
// но никто его не вызывает. Тесты такой код НЕ ловят по устройству: они проверяют функцию,
// значит вызов в тесте и считается «использованием».
//
// Правило: публичная функция в apps/mobile/lib без вызовов в других файлах — красный флаг.
// Исключения объявляются явно и с причиной: молчаливых исключений не бывает.
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';

const ROOT = 'apps/mobile/lib';

// Разрешено не иметь вызовов: точка входа библиотеки, элементы, которые вызывает Flutter.
const ALLOWED = new Map([
  ['main', 'точка входа, её вызывает Flutter'],
  ['build', 'переопределение Widget'],
  ['createState', 'переопределение StatefulWidget'],
  ['updateShouldNotify', 'переопределение InheritedWidget'],
  ['initState', 'переопределение State'],
  ['dispose', 'переопределение State'],
]);

function files(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) out.push(...files(full));
    else if (name.endsWith('.dart')) out.push(full);
  }
  return out;
}

const sources = files(ROOT).map((path) => ({ path, text: readFileSync(path, 'utf8') }));
const DECL = /^(?:Future<[^>]*>|void|bool|String|int|Widget|Uint8List)\s+(\w+)\s*\(/gm;

const orphans = [];
for (const { path, text } of sources) {
  DECL.lastIndex = 0;
  let match;
  while ((match = DECL.exec(text)) !== null) {
    const name = match[1];
    if (ALLOWED.has(name)) continue;
    const callers = sources.filter((other) =>
      other.path !== path && new RegExp('\\b' + name + '\\s*\\(').test(other.text));
    if (callers.length === 0) orphans.push(path + ' :: ' + name);
  }
}

if (orphans.length > 0) {
  console.error('Функции без вызовов (сделано, но не подключено):');
  for (const item of orphans) console.error('  ' + item);
  console.error('Либо подключите, либо удалите, либо добавьте в ALLOWED с причиной.');
  process.exit(1);
}
console.log('связность в порядке: все функции вызываются');
