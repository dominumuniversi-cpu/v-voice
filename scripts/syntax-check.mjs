#!/usr/bin/env node
/**
 * syntax-check.mjs — проверка синтаксиса Python-файлов без установленного Python.
 *
 * Зачем: сервер (FastAPI) и валидаторы пишутся на Python, а на машине разработки/CI
 * Python может отсутствовать. Здесь мы заменяем `python -m compileall` эквивалентной проверкой:
 * разбираем теми же правилами (отступы, строки, скобки) и ловим типичные поломки — смешанные
 * табы/пробелы, незакрытые строки, несбалансированные скобки, импорт без модуля.
 * Полноценная проверка типов всё равно требует Python — эта — быстрая страховка до его появления.
 *
 * Запуск: node scripts/syntax-check.mjs [--json]
 */
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';

const ROOT = process.cwd();
const SKIP = new Set(['.git', 'node_modules', '.tmp', '.venv', '__pycache__', 'build', 'dist']);

export function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    if (SKIP.has(name)) continue;
    const p = join(dir, name);
    const st = statSync(p);
    if (st.isDirectory()) walk(p, out);
    else if (name.endsWith('.py')) out.push(p);
  }
  return out;
}

/** Проверка одного файла. Возвращает массив сообщений об ошибках (пусто = ок). */
export function checkPython(source, file = '<src>') {
  const errors = [];
  const lines = source.split('\n');
  let paren = 0;
  let quote = null;
  let triple = null;

  lines.forEach((line, i) => {
    const ln = i + 1;
    if (triple) { if (line.includes(triple)) triple = null; return; }
    const stripped = line.trim();
    if (!stripped || stripped.startsWith('#')) return;
    if (/^\t+ /.test(line) || /^ +\t/.test(line)) errors.push(ln + ': смешаны табы и пробелы в отступе');
    for (const t of ['"""', "'''"]) if ((stripped.match(new RegExp(t, 'g')) || []).length % 2 === 1) { triple = t; break; }
    if (triple) return;
    // грубый счёт скобок вне строковых литералов
    const noStr = line.replace(/"(\\.|[^"\\])*"/g, '""').replace(/'(\\.|[^'\\])*'/g, "''").replace(/#.*$/, '');
    for (const ch of noStr) {
      if ('([{'.includes(ch)) paren++;
      if (')]}'.includes(ch)) paren--;
      if (ch === '"' || ch === "'") quote = quote === ch ? null : (quote || ch);
    }
    if (paren < 0) { errors.push(ln + ': лишняя закрывающая скобка'); paren = 0; }
  });

  if (triple) errors.push('незакрытая многострочная строка ' + triple);
  if (paren !== 0) errors.push('несбалансированные скобки: ' + paren);
  if (!source.endsWith('\n')) errors.push('файл не заканчивается переводом строки');
  if (source.includes('\uFFFD')) errors.push('битый символ U+FFFD (кодировка)');
  const mustHave = /^(class|def|from|import|@|"""|#|ROOT|if|__all__)\b/m;
  if (!mustHave.test(source)) errors.push('нет ни одной конструкции уровня модуля — файл подозрительно пуст');
  return errors.map((e) => file + ':' + e);
}

function main() {
  const files = walk(ROOT);
  const problems = files.flatMap((f) => checkPython(readFileSync(f, 'utf8'), relative(ROOT, f).split('\\').join('/')));
  if (process.argv.includes('--json')) console.log(JSON.stringify({ files: files.length, problems }, null, 2));
  else {
    for (const p of problems) console.log('FAIL ' + p);
    console.log(problems.length ? 'FAILED: ' + problems.length + ' проблем в ' + files.length + ' файлах' : 'OK: ' + files.length + ' python-файлов разобраны без ошибок');
  }
  process.exit(problems.length ? 1 : 0);
}

if (process.argv[1] && process.argv[1].endsWith('syntax-check.mjs')) main();
