#!/usr/bin/env node
/**
 * Гайд: класс с `implements` обязан объявить все методы интерфейса.
 *
 * Зачем: Dart не наследует тела методов по умолчанию через `implements`. Если в интерфейс
 * добавили метод, каждый реализующий класс должен его объявить — иначе компилятор падает
 * строкой «Missing concrete implementations», которую локально видно только в CI.
 * Такой случай уже был: добавили pause()/resume() в RecordingBridge, а мост в метод-канале
 * не обновили — раунд ушёл на разбор лога.
 */
import fs from 'node:fs';
import path from 'node:path';

/** Собирает .dart-файлы проекта, кроме сгенерированных. */
function dartFiles(root) {
  const out = [];
  const walk = (dir) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      if (entry.name === 'build' || entry.name === '.dart_tool') continue;
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) walk(full);
      else if (entry.name.endsWith('.dart')) out.push(full);
    }
  };
  walk(root);
  return out;
}

/** Имена методов, объявленных в теле класса/интерфейса (верхний уровень скобок). */
function declaredMethods(src, className) {
  const start = src.search(new RegExp('(abstract\\s+)?class\\s+' + className + '\\b'));
  if (start < 0) return null;
  const braceStart = src.indexOf('{', start);
  let depth = 0;
  let end = src.length;
  for (let i = braceStart; i < src.length; i++) {
    if (src[i] === '{') depth++;
    else if (src[i] === '}') {
      depth--;
      if (depth === 0) { end = i; break; }
    }
  }
  const body = src.slice(braceStart, end);
  const names = new Set();
  const re = /^\s{2}(?:@override\s+)?(?:static\s+)?(?:Future<[^>]*>|Stream<[^>]*>|void|bool|int|String|double|List<[^>]*>|Map<[^>]*>)\s+(?:get\s+)?(\w+)/gm;
  for (const m of body.matchAll(re)) names.add(m[1]);
  return names;
}

/** Интерфейсы, которые класс реализует через implements. */
function implementedNames(src) {
  const re = /class\s+(\w+)[^{]*\bimplements\s+([\w,\s]+)/g;
  return [...src.matchAll(re)].map((m) => ({ cls: m[1], ifaces: m[2].split(',').map((s) => s.trim()).filter(Boolean) }));
}

const root = path.join(process.cwd(), 'apps', 'mobile');
if (!fs.existsSync(root)) {
  console.log('OK: dart-исходников нет, проверять нечего');
  process.exit(0);
}
const files = dartFiles(root);
const sources = files.map((f) => ({ file: f, src: fs.readFileSync(f, 'utf8') }));
const problems = [];
for (const { file, src } of sources) {
  for (const { cls, ifaces } of implementedNames(src)) {
    const have = declaredMethods(src, cls) || new Set();
    for (const iface of ifaces) {
      const owner = sources.find((s) => new RegExp('class\\s+' + iface + '\\b').test(s.src));
      if (!owner) continue;
      const need = declaredMethods(owner.src, iface) || new Set();
      const missing = [...need].filter((n) => !have.has(n) && n !== iface);
      if (missing.length) problems.push(path.relative(process.cwd(), file) + ': ' + cls + ' не объявляет ' + missing.join(', '));
    }
  }
}
if (problems.length) {
  console.error('❌ классы не реализуют интерфейс целиком:');
  for (const p of problems) console.error('  ' + p);
  process.exit(1);
}
console.log('OK: каждый implements-класс объявляет методы своего интерфейса');
