"""
construir_externo.py
--------------------
Arma el CSV de PRUEBA EXTERNA (url,label) con datos de otra procedencia que el
entrenamiento (PhiUSIIL): phishing reciente de OpenPhish + legítimas de Tranco
(rango 1.000-100.000) y, opcionalmente, un archivo propio de legítimas con ruta
(--legit-file, una URL por línea). Quita lo que ya está en el corpus de
entrenamiento para que la prueba sea realmente externa.

Requiere internet (Colab). Uso:
    python src/construir_externo.py --train-csv data/raw/dataset_unificado.csv \
        --out data/externo/externo.csv --n 1000
Limitación (declararla en el informe): las legítimas de Tranco son solo dominios,
así que NO miden falsos positivos con ruta; para eso usa --legit-file.
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_feeds import leer_openphish, leer_tranco  # noqa: E402
from normalize import normalizar_url  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--train-csv", default="data/raw/dataset_unificado.csv")
    ap.add_argument("--out", default="data/externo/externo.csv")
    ap.add_argument("--n", type=int, default=1000, help="URLs por clase")
    ap.add_argument("--legit-file", default=None, help="TXT con legítimas con ruta (una por línea)")
    ap.add_argument("--phishing-file", default=None)
    ap.add_argument("--tranco-file", default=None)
    ap.add_argument(
        "--tranco-rango",
        type=int,
        nargs=2,
        default=[50000, 100000],
        metavar=("DESDE", "HASTA"),
        help="Ranking Tranco para la prueba externa; distinto al de entrenamiento (1000-50000)",
    )
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()

    vistos = set(pd.read_csv(a.train_csv)["url"].astype(str).map(normalizar_url))
    ph = [u for u in leer_openphish(a.phishing_file) if normalizar_url(u) not in vistos]
    ph = pd.Series(ph).drop_duplicates()
    ph = ph.sample(min(a.n, len(ph)), random_state=a.seed)

    tr = leer_tranco(a.tranco_file, a.tranco_rango[1])[a.tranco_rango[0] :]
    leg = pd.Series(["https://" + d for d in tr])
    if a.legit_file:
        extra = [ln.strip() for ln in Path(a.legit_file).read_text(encoding="utf-8").splitlines() if ln.strip()]
        leg = pd.concat([pd.Series(extra), leg], ignore_index=True)
    leg = leg[~leg.map(normalizar_url).isin(vistos)].drop_duplicates()
    leg = (
        pd.concat(
            [
                leg.iloc[: len(leg) if not a.legit_file else len(extra)],  # las con ruta primero
                leg.iloc[len(extra) if a.legit_file else 0 :].sample(frac=1, random_state=a.seed),
            ]
        )
        .drop_duplicates()
        .head(a.n)
    )

    df = pd.concat(
        [pd.DataFrame({"url": ph.values, "label": 1}), pd.DataFrame({"url": leg.values, "label": 0})], ignore_index=True
    )
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(a.out, index=False)
    print(
        f"Externo: {len(df):,} URLs ({(df.label == 1).sum():,} phishing, {(df.label == 0).sum():,} legitimas) -> {a.out}"  # noqa: E501 (mensaje de consola)
    )


if __name__ == "__main__":
    main()
