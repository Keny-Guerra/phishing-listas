import test from "node:test";
import assert from "node:assert/strict";
import { decidir } from "../src/decision.js";

const umbrales = { advertencia: 0.3864, bloqueo: 0.9549 };
const base = { url: "https://ejemplo.pe/x", umbrales };

test("orden de prioridad: usuario bloqueo > usuario permitido > lista del día > top > modelo", () => {
  assert.equal(decidir({ ...base, score: 0, listasUsuario: { block: ["ejemplo.pe"], allow: ["ejemplo.pe"] } }).motivo, "lista_usuario_bloqueo");
  assert.equal(decidir({ ...base, score: 1, listasUsuario: { allow: ["ejemplo.pe"] }, enBloqueoDia: true }).motivo, "lista_usuario_permitido");
  assert.equal(decidir({ ...base, score: 0, enBloqueoDia: true, enPermitidosDia: true }).motivo, "lista_del_dia_bloqueo");
  assert.equal(decidir({ ...base, score: 0.5, enPermitidosDia: true }).motivo, "allowlist_top");
  assert.equal(decidir({ ...base, score: 0.995, enPermitidosDia: true }).accion, "advertir");
});

test("si ninguna lista decide y no hay puntaje, pide el modelo (el modelo solo corre cuando hace falta)", () => {
  assert.equal(decidir(base).accion, "necesita_modelo");
});

test("umbrales del modelo", () => {
  assert.equal(decidir({ ...base, score: 0.1 }).accion, "permitir");
  assert.equal(decidir({ ...base, score: 0.5 }).accion, "advertir");
  assert.equal(decidir({ ...base, score: 0.97 }).accion, "bloquear");
});

test("Capa 2: marca en dominio ajeno advierte, pero no pisa listas ni el bloqueo del modelo", async () => {
  const { decidir } = await import("../src/decision.js");
  const um = umbrales;
  const marca = { marca: "bcp", regla: "termino", severidad: "alta" };
  assert.equal(decidir({ url: "http://bcp-login.xyz", score: 0.1, umbrales: um, marca }).accion, "advertir");
  assert.equal(decidir({ url: "http://bcp-login.xyz", score: 0.99, umbrales: um, marca }).accion, "bloquear");
  assert.equal(decidir({ url: "http://bcp-login.xyz", score: 0.1, umbrales: um, marca, listasUsuario: { allow: ["bcp-login.xyz"] } }).accion, "permitir");
  assert.equal(decidir({ url: "http://x.com", score: 0.1, umbrales: um, marca: null }).accion, "permitir");
});

test("Capa 2: la marca solo advierte, no bloquea; el modelo sobre el umbral de bloqueo gana", () => {
  const marca = { regla: "tipeo", marca: "bcp" };
  assert.equal(decidir({ ...base, score: 0.1, marca }).accion, "advertir");
  assert.equal(decidir({ ...base, score: 0.1, marca }).motivo, "marca_tipeo_bcp");
  assert.equal(decidir({ ...base, score: 0.99, marca }).accion, "bloquear");
});
