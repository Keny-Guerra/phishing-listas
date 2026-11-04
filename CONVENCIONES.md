# Convenciones de codificación

## Estructura (alineada con las capas del diseño)
| Carpeta | Capa / rol |
|---|---|
| `src/` (Python) | Lado del publicador y del entrenamiento: datos, modelo, listas del día (`listas_dia.py`), reentrenamiento |
| `extension/src/` | Núcleo de la extensión: `decision.js` (reglas), `actualizador.js` (Capa 1/5), `binlista.js`, `normalize.js`, `feedback.js`, `background.js`, `offscreen.js` |
| `extension/ui/` | Pantallas mínimas (popup, advertencia, opciones, bienvenida) |
| `extension/models/` | Modelo ONNX, vocabulario y umbrales |
| `tests/`, `extension/tests/` | Pruebas unitarias, de integración y e2e |
| `.github/workflows/` | CI y publicador de listas |
| `docs/` | Bitácora, calidad |

## Nombres
- Python: `snake_case` para funciones y variables, `PascalCase` para clases, `MAYUSCULAS` para constantes. Sin variables de una letra ambigua (`l`, `O`, `I`).
- JavaScript: `camelCase` para funciones y variables, constantes en `MAYUSCULAS`, módulos ES, un propósito por archivo.
- Identificadores de dominio en español (`decidir`, `actualizar`, `listasUsuario`), igual que el informe.
- Claves de `chrome.storage` solo en `config.js` (objeto `K`).

## Reglas de diseño
1. Ningún dato de navegación sale del dispositivo (RNF3). El único tráfico saliente es la descarga de datos públicos (listas y pesos).
2. Solo se actualizan datos, nunca lógica (política de código remoto de Chrome Web Store).
3. Toda descarga se verifica (tamaño y SHA-256) antes de activarse; la activación es una sola escritura.
4. La navegación nunca espera a la red.
5. Sin `eval`, sin `new Function`, sin `innerHTML` con datos externos.

## Control de versiones
- Commits pequeños, en español, en imperativo o sustantivo descriptivo ("Listas del día: generador, actualizador verificado y pruebas").
- Cada commit deja pasar pruebas y análisis estático.
- La CI (`.github/workflows/ci.yml`) corre ruff, bandit, pruebas Python, ESLint, pruebas JS y `npm audit`.

## Calidad
`ruff check src tests`, `bandit -c pyproject.toml -r src`, `npm run lint`, `npm test`, `npm run audit`.
