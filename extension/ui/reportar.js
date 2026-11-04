/** P04 · Reportar un error. */
import { $, mostrarMensaje } from "./comun.js";
import { esDominioValido, normalizarParaReporte, registrarCorreccion, estadoReportes, vistaPreviaReporte, MAX_REPORTES } from "../src/feedback.js";
const p = new URLSearchParams(location.search);
$("dominio").value = p.get("dominio") ?? "";
const origen = p.get("origen");
const tipoInicial = origen === "seguro" ? "falso_negativo" : "falso_positivo";
document.querySelector(`input[value=${tipoInicial}]`).checked = true;
const est = await estadoReportes(chrome.storage.local);
const puede = est.optin && est.cantidad < MAX_REPORTES;
$("compartir").disabled = !puede;
$("nota-comp").textContent = !est.optin ? "Para compartir, activa primero «Compartir reportes» en Opciones." : est.cantidad >= MAX_REPORTES ? `Hay ${MAX_REPORTES} reportes pendientes: no caben más.` : "Se comparte solo lo que ves en la vista previa.";
const tipo = () => document.querySelector("input[name=tipo]:checked")?.value;
function actualizar() {
  const d = normalizarParaReporte($("dominio").value.trim().toLowerCase());
  const ok = esDominioValido(d);
  $("err-dom").textContent = ok || !$("dominio").value ? "" : "Escribe un dominio válido, por ejemplo ejemplo.com";
  $("previa").textContent = JSON.stringify(vistaPreviaReporte({ dominio: d, tipo: tipo() }), null, 2);
  return ok;
}
$("f").addEventListener("input", actualizar); actualizar();
$("cancelar").addEventListener("click", () => window.close());
$("f").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!actualizar()) { $("dominio").focus(); return; }
  const dominio = normalizarParaReporte($("dominio").value.trim().toLowerCase());
  const r = await registrarCorreccion(chrome.storage.local, { dominio, tipo: tipo(), recordar: $("recordar").checked, compartir: $("compartir").checked && puede });
  mostrarMensaje($("msg"), r.ok ? "ok" : "error", r.ok ? `Guardado.${r.recordado ? " Se recordará en tu equipo." : ""}${r.compartido ? " Reporte agregado a los pendientes." : ""}` : "No se pudo guardar.");
  if (r.ok) setTimeout(() => window.close(), 1500);
});
