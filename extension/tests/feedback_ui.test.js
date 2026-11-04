import { test } from "node:test";
import assert from "node:assert/strict";
import { agregarDominio, registrarCorreccion, estadoReportes, restablecer, activarOptIn, MAX_REPORTES, esDominioValido } from "../src/feedback.js";

const mem = () => { const d = {}; return { async get(k) { const o = {}; for (const x of [].concat(k)) if (x in d) o[x] = d[x]; return o; }, async set(o) { Object.assign(d, o); }, d }; };

test("agregar valida, normaliza, detecta conflicto y duplicado", async () => {
  const s = mem();
  assert.equal((await agregarDominio(s, "allow", "no es dominio")).error, "invalido");
  const r = await agregarDominio(s, "allow", "https://www.Ejemplo.com/ruta?x=1");
  assert.equal(r.ok, true);
  assert.equal((await agregarDominio(s, "allow", "ejemplo.com")).error, "duplicado");
  assert.equal((await agregarDominio(s, "block", "ejemplo.com")).error, "en_lista_contraria");
});
test("corrección: recordar mueve de lista; compartir exige opt-in", async () => {
  const s = mem();
  await agregarDominio(s, "block", "sitio.com");
  let r = await registrarCorreccion(s, { dominio: "sitio.com", tipo: "falso_positivo", compartir: true });
  assert.equal(r.movido, true); assert.equal(r.compartido, false); assert.equal(r.motivoNoCompartido, "sin_consentimiento");
  await activarOptIn(s, true);
  r = await registrarCorreccion(s, { dominio: "sitio.com", tipo: "falso_positivo", compartir: true });
  assert.equal(r.compartido, true);
  assert.equal((await estadoReportes(s)).cantidad, 1);
});
test("cola llena y restablecer", async () => {
  const s = mem(); await activarOptIn(s, true);
  await s.set({ reportes_pendientes: Array.from({ length: MAX_REPORTES }, (_, i) => ({ dominio: `d${i}.com` })) });
  assert.equal((await registrarCorreccion(s, { dominio: "a.com", tipo: "falso_negativo", compartir: true })).motivoNoCompartido, "cola_llena");
  await restablecer(s);
  const e = await estadoReportes(s); assert.equal(e.cantidad, 0); assert.equal(e.optin, false);
  assert.equal(esDominioValido("a.b"), false); assert.equal(esDominioValido("a.com"), true);
});
