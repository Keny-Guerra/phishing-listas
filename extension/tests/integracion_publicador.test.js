// Integración publicador (Python) -> actualizador (JS): genera archivos reales con listas_dia.py,
// los sirve por HTTP local y verifica que la extensión los descarga, valida y activa.
import test from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { actualizar } from "../src/actualizador.js";
import { aUint32, contiene, huellaHost, deBase64 } from "../src/binlista.js";
import { K } from "../src/config.js";

const raiz = path.resolve(import.meta.dirname, "../..");
const py = spawnSync("python3", ["--version"]);

test("publicador real -> servidor HTTP -> actualizador: listas y modelo quedan activos", { skip: py.status !== 0 }, async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "pub-"));
  const feed = Array.from({ length: 150 }, (_, i) => `http://fraude${i}-login.xyz/a`).join("\n");
  const tranco = Array.from({ length: 500 }, (_, i) => `${i + 1},sitio${i}.com`).join("\n");
  fs.writeFileSync(path.join(tmp, "f.txt"), feed);
  fs.writeFileSync(path.join(tmp, "t.csv"), tranco);
  const r = spawnSync("python3", [path.join(raiz, "src/listas_dia.py"), "--phishing-file", path.join(tmp, "f.txt"), "--tranco-file", path.join(tmp, "t.csv"),
    "--salida", path.join(tmp, "out"), "--version", "2026-10-23", "--min-feed", "100", "--min-permitidos", "1",
    "--modelo-onnx", path.join(raiz, "extension/models/cnn_phishing.onnx"), "--umbrales", path.join(raiz, "extension/models/umbrales_sugeridos.json")], { encoding: "utf8" });
  assert.equal(r.status, 0, r.stderr);

  const srv = http.createServer((q, s) => {
    const f = path.join(tmp, "out", path.basename(q.url));
    if (!fs.existsSync(f)) { s.statusCode = 404; return s.end(); }
    s.setHeader("ETag", '"x1"'); s.end(fs.readFileSync(f));
  });
  await new Promise((ok) => srv.listen(0, ok));
  try {
    const d = {}; const storage = { async get(k) { return { [k]: d[k] }; }, async set(o) { Object.assign(d, o); } };
    const base = `http://127.0.0.1:${srv.address().port}/`;
    const res = await actualizar({ storage, base, validarModelo: async () => {} });
    assert.equal(res.estado, "actualizado", res.error);
    const bloqueo = aUint32(deBase64(d[K.listas].bloqueo.b64));
    assert.equal(contiene(bloqueo, await huellaHost("fraude7-login.xyz")), true);
    assert.equal(contiene(bloqueo, await huellaHost("sitio3.com")), false);
    assert.equal(d[K.modelo].umbral_bloqueo, JSON.parse(fs.readFileSync(path.join(raiz, "extension/models/umbrales_sugeridos.json"), "utf8")).umbral_bloqueo);
  } finally { srv.close(); }
});
