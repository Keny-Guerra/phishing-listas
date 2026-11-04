import { test } from "node:test";
import assert from "node:assert/strict";
import { estadoDe, puntajeRiesgo, marcasUmbral, textoMotivo, decididoPorListas, mensajeActualizacion, abreviarHuella, textoUmbral, textoListas } from "../src/ui_logica.js";

test("estados: desactivado manda y acciones mapean", () => {
  assert.equal(estadoDe({ activa: false, accion: "bloquear" }), "desactivado");
  assert.equal(estadoDe({ accion: "permitir" }), "seguro");
  assert.equal(estadoDe({ accion: "advertir" }), "precaucion");
  assert.equal(estadoDe({ accion: "bloquear" }), "peligro");
});
test("puntaje 0-100 y marcas v8", () => {
  assert.equal(puntajeRiesgo(0.9549), 95);
  assert.equal(puntajeRiesgo(1.4), 100);
  assert.equal(puntajeRiesgo(undefined), null);
  assert.deepEqual(marcasUmbral({ advertencia: 0.3864, bloqueo: 0.9549 }), { advertencia: 39, bloqueo: 95 });
});
test("motivos", () => {
  assert.match(textoMotivo("marca_tipeo_bcp", { nombre: "BCP", regla: "tipeo" }), /parece imitar a BCP/);
  assert.equal(decididoPorListas("lista_del_dia_bloqueo"), true);
  assert.equal(decididoPorListas("modelo_zona_de_duda"), false);
  assert.match(textoUmbral("modelo_sobre_umbral_bloqueo", 0.97, { bloqueo: 0.9549 }), /97 de 100.*95/);
});
test("mensajes de actualización", () => {
  assert.equal(mensajeActualizacion({ estado: "sin_publicador" }).tipo, "info");
  assert.equal(mensajeActualizacion({ estado: "actualizado", cambios: ["modelo"] }).tipo, "ok");
  assert.equal(mensajeActualizacion({ estado: "error" }).tipo, "error");
  assert.equal(abreviarHuella("a".repeat(64)).length, 17);
});
test("estado de listas en el popup", () => {
  assert.match(textoListas({ publicador: false }), /sin servidor/);
  assert.match(textoListas({ publicador: true, ultima: null }), /sin descargar/);
  assert.match(textoListas({ publicador: true, proteccion: "al_dia", ultima: "2026-11-04T10:00:00Z" }), /al día \(2026-11-04\)/);
  assert.match(textoListas({ publicador: true, proteccion: "sin_actualizar", ultima: "2026-10-01T10:00:00Z" }), /sin actualizar desde 2026-10-01/);
});
