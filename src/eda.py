"""
eda.py
------
Análisis exploratorio del dataset ANTES de entrenar (evidencia para el informe
y control de calidad de los datos).

Qué revisa y por qué:
  - Balance de clases (RNF6: >= 80,000 URLs balanceadas).
  - Duplicados exactos y casi duplicados (misma URL sin esquema ni "www.").
    Los casi duplicados inflan las métricas en una partición aleatoria.
  - Distribución de longitud (justifica maxlen = 200).
  - "Atajos": rasgos superficiales que podrían delatar la clase sin que el modelo
    aprenda phishing de verdad (esquema http/https, prefijo www., URL con ruta,
    host numérico). Si una clase casi siempre los tiene y la otra no, el modelo
    puede apoyarse en ellos y fallar con datos reales.

Salida: evidencias/eda_resumen.json, evidencias/eda_longitud.png,
        evidencias/eda_atajos.png

Uso:
    python src/eda.py --in data/raw/dataset_unificado.csv --out evidencias
"""

import argparse
import json
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

NAVY, BLUE, GRAY = "#1F3864", "#4472C4", "#7F7F7F"
RE_IP = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")


def partes(url: str):
    u = str(url).strip()
    m = re.match(r"^([a-zA-Z][a-zA-Z0-9+.-]*)://(.*)$", u)
    esquema, resto = (m.group(1).lower(), m.group(2)) if m else ("", u)
    host = re.split(r"[/?#]", resto, maxsplit=1)[0].lower()
    ruta = resto[len(host) :]
    return esquema, host, ruta


