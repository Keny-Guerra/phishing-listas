"""
corpus.py
---------
Corpus maestro versionable del ciclo de retroalimentación.

Problema que resuelve: un dataset estático (PhiUSIIL) es una foto de un
momento y el phishing cambia. El corpus maestro es un CSV de solo-agregar
(append-only) con una columna `fecha` por URL, de modo que:
  - cada mes se agregan URLs nuevas (feeds abiertos + reportes verificados);
  - se puede evaluar con split TEMPORAL (entrenar con lo viejo, probar con
    lo reciente) y así medir si el modelo detecta phishing FUTURO.

Columnas: url, label (1=phishing, 0=legítima), fecha (YYYY-MM-DD), fuente.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit

import pandas as pd

COLUMNAS = ["url", "label", "fecha", "fuente"]


def normalizar_url(url: str) -> str:
    """Minúsculas, sin espacios, sin fragmento (#...). Es la misma
    normalización que usa la tokenización de preprocess.py."""
    u = str(url).strip().lower()
    return u.split("#", 1)[0]


def dominio(url: str) -> str:
    """Hostname de la URL (sin puerto ni credenciales). Si la URL no trae
    esquema se le antepone http:// solo para poder parsearla."""
    u = normalizar_url(url)
    if "://" not in u:
        u = "http://" + u
    try:
        return (urlsplit(u).hostname or "").strip(".")
    except ValueError:
        return ""


def cargar(path: str | Path) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        return pd.DataFrame(columns=COLUMNAS)
    df = pd.read_csv(p, dtype={"url": str, "fecha": str, "fuente": str})
    faltan = set(COLUMNAS) - set(df.columns)
    if faltan:
        raise ValueError(f"El corpus {p} no tiene las columnas {sorted(faltan)}")
    return df[COLUMNAS]


def agregar(path: str | Path, nuevas: pd.DataFrame) -> tuple[int, int]:
    """Agrega filas nuevas al corpus, sin duplicar URLs ya existentes
    (gana la fila más antigua: conserva la fecha en que la URL entró).
    Devuelve (agregadas, descartadas_por_duplicado)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    base = cargar(p)
    nuevas = nuevas.copy()
    nuevas["url"] = nuevas["url"].map(normalizar_url)
    nuevas = nuevas[nuevas["url"].str.len() > 0]
    nuevas = nuevas.drop_duplicates(subset="url")
    ya = set(base["url"])
    a_agregar = nuevas[~nuevas["url"].isin(ya)][COLUMNAS]
    descartadas = len(nuevas) - len(a_agregar)
    out = pd.concat([base, a_agregar], ignore_index=True)
    out.to_csv(p, index=False)
    return len(a_agregar), descartadas
