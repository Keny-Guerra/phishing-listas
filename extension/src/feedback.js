/**
 * feedback.js — retroalimentación del usuario, en dos niveles.
 *
 * NIVEL A (siempre activo, 100 % local, cumple RNF3):
 *   "Esto es un falso positivo / falso negativo" actualiza al instante las
 *   listas personales del usuario en chrome.storage.local. Nada sale del
 *   dispositivo.
 *
 * NIVEL B (OPT-IN, desactivado por defecto):
 *   Con consentimiento explícito, se encola un reporte mínimo
 *   {dominio, tipo, reportero, fecha}. Nunca se envía la URL completa, ruta,
 *   parámetros ni contenido de la página. El identificador de reportero es
 *   aleatorio y rota cada 30 días para limitar el seguimiento entre reportes.
 *   Esos reportes alimentan src/feedback_ingest.py (cuarentena + verificación).
 *   Nota de seguridad/privacidad: enviar requiere declarar el endpoint en
 *   host_permissions; por eso se distribuye como variante opt-in y el
 *   manifest base (sin host_permissions) sigue sin permitir ninguna salida.
 *
 * `storage` es cualquier objeto con get(keys) y set(obj) asíncronos
 * (chrome.storage.local en producción; un objeto en memoria en las pruebas).
 */

import { hostDe } from "./decision.js";

const K_ALLOW = "usuario_allow";
const K_BLOCK = "usuario_block";
const K_OPTIN = "feedback_optin";
const K_ID = "reportero_id";
const K_ID_FECHA = "reportero_id_fecha";
const K_COLA = "reportes_pendientes";
const DIAS_ROTACION_ID = 30;
const MAX_COLA = 200;

const leer = async (storage, clave, def) => (await storage.get(clave))[clave] ?? def;
const sinWww = (h) => h.replace(/^www\./, "");

/** Solo el host, en minúsculas: sin esquema, usuario, puerto, ruta ni query. */
export function normalizarParaReporte(url) {
  const h = hostDe(url);
  return h ? sinWww(h) : "";
}

// ---------- NIVEL A: listas locales ----------
export async function marcarFalsoPositivo(storage, url) {
  const h = normalizarParaReporte(url);
  if (!h) return false;
  const allow = new Set(await leer(storage, K_ALLOW, []));
  const block = new Set(await leer(storage, K_BLOCK, []));
  allow.add(h); block.delete(h);
  await storage.set({ [K_ALLOW]: [...allow], [K_BLOCK]: [...block] });
  await encolarSiOptIn(storage, h, "falso_positivo");
  return true;
}

export async function marcarFalsoNegativo(storage, url) {
  const h = normalizarParaReporte(url);
  if (!h) return false;
  const allow = new Set(await leer(storage, K_ALLOW, []));
  const block = new Set(await leer(storage, K_BLOCK, []));
  block.add(h); allow.delete(h);
  await storage.set({ [K_ALLOW]: [...allow], [K_BLOCK]: [...block] });
  await encolarSiOptIn(storage, h, "falso_negativo");
  return true;
}

export async function listasUsuario(storage) {
  return { allow: await leer(storage, K_ALLOW, []), block: await leer(storage, K_BLOCK, []) };
}

// ---------- NIVEL B: reporte opt-in ----------
export async function activarOptIn(storage, activo) {
  await storage.set({ [K_OPTIN]: !!activo });
  if (!activo) await storage.set({ [K_COLA]: [] }); // al retirar el consentimiento se borra la cola
}

export async function idReportero(storage, ahora = new Date(), uuid = () => crypto.randomUUID()) {
  let id = await leer(storage, K_ID, null);
  const desde = await leer(storage, K_ID_FECHA, null);
  const vencido = !desde || (ahora - new Date(desde)) / 86_400_000 >= DIAS_ROTACION_ID;
  if (!id || vencido) {
    id = uuid();
    await storage.set({ [K_ID]: id, [K_ID_FECHA]: ahora.toISOString() });
  }
  return id;
}

export async function encolarReporte(storage, dominio, tipo, ahora = new Date()) { return encolarSiOptIn(storage, dominio, tipo, ahora); }

async function encolarSiOptIn(storage, dominio, tipo, ahora = new Date()) {
  if (!(await leer(storage, K_OPTIN, false))) return false;
  const cola = await leer(storage, K_COLA, []);
  if (cola.some((r) => r.dominio === dominio && r.tipo === tipo)) return false;
  cola.push({ dominio, tipo, reportero: await idReportero(storage, ahora), fecha: ahora.toISOString().slice(0, 10) });
  await storage.set({ [K_COLA]: cola.slice(-MAX_COLA) });
  return true;
}

/** Envía la cola al endpoint configurado (solo si hay opt-in). `fetchFn` inyectable. */
export async function enviarPendientes(storage, endpoint, fetchFn = fetch) {
  if (!(await leer(storage, K_OPTIN, false)) || !endpoint) return { enviados: 0 };
  const cola = await leer(storage, K_COLA, []);
  if (!cola.length) return { enviados: 0 };
  const resp = await fetchFn(endpoint, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ reportes: cola }),
  });
  if (!resp.ok) return { enviados: 0, error: resp.status };
  await storage.set({ [K_COLA]: [] });
  return { enviados: cola.length };
}

