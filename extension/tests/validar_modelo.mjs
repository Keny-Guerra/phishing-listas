// Validación del modelo EMPAQUETADO (ONNX + tokenizado JS) sobre train/val/test fijos de Fase A (v7).
// Uso: node tests/validar_modelo.mjs <carpeta con train_urls.csv val_urls.csv test_urls.csv>
import * as ort from "onnxruntime-node";
import fs from "node:fs";
import { tokenizar, normalizarUrl } from "../src/normalize.js";
const dir = process.argv[2];
const meta = JSON.parse(fs.readFileSync("models/vocab_meta.json", "utf8"));
const U = JSON.parse(fs.readFileSync("models/umbrales_sugeridos.json", "utf8"));
const sess = await ort.InferenceSession.create("models/cnn_phishing.onnx");
const leer = (f) => fs.readFileSync(`${dir}/${f}`, "utf8").trim().split("\n").slice(1).map((l) => { const i = l.indexOf(","); const j = l.indexOf(",", i + 1); return { url: l.slice(0, i), y: +l.slice(i + 1, j) }; });
async function puntuar(rows) {
  const out = new Float32Array(rows.length);
  for (let s = 0; s < rows.length; s += 500) {
    const ch = rows.slice(s, s + 500); const d = new Int32Array(ch.length * meta.maxlen);
    ch.forEach((r, k) => d.set(tokenizar(r.url, meta.vocab, meta.maxlen, meta.oov_idx, meta.normalizacion.modo), k * meta.maxlen));
    const o = await sess.run({ url_tokens: new ort.Tensor("int32", d, [ch.length, meta.maxlen]) });
    out.set(o[Object.keys(o)[0]].data, s);
  }
  return out;
}
const met = (rows, p, t) => { let tp = 0, fp = 0, fn = 0, tn = 0; rows.forEach((r, k) => { const q = p[k] >= t; if (r.y && q) tp++; else if (!r.y && q) fp++; else if (r.y) fn++; else tn++; }); return { n: rows.length, recall: +(tp / (tp + fn)).toFixed(4), fpr: +(fp / (fp + tn)).toFixed(4), precision: +(tp / (tp + fp)).toFixed(4) }; };
const host = (u) => normalizarUrl(u, meta.normalizacion.modo).split("/")[0];
const train = leer("train_urls.csv"), val = leer("val_urls.csv"), test = leer("test_urls.csv");
const pt = await puntuar(test);
const vistos = new Set(train.map((r) => host(r.url)));
const masc = (f) => test.map((r, k) => [r, pt[k]]).filter(([r]) => f(r));
const sub = (f) => { const a = masc(f); return { rows: a.map((x) => x[0]), p: Float32Array.from(a.map((x) => x[1])) }; };
const res = { tamanos: { entrenamiento: train.length, validacion: val.length, prueba: test.length }, umbrales: { advertencia: U.umbral_advertencia, bloqueo: U.umbral_bloqueo } };
for (const [nom, t] of [["0.5", 0.5], ["advertencia", U.umbral_advertencia], ["bloqueo", U.umbral_bloqueo]]) res[`prueba_en_${nom}`] = met(test, pt, t);
const vv = sub((r) => vistos.has(host(r.url))), nn = sub((r) => !vistos.has(host(r.url)));
res.hosts_vistos_en_entrenamiento = { ...met(vv.rows, vv.p, U.umbral_advertencia), pct_filas: +(vv.rows.length / test.length * 100).toFixed(1) };
res.hosts_nuevos = met(nn.rows, nn.p, U.umbral_advertencia);
console.log(JSON.stringify(res, null, 1));
