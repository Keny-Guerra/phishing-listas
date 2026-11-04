/**
 * binlista.js — listas compactas: huellas de 4 bytes (primeros 4 bytes de SHA-256 del host, big-endian)
 * ordenadas de menor a mayor y concatenadas. Búsqueda binaria; sin recorrer la lista.
 * Una colisión es posible pero rara (~N/2^32 por consulta); se mide en las pruebas.
 */
export async function huellaHost(host, subtle = globalThis.crypto.subtle) {
  const d = new Uint8Array(await subtle.digest("SHA-256", new TextEncoder().encode(host)));
  return ((d[0] << 24) | (d[1] << 16) | (d[2] << 8) | d[3]) >>> 0;
}
export function aUint32(bytes) {
  const n = bytes.byteLength >> 2, v = new DataView(bytes.buffer, bytes.byteOffset, n * 4), a = new Uint32Array(n);
  for (let i = 0; i < n; i++) a[i] = v.getUint32(i * 4, false);
  return a;
}
export function contiene(arr, x) {
  let lo = 0, hi = arr.length - 1;
  while (lo <= hi) { const m = (lo + hi) >> 1; const v = arr[m]; if (v === x) return true; if (v < x) lo = m + 1; else hi = m - 1; }
  return false;
}
export function aBase64(bytes) {
  let s = ""; for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(s);
}
export function deBase64(b64) { const s = atob(b64); const u = new Uint8Array(s.length); for (let i = 0; i < s.length; i++) u[i] = s.charCodeAt(i); return u; }
export async function sha256Hex(bytes, subtle = globalThis.crypto.subtle) {
  return [...new Uint8Array(await subtle.digest("SHA-256", bytes))].map((b) => b.toString(16).padStart(2, "0")).join("");
}
