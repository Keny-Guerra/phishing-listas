// Copia el runtime WASM de ONNX Runtime Web a vendor/ (no se versiona; se regenera con `npm run vendor`).
import { cpSync, mkdirSync } from "node:fs";
mkdirSync("vendor", { recursive: true });
for (const f of ["ort.wasm.min.js", "ort-wasm-simd-threaded.mjs", "ort-wasm-simd-threaded.wasm"])
  cpSync(`node_modules/onnxruntime-web/dist/${f}`, `vendor/${f}`);
console.log("vendor/ actualizado");
