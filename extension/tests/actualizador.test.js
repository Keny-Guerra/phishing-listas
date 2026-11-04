import test from "node:test";
import assert from "node:assert/strict";
import crypto from "node:crypto";
import { actualizar, volverAnterior, manifiestoValido, debeComprobar, estadoProteccion } from "../src/actualizador.js";
import { K } from "../src/config.js";

const sha = (b) => crypto.createHash("sha256").update(b).digest("hex");
const memoria = () => { const d = {}; return { d, async get(k) { return typeof k === "string" ? { [k]: d[k] } : Object.fromEntries(k.map((x) => [x, d[x]])); }, async set(o) { Object.assign(d, o); } }; };

function servidor({ bloq = new Uint8Array([0, 0, 0, 1]), urls = new Uint8Array([0, 0, 0, 2]), perm = new Uint8Array([0, 0, 0, 3]), modelo = new Uint8Array(40).fill(7), etag = '"a"', corromper = null } = {}) {
  const arch = { "bloqueo.bin": bloq, "bloqueo_urls.bin": urls, "permitidos.bin": perm, "modelo.onnx": modelo };
  const desc = (n, b, v = "2026-10-23") => ({ version: v, archivo: n, bytes: b.length, sha256: sha(b) });
  const manifest = { schema: 1, listas: { bloqueo: desc("bloqueo.bin", bloq), bloqueo_urls: desc("bloqueo_urls.bin", urls), permitidos: desc("permitidos.bin", perm) },
    modelo: { ...desc("modelo.onnx", modelo, "v7"), umbral_advertencia: 0.23, umbral_bloqueo: 0.94 } };
  const llamadas = [];
  const fetchFn = async (url, opts = {}) => {
    llamadas.push(url);
    const nombre = url.split("/").pop();
    if (nombre === "manifest.json") {
      if (opts.headers?.["If-None-Match"] === etag) return { ok: false, status: 304, headers: new Map() };
      return { ok: true, status: 200, headers: new Map([["ETag", etag]]), json: async () => manifest };
    }
    let b = arch[nombre]; if (corromper === nombre) b = new Uint8Array(b.length).fill(1);
    return b ? { ok: true, status: 200, arrayBuffer: async () => b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength) } : { ok: false, status: 404 };
  };
  return { fetchFn, manifest, llamadas };
}

test("primera actualización: descarga, verifica y activa listas y modelo", async () => {
  const s = memoria(); const srv = servidor();
  const r = await actualizar({ storage: s, fetchFn: srv.fetchFn, base: "https://x/", validarModelo: async () => {} });
  assert.equal(r.estado, "actualizado"); assert.deepEqual(r.cambios.sort(), ["bloqueo", "bloqueo_urls", "modelo", "permitidos"]);
  assert.equal(s.d[K.modelo].version, "v7"); assert.ok(s.d[K.listas].bloqueo.b64); assert.equal(s.d[K.candado], null);
});

test("sin cambios: el servidor responde 304 y no se descarga nada más", async () => {
  const s = memoria(); const srv = servidor();
  await actualizar({ storage: s, fetchFn: srv.fetchFn, base: "https://x/" });
  const n = srv.llamadas.length;
  const r = await actualizar({ storage: s, fetchFn: srv.fetchFn, base: "https://x/" });
  assert.equal(r.estado, "sin_cambios"); assert.equal(srv.llamadas.length, n + 1); // solo el manifiesto
});

test("huella distinta: se descarta y se conserva la versión vigente", async () => {
  const s = memoria();
  await actualizar({ storage: s, fetchFn: servidor().fetchFn, base: "https://x/" });
  const antes = JSON.stringify(s.d[K.listas]);
  const mala = servidor({ bloq: new Uint8Array([9, 9, 9, 9]), etag: '"b"', corromper: "bloqueo.bin" });
  const r = await actualizar({ storage: s, fetchFn: mala.fetchFn, base: "https://x/" });
  assert.equal(r.estado, "error"); assert.match(r.error, /huella/); assert.equal(JSON.stringify(s.d[K.listas]), antes);
});

test("prueba del modelo falla: no se activa nada (ni listas)", async () => {
  const s = memoria();
  const r = await actualizar({ storage: s, fetchFn: servidor().fetchFn, base: "https://x/", validarModelo: async () => { throw new Error("no carga"); } });
  assert.equal(r.estado, "error"); assert.equal(s.d[K.listas], undefined); assert.equal(s.d[K.modelo], undefined);
});

test("reversión: vuelve a la versión anterior de listas y modelo", async () => {
  const s = memoria();
  await actualizar({ storage: s, fetchFn: servidor().fetchFn, base: "https://x/" });
  const v1 = s.d[K.listas].bloqueo.sha256;
  await actualizar({ storage: s, fetchFn: servidor({ bloq: new Uint8Array([0, 0, 0, 5]), modelo: new Uint8Array(40).fill(8), etag: '"c"' }).fetchFn, base: "https://x/" });
  assert.notEqual(s.d[K.listas].bloqueo.sha256, v1);
  assert.equal(await volverAnterior(s), true); assert.equal(s.d[K.listas].bloqueo.sha256, v1);
});

test("candado: una segunda actualización simultánea no corre", async () => {
  const s = memoria(); s.d[K.candado] = new Date().toISOString();
  assert.equal((await actualizar({ storage: s, fetchFn: servidor().fetchFn, base: "https://x/" })).estado, "ocupado");
});

test("manifiesto inválido y nombres de archivo peligrosos se rechazan", () => {
  const { manifest } = servidor();
  assert.equal(manifiestoValido(manifest), true);
  const m2 = structuredClone(manifest); m2.listas.bloqueo.archivo = "../x.bin";
  assert.equal(manifiestoValido(m2), false);
  const m3 = structuredClone(manifest); m3.modelo.umbral_bloqueo = 0.1;
  assert.equal(manifiestoValido(m3), false);
  assert.equal(manifiestoValido({ schema: 2 }), false);
});

test("calendario: cuándo comprobar y el estado visible para el usuario", () => {
  const ahora = new Date("2026-10-23T12:00:00Z");
  assert.equal(debeComprobar(ahora, "2026-10-23T00:00:00Z"), false);
  assert.equal(debeComprobar(ahora, "2026-10-22T00:00:00Z"), true);
  assert.equal(estadoProteccion(ahora, "2026-10-22T12:00:00Z", null), "al_dia");
  assert.equal(estadoProteccion(ahora, "2026-10-20T12:00:00Z", null), "sin_actualizar");
});

test("una lista vacía es válida (p. ej., hoy no hay URLs de hosting compartido)", () => {
  const { manifest } = servidor({ urls: new Uint8Array(0) });
  assert.equal(manifiestoValido(manifest), true);
});

test("si el modelo publicado es el mismo que ya viene incluido, no se vuelve a descargar", async () => {
  const s = memoria(); const srv = servidor();
  const r = await actualizar({ storage: s, fetchFn: srv.fetchFn, base: "https://x/", shaIncluido: srv.manifest.modelo.sha256 });
  assert.equal(r.estado, "actualizado"); assert.deepEqual(r.cambios.sort(), ["bloqueo", "bloqueo_urls", "permitidos"]);
  assert.ok(!srv.llamadas.some((u) => u.endsWith("modelo.onnx")));
  assert.equal(s.d[K.modelo], undefined);
});
