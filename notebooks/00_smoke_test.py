"""
00_smoke_test.py
-----------------
Prueba de humo con datos SINTÉTICOS (no reales) para validar que el
pipeline download->preprocess->train funciona de punta a punta, dado que
el entorno de preparación de este proyecto no tiene acceso a internet
general (solo a PyPI). Ejecuta esto solo como sanity check del código;
el entrenamiento real debe hacerse en Colab con el dataset real
(ver src/download_dataset.py).
"""

import random
import string
from pathlib import Path

import pandas as pd

random.seed(42)

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)


def url_legitima():
    dominios = ["bcp.com.pe", "interbank.pe", "gob.pe", "ucsm.edu.pe", "sunat.gob.pe", "google.com"]
    rutas = ["", "/login", "/index.html", "/productos", "/ayuda", "/es/inicio"]
    return f"https://www.{random.choice(dominios)}{random.choice(rutas)}"


def url_phishing():
    marcas = ["bcp", "interbank", "sunat", "bbva", "scotiabank"]
    trucos = [
        f"http://{random.choice(marcas)}-verificacion.{''.join(random.choices(string.ascii_lowercase, k=6))}.com/login",
        f"http://{random.choice(marcas)}.actualiza-datos.info/{''.join(random.choices(string.ascii_lowercase+string.digits, k=10))}",
        f"http://{''.join(random.choices(string.digits, k=3))}.{''.join(random.choices(string.digits, k=3))}.{''.join(random.choices(string.digits, k=3))}.{''.join(random.choices(string.digits, k=3))}/{random.choice(marcas)}/secure",
    ]
    return random.choice(trucos)


def generar_dataset_sintetico(n_total=2000):
    filas = []
    for _ in range(n_total // 2):
        filas.append({"url": url_legitima(), "label": 0, "fuente": "sintetico_legit"})
        filas.append({"url": url_phishing(), "label": 1, "fuente": "sintetico_phish"})
    df = pd.DataFrame(filas).drop_duplicates(subset="url").reset_index(drop=True)
    return df


if __name__ == "__main__":
    df = generar_dataset_sintetico(2000)
    out = RAW_DIR / "dataset_unificado.csv"
    df.to_csv(out, index=False)
    print(f"Dataset sintético de prueba generado: {out} ({len(df)} filas, "
          f"{(df.label==1).sum()} phishing / {(df.label==0).sum()} legítimas)")
    print("\nEjecuta ahora:")
    print("  python src/preprocess.py --in data/raw/dataset_unificado.csv "
          "--outdir data/processed --maxlen 200")
