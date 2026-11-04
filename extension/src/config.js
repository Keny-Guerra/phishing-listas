/** Configuración central. Cambiar URL_BASE al publicar (GitHub Pages u otro alojamiento HTTPS). */
export const URL_BASE = "https://CAMBIAR-USUARIO.github.io/phishing-listas/";
export const HORAS_ENTRE_COMPROBACIONES = 24; // al abrir una pestaña, si pasó más de esto
export const MINUTOS_ALARMA = 360; // respaldo cada ~6 h (chrome.alarms)
export const HORAS_PROTECCION_AL_DIA = 48; // más de esto sin actualizar => "sin actualizar"
export const MINUTOS_CANDADO = 10; // un candado de actualización caduca a los 10 min
export const MAX_BYTES_LISTA = 5_000_000;
export const MAX_BYTES_MODELO = 3_000_000;
export const NOMBRES_LISTAS = ["bloqueo", "bloqueo_urls", "permitidos"];
export const K = {
  activa: "proteccion_activa", esquema: "schema_version", instalacion: "instalado_en",
  modelo: "modelo_vigente", modeloB64: "modelo_bytes_b64",
  listas: "listas_vigentes", // { nombre: { version, sha256, b64 } }
  versionAnterior: "version_anterior", ultima: "ultima_actualizacion", etag: "manifest_etag",
  candado: "actualizando",
};
export const SCHEMA_VERSION = 1;

/** Mientras URL_BASE conserve el valor de ejemplo no se intenta ninguna descarga (evita errores de red inútiles). */
export const publicadorConfigurado = () => !/CAMBIAR/i.test(URL_BASE);
export const K_EXCEPCIONES = "excepciones_visita"; // chrome.storage.session: { host: ISO }
export const MINUTOS_EXCEPCION = 30;
