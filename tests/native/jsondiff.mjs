/**
 * jsondiff.mjs — крошечный JSON-дифф (только для проверок фоновых прогонов).
 * zero-dependency, ESM. Цель: не тянуть сторонние пакеты в CI-проверку.
 */
function typeOf(v) { return v === null ? 'null' : Array.isArray(v) ? 'array' : typeof v; }
function stable(v) {
  if (v === null || typeof v !== 'object') return v;
  if (Array.isArray(v)) return v.map(stable);
  const o = {};
  for (const k of Object.keys(v).sort()) o[k] = stable(v[k]);
  return o;
}
export function normalizeReport(r, opts = {}) {
  const drop = new Set(opts.drop || ['generatedAt', 'elapsedMs', 'peakRssMb', 'pid']);
  const walk = (v) => {
    if (Array.isArray(v)) return v.map(walk);
    if (v && typeof v === 'object') {
      const o = {};
      for (const k of Object.keys(v)) if (!drop.has(k)) o[k] = walk(v[k]);
      return o;
    }
    return v;
  };
  return stable(walk(r));
}
export function diff(a, b, path = '') {
  const ta = typeOf(a), tb = typeOf(b);
  if (ta !== tb) return [{ path: path || '$', a: ta, b: tb }];
  if (ta === 'array') {
    const out = [];
    if (a.length !== b.length) out.push({ path: path + '.length', a: a.length, b: b.length });
    for (let i = 0; i < Math.min(a.length, b.length); i++) out.push(...diff(a[i], b[i], path + '[' + i + ']'));
    return out;
  }
  if (ta === 'object') {
    const out = [];
    const keys = new Set([...Object.keys(a), ...Object.keys(b)]);
    for (const k of keys) {
      if (!(k in a)) out.push({ path: path + '.' + k, a: '<missing>', b: typeOf(b[k]) });
      else if (!(k in b)) out.push({ path: path + '.' + k, a: typeOf(a[k]), b: '<missing>' });
      else out.push(...diff(a[k], b[k], path + '.' + k));
    }
    return out;
  }
  return a === b ? [] : [{ path: path || '$', a, b }];
}