def rasgos(df: pd.DataFrame) -> pd.DataFrame:
    p = df["url"].map(partes)
    out = pd.DataFrame(
        {
            "label": df["label"].values,
            "largo": df["url"].astype(str).str.len().values,
            "https": [x[0] == "https" for x in p],
            "http": [x[0] == "http" for x in p],
            "www": [x[1].startswith("www.") for x in p],
            "con_ruta": [len(x[2].strip("/")) > 0 for x in p],
            "con_query": ["?" in str(u) for u in df["url"]],
            "host_ip": [bool(RE_IP.match(x[1].split(":")[0])) for x in p],
            "n_puntos_host": [x[1].count(".") for x in p],
        }
    )
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="inp", default="data/raw/dataset_unificado.csv")
    ap.add_argument("--out", default="evidencias")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(a.inp).dropna(subset=["url", "label"]).reset_index(drop=True)
    r = rasgos(df)
    n = len(df)
    n1 = int((df.label == 1).sum())
    n0 = n - n1
    resumen = {"n_total": n, "n_phishing": n1, "n_legitimas": n0, "balance_phishing_pct": round(100 * n1 / n, 2)}

    # Duplicados
    resumen["duplicados_exactos"] = int(df.duplicated(subset="url").sum())
    norm = (
        df["url"]
        .astype(str)
        .str.lower()
        .str.replace(r"^[a-z]+://", "", regex=True)
        .str.replace(r"^www\.", "", regex=True)
        .str.rstrip("/")
    )
    resumen["casi_duplicados_sin_esquema_ni_www"] = int(norm.duplicated().sum())
    # Mismo host en muchas URLs (riesgo de fuga entre train y test)
    hosts = pd.Series([partes(u)[1] for u in df["url"]])
    resumen["hosts_distintos"] = int(hosts.nunique())
    resumen["urls_en_hosts_repetidos_pct"] = round(100 * float(hosts.duplicated(keep=False).mean()), 2)

    # Longitud
    lg = {}
    for c, nombre in [(1, "phishing"), (0, "legitimas")]:
        s = r.loc[r.label == c, "largo"]
        lg[nombre] = {
            "media": round(float(s.mean()), 1),
            "p50": float(s.quantile(0.5)),
            "p95": float(s.quantile(0.95)),
            "p99": float(s.quantile(0.99)),
            "max": int(s.max()),
        }
    resumen["longitud"] = lg
    resumen["pct_urls_mayores_a_200"] = round(100 * float((r.largo > 200).mean()), 2)

    # Atajos
    atajos = {}
    for col in ["https", "http", "www", "con_ruta", "con_query", "host_ip"]:
        p1 = float(r.loc[r.label == 1, col].mean())
        p0 = float(r.loc[r.label == 0, col].mean())
        atajos[col] = {
            "phishing_pct": round(100 * p1, 1),
            "legitimas_pct": round(100 * p0, 1),
            "diferencia_pp": round(100 * (p1 - p0), 1),
            "alerta": bool(abs(p1 - p0) >= (0.20 if col in ("con_ruta", "con_query") else 0.30)),
        }
    resumen["atajos_posibles"] = atajos
    resumen["columnas_con_alerta"] = [k for k, v in atajos.items() if v["alerta"]]
    (out / "eda_resumen.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")

    # Figura 1: longitud
    fig, ax = plt.subplots(figsize=(8, 4.2), dpi=200)
    tope = 300
    ax.hist(r.loc[r.label == 0, "largo"].clip(upper=tope), bins=60, alpha=0.7, color=BLUE, label="Legítimas")
    ax.hist(r.loc[r.label == 1, "largo"].clip(upper=tope), bins=60, alpha=0.6, color=NAVY, label="Phishing")
    ax.axvline(200, color="#C00000", ls="--", lw=1.4, label="maxlen = 200")
    ax.set_xlabel("Largo de la URL (caracteres; valores > 300 agrupados)")
    ax.set_ylabel("Cantidad de URLs")
    ax.set_title("Distribución del largo de URL por clase", color=NAVY, fontweight="bold")
    ax.legend(frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out / "eda_longitud.png")
    plt.close(fig)

    # Figura 2: atajos
    cols = ["https", "http", "www", "con_ruta", "con_query", "host_ip"]
    nombres = ["usa https", "usa http", "empieza con www.", "tiene ruta", "tiene ?query", "host = IP"]
    x = np.arange(len(cols))
    w = 0.38
    fig, ax = plt.subplots(figsize=(9, 4.4), dpi=200)
    ax.bar(x - w / 2, [atajos[c]["legitimas_pct"] for c in cols], w, color=BLUE, label="Legítimas")
    ax.bar(x + w / 2, [atajos[c]["phishing_pct"] for c in cols], w, color=NAVY, label="Phishing")
    ax.set_xticks(x)
    ax.set_xticklabels(nombres, fontsize=8)
    ax.set_ylabel("% de URLs de la clase")
    ax.set_title("Rasgos superficiales por clase (posibles atajos)", color=NAVY, fontweight="bold")
    ax.legend(frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_ylim(0, 105)
    fig.tight_layout()
    fig.savefig(out / "eda_atajos.png")
    plt.close(fig)

    print(f"URLs: {n:,} | phishing {n1:,} ({100 * n1 / n:.1f}%) | legítimas {n0:,}")
    print(
        f"Duplicados exactos: {resumen['duplicados_exactos']:,} | casi duplicados: {resumen['casi_duplicados_sin_esquema_ni_www']:,}"  # noqa: E501 (mensaje de consola)
    )
    print(
        f"URLs en hosts que se repiten: {resumen['urls_en_hosts_repetidos_pct']}%  (hosts distintos: {resumen['hosts_distintos']:,})"  # noqa: E501 (mensaje de consola)
    )
    print(
        f"Largo p95 phishing={lg['phishing']['p95']:.0f} | legítimas={lg['legitimas']['p95']:.0f} | URLs > 200: {resumen['pct_urls_mayores_a_200']}%"  # noqa: E501 (mensaje de consola)
    )
    print("\nPosibles atajos (% de cada clase):")
    for k, v in atajos.items():
        marca = "  <-- ALERTA" if v["alerta"] else ""
        print(f"  {k:10s} phishing {v['phishing_pct']:5.1f}% | legítimas {v['legitimas_pct']:5.1f}%{marca}")
    if resumen["columnas_con_alerta"]:
        print(
            "\nATENCIÓN: hay rasgos superficiales muy desbalanceados entre clases. El modelo podría usarlos como "
            "atajo; la prueba de robustez de evaluate.py lo mide quitándolos del test."
        )
    print(f"\nGuardado en {out}/")


if __name__ == "__main__":
    main()
