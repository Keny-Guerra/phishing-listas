"""
fetch_feeds.py
--------------
Paso 1 del ciclo mensual de retroalimentación: trae URLs NUEVAS de feeds
abiertos y las agrega al corpus maestro con la fecha de hoy.

  - Phishing:   OpenPhish community feed (https://openphish.com/feed.txt,
                texto plano, uno por línea, sin registro) y, opcionalmente,
                PhishTank (online-valid.csv; requiere app key gratuita).
  - Legítimas:  Tranco top sites (https://tranco-list.eu, lista de ranking
                resistente a manipulación; CSV rank,dominio).

También genera `allowlist_top.json` (los N dominios más populares) que la
extensión usa para NO bloquear sitios muy conocidos aunque la CNN dude
(reducción de falsos positivos).

LIMITACIONES (se declaran para no sobreestimar resultados):
  * Las legítimas de Tranco son solo dominios (https://dominio/); las de
    PhiUSIIL traen rutas. Esto puede sesgar al modelo hacia "con ruta ->
    sospechosa". Mitigación: mezclar siempre con el corpus base y revisar
    la tasa de falsos positivos por tipo (retrain.py la reporta).
  * Los feeds de phishing contienen también sitios legítimos comprometidos;
    por eso se descartan phishing cuyo host está en el top-1000 de Tranco
    (etiqueta contradictoria con la allowlist).
  * Requiere internet: ejecutar en Colab o en tu máquina. El sandbox donde
    se preparó el código no tiene salida a esos hosts; en pruebas se usan
    --phishing-file / --tranco-file locales.

Uso (con internet):
    python src/fetch_feeds.py --corpus data/corpus/corpus.csv
Uso (offline / pruebas):
    python src/fetch_feeds.py --phishing-file feed.txt --tranco-file top.csv
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import zipfile
from datetime import date
from pathlib import Path
from urllib.request import Request, urlopen

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import corpus as C  # noqa: E402

RANDOM_SEED = 42
OPENPHISH_URL = "https://openphish.com/feed.txt"
TRANCO_ZIP_URL = "https://tranco-list.eu/top-1m.csv.zip"
PHISHTANK_URL = "http://data.phishtank.com/data/{key}/online-valid.csv"
UA = {"User-Agent": "phishing-detector-pfc-ucsm/1.0 (proyecto academico)"}


def _descargar(url: str, timeout: int = 60) -> bytes:
    if not url.startswith("https://"):
        raise ValueError(f"Solo se permiten URLs https: {url}")
    with urlopen(Request(url, headers=UA), timeout=timeout) as r:  # nosec B310 # esquema https verificado arriba
        return r.read()


def leer_openphish(path: str | None) -> list[str]:
    raw = Path(path).read_bytes() if path else _descargar(OPENPHISH_URL)
    return [ln.strip() for ln in raw.decode("utf-8", "ignore").splitlines() if ln.strip()]


def leer_phishtank(key: str | None) -> list[str]:
    if not key:
        return []
    raw = _descargar(PHISHTANK_URL.format(key=key), timeout=120)
    df = pd.read_csv(io.BytesIO(raw))
    return df["url"].dropna().astype(str).tolist()


def leer_tranco(path: str | None, top_n: int) -> list[str]:
    """Devuelve los top_n dominios de Tranco (CSV 'rank,dominio', con o sin zip)."""
    if path:
        raw = Path(path).read_bytes()
    else:
        raw = _descargar(TRANCO_ZIP_URL, timeout=180)
    if raw[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            raw = z.read(z.namelist()[0])
    df = pd.read_csv(io.BytesIO(raw), header=None, names=["rank", "dominio"], nrows=top_n)
    return df["dominio"].astype(str).str.strip().str.lower().tolist()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", default="data/corpus/corpus.csv")
    ap.add_argument("--fecha", default=None, help="Fecha a registrar (YYYY-MM-DD). Por defecto hoy.")
    ap.add_argument("--phishing-file", default=None, help="Feed de phishing local (uno por línea)")
    ap.add_argument("--tranco-file", default=None, help="CSV/zip de Tranco local")
    ap.add_argument("--phishtank-key", default=None, help="App key de PhishTank (opcional)")
    ap.add_argument(
        "--n-legit",
        type=int,
        default=None,
        help="Cuántas legítimas agregar (por defecto: tantas como phishing nuevo, balanceado)",
    )
    ap.add_argument("--tranco-top", type=int, default=100_000)
    ap.add_argument("--allowlist-top", type=int, default=10_000)
    ap.add_argument("--allowlist-out", default="models/allowlist_top.json")
    ap.add_argument("--seed", type=int, default=RANDOM_SEED)
    args = ap.parse_args()

    hoy = args.fecha or date.today().isoformat()

    # --- Phishing nuevo ---
    phishing = leer_openphish(args.phishing_file) + leer_phishtank(args.phishtank_key)
    print(f"Phishing descargado: {len(phishing):,} URLs")

    # --- Dominios populares (legítimas + allowlist) ---
    tranco = leer_tranco(args.tranco_file, args.tranco_top)
    top1000 = set(tranco[:1000])
    print(f"Tranco leído: {len(tranco):,} dominios")

    # Etiqueta contradictoria: phishing alojado en dominios top-1000
    # (p. ej. servicios de hosting/forms legítimos) -> se descarta
    antes = len(phishing)
    phishing = [u for u in phishing if C.dominio(u) not in top1000]
    print(f"Descartadas por host en top-1000 Tranco: {antes - len(phishing):,}")

    df_ph = pd.DataFrame({"url": phishing, "label": 1, "fecha": hoy, "fuente": "feed_phishing"})

    # --- Legítimas nuevas (muestreo de Tranco, sin repetir dominios de phishing) ---
    dom_ph = {C.dominio(u) for u in phishing}
    base = C.cargar(args.corpus)
    ya = set(base["url"])
    candidatas = [f"https://{d}/" for d in tranco if d not in dom_ph]
    candidatas = [u for u in candidatas if C.normalizar_url(u) not in ya]
    n_legit = args.n_legit if args.n_legit is not None else len(df_ph)
    n_legit = min(n_legit, len(candidatas))
    if n_legit > 0:
        rng = pd.Series(candidatas).sample(n=n_legit, random_state=args.seed)
        df_lg = pd.DataFrame({"url": rng.tolist(), "label": 0, "fecha": hoy, "fuente": "tranco"})
    else:
        df_lg = pd.DataFrame(columns=C.COLUMNAS)

    nuevas = pd.concat([df_ph, df_lg], ignore_index=True)
    agregadas, dup = C.agregar(args.corpus, nuevas)
    print(f"Corpus {args.corpus}: +{agregadas:,} URLs nuevas ({dup:,} ya existían) con fecha {hoy}")

    # --- Allowlist para la extensión ---
    out = Path(args.allowlist_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "fecha": hoy,
                "fuente": "Tranco",
                "aviso": "Coincidencia EXACTA de host; no aplica a subdominios (hosting de terceros).",
                "dominios": tranco[: args.allowlist_top],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"Allowlist ({min(args.allowlist_top, len(tranco)):,} dominios) -> {out}")


if __name__ == "__main__":
    main()
