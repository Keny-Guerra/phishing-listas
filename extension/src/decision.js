/**
 * decision.js — lógica de decisión de la extensión (función pura, sin DOM).
 *
 * Combina el score de la CNN con las listas, en este orden de prioridad:
 *   1. blocklist del usuario        -> bloquear   (el usuario marcó un falso negativo)
 *   2. allowlist del usuario        -> permitir   (el usuario marcó un falso positivo)
 *   3. lista de bloqueo del día     -> bloquear   (feed OpenPhish procesado por el publicador)
 *   4. allowlist de dominios top    -> permitir   (reduce falsos positivos; ver aviso)
 *   5. marca peruana en dominio ajeno (Capa 2) -> advertir (nunca bloquea por sí sola)
 *   6. umbrales del modelo vigente  -> bloquear / advertir / permitir (solo si ninguna lista decidió)
 *
 * Los dos umbrales vienen de manifest.json del modelo (calculados en retrain.py
 * sobre validación): entre `advertencia` y `bloqueo` solo se muestra aviso.
 *
 * AVISO sobre la allowlist top: coincide por host EXACTO (con o sin "www.").
 * No cubre subdominios porque servicios de hosting populares (p. ej. páginas
 * de terceros) pueden alojar phishing. Aun así, si la CNN da score >= 0.99
 * sobre un host de la allowlist, se advierte en lugar de permitir en silencio.
 */

export const SCORE_SOSPECHA_EXTREMA = 0.99;

export function hostDe(url) {
  try {
    const u = new URL(/^[a-z][a-z0-9+.-]*:\/\//i.test(url) ? url : `http://${url}`);
    return u.hostname.toLowerCase().replace(/\.$/, "");
  } catch {
    return "";
  }
}

const sinWww = (h) => h.replace(/^www\./, "");

export function decidir({ url, score, umbrales, listasUsuario = {}, allowlistTop = new Set(), enBloqueoDia = false, enPermitidosDia = false, marca = null }) {
  const host = hostDe(url);
  const allow = new Set(listasUsuario.allow ?? []);
  const block = new Set(listasUsuario.block ?? []);

  if (host && (block.has(host) || block.has(sinWww(host)))) {
    return { accion: "bloquear", motivo: "lista_usuario_bloqueo" };
  }
  if (host && (allow.has(host) || allow.has(sinWww(host)))) {
    return { accion: "permitir", motivo: "lista_usuario_permitido" };
  }
  // Lista de bloqueo del día (feed): después de lo que el usuario decidió y antes de los permitidos.
  if (enBloqueoDia) return { accion: "bloquear", motivo: "lista_del_dia_bloqueo" };
  const esTop = enPermitidosDia || (host && (allowlistTop.has(host) || allowlistTop.has(sinWww(host))));
  if (esTop) {
    return score !== undefined && score >= SCORE_SOSPECHA_EXTREMA
      ? { accion: "advertir", motivo: "allowlist_top_con_score_extremo" }
      : { accion: "permitir", motivo: "allowlist_top" };
  }
  // Ninguna lista decidió: hace falta el modelo (la extensión lo ejecuta solo en este caso).
  if (score === undefined) return { accion: "necesita_modelo", motivo: "sin_decision_de_listas" };
  if (score >= umbrales.bloqueo) return { accion: "bloquear", motivo: "modelo_sobre_umbral_bloqueo" };
  // Capa 2: el dominio imita a una marca (resultado de marcas.evaluar). Solo advierte; el bloqueo del modelo gana.
  if (marca) return { accion: "advertir", motivo: `marca_${marca.regla}_${marca.marca}` };
  if (score >= umbrales.advertencia) return { accion: "advertir", motivo: "modelo_zona_de_duda" };
  return { accion: "permitir", motivo: "modelo_bajo_umbral" };
}
