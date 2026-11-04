# Sistema Predictivo de Detección de Phishing — Implementación (Modelo CNN + ONNX)

Proyecto: *Sistema Predictivo Basado en Deep Learning para la Detección de Phishing en Usuarios Digitales de Arequipa*
Autor: Keny Russell Guerra Huanaco, Ingeniería de Sistemas

Este directorio contiene el código de implementación (RF5-RF8, CU-01 a CU-08) que entrena y exporta el
modelo de clasificación de URLs, siguiendo las decisiones documentadas en el Capítulo 1 y la Práctica 5:
arquitectura **CNN a nivel de caracteres**, ejecución **100% local en el navegador** vía **ONNX Runtime
Web**, sin backend propio (RNF3: privacidad, Ley N.° 29733).

## Reproducibilidad (RNF7)

Todo el código está versionable en Git y es determinístico (semilla fija `RANDOM_SEED=42` en todos los
scripts: muestreo del dataset, split train/val/test, inicialización y validación cruzada).

### Opción recomendada: Google Colab (GPU gratuita)

Este es el entorno planificado en las Prácticas 1 y 4 (factibilidad económica: cómputo gratuito).

1. Abre `notebooks/entrenamiento_colab.ipynb` en Google Colab.
2. Activa GPU: `Entorno de ejecución > Cambiar tipo de entorno de ejecución > GPU (T4)`.
3. Comprime esta carpeta completa (`phishing_detector/`) en un `.zip` y súbela cuando el notebook lo
   pida.
4. Ejecuta las celdas en orden. El notebook instala dependencias, descarga el dataset, preprocesa,
   entrena con k-fold (k=10) y exporta a ONNX, midiendo la latencia de inferencia.
5. Al final, descarga `modelos_entrenados.zip` con el modelo `.onnx`, las métricas y el modelo `.keras`.

### Opción local (si tienes Python 3.10+ y suficiente RAM/CPU o GPU propia)

```bash
cd phishing_detector
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt

python src/download_dataset.py --n-total 80000 --out data/raw/dataset_unificado.csv
python src/preprocess.py --in data/raw/dataset_unificado.csv --outdir data/processed --maxlen 200
python src/train.py --processed-dir data/processed --models-dir models --epochs 15 --k-folds 10
python src/export_onnx.py --model models/cnn_phishing_final.keras --out models/cnn_phishing.onnx
```

## Estructura del proyecto

```
phishing_detector/
├── README.md
├── requirements.txt
├── data/
│   ├── raw/                  # dataset_unificado.csv (generado por download_dataset.py)
│   └── processed/            # train.npz, val.npz, test.npz, vocab_meta.json
├── src/
│   ├── download_dataset.py   # descarga PhiUSIIL (UCI) + opcional Kaggle, balancea a 80,000 URLs
│   ├── preprocess.py         # tokenización a nivel de carácter, split 70/10/20
│   ├── model.py               # arquitectura CNN multi-escala (kernels 3/5/7)
│   ├── train.py               # entrenamiento con k-fold (k=10) + reentrenamiento final
│   └── export_onnx.py         # exporta a ONNX, valida equivalencia, mide latencia (RNF1)
├── models/                   # salidas: .keras, .onnx, métricas .json
├── notebooks/
│   ├── 00_smoke_test.py       # genera datos sintéticos para probar el pipeline sin internet
│   └── entrenamiento_colab.ipynb
├── src/corpus.py · fetch_feeds.py · feedback_ingest.py · retrain.py · promote_model.py   # ciclo de mejora
└── extension/                 # decision.js + feedback.js (lógica probada); falta manifest.json/UI
```

## Fuente del dataset

**PhiUSIIL Phishing URL Dataset** (UCI Machine Learning Repository, ID 967): 235,795 URLs reales
verificadas (134,850 legítimas + 100,945 phishing), acceso público sin necesidad de credenciales.
Se eligió sobre el feed directo de PhishTank (hoy requiere registro) y sobre Kaggle (requiere token de
API) por ser la fuente de acceso más simple y reproducible que además supera ampliamente el umbral de
80,000 URLs balanceadas exigido en RNF6/OE2. El script `download_dataset.py` también admite incorporar
opcionalmente un CSV de Kaggle ("Malicious URLs dataset") si el estudiante quiere sumar una segunda
fuente, tal como contempla RF8 (CU-08 "Importar datasets externos").

> Nota: el entorno donde se preparó este código no tenía acceso general a internet (solo a
> repositorios de paquetes), así que la descarga real del dataset y el entrenamiento con GPU deben
> hacerse en Colab o en tu propia máquina — exactamente el flujo que ya estaba planificado en la
> Práctica 1/4. El pipeline fue validado end-to-end aquí con datos sintéticos
> (`notebooks/00_smoke_test.py`) para asegurar que el código corre sin errores.

## Convención de etiquetas

`label = 1` → phishing · `label = 0` → legítima (consistente con RF1-RF4 y el diagrama de casos de uso).

## Verificación de requerimientos no funcionales

| RNF | Criterio | Dónde se verifica |
|---|---|---|
| RNF1 | Latencia <100ms en el 95% de las clasificaciones | `export_onnx.py` → `models/latencia_onnx_metrics.json` (medido en CPU local; **remedir dentro del navegador** antes de darlo por cumplido) |
| RNF2 | Recall >85% en amenazas emergentes | `train.py` → promedio de recall en validación k-fold, impreso al final del entrenamiento |
| RNF3 | 100% procesamiento local (Ley N.° 29733) | Arquitectura: inferencia vía ONNX Runtime Web dentro de la extensión, sin llamadas de red |
| RNF6 | Dataset ≥80,000 URLs balanceadas 70/10/20 | `download_dataset.py` + `preprocess.py` |
| RNF7 | Reproducibilidad, código versionado | Este repositorio, semillas fijas, este README |

