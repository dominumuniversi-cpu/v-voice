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

// Ключи Info.plist — не украшение: без NSMicrophoneUsageDescription приложение падает при первом
// обращении к микрофону, без описания локальной сети iOS молча блокирует наш же сервер.
function checkPlistKeys(root, contract) {
  const problems = [];
  const keys = (contract.ios && contract.ios.requiredPlistKeys) || [];
  if (!keys.length) return problems;
  const plistPath = 'apps/mobile/ios/Runner/Info.plist';
  if (!existsSync(join(root, plistPath))) {
    problems.push({ platform: 'ios', missingFile: plistPath, why: 'не найден Info.plist' });
    return problems;
  }
  const plist = readFileSync(join(root, plistPath), 'utf8');
  for (const key of keys) {
    if (!plist.includes('<key>' + key + '</key>')) {
      problems.push({ platform: 'ios', missingPlistKey: key, why: 'в Info.plist нет обязательного ключа' });
    }
  }
  return problems;
}

/// Манифест обязан быть валидным XML: битый тег иначе всплывает только на сборке APK,
/// через несколько минут и с невнятным сообщением Gradle.
function checkManifestXml(root) {
  const problems = [];
  const file = 'apps/mobile/android/app/src/main/AndroidManifest.xml';
  const full = join(root, file);
  if (!existsSync(full)) return problems;
  const text = readFileSync(full, 'utf8');
  // Строковый сканер, а не регулярка: регулярка проглатывает соседний тег и «не замечает»
  // именно ту поломку, ради которой написана. Здесь каждый тег читается посимвольно.
  const stack = [];
  let i = 0;
  while (i < text.length) {
    const lt = text.indexOf('<', i);
    if (lt === -1) break;
    const gt = text.indexOf('>', lt);
    if (gt === -1) { problems.push({ file, problem: 'manifest_unclosed_tag', at: lt }); break; }
    // Пролог и комментарии — не теги: без этой строки валидатор ругается на исправный манифест.
    if (text.startsWith('<!--', lt)) {
      const close = text.indexOf('-->', lt);
      if (close === -1) { problems.push({ file, problem: 'manifest_comment_unclosed', at: lt }); break; }
      i = close + 3;
      continue;
    }
    if (text.startsWith('<?', lt)) { i = gt + 1; continue; }
    const inner = text.slice(lt + 1, gt);
    // Внутри тега не может быть ещё одного '<': это признак незакрытого предыдущего.
    if (inner.includes('<')) problems.push({ file, problem: 'manifest_nested', at: lt });
    if (inner.startsWith('/')) {
      const name = inner.slice(1).trim();
      const top = stack.pop();
      if (top !== name) problems.push({ file, problem: 'manifest_unbalanced', expected: top, found: name });
    } else if (!inner.trim().endsWith('/')) {
      const name = inner.split(/\s/)[0];
      if (name) stack.push(name);
    }
    i = gt + 1;
  }
  if (stack.length) problems.push({ file, problem: 'manifest_unclosed', open: stack });
  return problems;
}

function main() {
  const contract = loadContract();
  const out = [];
  const platforms = ['android', 'ios', ...(contract.mobile_ui ? ['mobile_ui'] : [])];
  for (const platform of platforms) {
    out.push(...checkPlatform(root, contract, platform));
    if (platform === 'android') out.push(...checkPlatformFiles(root, contract, platform));
    if (platform === 'ios') out.push(...checkPlistKeys(root, contract));
  }
  out.push(...checkManifestXml(root));

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
