/** Utilidades de las pantallas. Todo el texto se inserta con textContent (nunca innerHTML): sin riesgo de inyección. */
export const $ = (id) => document.getElementById(id);
export const nombreApp = () => chrome.runtime.getManifest().name;
export const enviar = (tipo, extra = {}) => chrome.runtime.sendMessage({ destino: "background", tipo, ...extra });
export const rutaUi = (pagina, params = {}) => `${chrome.runtime.getURL(`ui/${pagina}`)}${Object.keys(params).length ? `?${new URLSearchParams(params)}` : ""}`;

/** Crea un elemento: el() con atributos (class, texto, on*, aria-*) y nodos hijos. */
export function el(tag, atributos = {}, ...hijos) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(atributos)) {
    if (k === "texto") e.textContent = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (v === true) e.setAttribute(k, "");
    else if (v !== false && v !== null && v !== undefined) e.setAttribute(k, v);
  }
  for (const h of hijos.flat()) if (h !== null && h !== undefined) e.append(h);
  return e;
}

/** Muestra un mensaje de estado en `contenedor` (se anuncia a lectores de pantalla). */
export function mostrarMensaje(contenedor, tipo, texto) {
  contenedor.replaceChildren();
  if (!texto) return;
  contenedor.append(el("div", { class: `msg ${tipo}`, role: tipo === "error" ? "alert" : "status", texto }));
}

/** Diálogo de confirmación accesible (<dialog>). Devuelve una promesa con true/false. */
export function confirmar({ titulo, texto, aceptar = "Aceptar", cancelar = "Cancelar", destructivo = false }) {
  return new Promise((resolver) => {
    const d = el("dialog", { "aria-labelledby": "dlg-t" },
      el("h2", { id: "dlg-t", texto: titulo }), el("p", { texto }),
      el("div", { class: "acciones" },
        el("button", { type: "button", texto: cancelar, onclick: () => d.close("no") }),
        el("button", { type: "button", class: destructivo ? "principal peligro-btn" : "principal", texto: aceptar, onclick: () => d.close("si") })));
    d.addEventListener("close", () => { resolver(d.returnValue === "si"); d.remove(); });
    document.body.append(d);
    d.showModal();
  });
}

export const esUrlWeb = (u) => { try { return /^https?:$/.test(new URL(u).protocol); } catch { return false; } };