// ---------- Interfaces P04 (reportar) y P05 (opciones) ----------
export const MAX_REPORTES = MAX_COLA;
export const DOMINIO_VALIDO = /^(?=.{1,253}$)([a-z0-9-]{1,63}\.)+[a-z0-9-]{2,63}$/;
export const esDominioValido = (d) => DOMINIO_VALIDO.test(String(d));
const LISTA = { allow: K_ALLOW, block: K_BLOCK };
const CONTRARIA = { allow: "block", block: "allow" };

/** Agrega un dominio a una lista propia. Acepta un dominio o una URL (se normaliza al dominio). */
export async function agregarDominio(storage, lista, entrada) {
  const dominio = normalizarParaReporte(String(entrada ?? "").trim().toLowerCase());
  if (!esDominioValido(dominio)) return { ok: false, error: "invalido" };
  const mia = await leer(storage, LISTA[lista], []);
  const otra = await leer(storage, LISTA[CONTRARIA[lista]], []);
  if (otra.includes(dominio)) return { ok: false, error: "en_lista_contraria", dominio };
  if (mia.includes(dominio)) return { ok: false, error: "duplicado", dominio };
  await storage.set({ [LISTA[lista]]: [...mia, dominio] });
  return { ok: true, dominio, normalizado: dominio !== String(entrada).trim().toLowerCase() };
}

export async function quitarDominio(storage, lista, dominio) {
  const mia = await leer(storage, LISTA[lista], []);
  await storage.set({ [LISTA[lista]]: mia.filter((d) => d !== dominio) });
}

/**
 * Corrección del usuario desde P04. `recordar` actualiza solo sus listas (siempre local);
 * `compartir` agrega un reporte mínimo a la cola y exige consentimiento y cupo.
 */
export async function registrarCorreccion(storage, { dominio, tipo, recordar = true, compartir = false, ahora = new Date() }) {
  if (!esDominioValido(dominio) || !["falso_positivo", "falso_negativo"].includes(tipo)) return { ok: false, error: "invalido" };
  const res = { ok: true, recordado: false, movido: false, compartido: false };
  if (recordar) {
    const destino = tipo === "falso_positivo" ? "allow" : "block";
    const mia = await leer(storage, LISTA[destino], []);
    const otra = await leer(storage, LISTA[CONTRARIA[destino]], []);
    res.movido = otra.includes(dominio);
    await storage.set({
      [LISTA[destino]]: mia.includes(dominio) ? mia : [...mia, dominio],
      [LISTA[CONTRARIA[destino]]]: otra.filter((d) => d !== dominio),
    });
    res.recordado = true;
  }
  if (compartir) {
    const cola = await leer(storage, K_COLA, []);
    if (!(await leer(storage, K_OPTIN, false))) res.motivoNoCompartido = "sin_consentimiento";
    else if (cola.length >= MAX_COLA) res.motivoNoCompartido = "cola_llena";
    else res.compartido = await encolarSiOptIn(storage, dominio, tipo, ahora);
  }
  return res;
}

export function diasRestantesId(fechaIso, ahora = new Date()) {
  if (!fechaIso) return DIAS_ROTACION_ID;
  return Math.max(0, DIAS_ROTACION_ID - Math.floor((ahora - new Date(fechaIso)) / 86_400_000));
}

export async function estadoReportes(storage, ahora = new Date()) {
  const [optin, cola, fecha] = [await leer(storage, K_OPTIN, false), await leer(storage, K_COLA, []), await leer(storage, K_ID_FECHA, null)];
  return { optin, pendientes: cola, cantidad: cola.length, diasParaRotar: diasRestantesId(fecha, ahora), tieneId: !!(await leer(storage, K_ID, null)) };
}

/** Lo que se guardaría exactamente (nada más: sin ruta, sin parámetros, sin datos personales). */
export function vistaPreviaReporte({ dominio, tipo, reportero = "(se genera al guardar)", ahora = new Date() }) {
  return { dominio, tipo, fecha: ahora.toISOString().slice(0, 10), reportero_id: reportero };
}

export async function exportarReportes(storage) {
  return JSON.stringify({ reportes: await leer(storage, K_COLA, []) }, null, 2);
}

export async function borrarPendientes(storage) { await storage.set({ [K_COLA]: [] }); }

export async function renovarId(storage, ahora = new Date(), uuid = () => crypto.randomUUID()) {
  await storage.set({ [K_ID]: uuid(), [K_ID_FECHA]: ahora.toISOString() });
}

/** Restablece lo del usuario: listas propias, reportes, identificador y consentimiento. El modelo y las listas del día se conservan. */
export async function restablecer(storage) {
  await storage.set({ [K_ALLOW]: [], [K_BLOCK]: [], [K_COLA]: [], [K_OPTIN]: false, [K_ID]: null, [K_ID_FECHA]: null });
}
