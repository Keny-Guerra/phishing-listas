import test from "node:test";
import assert from "node:assert/strict";
import { decidir, hostDe } from "../src/decision.js";
import {
  normalizarParaReporte, marcarFalsoPositivo, marcarFalsoNegativo, listasUsuario,
  activarOptIn, enviarPendientes, idReportero,
} from "../src/feedback.js";

const memoria = () => { const d = {}; return {
  d, async get(k) { return typeof k === "string" ? { [k]: d[k] } : Object.fromEntries(k.map((x) => [x, d[x]])); },
  async set(o) { Object.assign(d, o); } }; };
const U = { advertencia: 0.40, bloqueo: 0.85 };

test("umbrales: permitir / advertir / bloquear", () => {
  assert.equal(decidir({ url: "http://x.com/a", score: 0.1, umbrales: U }).accion, "permitir");
  assert.equal(decidir({ url: "http://x.com/a", score: 0.6, umbrales: U }).accion, "advertir");
  assert.equal(decidir({ url: "http://x.com/a", score: 0.9, umbrales: U }).accion, "bloquear");
});

test("allowlist top permite, salvo score extremo", () => {
  const top = new Set(["bcp.com.pe"]);
  assert.equal(decidir({ url: "https://www.bcp.com.pe/", score: 0.9, umbrales: U, allowlistTop: top }).accion, "permitir");
  assert.equal(decidir({ url: "https://bcp.com.pe/", score: 0.995, umbrales: U, allowlistTop: top }).accion, "advertir");
});

test("allowlist top NO cubre subdominios (hosting de terceros)", () => {
  const top = new Set(["github.io"]);
  assert.equal(decidir({ url: "https://falso-bcp.github.io/", score: 0.9, umbrales: U, allowlistTop: top }).accion, "bloquear");
});

test("listas del usuario mandan sobre el modelo", () => {
  const l = { allow: ["miweb.pe"], block: ["estafa.xyz"] };
  assert.equal(decidir({ url: "http://miweb.pe/", score: 0.99, umbrales: U, listasUsuario: l }).accion, "permitir");
  assert.equal(decidir({ url: "http://estafa.xyz/", score: 0.01, umbrales: U, listasUsuario: l }).accion, "bloquear");
});

test("normalización: solo host, sin ruta/query/puerto/credenciales", () => {
  assert.equal(normalizarParaReporte("https://user:pw@WWW.Ejemplo.com:8080/ruta?token=abc#x"), "ejemplo.com");
  assert.equal(normalizarParaReporte("basura sin url ::"), "");
  assert.equal(hostDe("ejemplo.com/ruta"), "ejemplo.com");
});

test("nivel A: falso positivo / negativo actualizan listas y NO encolan sin opt-in", async () => {
  const s = memoria();
  await marcarFalsoPositivo(s, "https://www.legit.pe/login?x=1");
  await marcarFalsoNegativo(s, "http://estafa.xyz/pagar");
  const l = await listasUsuario(s);
  assert.deepEqual(l.allow, ["legit.pe"]); assert.deepEqual(l.block, ["estafa.xyz"]);
  assert.equal((await s.get("reportes_pendientes")).reportes_pendientes, undefined);
});

test("cambiar de opinión mueve el dominio entre listas", async () => {
  const s = memoria();
  await marcarFalsoPositivo(s, "http://a.com"); await marcarFalsoNegativo(s, "http://a.com");
  const l = await listasUsuario(s);
  assert.deepEqual(l.allow, []); assert.deepEqual(l.block, ["a.com"]);
});

test("nivel B: con opt-in encola reporte mínimo (sin URL completa) y envía", async () => {
  const s = memoria();
  await activarOptIn(s, true);
  await marcarFalsoNegativo(s, "http://estafa.xyz/ruta-secreta?token=123");
  const cola = (await s.get("reportes_pendientes")).reportes_pendientes;
  assert.equal(cola.length, 1);
  assert.deepEqual(Object.keys(cola[0]).sort(), ["dominio", "fecha", "reportero", "tipo"]);
  assert.equal(cola[0].dominio, "estafa.xyz");
  assert.ok(!JSON.stringify(cola).includes("ruta-secreta") && !JSON.stringify(cola).includes("token"));
  let cuerpo = null;
  const r = await enviarPendientes(s, "https://ejemplo.invalid/reportes", async (_u, o) => { cuerpo = o.body; return { ok: true }; });
  assert.equal(r.enviados, 1); assert.ok(cuerpo.includes("estafa.xyz"));
  assert.deepEqual((await s.get("reportes_pendientes")).reportes_pendientes, []);
});

test("sin opt-in nunca se envía nada; retirar consentimiento borra la cola", async () => {
  const s = memoria();
  let llamado = false;
  assert.equal((await enviarPendientes(s, "https://x.invalid", async () => { llamado = true; })).enviados, 0);
  assert.equal(llamado, false);
  await activarOptIn(s, true); await marcarFalsoPositivo(s, "http://a.com");
  await activarOptIn(s, false);
  assert.deepEqual((await s.get("reportes_pendientes")).reportes_pendientes, []);
});

test("el id de reportero rota a los 30 días", async () => {
  const s = memoria(); let n = 0; const gen = () => `id${++n}`;
  const t0 = new Date("2026-10-01");
  const a = await idReportero(s, t0, gen);
  assert.equal(await idReportero(s, new Date("2026-10-20"), gen), a);
  assert.notEqual(await idReportero(s, new Date("2026-11-05"), gen), a);
});
