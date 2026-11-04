/** P02 · Ventana emergente de estado (Práctica 7, Tablas 3 y 4). */
import { $, enviar, nombreApp, rutaUi } from "./comun.js";
import { ESTADOS, textoListas, estadoDe, puntajeRiesgo, marcasUmbral, textoMotivo, decididoPorListas } from "../src/ui_logica.js";

$("nombre").textContent = nombreApp();
const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
const tabUrl = new URLSearchParams(location.search).get("url") ?? tab?.url ?? ""; // ?url= solo para pruebas y capturas

function pintarEstado(clave, texto) {
  const e = ESTADOS[clave] ?? { clase: "desactivado", simbolo: "–", texto };
  const t = $("tarjeta");
  t.className = `tarjeta ${e.clase}`;
  $("simbolo").textContent = e.simbolo;
  $("texto").textContent = texto ?? e.texto;
}

async function pintar() {
  const r = await enviar("estado_sitio", { url: tabUrl });
  $("activa").checked = r.activa;
  $("pie").textContent = `Modelo ${r.modelo?.version ?? "—"} · Tus direcciones no salen de este equipo.`;
  $("pie-listas").textContent = textoListas(r);
  $("dominio").textContent = r.analizable ? r.dominio : "Página interna del navegador";
  const sinAnalisis = !r.activa || !r.analizable;
  $("bloque-puntaje").hidden = sinAnalisis || typeof r.score !== "number";
  $("reportar").disabled = sinAnalisis;
  $("volver").hidden = true;

  if (!r.activa) { pintarEstado("desactivado"); $("motivo").textContent = "Activa la protección para analizar los sitios."; return; }
  if (!r.analizable) { pintarEstado("noanalizable", "Esta página no se analiza"); $("motivo").textContent = "Solo se analizan sitios web (http y https)."; return; }

  const clave = estadoDe({ activa: true, accion: r.accion });
  pintarEstado(clave);
  $("motivo").textContent = textoMotivo(r.motivo, r.marca);
  $("volver").hidden = clave !== "peligro";
  $("reportar").dataset.estado = clave;

  if (typeof r.score === "number") {
    const p = puntajeRiesgo(r.score), m = marcasUmbral(r.umbrales);
    $("num").textContent = String(p);
    $("relleno").style.width = `${p}%`;
    $("barra").setAttribute("aria-valuenow", String(p));
    $("barra").style.setProperty("--a", `${m.advertencia}%`); $("barra").style.setProperty("--b", `${m.bloqueo}%`);
    $("marca-a").style.left = `${m.advertencia}%`; $("marca-b").style.left = `${m.bloqueo}%`;
    $("esc-a").style.left = `${m.advertencia}%`; $("esc-a").textContent = String(m.advertencia);
    $("esc-b").style.left = `${m.bloqueo}%`; $("esc-b").textContent = String(m.bloqueo);
    $("nota-puntaje").textContent = (decididoPorListas(r.motivo) || r.marca && r.motivo.startsWith("marca_"))
      ? "La decisión no salió solo del puntaje: ver el motivo. El puntaje es informativo. Es una estimación y puede equivocarse."
      : "Es una estimación, no una probabilidad, y puede equivocarse. Las marcas indican dónde empieza la precaución y el peligro.";
  }
}

$("activa").addEventListener("change", async (ev) => { await chrome.storage.local.set({ proteccion_activa: ev.target.checked }); await pintar(); });
$("ajustes").addEventListener("click", () => { chrome.runtime.openOptionsPage(); window.close(); });
$("reportar").addEventListener("click", async () => {
  const r = await enviar("estado_sitio", { url: tabUrl });
  await chrome.tabs.create({ url: rutaUi("reportar.html", { dominio: r.dominio, origen: $("reportar").dataset.estado ?? "seguro" }) });
  window.close();
});
$("volver").addEventListener("click", async () => {
  try { await chrome.tabs.update(tab.id, { url: "chrome://newtab/" }); } catch { await chrome.tabs.remove(tab.id); }
  window.close();
});
ESTADOS.noanalizable = { clase: "desactivado", simbolo: "–", texto: "Esta página no se analiza" };
await pintar();
