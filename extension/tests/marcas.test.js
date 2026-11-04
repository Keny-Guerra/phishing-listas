import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { evaluar } from "../src/marcas.js";

const rd = (p) => readFileSync(new URL(p, import.meta.url), "utf8");
const marcas = JSON.parse(rd("../data/marcas_peru.json")).marcas;

test("la copia de marcas de la extensión es idéntica a config/marcas_peru.json", () => {
  const raiz = JSON.parse(rd("../../config/marcas_peru.json"));
  assert.deepEqual(raiz.marcas, marcas);
});

test("paridad con Python (vectores generados por capa2_marcas.py)", () => {
  const vec = JSON.parse(rd("./fixtures/marcas_paridad.json"));
  for (const { host, esperado } of vec) assert.deepEqual(evaluar(host, marcas), esperado, host);
});

test("dominios oficiales y sus subdominios no se marcan", () => {
  for (const m of marcas) for (const d of m.dominios) {
    assert.equal(evaluar(d, marcas), null, d);
    assert.equal(evaluar(`www.${d}`, marcas), null, `www.${d}`);
    assert.equal(evaluar(`app.${d}`, marcas), null, `app.${d}`);
  }
});

test("casos de suplantación típicos", () => {
  assert.equal(evaluar("bcp-verificacion.xyz", marcas)?.marca, "bcp");
  assert.equal(evaluar("yappe.pe", marcas)?.regla, "tipeo");
  assert.equal(evaluar("rnibanco.com.pe", marcas)?.marca, "mibanco");
  assert.equal(evaluar("login.interbank.pages.dev", marcas)?.severidad, "alta");
  assert.equal(evaluar("xn--80ak6ak.com", marcas)?.marca, "yape"); // «уаре» en cirílico
  assert.equal(evaluar("example.org", marcas), null);
});
