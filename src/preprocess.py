"""
preprocess.py
-------------
Preprocesamiento de URLs para la CNN a nivel de caracteres (arquitectura
elegida en la Matriz de decisión de la Práctica 3: extensión local,
sin backend, prioriza latencia y tamaño de modelo sobre comprensión
semántica profunda).

Pasos:
  1. Normalizar URLs (src/normalize.py: minúsculas, sin esquema, sin 'www.', sin '/' final).
  2. Construir un vocabulario a nivel de carácter (alfabeto de URL:
     letras, dígitos y símbolos típicos: :/?.#[]@!$&'()*+,;=-_~%).
  3. Convertir cada URL en una secuencia de enteros (tokenización por
     carácter) con padding/truncado a una longitud fija.
  4. Split estratificado 70/10/20 (train/val/test) con semilla fija,
     tal como especifica la Ficha Técnica de la Práctica 1.

Uso:
    python src/preprocess.py --in data/raw/dataset_unificado.csv \
                              --outdir data/processed --maxlen 200
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

sys.path.insert(0, str(Path(__file__).resolve().parent))
from normalize import MODOS, normalizar_url  # noqa: E402

RANDOM_SEED = 42

# Alfabeto de caracteres esperables en una URL (RFC 3986 + acentos/ñ
# ocasionales en dominios internacionalizados). Índice 0 reservado para
# PAD, último índice para OOV (cualquier carácter fuera del alfabeto).
ALFABETO = list("abcdefghijklmnopqrstuvwxyz0123456789:/?.#[]@!$&'()*+,;=-_~%")
PAD_IDX = 0
OOV_IDX = len(ALFABETO) + 1  # después de PAD y de todo el alfabeto


def construir_vocabulario() -> dict:
    """char -> índice, con 0=PAD reservado y el último índice=OOV."""
    vocab = {ch: i + 1 for i, ch in enumerate(ALFABETO)}
    return vocab


def tokenizar_url(url: str, vocab: dict, maxlen: int, modo: str = "completa") -> list[int]:
    # Normalización compartida con la extensión: sin esquema, sin "www.", sin "/" final
    url = normalizar_url(url, modo)
    ids = [vocab.get(ch, OOV_IDX) for ch in url[:maxlen]]
    if len(ids) < maxlen:
        ids = ids + [PAD_IDX] * (maxlen - len(ids))
    return ids


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in", dest="in_path", type=str, default="data/raw/dataset_unificado.csv")
    parser.add_argument("--outdir", type=str, default="data/processed")
    parser.add_argument(
        "--maxlen", type=int, default=200, help="Longitud fija de secuencia (percentil ~95 de longitud de URL)"
    )
    parser.add_argument("--seed", type=int, default=RANDOM_SEED)
    parser.add_argument(
        "--ruta-modo",
        choices=list(MODOS),
        default="completa",
        help="completa = URL sin esquema/www (recomendado). "
        "solo_host = solo el host; usar si las legitimas del corpus no traen rutas.",
    )
    parser.add_argument(
        "--split-mode",
        choices=["aleatorio", "temporal"],
        default="aleatorio",
        help="aleatorio = 70/10/20 estratificado (Ficha Tecnica PRACT1). "
        "temporal = test con las URLs MAS RECIENTES (fecha >= --cutoff), "
        "mide si el modelo detecta phishing futuro; requiere columna 'fecha'.",
    )
    parser.add_argument(
        "--cutoff",
        type=str,
        default=None,
        help="Fecha YYYY-MM-DD: fecha >= cutoff va a TEST (solo --split-mode temporal)",
    )
    parser.add_argument(
        "--val-frac",
        type=float,
        default=0.10,
        help="Fraccion del total para validacion en modo temporal (se saca del pasado)",
    )
    args = parser.parse_args()

    df = pd.read_csv(args.in_path)
    if not {"url", "label"}.issubset(df.columns):
        raise ValueError("El CSV debe tener columnas 'url' y 'label'")
    df = df.dropna(subset=["url", "label"]).reset_index(drop=True)

    print(f"URLs cargadas: {len(df):,}")
    print(
        f"Longitud de URL — percentiles: "
        f"p50={df['url'].str.len().quantile(0.50):.0f}, "
        f"p95={df['url'].str.len().quantile(0.95):.0f}, "
        f"p99={df['url'].str.len().quantile(0.99):.0f}"
    )

    vocab = construir_vocabulario()

    if args.split_mode == "temporal":
        if "fecha" not in df.columns:
            raise ValueError("El split temporal requiere la columna 'fecha' en el CSV")
        if not args.cutoff:
            raise ValueError("El split temporal requiere --cutoff YYYY-MM-DD")
        test_df = df[df["fecha"] >= args.cutoff]
        pasado = df[df["fecha"] < args.cutoff]
        if len(test_df) == 0 or len(pasado) == 0:
            raise SystemExit(
                f"Split temporal vacio con cutoff={args.cutoff}: "
                f"pasado={len(pasado)}, test={len(test_df)}. Ajusta --cutoff."
            )
        if test_df["label"].nunique() < 2:
            raise SystemExit(
                "El conjunto de test temporal tiene una sola clase; "
                "agrega URLs legitimas recientes (fetch_feeds.py) antes de reentrenar."
            )
        # Validacion = muestra estratificada del PASADO (nunca del futuro)
        val_frac_pasado = min(0.5, args.val_frac * len(df) / len(pasado))
        train_df, val_df = train_test_split(
            pasado, test_size=val_frac_pasado, stratify=pasado["label"], random_state=args.seed
        )
        print(f"Split TEMPORAL (cutoff={args.cutoff}): test = URLs desde esa fecha")
    else:
        # Split 70/10/20 estratificado por clase (Ficha Tecnica PRACT1)
        train_df, temp_df = train_test_split(df, test_size=0.30, stratify=df["label"], random_state=args.seed)
        val_df, test_df = train_test_split(temp_df, test_size=2 / 3, stratify=temp_df["label"], random_state=args.seed)
        # 0.30 * (2/3) = 0.20 del total -> test; 0.30 * (1/3) = 0.10 -> val

    print(
        f"Split -> train: {len(train_df):,} ({len(train_df) / len(df):.1%}) | "
        f"val: {len(val_df):,} ({len(val_df) / len(df):.1%}) | "
        f"test: {len(test_df):,} ({len(test_df) / len(df):.1%})"
    )

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    for nombre, split_df in [("train", train_df), ("val", val_df), ("test", test_df)]:
        X = np.array([tokenizar_url(u, vocab, args.maxlen, args.ruta_modo) for u in split_df["url"]], dtype=np.int32)
        y = split_df["label"].to_numpy(dtype=np.int32)
        np.savez_compressed(outdir / f"{nombre}.npz", X=X, y=y)
        split_df[[c for c in ["url", "label", "fuente"] if c in split_df.columns]].to_csv(
            outdir / f"{nombre}_urls.csv", index=False
        )
        print(f"  Guardado {nombre}: X{X.shape}, y{y.shape} -> {outdir / f'{nombre}.npz'}")

    # Guardar vocabulario y metadatos (necesarios para inferencia y para
    # reconstruir el preprocesamiento en la extensión de navegador / ONNX)
    meta = {
        "vocab": vocab,
        "pad_idx": PAD_IDX,
        "oov_idx": OOV_IDX,
        "maxlen": args.maxlen,
        "vocab_size": len(ALFABETO) + 2,  # + PAD + OOV
        "label_convention": {"0": "legitima", "1": "phishing"},
        "normalizacion": {
            "version": 2,
            "modo": args.ruta_modo,
            "reglas": ["minusculas", "sin_fragmento", "sin_esquema", "sin_www", "sin_barra_final"],
        },
        "split_mode": args.split_mode,
        "cutoff": args.cutoff,
    }
    with open(outdir / "vocab_meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(
        f"\nMetadatos de vocabulario guardados en {outdir / 'vocab_meta.json'} "
        f"(vocab_size={meta['vocab_size']}, maxlen={args.maxlen})"
    )


if __name__ == "__main__":
    main()
