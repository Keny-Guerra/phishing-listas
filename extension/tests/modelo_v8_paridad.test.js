// Paridad del pipeline completo de la extensión con el modelo v8 entrenado en Colab:
// normalización + tokenización (JS) + ONNX Runtime (Node) = host y puntuación esperados (generados en Python).
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import * as ort from "onnxruntime-node";
import { normalizarHost, tokenizar } from "../src/normalize.js";

const rd = (p) => fs.readFileSync(new URL(p, import.meta.url), "utf8");
const meta = JSON.parse(rd("../models/vocab_meta.json"));
const vec = JSON.parse(rd("./fixtures/v8_paridad.json"));

test("modelo v8: metadatos coherentes", () => {
  assert.equal(meta.modelo.version, "v8");
  assert.equal(meta.normalizacion.modo, "host");
  assert.equal(meta.maxlen, 200);
  assert.equal(meta.oov_idx, 60);
  assert.equal(Object.keys(meta.vocab).length, 59);
});

test("normalizarHost coincide con host_norm de Python en todos los vectores", () => {
  for (const v of vec) assert.equal(normalizarHost(v.entrada), v.host, v.entrada);
});

test("las puntuaciones de la extensión coinciden con las de Python (|Δ| < 1e-4)", async () => {
  const sess = await ort.InferenceSession.create(new URL("../models/cnn_phishing.onnx", import.meta.url).pathname);
  const data = new Int32Array(vec.length * meta.maxlen);
  vec.forEach((v, k) => data.set(tokenizar(v.entrada, meta.vocab, meta.maxlen, meta.oov_idx, meta.normalizacion.modo), k * meta.maxlen));
  const out = await sess.run({ [sess.inputNames[0]]: new ort.Tensor("int32", data, [vec.length, meta.maxlen]) });
  const p = out[sess.outputNames[0]].data;
  let max = 0;
  vec.forEach((v, k) => { max = Math.max(max, Math.abs(p[k] - v.score)); });
  assert.ok(max < 1e-4, `diferencia máxima ${max}`);
});

test("umbrales publicados son los del modelo v8", () => {
  const u = JSON.parse(rd("../models/umbrales_sugeridos.json"));
  assert.equal(u.umbral_advertencia, 0.3864);
  assert.equal(u.umbral_bloqueo, 0.9549);
});
