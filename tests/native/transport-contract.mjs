import fs from 'node:fs';
import path from 'node:path';

// Контракт HttpTransport общий для приложения и тестов. Когда он меняется, отставшая реализация
// ловится только на flutter analyze — через три шага сборки. Здесь — за секунду.
const root = process.cwd();
const dirs = ['apps/mobile/lib', 'apps/mobile/test'];
const bad = [];

function walk(dir) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(full);
    else if (entry.name.endsWith('.dart')) check(full);
  }
}

function check(file) {
  const text = fs.readFileSync(file, 'utf8');
  if (!text.includes('implements HttpTransport')) return;
  const posts = text.match(/Future<\(int, String\)> post\(String path[^)]*\)/g) || [];
  const gets = text.match(/Future<\(int, String\)> get\(String path[^)]*\)/g) || [];
  for (const sig of [...posts, ...gets]) {
    if (!sig.includes('headers')) bad.push(path.relative(root, file) + ' :: ' + sig);
  }
}

for (const dir of dirs) {
  const full = path.join(root, dir);
  if (fs.existsSync(full)) walk(full);
}

if (bad.length) {
  console.error('Реализации HttpTransport отстали от контракта (нужен {Map<String, String>? headers}):');
  for (const line of bad) console.error('  ' + line);
  process.exit(1);
}
console.log('OK: все реализации HttpTransport принимают заголовки');
