/**
 * background.js — service worker (MV3). Orquesta: decisión por listas -> modelo (si hace falta) -> acción.
 * Todo ocurre en el dispositivo. La navegación nunca espera a la red: solo se consultan datos ya guardados.
 */
import { K, URL_BASE, MINUTOS_ALARMA, HORAS_PROTECCION_AL_DIA, SCHEMA_VERSION, publicadorConfigurado, K_EXCEPCIONES, MINUTOS_EXCEPCION } from "./config.js";
import { actualizar, debeComprobar, estadoProteccion } from "./actualizador.js";
import { aUint32, contiene, huellaHost, deBase64, sha256Hex } from "./binlista.js";
import { decidir, hostDe } from "./decision.js";
import { listasUsuario } from "./feedback.js";
import { evaluar as evaluarMarca } from "./marcas.js";

const storage = chrome.storage.local;
const UMBRALES_INICIALES = { advertencia: 0.3864, bloqueo: 0.9549 }; // modelo v8 (models/umbrales_sugeridos.json)
let cacheListas = null; // { sha: {bloqueo,permitidos,bloqueo_urls} } en memoria del worker

async function cargarListas() {
  const v = (await storage.get(K.listas))[K.listas];
  if (!v) return null;
  const firma = Object.values(v).map((x) => x.sha256).join();
  if (cacheListas?.firma === firma) return cacheListas;
  cacheListas = { firma, ...Object.fromEntries(Object.entries(v).map(([n, d]) => [n, aUint32(deBase64(d.b64))])) };
  return cacheListas;
}

async function umbrales() {
  const m = (await storage.get(K.modelo))[K.modelo];
  return m ? { advertencia: m.umbral_advertencia, bloqueo: m.umbral_bloqueo } : UMBRALES_INICIALES;
}

let creando = null;
async function asegurarOffscreen() {
  const ya = await chrome.runtime.getContexts({ contextTypes: ["OFFSCREEN_DOCUMENT"] });
  if (ya.length) return;
  creando ??= chrome.offscreen.createDocument({ url: "ui/offscreen.html", reasons: ["WORKERS"], justification: "Ejecutar el modelo ONNX local (WebAssembly) que puntúa el dominio visitado." })
    .finally(() => { creando = null; });
  await creando;
}

/** Envía un mensaje al documento offscreen; reintenta mientras su script termina de cargar (solo tras crearlo). */
async function alOffscreen(msg) {
  await asegurarOffscreen();
  for (let i = 0; i < 40; i++) {
    const r = await chrome.runtime.sendMessage({ destino: "offscreen", ...msg }).catch(() => undefined);
    if (r !== undefined) return r;
    await new Promise((ok) => setTimeout(ok, 100));
  }
  throw new Error("el documento del modelo no respondió");
}

let shaEnviado = null;
async function sincronizarModelo() {
  const g = await storage.get([K.modelo, K.modeloB64]);
  const sha = g[K.modelo]?.sha256;
  if (sha && sha !== shaEnviado && g[K.modeloB64]) {
    const r = await alOffscreen({ tipo: "cargar", sha256: sha, b64: g[K.modeloB64] });
    if (!r.ok) throw new Error(r.error ?? "no se pudo cargar el modelo actualizado");
    shaEnviado = sha;
  }
}

async function puntuar(url) {
  await sincronizarModelo();
  const r = await alOffscreen({ tipo: "puntuar", url });
  if (typeof r.score !== "number") throw new Error(r.error ?? "sin puntaje");
  return r.score;
}

let cacheMarcas = null;
async function marcas() {
  cacheMarcas ??= (await (await fetch(chrome.runtime.getURL("data/marcas_peru.json"))).json()).marcas;
  return cacheMarcas;
}

/**
 * Decide para una URL. Devuelve {accion, motivo, score?, marca?}.
 * Orden: listas del usuario -> lista del día -> populares -> modelo -> (Capa 2 solo advierte).
 * `conPuntaje` pide además el puntaje del modelo aunque una lista ya haya decidido (lo usa el popup).
 */
