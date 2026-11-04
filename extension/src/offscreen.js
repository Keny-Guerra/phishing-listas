/** offscreen.js — inferencia con ONNX Runtime Web (WASM). Ejecuta solo el modelo local; sin red. */
import { tokenizar } from "./normalize.js";

const ort = globalThis.ort;
ort.env.wasm.wasmPaths = chrome.runtime.getURL("vendor/");
ort.env.wasm.numThreads = 1;
let sesion = null, meta = null;

async function cargar() {
  if (!sesion) { // modelo incluido en el paquete (hasta recibir uno actualizado desde el service worker)
    sesion = await ort.InferenceSession.create(chrome.runtime.getURL("models/cnn_phishing.onnx"));
  }
  meta ??= await (await fetch(chrome.runtime.getURL("models/vocab_meta.json"))).json();
}

async function correr(ses, url) {
  const ids = tokenizar(url, meta.vocab, meta.maxlen, meta.oov_idx, meta.normalizacion.modo);
  const t = new ort.Tensor("int32", Int32Array.from(ids), [1, meta.maxlen]);
  const sal = await ses.run({ [ses.inputNames[0]]: t });
  return sal[ses.outputNames[0]].data[0];
}

chrome.runtime.onMessage.addListener((m, _s, responder) => {
  if (m?.destino !== "offscreen") return;
  (async () => {
    try {
      if (m.tipo === "cargar") {
        sesion = await ort.InferenceSession.create(Uint8Array.from(atob(m.b64), (c) => c.charCodeAt(0)));
        responder({ ok: true });
      } else if (m.tipo === "puntuar") { await cargar(); responder({ score: await correr(sesion, m.url) }); }
      else if (m.tipo === "validar") {
        meta ??= await (await fetch(chrome.runtime.getURL("models/vocab_meta.json"))).json();
        const s = await ort.InferenceSession.create(Uint8Array.from(m.bytes));
        const p = await correr(s, "ejemplo.com");
        responder({ ok: Number.isFinite(p) && p >= 0 && p <= 1 });
      }
    } catch (e) { responder({ ok: false, error: String(e.message ?? e) }); }
  })();
  return true;
});
