/**
 * normalize.js — misma normalización que src/normalize.py (DEBE coincidir:
 * el modelo se entrenó con URLs normalizadas así).
 * modo "completa": minúsculas, sin #fragmento, sin esquema, sin "www." inicial, sin "/" final.
 * modo "solo_host": además descarta ruta y query.
 * modo "host" (modelo v8): réplica exacta de host_norm() del Colab fase_A_v8 —
 *   minúsculas; si no trae "://" se asume http://; se toma solo el dominio
 *   (sin usuario@, sin :puerto); se quita "www" + dígitos opcionales + ".".
 */
export function normalizarHost(url) {
  let u = String(url).trim().toLowerCase();
  if (!u.includes("://")) u = "http://" + u;
  const m = u.match(/^[^/?#:]*:\/\/([^/?#]*)/);
  let h = m ? m[1] : "";
  h = h.split("@").pop().replace(/:\d+$/, "");
  return h.replace(/^www\d*\./, "");
}

export function normalizarUrl(url, modo = "completa") {
  if (modo === "host") return normalizarHost(url);
  let u = String(url).trim().toLowerCase().split("#")[0];
  u = u.replace(/^[a-z][a-z0-9+.-]*:\/\//, "");
  u = u.replace(/^www\./, "");
  if (modo === "solo_host") u = u.split(/[/?]/)[0];
  return u.replace(/\/+$/, "");
}

/** Tokeniza igual que preprocess.py: índice de carácter (0=PAD, último=OOV), maxlen fijo. */
export function tokenizar(url, vocab, maxlen, oovIdx, modo = "completa") {
  const u = normalizarUrl(url, modo).slice(0, maxlen);
  const ids = Array.from(u, (c) => vocab[c] ?? oovIdx);
  while (ids.length < maxlen) ids.push(0);
  return ids;
}
