#!/usr/bin/env node
/**
 * native-drift-check.mjs — CI-проверка «нативные мосты не разошлись».
 *
 * Зачем: у нас две платформы с отдельными нативными слоями записи (Android Kotlin, iOS Swift).
 * Контракт между оболочкой и нативом описан в tests/native/contract.json и продублирован
 * в нативных проектах. Эта проверка ловит расхождение ДО сборки на телефоне.
 * Работает без Flutter/Gradle/Xcode — только node (есть на любой машине и в CI).
 */
import { readFileSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { normalizeReport, diff } from './jsondiff.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, '..', '..');

export function loadContract() {
  return JSON.parse(readFileSync(join(here, 'contract.json'), 'utf8'));
}

/** Возвращает список нарушений контракта (пустой массив = всё в порядке). */
export function checkSource(contract, source, platform) {
  const problems = [];
  const need = (s, why) => { if (!source.includes(s)) problems.push({ platform, missing: s, why }); };
  const forbid = (s, why) => { if (source.includes(s)) problems.push({ platform, forbidden: s, why }); };
  for (const sym of contract[platform].requiredSymbols) need(sym, 'обязательный символ моста записи');
  for (const perm of contract[platform].requiredPermissions || []) need(perm, 'обязательное разрешение платформы');
  // События в Flutter приходят только через EventChannel. Если на Android объявить событийный канал
  // как MethodChannel, Dart-подписка молча не сработает: приложение «работает», а текста нет.
  if (platform === 'android') need('EventChannel', 'событийный канал должен быть EventChannel, а не MethodChannel');
  for (const s of contract[platform].forbiddenSymbols || []) forbid(s, 'запрещено правилами платформы/проекта');
  return problems;
}

/** Читает файлы из манифеста платформы и проверяет их. */
export function checkPlatform(rootDir, contract, platform) {
  const files = contract[platform].files;
  const all = files.map((f) => {
    try { return readFileSync(join(rootDir, f), 'utf8'); } catch { return null; }
  });
  const problems = [];
  files.forEach((f, i) => {
    if (all[i] === null) problems.push({ platform, missingFile: f, why: 'файл нативного моста не найден' });
  });
  if (problems.length) return problems;
  return checkSource(contract, all.join('\n'), platform);
}

// Проверки, которые не про содержимое мостов, а про платформенные файлы рядом с ним:
// пропавшие правила бэкапа или разрешения ломают политику данных молча, без единой ошибки сборки.
function checkPlatformFiles(root, contract, platform) {
  const problems = [];
  const spec = contract[platform];
  for (const rel of spec.requiredXmlFiles || []) {
    if (!existsSync(join(root, rel))) {
      problems.push({ platform, missingXmlFile: rel, why: 'файл политики платформы не найден' });
    }
  }
  const flags = spec.requiredPermissionFlags || [];
  if (flags.length) {
    const manifestPath = (spec.files || []).find((f) => f.endsWith('AndroidManifest.xml'));
    if (manifestPath && existsSync(join(root, manifestPath))) {
      const manifest = readFileSync(join(root, manifestPath), 'utf8');
      for (const flag of flags) {
        if (!manifest.includes(flag)) {
          problems.push({ platform, missingManifestFlag: flag, why: 'в манифесте нет подключения политики платформы' });
        }
      }
    }
  }
  return problems;
}

function main() {
  const contract = loadContract();
  const out = [];
  const platforms = ['android', 'ios', ...(contract.mobile_ui ? ['mobile_ui'] : [])];
  for (const platform of platforms) {
    out.push(...checkPlatform(root, contract, platform));
    if (platform === 'android') out.push(...checkPlatformFiles(root, contract, platform));
  }
  const report = normalizeReport({ contractVersion: contract.version, problems: out });
  if (process.argv.includes('--json')) console.log(JSON.stringify(report, null, 2));
  else {
    console.log('# native drift check: contract v' + contract.version);
    if (!out.length) console.log('OK: нативные мосты соответствуют контракту');
    else for (const p of out) console.log('FAIL ' + JSON.stringify(p));
  }
  process.exit(out.length ? 1 : 0);
}

if (process.argv[1] && process.argv[1].endsWith('native-drift-check.mjs')) main();
