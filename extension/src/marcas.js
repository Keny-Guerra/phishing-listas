/**
 * marcas.js — Capa 2: suplantación de marcas. Port 1:1 de src/capa2_marcas.py.
 * Función pura: evaluar(host, marcas) -> {marca, nombre, regla, severidad, segmento} | null
 * `marcas` es el arreglo "marcas" de data/marcas_peru.json (copia idéntica de config/marcas_peru.json).
 * La paridad con Python se verifica en tests/marcas.test.js con tests/fixtures/marcas_paridad.json.
 */

const PALABRAS_ENGANO = ["login", "log-in", "signin", "verific", "valida", "segur", "clave", "acceso", "cuenta", "banca",
  "soporte", "ayuda", "pago", "token", "bloque", "actualiz", "confirm", "clientes", "oficial",
  "app", "web", "online", "digital", "recompensa", "premio", "gratis", "beneficio", "cobro"];
const EXCEPCIONES = new Set(["ripple", "riley", "tapes", "plain", "plan", "plano", "claro", "apple"]);
const SUFIJOS_2 = new Set(["com", "org", "net", "gob", "edu", "gov", "co", "ac", "or", "ne", "go", "mil", "nom"]);
const HOMO = {
  "0": "o", "3": "e", "4": "a", "5": "s", "7": "t", "8": "b", "$": "s", "@": "a",
  "ı": "i", "ɩ": "i", "ο": "o", "ν": "v", "α": "a", "ε": "e", "ρ": "p", "τ": "t", "κ": "k",
  "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "х": "x", "у": "y", "і": "i", "ј": "j", "ѕ": "s", "һ": "h", "ԁ": "d",
};

// ---- Punycode (RFC 3492), solo decodificación
function punycodeDecode(input) {
  const base = 36, tMin = 1, tMax = 26, skew = 38, damp = 700;
  const out = [];
  let basic = input.lastIndexOf("-");
  if (basic < 0) basic = 0;
  for (let j = 0; j < basic; ++j) out.push(input.charCodeAt(j));
  const adapt = (delta, numPoints, first) => {
    let k = 0;
    delta = first ? Math.floor(delta / damp) : delta >> 1;
    delta += Math.floor(delta / numPoints);
    for (; delta > ((base - tMin) * tMax) >> 1; k += base) delta = Math.floor(delta / (base - tMin));
    return Math.floor(k + ((base - tMin + 1) * delta) / (delta + skew));
  };
  let n = 128, i = 0, bias = 72;
  for (let idx = basic > 0 ? basic + 1 : 0; idx < input.length;) {
    const oldi = i;
    for (let w = 1, k = base; ; k += base) {
      if (idx >= input.length) throw new Error("punycode");
      const c = input.charCodeAt(idx++);
      const digit = c - 48 < 10 ? c - 22 : c - 65 < 26 ? c - 65 : c - 97 < 26 ? c - 97 : base;
      if (digit >= base) throw new Error("punycode");
      i += digit * w;
      const t = k <= bias ? tMin : k >= bias + tMax ? tMax : k - bias;
      if (digit < t) break;
      w *= base - t;
    }
    const len = out.length + 1;
    bias = adapt(i - oldi, len, oldi === 0);
    n += Math.floor(i / len);
    i %= len;
    out.splice(i++, 0, n);
  }
  return String.fromCodePoint(...out);
}

function etiquetaAUnicode(e) {
  if (e.startsWith("xn--")) {
    try { return punycodeDecode(e.slice(4)); } catch { return e; }
  }
  return e;
}

export function normalizarHost(host) {
  let h = String(host).trim().toLowerCase().split("#")[0];
  h = h.replace(/^[a-z][a-z0-9+.-]*:\/\//, "");
  h = h.split(/[/?]/)[0].split("@").pop();
  h = h.replace(/:\d+$/, "").replace(/\.+$/, "");
  h = h.replace(/^www\d*\./, "");
  return h.split(".").map(etiquetaAUnicode).join(".");
}

function etiquetasSinSufijo(h) {
  const p = h.split(".");
  if (p.length >= 3 && SUFIJOS_2.has(p[p.length - 2]) && p[p.length - 1].length === 2) return p.slice(0, -2);
  return p.length >= 2 ? p.slice(0, -1) : p;
}

function formas(s) {
  s = s.normalize("NFKD").replace(/\p{M}/gu, "");
  s = Array.from(s).map((c) => HOMO[c] ?? c).join("").replaceAll("rn", "m").replaceAll("vv", "w");
  return new Set([s.replaceAll("1", "l"), s.replaceAll("1", "i")]);
}

const colapsa = (s) => s.replace(/(.)\1+/gu, "$1");

function dl1(a, b) {
  if (a === b || Math.abs(a.length - b.length) > 1) return false;
  if (a.length === b.length) {
    const d = [];
    for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) d.push(i);
    if (d.length === 1) return true;
    return d.length === 2 && d[1] === d[0] + 1 && a[d[0]] === b[d[1]] && a[d[1]] === b[d[0]];
  }
  const [c, l] = a.length < b.length ? [a, b] : [b, a];
  let i = 0;
  while (i < c.length && c[i] === l[i]) i++;
  return c.slice(i) === l.slice(i + 1);
}

const esOficial = (host, m) => m.dominios.some((d) => host === d || host.endsWith("." + d));
const base = (id) => id.split("_")[0];

export function evaluar(host, marcas) {
  const h = normalizarHost(host);
  if (!h || !h.includes(".")) return null;
  const etiquetas = etiquetasSinSufijo(h);
  const segs = [];
  for (const e of etiquetas) { segs.push(e); for (const x of e.split("-")) if (x) segs.push(x); }
  const engano = PALABRAS_ENGANO.some((w) => h.includes(w));
  let mejor = null;
  for (const m of marcas) {
    if (marcas.some((mm) => base(mm.id) === base(m.id) && esOficial(h, mm))) continue;
    for (const t of m.terminos) {
      let hit = null;
      for (const s of segs) {
        if (EXCEPCIONES.has(s)) continue;
        if (s === t) { hit = ["termino", s]; break; }
        if (t.length >= 6 && m.modo === "amplio" && s.includes(t)) { hit = ["termino", s]; break; }
        if (Array.from(s).length >= 3) {
          const ls = Array.from(s).length;
          for (const f of formas(s)) {
            const fc = colapsa(f), tc = colapsa(t);
            if (f === t && s !== t) hit = ["tipeo", s];
            else if (ls >= 4 && t.length <= 5 && fc === tc && f !== t) hit = ["tipeo", s];
            else if (ls >= 4 && t.length >= 6 && (dl1(f, t) || (fc === tc && f !== t))) hit = ["tipeo", s];
            if (hit) break;
          }
        }
        if (hit) break;
      }
      if (hit) {
        const [regla, seg] = hit;
        const entero = etiquetas.length === 1 && etiquetas[0] === seg;
        const sev = regla === "tipeo" || engano || entero ? "alta" : "media";
        const r = { marca: m.id, nombre: m.nombre, regla, severidad: sev, segmento: seg };
        if (mejor === null || (sev === "alta" && mejor.severidad !== "alta")) mejor = r;
      }
    }
  }
  return mejor;
}