## Ciclo de retroalimentación mensual (mejora continua)

El modelo entrenado con un dataset estático envejece: el phishing cambia. Por eso el proyecto incluye un ciclo
de reentrenamiento **offline** (sin backend en producción, RNF3 intacto):

```
fetch_feeds.py  ->  feedback_ingest.py  ->  retrain.py  ->  promote_model.py  ->  publicar models/vigente/
 (URLs nuevas)       (reportes verificados)  (split temporal,    (ONNX + SHA-256 +     (actualización de la
                                              vs. campeón)        rollback)             extensión)
```

| Paso | Comando (Colab o local, con internet) |
|---|---|
| 0. Corpus base (una vez) | convertir `dataset_unificado.csv` a `data/corpus/corpus.csv` con columnas `url,label,fecha,fuente` (`fecha` = fecha de corte del dataset base) |
| 1. Traer URLs nuevas | `python src/fetch_feeds.py --corpus data/corpus/corpus.csv` |
| 2. Verificar reportes | `python src/feedback_ingest.py --reportes reportes.csv --feed-phishing feed.txt` |
| 3. Reentrenar y comparar | `python src/retrain.py --cutoff 2026-11-01` (test = URLs desde esa fecha) |
| 4. Promover / revertir | `python src/promote_model.py --candidato models/candidatos/vYYYYMMDD` · `--rollback` |

Decisiones de diseño clave:

- **Split temporal**: el test son las URLs más recientes, no una muestra aleatoria; mide si detecta phishing *futuro*.
- **Dos umbrales** (calculados en validación): *advertencia* (recall objetivo 90 %, RNF2 > 85 %) y *bloqueo* (FPR ≤ 0.5 %).
  Entre ambos la extensión solo avisa. Esto reduce el costo de los falsos positivos sin sacrificar recall.
- **Un reporte no es una etiqueta**: pasa por cuarentena (quórum de reporteros distintos, límite diario anti-spam,
  contraste con feed de phishing / allowlist Tranco, revisión manual de conflictos) antes de entrar al corpus.
- **Promoción con guardas**: el candidato solo reemplaza al vigente si no baja el recall ni sube la FPR sobre el
  mismo test futuro; si no, se conserva el vigente. Siempre hay `--rollback`.
- **Extensión** (`extension/src/`): `decision.js` (listas del usuario → allowlist top → umbrales) y `feedback.js`
  (Nivel A local siempre activo; Nivel B opt-in con reporte mínimo `{dominio, tipo, reportero, fecha}`).
  Pruebas: `cd extension && npm test`.

Prueba de humo del ciclo completo (datos sintéticos, sin internet): `python notebooks/01_smoke_test_ciclo.py`.

**Límites que conviene declarar en la tesis:** (a) las legítimas de Tranco son solo dominios, lo que puede sesgar al
modelo hacia "con ruta = sospechosa" (`retrain.py` reporta la FPR por tipo para vigilarlo); (b) los feeds abiertos
tienen su propio retraso de catalogación, así que el ciclo reduce la ventana de exposición pero no la elimina;
(c) la verificación externa con Safe Browsing/VirusTotal queda como gancho (`verificar_externo()`), requiere API key;
(d) el aprendizaje federado queda como trabajo futuro.

## Próximos pasos (no incluidos en esta entrega)

- Desarrollo de la extensión de navegador Manifest V3 (`extension/`) que consuma `cnn_phishing.onnx`
  vía `onnxruntime-web`, siguiendo el diagrama de componentes de la Práctica 5 (Content Script →
  Background Service Worker → Módulo de Inferencia / Popup UI).
- Prueba de usabilidad con 30 usuarios (TAM/Likert), según RNF4.
- Publicación en Chrome Web Store (CU-07).

## Estado de la implementación (Práctica 8, 23/10/2026)

- **Extensión MV3** (`extension/`): decisión por capas (usuario → lista del día → top → modelo), actualizador silencioso verificado con SHA-256, inferencia con ONNX Runtime Web en un documento offscreen, interfaz mínima. Se carga con «Cargar descomprimida» tras `npm ci && npm run vendor`.
- **Publicador de listas** (`src/listas_dia.py`): genera `bloqueo.bin`, `bloqueo_urls.bin`, `permitidos.bin` y `manifest.json`. Flujo programado en `.github/workflows/actualizar-listas.yml` (aún no ejecutado en GitHub). Guía: `docs/PUBLICAR_CAPA1.md`.
- **Calidad**: `ruff`, `bandit`, `ESLint`, `npm audit`; CI en `.github/workflows/ci.yml`. Convenciones en `CONVENCIONES.md`; bitácora en `docs/BITACORA.md`; evidencias en `docs/calidad/`.
- **Pendiente**: content script y señales de página (Capa 4), marcas peruanas (Capa 2), medir tamaño real de los feeds, publicar en alojamiento y reemplazar `URL_BASE`.

## Pruebas
```
python -m unittest discover -s tests          # generador de listas
cd extension && npm test && npm run lint      # núcleo de la extensión
python tests/e2e/e2e_chromium.py              # extremo a extremo + latencia (requiere Chromium y Playwright)
```
