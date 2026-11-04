import test from "node:test";
import assert from "node:assert/strict";
import { normalizarUrl, tokenizar } from "../src/normalize.js";

// Mismos casos que se verifican en Python (src/normalize.py)
test("completa: sin esquema, sin www, sin / final, minúsculas, sin fragmento", () => {
  assert.equal(normalizarUrl("HTTPS://www.Ejemplo.com/"), "ejemplo.com");
  assert.equal(normalizarUrl("http://a.com/x?y=1#f"), "a.com/x?y=1");
  assert.equal(normalizarUrl("www.a.com"), "a.com");
  assert.equal(normalizarUrl("https://wwwx.com"), "wwwx.com");
});
test("solo_host conserva usuario@host:puerto", () => {
  assert.equal(normalizarUrl("https://user@evil.com:8080/p?q=1", "solo_host"), "user@evil.com:8080");
});
test("http y https dan la misma entrada al modelo", () => {
  assert.equal(normalizarUrl("http://www.sitio.com/a"), normalizarUrl("https://sitio.com/a"));
});
test("tokenizar: PAD=0, OOV, maxlen", () => {
  const vocab = { a: 1, b: 2 };
  assert.deepEqual(tokenizar("https://www.ab", vocab, 5, 9), [1, 2, 0, 0, 0].map((x, i) => i < 2 ? x : 0).slice(0, 0).concat(
    Array.from("ab").map((c) => vocab[c]), [0, 0, 0]));
  assert.deepEqual(tokenizar("zz", vocab, 3, 9), [9, 9, 0]);
});
