# Publicar la Capa 1 (listas del día) — guía paso a paso

Qué hace: cada 12 horas GitHub descarga OpenPhish y Tranco, genera tres listas compactas y un `manifest.json` con SHA-256, y las publica en GitHub Pages. La extensión las descarga sola (una vez al día), verifica la huella y las activa; si algo falla, conserva las anteriores. Las direcciones que visita el usuario **nunca** se envían: solo se descargan las listas.

## 1. Crear el repositorio
1. En github.com: **New repository** → nombre `phishing-listas` → **Public** (GitHub Pages gratis lo requiere) → sin README.
2. Sube **todo este proyecto** (el flujo usa `src/`, `tests/` y `extension/models/`). Desde la carpeta del proyecto:
   `git init && git add . && git commit -m "Proyecto" && git branch -M main && git remote add origin https://github.com/TU_USUARIO/phishing-listas.git && git push -u origin main`
   (O arrastra los archivos con «Add file → Upload files»).

## 2. Permitir que el flujo publique
- **Settings → Actions → General → Workflow permissions → Read and write permissions** → Save.

## 3. Ejecutar el publicador la primera vez
- Pestaña **Actions → Actualizar listas del día → Run workflow**.
- Debe terminar en verde. Si falla en «Generar y verificar listas», **no publica nada** (es la protección): el mensaje dice por qué (feed vacío, Tranco caído, huella distinta…).

## 4. Activar GitHub Pages
- **Settings → Pages → Source: Deploy from a branch → Branch `gh-pages` / `(root)`** → Save.
- Espera 1–2 minutos y abre `https://TU_USUARIO.github.io/phishing-listas/manifest.json`: debe mostrar el JSON (versión del día, tamaños, SHA-256 y el modelo v8).

## 5. Conectar la extensión
```
python scripts/configurar_publicador.py TU_USUARIO
```
Cambia `URL_BASE` en `extension/src/config.js`. Luego en `chrome://extensions` pulsa **Recargar** en la extensión.
Comprobación: Opciones → **Buscar actualización del modelo** → «Se actualizaron las listas del día» (la segunda vez: «Ya tienes el modelo y las listas más recientes»). El popup mostrará «Listas del día: al día (fecha)».

## 6. Medir la persistencia del feed (para la tesis)
Cada ejecución guarda una copia del feed del día como *artifact* (90 días): **Actions → ejecución → Artifacts**. Descarga las de los días 0, 2–3 y 7 y repite el Colab del paso 1. Así se mide cuánto del phishing de hoy sigue en el feed después.

## Si algo sale mal
- Sin publicar nada: la extensión sigue con las últimas listas buenas y el modelo incluido (nunca queda sin protección).
- Reversión: ejecuta de nuevo el flujo desde un commit anterior, o borra la rama `gh-pages` y vuelve a ejecutarlo.
- Cambiar de alojamiento: `python scripts/configurar_publicador.py --url https://tu-sitio/listas/` (debe ser HTTPS y terminar en `/`).

## Licencias y límites (declararlos en el documento)
- OpenPhish feed comunitario: uso **no comercial**; mantén el proyecto académico y cita la fuente. El repositorio publica solo huellas de 4 bytes (no el feed) y el feed completo queda solo como artifact temporal.
- Tranco: lista de investigación; cítala (Le Pochat et al., 2019).
- Las huellas de 4 bytes admiten colisiones raras; el publicador las mide y rechaza la publicación si superan el 1 %.
- Medición: con feed de un solo día no hay cobertura demostrada de la Capa 1; se mide con las copias diarias (paso 6).
