/**
 * ui_logica.js — reglas de las pantallas (Práctica 7), sin DOM: se prueban con node --test.
 * Estados de P02, puntaje de riesgo, textos de motivo y mensajes de actualización.
 */

/** Los cuatro estados de la ventana emergente (Tabla 3 de la Práctica 7). Nunca dependen solo del color. */
export const ESTADOS = {
  seguro: { clase: "seguro", simbolo: "✓", texto: "Sin riesgo detectado" },
  precaucion: { clase: "precaucion", simbolo: "▲", texto: "Precaución: revisa la dirección antes de ingresar datos" },
  peligro: { clase: "peligro", simbolo: "✕", texto: "Peligro: posible phishing" },
  desactivado: { clase: "desactivado", simbolo: "○", texto: "Protección desactivada" },
};

export function estadoDe({ activa = true, accion }) {
  if (!activa) return "desactivado";
  return { permitir: "seguro", advertir: "precaucion", bloquear: "peligro" }[accion] ?? "seguro";
}

export const puntajeRiesgo = (score) => (typeof score === "number" && Number.isFinite(score) ? Math.max(0, Math.min(100, Math.round(score * 100))) : null);

/** Posición (0-100) de las marcas de umbral sobre la barra de puntaje. */
export const marcasUmbral = (u) => ({ advertencia: puntajeRiesgo(u.advertencia), bloqueo: puntajeRiesgo(u.bloqueo) });

const MOTIVOS_LISTA = {
  lista_usuario_bloqueo: "Lista bloqueada por ti",
  lista_usuario_permitido: "Lista permitida por ti",
  lista_del_dia_bloqueo: "Figura en la lista de sitios fraudulentos del día",
  allowlist_top: "Sitio popular verificado",
  allowlist_top_con_score_extremo: "Sitio popular, pero el análisis detecta señales extremas",
  modelo_no_disponible: "El análisis no está disponible; solo se usan las listas",
  no_web: "Página interna del navegador",
};

/** Texto de «Motivo de la decisión». `marca` = resultado de marcas.evaluar o null. */
export function textoMotivo(motivo, marca = null) {
  if (MOTIVOS_LISTA[motivo]) return MOTIVOS_LISTA[motivo];
  if (String(motivo).startsWith("marca_")) {
    return `El dominio parece imitar a ${marca?.nombre ?? "una marca conocida"}${marca?.regla === "tipeo" ? " (con un error de escritura)" : ""}`;
  }
  if (String(motivo).startsWith("modelo_")) return "Análisis del modelo";
  return "Análisis del modelo";
}

/** ¿La decisión salió de las listas/marcas y no del puntaje? (para avisarlo junto al puntaje). */
export const decididoPorListas = (motivo) => Object.hasOwn(MOTIVOS_LISTA, motivo) && motivo !== "modelo_no_disponible";

/** Texto de la pantalla P03 sobre el umbral superado. */
export function textoUmbral(motivo, score, umbrales) {
  if (motivo === "modelo_sobre_umbral_bloqueo") return `Puntaje de riesgo ${puntajeRiesgo(score)} de 100, igual o mayor que el umbral de bloqueo (${puntajeRiesgo(umbrales.bloqueo)}).`;
  if (motivo === "lista_del_dia_bloqueo") return "El sitio figura en la lista de sitios fraudulentos del día.";
  if (motivo === "lista_usuario_bloqueo") return "Tú marcaste este sitio como peligroso.";
  return "El análisis detectó señales de phishing.";
}

/** Mensaje al pulsar «Buscar actualización del modelo». */
export function mensajeActualizacion(r) {
  switch (r?.estado) {
    case "actualizado": return { tipo: "ok", texto: r.cambios?.includes("modelo") ? "Se instaló un modelo nuevo y verificado." : "Se actualizaron las listas del día." };
    case "sin_cambios": return { tipo: "ok", texto: "Ya tienes el modelo y las listas más recientes." };
    case "ocupado": return { tipo: "info", texto: "Ya hay una comprobación en curso. Inténtalo en unos minutos." };
    case "sin_publicador": return { tipo: "info", texto: "Todavía no hay un servidor de actualizaciones configurado. La protección sigue con el modelo incluido." };
    default: return { tipo: "error", texto: "No se pudo comprobar ahora (sin conexión o servidor no disponible). Se conserva el modelo actual." };
  }
}

export const abreviarHuella = (h) => (h ? `${h.slice(0, 8)}…${h.slice(-8)}` : "—");
export const fechaCorta = (iso) => (iso ? String(iso).slice(0, 10) : "—");

/** Línea de estado de las listas del día en la ventana emergente. */
export function textoListas({ publicador, proteccion, ultima }) {
  if (publicador === false) return "Listas del día: sin servidor configurado";
  if (!ultima) return "Listas del día: aún sin descargar";
  return proteccion === "al_dia" ? `Listas del día: al día (${fechaCorta(ultima)})` : `Listas del día: sin actualizar desde ${fechaCorta(ultima)}`;
}
