/**
 * actualizador.js — actualización silenciosa y verificada de listas y modelo.
 *
 * Flujo: candado -> manifest.json (ETag) -> descarga a memoria -> verifica tamaño y SHA-256 ->
 * prueba del modelo -> guarda TODO en una sola escritura (activación atómica) conservando la
 * versión anterior para poder volver. Cualquier fallo deja la versión vigente intacta.
 * No contiene lógica descargada: solo datos (listas y pesos del mismo modelo), según la política
 * de código alojado de forma remota de Chrome Web Store.
 */
import { K, MINUTOS_CANDADO, HORAS_ENTRE_COMPROBACIONES, MAX_BYTES_LISTA, MAX_BYTES_MODELO, NOMBRES_LISTAS } from "./config.js";
import { sha256Hex, aBase64 } from "./binlista.js";

const HEX64 = /^[0-9a-f]{64}$/;
const ARCHIVO_SEGURO = /^[A-Za-z0-9._-]+$/;
const leer = async (s, k, def = null) => (await s.get(k))[k] ?? def;

function descriptorValido(d, max, min = 1) {
  return d && typeof d.version === "string" && HEX64.test(d.sha256 ?? "") && ARCHIVO_SEGURO.test(d.archivo ?? "") &&
    !String(d.archivo).includes("..") && Number.isInteger(d.bytes) && d.bytes >= min && d.bytes <= max;
}

export function manifiestoValido(m) {
  if (!m || m.schema !== 1 || !m.listas) return false;
  if (!NOMBRES_LISTAS.every((n) => descriptorValido(m.listas[n], MAX_BYTES_LISTA, 0))) return false;
  if (m.modelo) {
    const u = m.modelo;
    if (!descriptorValido(u, MAX_BYTES_MODELO) || !(u.umbral_advertencia >= 0 && u.umbral_advertencia < u.umbral_bloqueo && u.umbral_bloqueo <= 1)) return false;
  }
  return true;
}

export const debeComprobar = (ahora, ultima, horas = HORAS_ENTRE_COMPROBACIONES) =>
  !ultima || (ahora - new Date(ultima)) / 3_600_000 >= horas;

export function estadoProteccion(ahora, ultima, instalacion, horas = 48) {
  const ref = ultima ?? instalacion;
  return ref && (ahora - new Date(ref)) / 3_600_000 <= horas ? "al_dia" : "sin_actualizar";
}

async function descargar(fetchFn, url, desc, subtle) {
  const r = await fetchFn(url, { cache: "no-store" });
  if (!r.ok) throw new Error(`descarga ${desc.archivo}: HTTP ${r.status}`);
  const b = new Uint8Array(await r.arrayBuffer());
  if (b.length !== desc.bytes) throw new Error(`tamaño distinto en ${desc.archivo}`);
  if ((await sha256Hex(b, subtle)) !== desc.sha256) throw new Error(`huella SHA-256 distinta en ${desc.archivo}`);
  return b;
}

/** @returns {Promise<{estado:string, cambios?:string[], error?:string}>} nunca lanza: la actualización no debe molestar. */
export async function actualizar({ storage, fetchFn = fetch, base, ahora = new Date(), subtle = globalThis.crypto?.subtle, validarModelo, shaIncluido = null }) {
  const candado = await leer(storage, K.candado);
  if (candado && (ahora - new Date(candado)) / 60_000 < MINUTOS_CANDADO) return { estado: "ocupado" };
  await storage.set({ [K.candado]: ahora.toISOString() });
  try {
    const etag = await leer(storage, K.etag);
    const r = await fetchFn(`${base}manifest.json`, { cache: "no-store", headers: etag ? { "If-None-Match": etag } : {} });
    if (r.status === 304) { await storage.set({ [K.ultima]: ahora.toISOString() }); return { estado: "sin_cambios" }; }
    if (!r.ok) throw new Error(`manifiesto: HTTP ${r.status}`);
    const m = await r.json();
    if (!manifiestoValido(m)) throw new Error("manifiesto inválido");

    const vigentes = await leer(storage, K.listas, {});
    const modeloVigente = await leer(storage, K.modelo);
    const nuevas = { ...vigentes }; const cambios = [];
    for (const n of NOMBRES_LISTAS) {
      const d = m.listas[n];
      if (vigentes[n]?.sha256 === d.sha256) continue;
      const b = await descargar(fetchFn, `${base}${d.archivo}`, d, subtle);
      nuevas[n] = { version: d.version, sha256: d.sha256, b64: aBase64(b) };
      cambios.push(n);
    }
    const escritura = {};
    // Si el modelo publicado es el mismo que ya viene en la extensión, no se vuelve a descargar.
    if (m.modelo && (modeloVigente?.sha256 ?? shaIncluido) !== m.modelo.sha256) {
      const b = await descargar(fetchFn, `${base}${m.modelo.archivo}`, m.modelo, subtle);
      if (validarModelo) await validarModelo(b); // si no carga o no responde, se descarta
      escritura[K.modeloB64] = aBase64(b);
      escritura[K.modelo] = { version: m.modelo.version, sha256: m.modelo.sha256, umbral_advertencia: m.modelo.umbral_advertencia, umbral_bloqueo: m.modelo.umbral_bloqueo, fecha: ahora.toISOString() };
      cambios.push("modelo");
    }
    if (cambios.length) {
      escritura[K.versionAnterior] = { listas: vigentes, modelo: modeloVigente, modeloB64: await leer(storage, K.modeloB64) };
      escritura[K.listas] = nuevas;
    }
    escritura[K.etag] = r.headers?.get?.("ETag") ?? null;
    escritura[K.ultima] = ahora.toISOString();
    await storage.set(escritura); // una sola escritura = activación atómica
    return { estado: cambios.length ? "actualizado" : "sin_cambios", cambios };
  } catch (e) {
    return { estado: "error", error: String(e.message ?? e) }; // se conserva la versión vigente
  } finally {
    await storage.set({ [K.candado]: null });
  }
}

/** Vuelve a la versión anterior (reversión del publicador o prueba fallida). */
export async function volverAnterior(storage) {
  const prev = await leer(storage, K.versionAnterior);
  if (!prev) return false;
  const e = { [K.listas]: prev.listas ?? {}, [K.versionAnterior]: null, [K.etag]: null };
  if (prev.modelo) { e[K.modelo] = prev.modelo; e[K.modeloB64] = prev.modeloB64; }
  await storage.set(e);
  return true;
}