export async function evaluar(url, { conPuntaje = false } = {}) {
  const host = hostDe(url);
  if (!host || !/^https?:/.test(url)) return { accion: "permitir", motivo: "no_web" };
  const l = await cargarListas();
  const h = await huellaHost(host.replace(/^www\./, ""));
  const hu = await huellaHost(url.replace(/^https?:\/\//, "").replace(/[#].*$/, "").replace(/\/$/, ""));
  const marca = evaluarMarca(host, await marcas());
  const base = {
    url, umbrales: await umbrales(), listasUsuario: await listasUsuario(storage), marca,
    enBloqueoDia: !!l && (contiene(l.bloqueo, h) || contiene(l.bloqueo_urls, hu)),
    enPermitidosDia: !!l && contiene(l.permitidos, h),
  };
  let d = decidir(base);
  let score;
  if (d.accion === "necesita_modelo") {
    try { score = await puntuar(url); d = decidir({ ...base, score }); } catch (e) {
      console.warn("modelo_no_disponible:", e.message);
      d = marca ? { accion: "advertir", motivo: `marca_${marca.regla}_${marca.marca}` } : { accion: "permitir", motivo: "modelo_no_disponible" };
    }
  } else if (conPuntaje) {
    try { score = await puntuar(url); } catch { /* el puntaje es solo informativo */ }
  }
  return { ...d, score, marca: marca ?? null };
}

async function hayExcepcion(host) {
  const e = (await chrome.storage.session.get(K_EXCEPCIONES))[K_EXCEPCIONES] ?? {};
  return !!e[host] && (Date.now() - e[host]) / 60_000 < MINUTOS_EXCEPCION;
}
async function crearExcepcion(host) {
  const e = (await chrome.storage.session.get(K_EXCEPCIONES))[K_EXCEPCIONES] ?? {};
  await chrome.storage.session.set({ [K_EXCEPCIONES]: { ...e, [host]: Date.now() } });
}

async function alNavegar({ tabId, url, frameId }) {
  if (frameId !== 0) return;
  if ((await storage.get(K.activa))[K.activa] === false) return;
  const host = hostDe(url);
  if (host && (await hayExcepcion(host))) { chrome.action.setBadgeText({ tabId, text: "" }); return; } // «Continuar de todos modos»
  const d = await evaluar(url);
  if (d.accion === "bloquear") {
    const q = new URLSearchParams({ destino: url, motivo: d.motivo });
    if (typeof d.score === "number") q.set("score", String(Math.round(d.score * 100)));
    if (d.marca) q.set("marca", d.marca.marca);
    chrome.tabs.update(tabId, { url: chrome.runtime.getURL(`ui/advertencia.html?${q}`) });
  } else if (d.accion === "advertir") {
    chrome.action.setBadgeText({ tabId, text: "!" });
    chrome.action.setBadgeBackgroundColor({ tabId, color: "#b45309" });
  } else chrome.action.setBadgeText({ tabId, text: "" });
}

/** Comprueba (y aplica) actualizaciones de listas y modelo. Devuelve el resultado para mostrarlo en Opciones. */
async function mantener(forzar = false) {
  if (!publicadorConfigurado()) return { estado: "sin_publicador" };
  const s = await storage.get([K.ultima]);
  if (!forzar && !debeComprobar(new Date(), s[K.ultima])) return { estado: "sin_cambios" };
  const inc = await infoModelo();
  return actualizar({ storage, base: URL_BASE, shaIncluido: inc.origen === "incluido" ? inc.sha256 : null, validarModelo: async (bytes) => {
    const r = await alOffscreen({ tipo: "validar", bytes: Array.from(bytes) });
    if (!r?.ok) throw new Error(r?.error ?? "el modelo no responde");
  } });
}

let infoIncluido = null;
/** Versión, huella y umbrales del modelo en uso. El modelo incluido se verifica contra models/huella.json. */
async function infoModelo() {
  const m = (await storage.get(K.modelo))[K.modelo];
  if (m) return { version: m.version, sha256: m.sha256, fecha: m.fecha, umbrales: { advertencia: m.umbral_advertencia, bloqueo: m.umbral_bloqueo }, origen: "actualizado", verificado: true };
  if (!infoIncluido) {
    const leer = async (p) => (await fetch(chrome.runtime.getURL(p))).json();
    const hu = await leer("models/huella.json");
    const verificado = await (async () => {
      try {
        const bytes = new Uint8Array(await (await fetch(chrome.runtime.getURL(`models/${hu.archivo}`))).arrayBuffer());
        return (await sha256Hex(bytes)) === hu.sha256;
      } catch { return false; }
    })();
    infoIncluido = { version: hu.version, sha256: hu.sha256, fecha: hu.fecha, umbrales: UMBRALES_INICIALES, origen: "incluido", verificado };
  }
  return infoIncluido;
}

async function infoListas() {
  const g = await storage.get([K.listas, K.ultima]);
  return { ultima: g[K.ultima] ?? null, listas: Object.fromEntries(Object.entries(g[K.listas] ?? {}).map(([n, d]) => [n, { version: d.version }])) };
}

chrome.runtime.onInstalled.addListener(async (info) => {
  if (info.reason === "install") chrome.tabs.create({ url: chrome.runtime.getURL("ui/bienvenida.html") });
  const s = await storage.get([K.esquema, K.instalacion]);
  await storage.set({ [K.esquema]: SCHEMA_VERSION, [K.instalacion]: s[K.instalacion] ?? new Date().toISOString() });
  chrome.alarms.create("mantenimiento", { periodInMinutes: MINUTOS_ALARMA });
  mantener(true);
});
chrome.runtime.onStartup.addListener(() => mantener());
chrome.alarms.onAlarm.addListener((a) => a.name === "mantenimiento" && mantener());
chrome.webNavigation.onBeforeNavigate.addListener(alNavegar);
chrome.webNavigation.onCommitted.addListener((d) => { if (d.frameId === 0) mantener(); }); // al abrir/usar pestañas, solo si pasó el plazo

chrome.runtime.onMessage.addListener((m, _s, responder) => {
  if (m?.destino !== "background") return;
  (async () => {
    if (m.tipo === "estado") {
      const s = await storage.get([K.ultima, K.instalacion, K.activa]);
      responder({ activa: s[K.activa] !== false, estado: estadoProteccion(new Date(), s[K.ultima], s[K.instalacion], HORAS_PROTECCION_AL_DIA) });
    } else if (m.tipo === "evaluar") responder(await evaluar(m.url));
    else if (m.tipo === "estado_sitio") {
      const s = await storage.get([K.ultima, K.instalacion, K.activa]);
      const activa = s[K.activa] !== false;
      const dominio = hostDe(m.url ?? "").replace(/^www\./, "");
      const analizable = !!dominio && /^https?:/.test(m.url ?? "");
      const r = { activa, analizable, dominio, umbrales: await umbrales(), modelo: await infoModelo(),
        proteccion: estadoProteccion(new Date(), s[K.ultima], s[K.instalacion], HORAS_PROTECCION_AL_DIA),
        publicador: publicadorConfigurado(), ultima: s[K.ultima] ?? null };
      responder(activa && analizable ? { ...r, ...(await evaluar(m.url, { conPuntaje: true })) } : r);
    } else if (m.tipo === "info_modelo") responder({ modelo: await infoModelo(), ...(await infoListas()), publicador: publicadorConfigurado() });
    else if (m.tipo === "buscar_actualizacion") responder(await mantener(true));
    else if (m.tipo === "excepcion_visita") { await crearExcepcion(hostDe(m.url ?? "")); responder({ ok: true }); }
  })().catch((e) => responder({ error: String(e.message ?? e) }));
  return true;
});
