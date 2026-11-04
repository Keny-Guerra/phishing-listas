# Bitácora de avance (Unidad 6)

| Sprint | Fechas | Módulo trabajado | Completado | Pendiente / desviación |
|---|---|---|---|---|
| Sprint 1 | 16–22/10/2026 | Modelo v7 (Fase A) y reglas de decisión con listas | Modelo entrenado y exportado; reglas `decision.js`; paridad JS = Python verificada | Recall interno 76,6 % < 85 % (RNF2); se propone RNF2a/RNF2b |
| Sprint 2 | 19–25/10/2026 | Capa 1 (listas del día) + núcleo de la extensión | Generador `listas_dia.py`, actualizador verificado, service worker, offscreen con ONNX Runtime Web, UI mínima, CI y análisis estático | Capa 2 (marcas peruanas), Capa 4 (señales de página), publicación real en alojamiento, tamaños reales de feeds, medición en equipo del usuario |

## Desviaciones respecto al plan de la Fase 1
1. **Cambio de alcance (C9/C10):** la brecha de vigencia del modelo obligó a añadir listas del día y actualización silenciosa; no estaba en el plan inicial. Costó ~1 semana.
2. **Retraso global:** el proyecto está en la semana 11 con menos avance que el planificado (ver curva S).
3. **Hallazgo técnico:** `chrome.storage` no existe en el documento offscreen; el service worker debe entregarle el modelo. Ocurrió en la prueba e2e y se corrigió.
4. **Hallazgo técnico:** el manifiesto rechazaba listas vacías; la prueba de integración con el generador real lo detectó y se corrigió.

## 2026-11-03 — Capa 2 (marcas peruanas) y paso 1 de la Capa 1
- Paso 1 (Colab, datos del 03/11/2026): sobre 224 hosts frescos de OpenPhish el modelo v8 detecta 87,5 % (adv.), pero 50 % del feed está en plataformas gratuitas (pages.dev, vercel.app…) detectadas al 100 %; en el resto el recall es 74,8 % (IC95 ±8). Falsos positivos en sitios populares de Tranco: 19,7 %. Solapamiento del feed con v7: 1,34 %.
- Capa 2: `config/marcas_peru.json` (37 marcas: 18 confirmadas, 12 por confirmar, 7 globales), `src/capa2_marcas.py`, `extension/src/marcas.js` (paridad verificada con 403 vectores), integración en `decision.js` (advertir; no bloquea sola).
- Evaluación (`docs/calidad/capa2_evaluacion.json`): FPR sobre legítimas v7 ≈ 0,05 %; marca 0,74 % del phishing v7 (sobre todo marcas globales); en el feed de hoy rescata 0 de los 28 que el modelo perdió si se excluye Roblox (agregada tras ver el feed). Variantes sintéticas: solo prueban cobertura de reglas.

## 2026-11-03 — Extensión: paso 1, modelo v8
- `extension/models/cnn_phishing.onnx` ahora es el modelo v8 (variante ancha, 163 793 parámetros, ≈650 KB); `vocab_meta.json` reemplazado con el alfabeto del entrenamiento v8 (el orden difiere del v7: usar el del v7 habría dado puntuaciones erróneas sin avisar).
- Nueva normalización `host` en `normalize.js` (réplica de `host_norm` del Colab: sin usuario, sin puerto, sin `www\d*.`).
- Umbrales: advertencia 0,3864 / bloqueo 0,9549 (`umbrales_sugeridos.json`, `background.js`).
- Pruebas: `tests/modelo_v8_paridad.test.js` (416 entradas; normalización idéntica a Python y |Δ puntuación| < 1e-4). 38/38 pruebas JS y eslint limpios. E2E en Chromium con la extensión: p95 14,3 ms ida y vuelta (`docs/calidad/e2e_v8_chromium.json`).

## Interfaces de la Práctica 7 (extensión "Anzuelo Alerta")
- P01 bienvenida y consentimiento, P02 popup (4 estados + no analizable, puntaje 0-100 con marcas en 39 y 95), P03 advertencia (checkbox «Entiendo el riesgo», solo visita), P04 reportar error, P05 opciones (listas, opt-in, exportar/borrar, id anónimo, modelo con SHA-256, «Buscar actualización del modelo», restablecer).
- Umbrales v8: 0.3864 / 0.9549. Capa 2 solo advierte ("parece imitar a [marca]"); el bloqueo por modelo prevalece.
- «Buscar actualización» responde «sin servidor configurado» mientras URL_BASE sea el marcador de posición.
- Nombre por defecto «Anzuelo Alerta» (manifest.name); sin «UCSM». Pruebas: 46 unitarias + e2e Chromium (31 comprobaciones) OK.
- Paso 2 (Capa 2 conectada): decision.js + background.js (marcas_peru.json) + P02 (motivo) + P03 (aviso «parece imitar a [marca]» junto al bloqueo del modelo). Prueba e2e: bcp-peru-ayuda.com → Precaución (nunca bloquea solo).

## Capa 1 real — publicador preparado (04/11/2026)
- `listas_dia.py`: modelo v8 por defecto, `verificar_salida` (tamaños, SHA-256, huellas ordenadas, límites de la extensión, mínimo de permitidos) antes de publicar; estadísticas (solo conteos) en el manifest. La verificación detectó un error de orden (archivo del modelo copiado después de verificar): corregido.
- Flujo `actualizar-listas.yml`: reintentos, tiempo límite, publica modelo v8 con umbrales, copia privada del feed (artifact 90 días) para medir persistencia, `enable_jekyll: false`.
- `scripts/configurar_publicador.py` (URL_BASE con validación) + guía `docs/PUBLICAR_CAPA1.md`.
- Extensión: si el modelo publicado es el incluido (mismo SHA-256) no se descarga de nuevo; popup muestra «Listas del día: al día (fecha)».
- Ensayo con el feed real del 03/11 (300 URL → 115 hosts + 145 URL de plataformas) y un Tranco de ENSAYO (1 516 dominios sintéticos+reales; el de verdad no era descargable desde el entorno): E2E en Chromium con servidor local: listas descargadas y verificadas, 304 sin cambios, 8/8 hosts del feed con puntaje < 0,30 bloqueados por lista (motivo «lista del día»), popular permitido por lista. Es una prueba de funcionamiento, NO de cobertura (los hosts bloqueados salen del mismo feed).
- CI: ruff/bandit limpios (se configuraron excepciones para guiones e2e y se corrigieron avisos de Capa 2).
- Pruebas: 16 Python + 48 JS + 2 suites E2E.
