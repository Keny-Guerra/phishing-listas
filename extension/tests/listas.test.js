import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { aUint32, contiene, huellaHost, aBase64, deBase64 } from "../src/binlista.js";

test("paridad Python <-> JS: el archivo generado por listas_dia.py se consulta igual desde JavaScript", async () => {
  const lista = aUint32(new Uint8Array(fs.readFileSync(new URL("./fixtures/bloqueo_ejemplo.bin", import.meta.url))));
  for (const h of ["secure-bcp-verificacion.xyz", "banco-falso.top", "ejemplo.pe"]) assert.equal(contiene(lista, await huellaHost(h)), true, h);
  for (const h of ["google.com", "bcp.com.pe"]) assert.equal(contiene(lista, await huellaHost(h)), false, h);
});

test("la lista viene ordenada y base64 es reversible", () => {
  const b = new Uint8Array([0, 0, 0, 1, 0, 0, 1, 0, 255, 255, 255, 255]);
  assert.deepEqual([...aUint32(b)], [1, 256, 4294967295]);
  assert.deepEqual([...deBase64(aBase64(b))], [...b]);
});
