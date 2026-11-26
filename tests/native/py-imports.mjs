// Ловит NameError, который иначе находится только в CI. Так уже было: 317 проверок зелёные,
// а CI красный на "name 're' is not defined" — import re отсутствовал, и файл умирал на 870-й строке.
//
// Модель: для каждого использования модуля M.x( ищем ЛЮБОЙ импорт M ВЫШЕ по тексту (на уровне модуля
// или локально в функции). Локальный импорт честно покрывает своё использование ниже — так Python
// и работает. Ошибкой считается использование модуля, которому ни один импорт не предшествует.
import { readFileSync } from 'node:fs';

const files = process.argv.slice(2);
const MODULES = ['re', 'json', 'sys', 'os', 'math', 'hashlib', 'hmac', 'base64', 'datetime',
  'collections', 'itertools', 'time', 'tempfile', 'shutil', 'subprocess', 'urllib', 'io', 'uuid',
  'string', 'traceback', 'argparse', 'logging', 'unicodedata', 'struct', 'inspect', 'threading'];

let problems = 0;
for (const file of files) {
  const lines = readFileSync(file, 'utf8').split('\n');
  // Для каждого модуля — номера строк, где он импортирован.
  const importedAt = new Map();
  const add = (name, index) => {
    if (!importedAt.has(name)) importedAt.set(name, []);
    importedAt.get(name).push(index);
  };
  lines.forEach((line, index) => {
    const top = line.match(/^\s*import\s+(.+?)(?:\s*#.*)?$/);
    if (top) {
      for (const part of top[1].split(',')) {
        // "import X as Y" делает доступным Y (а не X) — иначе забытый синоним не поймать.
        const pieces = part.trim().split(/\s+as\s+/);
        const name = (pieces.length > 1 ? pieces[1] : pieces[0]).split('.')[0];
        if (name) add(name, index);
      }
    }
    const from = line.match(/^\s*from\s+([\w.]+)\s+import\s+(.+?)(?:\s*#.*)?$/);
    if (from) {
      add(from[1].split('.')[0], index);
      // "from pkg import name as alias" делает доступным alias — его тоже надо помнить.
      for (const part of from[2].split(',')) {
        const pieces = part.trim().split(/\s+as\s+/);
        if (pieces.length > 1) add(pieces[1].split('.')[0], index);
      }
    }
  });

  // Все имена-алиасы, объявленные импортом в этом файле.
  const aliasNames = new Set();
  lines.forEach((line) => {
    const top = line.match(/^\s*import\s+(.+?)(?:\s*#.*)?$/);
    if (top) {
      for (const part of top[1].split(',')) {
        const pieces = part.trim().split(/\s+as\s+/);
        if (pieces.length > 1) aliasNames.add(pieces[1].split('.')[0]);
      }
    }
    const from = line.match(/^\s*from\s+[\w.]+\s+import\s+(.+?)(?:\s*#.*)?$/);
    if (from) {
      for (const part of from[1].split(',')) {
        const pieces = part.trim().split(/\s+as\s+/);
        if (pieces.length > 1) aliasNames.add(pieces[1].split('.')[0]);
      }
    }
  });

  // Имена, объявленные присваиванием, включая распаковку: "_code, _body = f()", "_a: int = 1".
  const assignedNames = new Map();
  lines.forEach((line, index) => {
    const left = line.split('=')[0];
    const isAssign = line.includes('=') && !/[=!<>]=/.test(line.split('=')[0].slice(-3)) && left.trim().length > 0;
    const m = isAssign ? left.trim().match(/^([A-Za-z_][A-Za-z0-9_]*)/) : null;
    // "with open(...) as _fh:" и "for _x in ..." объявляют имя без знака "=".
    const asName = line.match(/\bas\s+([A-Za-z_][A-Za-z0-9_]*)\s*:/);
    if (asName) {
      if (!assignedNames.has(asName[1])) assignedNames.set(asName[1], []);
      assignedNames.get(asName[1]).push(index);
    }
    const forName = line.match(/^\s*for\s+([A-Za-z_][A-Za-z0-9_]*)\s+in\b/);
    if (forName) {
      if (!assignedNames.has(forName[1])) assignedNames.set(forName[1], []);
      assignedNames.get(forName[1]).push(index);
    }
    if (isAssign) {
      // Все имена слева от "=", а не только первое: _code, _body, _audio = ...
      for (const part of left.split(',')) {
        const name = part.trim().split(':')[0].trim().match(/^([A-Za-z_][A-Za-z0-9_]*)$/);
        if (name) {
          if (!assignedNames.has(name[1])) assignedNames.set(name[1], []);
          assignedNames.get(name[1]).push(index);
        }
      }
    }
  });

  let inDoc = false;
  lines.forEach((line, index) => {
    const t = line.trim();
    if (t.startsWith('"""') || t.startsWith("'''")) inDoc = !inDoc;
    if (inDoc || t.startsWith('#')) return;
    for (const m of line.matchAll(/(?<![\w.])([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\s*\(/g)) {
      const name = m[1];
      if (!MODULES.includes(name)) {
        // Имя вида _x.y(...) — это либо модуль с алиасом, либо объект. Объект в этом файле всегда
        // объявлен присваиванием выше (self, словари), поэтому проверяем объявления двумя видами:
        // import ... as _x и присваивание _x = / _x: .
        if (!/^_/.test(name)) continue;
        // Порядок для объектов не важен (Python вычислит имя до использования в том же блоке),
        // а многострочные присваивания построчный разбор не ловит. Поэтому достаточно факта
        // объявления имени где-либо в файле: цель проверки — NameError, а не анализ потока.
        const declared = (importedAt.get(name) || []).length > 0 || (assignedNames.get(name) || []).length > 0;
        if (declared) continue;
        problems++;
        console.error('FAIL ' + file + ':' + (index + 1) + ': ' + name + '.* используется как модуль, но импорта нет (неизвестный модуль)');
        continue;
      }
      const at = importedAt.get(name) || [];
      if (!at.some((i) => i <= index)) {
        problems++;
        console.error('FAIL ' + file + ':' + (index + 1) + ': используется ' + name + '.*, но импорта ' + name + ' выше нет');
      }
    }
  });
}

if (problems > 0) process.exit(1);
console.log('OK: каждый модуль импортирован до использования');
