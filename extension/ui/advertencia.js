/** P03 · Advertencia de alto riesgo. «Volver» tiene el foco inicial. */
import { $, enviar, rutaUi, esUrlWeb } from "./comun.js";
import { textoMotivo, textoUmbral } from "../src/ui_logica.js";
const p = new URLSearchParams(location.search);
const destino = p.get("destino") ?? ""; const motivo = p.get("motivo") ?? ""; const score = Number(p.get("score")) / 100;
let host = ""; try { host = new URL(destino).hostname.replace(/^www\./, ""); } catch { /* inválido */ }
$("host").textContent = host || "(dirección no válida)";
const info = await enviar("info_modelo");
const umbrales = info?.modelo?.umbrales ?? { advertencia: 0.3864, bloqueo: 0.9549 };
$("porque").textContent = textoMotivo(motivo, null);
$("detalle").textContent = textoUmbral(motivo, Number.isFinite(score) ? score : null, umbrales);
const idMarca = p.get("marca");
if (idMarca) {
  try {
    const marcas = (await (await fetch(chrome.runtime.getURL("data/marcas_peru.json"))).json()).marcas;
    const m = marcas.find((x) => x.id === idMarca);
    if (m) { $("marca").textContent = `Además, la dirección parece imitar a ${m.nombre}. La dirección oficial no es esta.`; $("marca").hidden = false; }
  } catch { /* sin datos de marcas: se omite el aviso */ }
}
$("volver").focus();
$("volver").addEventListener("click", async () => {
  if (history.length > 1) history.back();
  else { try { await chrome.tabs.update({ url: "chrome://newtab/" }); } catch { window.close(); } }
});
$("entiendo").addEventListener("change", (e) => { $("seguir").disabled = !e.target.checked || !esUrlWeb(destino); });
$("seguir").addEventListener("click", async () => { await enviar("excepcion_visita", { url: destino }); location.href = destino; });
$("falso").addEventListener("click", () => { location.href = rutaUi("reportar.html", { dominio: host, origen: "peligro" }); });
