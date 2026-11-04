// Paridad: pipeline JS (normalizar + tokenizar) + ONNX v7 reproduce las métricas del test de Python.
import * as ort from "onnxruntime-node";
import fs from "node:fs";
import { tokenizar } from "../src/normalize.js";
const meta = JSON.parse(fs.readFileSync("models/vocab_meta.json", "utf8"));
const sess = await ort.InferenceSession.create("models/cnn_phishing.onnx");
const lines = fs.readFileSync(process.argv[2], "utf8").trim().split("\n").slice(1);
const rows = lines.map(l => { const i = l.indexOf(","); const j = l.indexOf(",", i + 1); return { url: l.slice(0, i), y: +l.slice(i + 1, j) }; });
const B = 500; let tp = 0, fp = 0, fn = 0, tn = 0; const t0 = performance.now();
for (let s = 0; s < rows.length; s += B) {
  const ch = rows.slice(s, s + B);
  const data = new Int32Array(ch.length * meta.maxlen);
  ch.forEach((r, k) => data.set(tokenizar(r.url, meta.vocab, meta.maxlen, meta.oov_idx, meta.normalizacion.modo), k * meta.maxlen));
  const out = await sess.run({ url_tokens: new ort.Tensor("int32", data, [ch.length, meta.maxlen]) });
  const p = out[Object.keys(out)[0]].data;
  ch.forEach((r, k) => { const pred = p[k] >= 0.5 ? 1 : 0; if (r.y && pred) tp++; else if (!r.y && pred) fp++; else if (r.y) fn++; else tn++; });
}
console.log(JSON.stringify({ n: rows.length, tp, fp, fn, tn, recall: +(tp / (tp + fn)).toFixed(6), fpr: +(fp / (fp + tn)).toFixed(6), segundos: +((performance.now() - t0) / 1000).toFixed(1) }));
