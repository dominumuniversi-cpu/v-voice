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
// Объявление функции или метода: тип, имя, скобка. Отступ разрешён (методы классов),
// тип может содержать угловые и круглые скобки (Future<(int, int, String)>).
// Внимание: наивная регулярка «от начала строки» не видела методы и врала «связность в порядке».
const DECL = /^[ \t]*(?:Future<[^(]*>|Future<[^>]*>>|void|bool|String\??|int|double|Widget|Uint8List\??|List<[^>]*>)\s+(\w+)\s*\(/gm;

const orphans = [];
for (const { path, text } of sources) {
  DECL.lastIndex = 0;
  let match;
  while ((match = DECL.exec(text)) !== null) {
    const name = match[1];
    if (ALLOWED.has(name)) continue;
    // Вызов внутри того же файла тоже считается: методы одного класса зовут друг друга.
    // Объявление отличается от вызова тем, что перед именем стоит тип возврата.
    // Тип возврата может быть сложным, но между ним и именем НЕ должно быть других скобок:
    // иначе «ListView( ... _name( » засчитывается как объявление, и настоящий вызов теряется.
    const DECL_AT = new RegExp('(Future|void|bool|String|int|double|Widget|Uint8List|List)[^;{}=()]*\\b' + name + '\\s*\\(', 'g');
    const all = [...text.matchAll(new RegExp('\\b' + name + '\\s*\\(', 'g'))].length;
    const declarations = [...text.matchAll(DECL_AT)].length;
    let calls = all - declarations;
    // Ссылка на метод без скобок тоже использование: onPressed: _retry — это вызов при нажатии.
    // Ссылки без скобок: onPressed: _retry, map(_providerCard), элементы списков.
    const asReference = new RegExp('(?:[:,]|\\()\\s*' + name + '\\s*[,)]').test(text);
    const external = sources.some((other) =>
      other.path !== path && new RegExp('\\b' + name + '\\s*\\(').test(other.text));
    if (asReference) calls = calls + 1;
    if (calls === 0 && !external) orphans.push(path + ' :: ' + name);
  }
}

if (orphans.length > 0) {
  console.error('Функции без вызовов (сделано, но не подключено):');
  for (const item of orphans) console.error('  ' + item);
  console.error('Либо подключите, либо удалите, либо добавьте в ALLOWED с причиной.');
  process.exit(1);
}
console.log('связность в порядке: все функции вызываются');
