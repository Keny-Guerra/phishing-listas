/** P05 · Opciones y ajustes. */
import { $, el, enviar, nombreApp, confirmar, mostrarMensaje } from "./comun.js";
import { agregarDominio, quitarDominio, listasUsuario, activarOptIn, estadoReportes, exportarReportes, borrarPendientes, renovarId, restablecer } from "../src/feedback.js";
import { mensajeActualizacion, abreviarHuella, fechaCorta, puntajeRiesgo } from "../src/ui_logica.js";
const S = chrome.storage.local;
$("nombre").textContent = nombreApp();

async function pintarListas() {
  const l = await listasUsuario(S);
  for (const [lista, datos] of [["allow", l.allow ?? l.permitidos ?? []], ["block", l.block ?? l.bloqueados ?? []]]) {
    const ul = $(`ul-${lista}`); ul.replaceChildren();
    if (!datos.length) ul.append(el("li", { class: "vacia", texto: "Sin sitios" }));
    for (const d of datos) ul.append(el("li", {}, el("span", { texto: d }),
      el("button", { type: "button", "aria-label": `Quitar ${d}`, texto: "Quitar", onclick: async () => { await quitarDominio(S, lista, d); await pintarListas(); } })));
  }
}
const ERR = { invalido: "Escribe un dominio válido, por ejemplo ejemplo.com", en_lista_contraria: "Ya está en la otra lista. Quítalo primero.", duplicado: "Ya está en esta lista." };
for (const lista of ["allow", "block"]) {
  const agregar = async () => {
    const r = await agregarDominio(S, lista, $(`in-${lista}`).value);
    $(`err-${lista}`).textContent = r.ok ? "" : ERR[r.error];
    if (r.ok) { $(`in-${lista}`).value = ""; await pintarListas(); }
  };
  $(`add-${lista}`).addEventListener("click", agregar);
  $(`in-${lista}`).addEventListener("keydown", (e) => { if (e.key === "Enter") agregar(); });
}

async function pintarReportes() {
  const r = await estadoReportes(S);
  $("optin").checked = r.optin; $("cuenta").textContent = String(r.cantidad);
  $("id-info").textContent = r.tieneId ? `Se renueva en ${r.diasParaRotar} días` : "Aún no generado";
  $("borrar").disabled = $("exportar").disabled = r.cantidad === 0;
}
$("optin").addEventListener("change", async (e) => {
  const quiere = e.target.checked;
  if (quiere && !(await confirmar({ titulo: "Compartir reportes", texto: "Los reportes que tú envíes llevarán solo dominio, tipo, fecha e identificador anónimo. Puedes desactivarlo cuando quieras.", aceptar: "Activar" }))) { e.target.checked = false; return; }
  if (!quiere && (await estadoReportes(S)).cantidad > 0 && !(await confirmar({ titulo: "Desactivar", texto: "Tienes reportes pendientes. ¿Desactivar el envío? Los pendientes se conservan hasta que los borres.", aceptar: "Desactivar" }))) { e.target.checked = true; return; }
  await activarOptIn(S, quiere); await pintarReportes();
});
$("exportar").addEventListener("click", async () => {
  const url = URL.createObjectURL(new Blob([await exportarReportes(S)], { type: "application/json" }));
  const a = el("a", { href: url, download: "reportes_pendientes.json" }); document.body.append(a); a.click(); a.remove(); URL.revokeObjectURL(url);
});
$("borrar").addEventListener("click", async () => { if (await confirmar({ titulo: "Borrar pendientes", texto: "Se eliminarán todos los reportes pendientes de este equipo.", aceptar: "Borrar", destructivo: true })) { await borrarPendientes(S); await pintarReportes(); } });
$("renovar").addEventListener("click", async () => { await renovarId(S); await pintarReportes(); });

async function pintarModelo() {
  const i = await enviar("info_modelo"); const m = i.modelo ?? {};
  $("m-ver").textContent = m.version ?? "—"; $("m-fecha").textContent = fechaCorta(m.fecha);
  $("m-sha").textContent = abreviarHuella(m.sha256); $("m-sha").title = m.sha256 ?? "";
  $("m-verif").textContent = m.verificado ? "✓ Coincide con la huella registrada" : "✕ No coincide: reinstala la extensión";
  $("m-umb").textContent = m.umbrales ? `Precaución desde ${puntajeRiesgo(m.umbrales.advertencia)} · Peligro desde ${puntajeRiesgo(m.umbrales.bloqueo)}` : "—";
  const n = Object.keys(i.listas ?? {}).length;
  $("m-listas").textContent = n ? `${n} lista(s) · última actualización ${fechaCorta(i.ultima)}` : "Aún sin descargar";
}
$("actualizar").addEventListener("click", async () => {
  $("actualizar").disabled = true; mostrarMensaje($("msg-act"), "info", "Buscando…");
  const r = await enviar("buscar_actualizacion"); const m = mensajeActualizacion(r);
  mostrarMensaje($("msg-act"), m.tipo, m.texto); $("actualizar").disabled = false; await pintarModelo();
});

$("activa").addEventListener("change", async (e) => { await S.set({ proteccion_activa: e.target.checked }); await pintarProteccion(); });
async function pintarProteccion() {
  const s = await enviar("estado"); $("activa").checked = s.activa;
  $("est-prot").textContent = s.activa ? "El análisis de sitios está encendido." : "El análisis está apagado: no se avisará de ningún sitio.";
}
$("restablecer").addEventListener("click", async () => {
  if (!(await confirmar({ titulo: "Restablecer ajustes", texto: "Se borrarán tus listas, reportes pendientes, identificador y consentimiento. El modelo y las listas del día se conservan.", aceptar: "Restablecer", destructivo: true }))) return;
  await restablecer(S); mostrarMensaje($("msg-rest"), "ok", "Ajustes restablecidos."); await Promise.all([pintarListas(), pintarReportes()]);
});
await Promise.all([pintarListas(), pintarReportes(), pintarModelo(), pintarProteccion()]);
