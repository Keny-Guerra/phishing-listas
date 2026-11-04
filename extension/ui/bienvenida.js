/** P01 · Bienvenida y consentimiento. */
import { $, enviar, nombreApp, mostrarMensaje } from "./comun.js";
$("nombre").textContent = nombreApp(); $("nombre2").textContent = nombreApp();
$("acepto").addEventListener("change", (e) => { $("activar").disabled = !e.target.checked; });
$("activar").addEventListener("click", async () => {
  await chrome.storage.local.set({ proteccion_activa: true, feedback_optin: false, schema_version: 1 });
  const info = await enviar("info_modelo");
  const ok = info?.modelo?.verificado !== false;
  mostrarMensaje($("msg"), ok ? "ok" : "error", ok ? "Protección activada. El modelo incluido fue verificado." : "Protección activada, pero no se pudo verificar el modelo incluido. Reinstala la extensión.");
  $("activar").disabled = true; $("acepto").disabled = true;
  $("fijar").hidden = false;
  try { await chrome.action.openPopup(); } catch { /* no disponible: queda la instrucción */ }
});
