"""
normalize.py
------------
Normalización ÚNICA de URLs para el modelo. La usan preprocess.py (entrenamiento),
evaluate.py y la extensión (extension/src/normalize.js, mismo comportamiento).

Por qué existe: en el dataset base TODAS las legítimas empiezan con "https://www."
y las phishing no. La CNN aprendió ese atajo (prueba de robustez: sin
"https://www." el FPR subió a 52 %). Quitar esquema y "www." antes de tokenizar
elimina esa pista, tanto al entrenar como al predecir en el navegador.

Reglas (modo "completa"):
  1. minúsculas y sin espacios;
  2. sin fragmento (#...);
  3. sin esquema (http://, https://, ftp://...);
  4. sin "www." inicial;
  5. sin "/" final.
Modo "solo_host": además descarta ruta, query y fragmento (se queda con
usuario@host:puerto). Plan B si las legítimas del corpus no traen rutas.
"""

import re

MODOS = ("completa", "solo_host")
_RE_ESQUEMA = re.compile(r"^[a-z][a-z0-9+.\-]*://")


def normalizar_url(url, modo: str = "completa") -> str:
    if modo not in MODOS:
        raise ValueError(f"modo debe ser uno de {MODOS}")
    u = str(url).strip().lower().split("#", 1)[0]
    u = _RE_ESQUEMA.sub("", u)
    u = re.sub(r"^www\.", "", u)
    if modo == "solo_host":
        u = re.split(r"[/?]", u, maxsplit=1)[0]
    return u.rstrip("/")
