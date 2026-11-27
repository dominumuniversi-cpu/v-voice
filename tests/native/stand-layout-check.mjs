#!/usr/bin/env node
/**
 * Гайд: ловушки стенда /voice/ не теряются.
 *
 * Зачем: на эти три шишки ушёл час. Запись в документе сама себя не проверяет — через полгода
 * кто-то (или я) повторит и пустой токен, и слэш в proxy_pass, и незнание про префикс.
 * Здесь проверяется то, что можно проверить кодом, остальное — что оно записано.
 */
import fs from 'node:fs';

const problems = [];
const page = fs.readFileSync('services/api/web/index.html', 'utf8');
const main = fs.readFileSync('services/api/main.py', 'utf8');
const doc = fs.readFileSync('docs/ARCHITECTURE/STAND.md', 'utf8');

// 1. Сервер обязан понимать префикс /voice: иначе за nginx он отвечает 404 при здоровом коде.
if (!main.includes('_strip_prefix')) {
  problems.push('main.py не снимает префикс /voice — за nginx API будет отвечать 404');
}

// 2. Страница должна уметь показать, что подключено: без этого человек не знает, где настройки.
if (!page.includes('/api/v1/health') || !page.includes('Подключённые модели')) {
  problems.push('веб-экран не показывает подключённые модели');
}

// 3. Ловушки должны быть записаны: пустой токен, слэш в proxy_pass, порядок reload.
const traps = [
  ['пустой токен', /VV_DEVICE_TOKENS/],
  ['слэш в proxy_pass', /proxy_pass.*8080\//],
  ['reload nginx', /nginx -s reload/],
];
for (const [name, re] of traps) {
  if (!re.test(doc)) problems.push('в STAND.md не записана ловушка: ' + name);
}

// 4. Маршрут nginx не должен иметь слэша на конце у proxy_pass — это и был 404.
const routePath = 'E:/DockerData/nginx/stands/voice.conf';
if (fs.existsSync(routePath)) {
  const route = fs.readFileSync(routePath, 'utf8');
  const pass = /proxy_pass\s+http:\/\/voice-app:8080([^;]*);/.exec(route);
  if (pass && pass[1].trim() === '/') {
    problems.push('в voice.conf proxy_pass со слэшем на конце — страница отдаст 404');
  }
}

if (problems.length) {
  console.error('❌ стенд /voice/ расходится с тем, что уже проходили:');
  for (const p of problems) console.error('  ' + p);
  process.exit(1);
}
console.log('OK: стенд /voice/ помнит свои три ловушки');
