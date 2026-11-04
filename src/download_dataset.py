"""
download_dataset.py
--------------------
Descarga y unifica el dataset de URLs de phishing/legítimas para el proyecto
"Sistema Predictivo Basado en Deep Learning para la Detección de Phishing
en Usuarios Digitales de Arequipa" (Keny Russell Guerra Huanaco, UCSM).

Fuente principal: PhiUSIIL Phishing URL Dataset (UCI Machine Learning
Repository, ID 967) — 235,795 URLs reales (134,850 legítimas + 100,945
phishing), recolectadas y verificadas por Prasad & Chandra (2023/2024).
Es un dataset público, citable académicamente y de acceso directo sin
necesidad de credenciales (a diferencia del feed de PhishTank, que hoy
exige registro, o de Kaggle, que exige un token de API).

Fuente secundaria opcional: si tienes credenciales de Kaggle
(~/.kaggle/kaggle.json), el script puede además incorporar el dataset
"Malicious URLs dataset" (sid321axn) para robustecer la muestra con URLs
de otra procedencia, tal como especifica RF8 / OE2 (dataset unificado de
múltiples fuentes).

IMPORTANTE: este script está pensado para ejecutarse en un entorno CON
acceso a internet (Google Colab, Kaggle Notebooks, o tu propia máquina).
El sandbox donde se preparó este proyecto no tiene salida a internet
general, así que no pudo descargar el dataset real aquí; el pipeline fue
validado con datos sintéticos (ver notebooks/00_smoke_test.py).

Uso:
    python src/download_dataset.py --n-total 80000 --out data/raw/dataset_unificado.csv
"""

import argparse
from pathlib import Path

import pandas as pd

RANDOM_SEED = 42

# Convención de etiquetas del proyecto (documentada en el Capítulo 1 / RF1-RF4):
#   1 = phishing
#   0 = legítima
LABEL_PHISHING = 1
LABEL_LEGIT = 0


def cargar_phiusiil() -> pd.DataFrame:
    """Descarga PhiUSIIL desde UCI vía el paquete `ucimlrepo` y normaliza
    columnas a (url, label) con la convención del proyecto.

    PhiUSIIL usa la convención inversa (1=legítima, 0=phishing) en su
    columna `label`, por lo que se invierte aquí.
    """
    try:
        from ucimlrepo import fetch_ucirepo
    except ImportError as exc:
        raise SystemExit("Falta el paquete 'ucimlrepo'. Instálalo con: pip install ucimlrepo") from exc

    print("Descargando PhiUSIIL Phishing URL Dataset (UCI ID 967)...")
    dataset = fetch_ucirepo(id=967)
    X = dataset.data.features
    y = dataset.data.targets

    df = pd.DataFrame(
        {
            "url": X["URL"],
            "label_uci": y.iloc[:, 0].astype(int),
        }
    )
    # Invertir convención: en PhiUSIIL 1=legítima, 0=phishing
    df["label"] = df["label_uci"].map({1: LABEL_LEGIT, 0: LABEL_PHISHING})
    df = df.drop(columns=["label_uci"])
    df["fuente"] = "PhiUSIIL_UCI"
    print(
        f"  -> {len(df):,} URLs cargadas "
        f"({(df['label'] == LABEL_PHISHING).sum():,} phishing, "
        f"{(df['label'] == LABEL_LEGIT).sum():,} legítimas)"
    )
    return df


def cargar_kaggle_malicious_urls(csv_path: str) -> pd.DataFrame:
    """Carga el dataset 'Malicious URLs dataset' (sid321axn, Kaggle) si el
    usuario lo descargó manualmente (o vía `kaggle datasets download`).

    Ese dataset trae 4 clases (benign, defacement, phishing, malware); aquí
    se colapsan a la convención binaria del proyecto: phishing=1,
    todo lo demás (benign/defacement/malware) se descarta salvo 'benign',
    que se usa como legítima=0. defacement/malware quedan fuera del alcance
    (el proyecto solo distingue phishing vs. legítima, ver Alcance PRACT1).
    """
    path = Path(csv_path)
    if not path.exists():
        print(f"  (opcional) No se encontró {csv_path}; se omite la fuente Kaggle.")
        return pd.DataFrame(columns=["url", "label", "fuente"])

    raw = pd.read_csv(path)
    raw.columns = [c.strip().lower() for c in raw.columns]
    if "url" not in raw.columns or "type" not in raw.columns:
        print(f"  (opcional) {csv_path} no tiene columnas 'url'/'type' esperadas; se omite.")
        return pd.DataFrame(columns=["url", "label", "fuente"])

    df = raw[raw["type"].isin(["phishing", "benign"])].copy()
    df["label"] = df["type"].map({"phishing": LABEL_PHISHING, "benign": LABEL_LEGIT})
    df = df[["url", "label"]]
    df["fuente"] = "Kaggle_MaliciousURLs"
    print(f"  -> {len(df):,} URLs adicionales cargadas desde Kaggle")
    return df


def leer_lista_tranco(archivo: str | None, hasta: int) -> pd.DataFrame:
    """Lista Tranco (rank, dominio) hasta el ranking 'hasta'."""
    import io
    import zipfile
    from urllib.request import Request, urlopen

    if archivo:
        raw = Path(archivo).read_bytes()
    else:
        req = Request("https://tranco-list.eu/top-1m.csv.zip", headers={"User-Agent": "phishing-detector-pfc-ucsm/1.0"})
        raw = urlopen(req, timeout=180).read()  # nosec B310 # URL https fija (Tranco)
    if raw[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            raw = z.read(z.namelist()[0])
    tr = pd.read_csv(io.BytesIO(raw), header=None, names=["rank", "dominio"], nrows=hasta)
    tr["dominio"] = tr["dominio"].astype(str).str.strip().str.lower()
    return tr


def host_de(url: str) -> str:
    """Host sin 'www.' ni puerto/credenciales (para comparar con Tranco)."""
    u = str(url).strip().lower().split("#", 1)[0].split("://", 1)[-1]
    h = u.split("/", 1)[0].split("?", 1)[0].rsplit("@", 1)[-1].split(":", 1)[0].strip(".")
    return h[4:] if h.startswith("www.") else h


def limpiar_contradictorios(df: pd.DataFrame, top: set) -> pd.DataFrame:
    """Quita URLs etiquetadas PHISHING cuyo host esta en el top de Tranco (youtube.com, nytimes.com...).
    El dataset de Kaggle trae algunas asi (etiqueta contradictoria). Solo host EXACTO: los subdominios de
    hosting (pages.dev, github.io, blogspot) se conservan porque ahi si hay phishing real."""
    malas = (df["label"] == LABEL_PHISHING) & df["url"].map(host_de).isin(top)
    print(
        f"Limpieza: {int(malas.sum()):,} URLs phishing con host en el top de Tranco descartadas (etiqueta contradictoria)"  # noqa: E501 (mensaje de consola)
    )
    return df[~malas].reset_index(drop=True)


def cargar_tranco(
    n: int, desde: int, hasta: int, archivo: str | None, seed: int, lista: pd.DataFrame | None = None
) -> pd.DataFrame:
    """Legitimas de Tranco (https://dominio) tomadas al azar del rango de ranking
    [desde, hasta). Aporta dominios de infraestructura/regionales que PhiUSIIL casi no
    trae (msedge.net, olx.pl, ...) -> baja los falsos positivos de la prueba externa.
    Solo son dominios: usar con --ruta-modo solo_host (si no, refuerzan 'ruta = phishing')."""
    tr = lista if lista is not None else leer_lista_tranco(archivo, hasta)
    tr = tr.iloc[desde:hasta]
    tr = tr.sample(n=min(n, len(tr)), random_state=seed)
    df = pd.DataFrame({"url": "https://" + tr["dominio"].astype(str).str.strip().str.lower(), "label": LABEL_LEGIT})
    df["fuente"] = "Tranco"
    print(f"  -> {len(df):,} legitimas Tranco (ranking {desde:,}-{hasta:,})")
    return df


def tiene_ruta(url: str) -> bool:
    """True si la URL trae ruta o query (más allá del dominio)."""
    u = str(url).strip().lower().split("#", 1)[0]
    u = u.split("://", 1)[-1]
    return len(u.split("/", 1)[1].strip("/")) > 0 if "/" in u else "?" in u


def cargar_csv_generico(path: str, etiqueta: int | None) -> pd.DataFrame:
    """CSV propio con columna 'url' (y 'label' si etiqueta=None). Sirve para
    sumar legítimas con ruta de otra procedencia (p. ej. URLs de navegación
    de uso normal, o cualquier lista pública que consigas)."""
    p = Path(path)
    if not p.exists():
        raise SystemExit(f"No existe {path}")
    raw = pd.read_csv(p)
    raw.columns = [c.strip().lower() for c in raw.columns]
    df = pd.DataFrame({"url": raw["url"].astype(str)})
    df["label"] = raw["label"].astype(int) if etiqueta is None else etiqueta
    df["fuente"] = f"extra_{p.stem}"
    print(f"  -> {len(df):,} URLs extra desde {path}")
    return df


def descargar_kaggle_malicious(dest: str) -> None:
    """Intenta bajar 'Malicious URLs dataset' con la CLI de Kaggle (requiere
    ~/.kaggle/kaggle.json). Si falla, descárgalo a mano y pasa --kaggle-csv."""
    import subprocess  # nosec B404 # se invoca con lista fija de argumentos, sin shell

    d = Path(dest).parent
    d.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(  # nosec B603 B607 # comando fijo "kaggle", sin shell
        ["kaggle", "datasets", "download", "-d", "sid321axn/malicious-urls-dataset", "-p", str(d), "--unzip"],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        print("  No se pudo descargar de Kaggle:", (r.stderr or r.stdout).strip()[:300])
        return
    for f in d.glob("*.csv"):
        if "malicious" in f.name.lower() and f.name != Path(dest).name:
            f.rename(dest)
            break
    print("  Kaggle descargado ->", dest)


def unificar_y_balancear(
    dfs: list[pd.DataFrame],
    n_total: int,
    seed: int = RANDOM_SEED,
    pct_legit_con_ruta: float = 0.0,
    pct_legit_tranco: float = 0.0,
) -> pd.DataFrame:
    """Une las fuentes, elimina duplicados por URL, y muestrea un
    subconjunto balanceado 50/50 de tamaño n_total (RNF6: mínimo 80,000
    URLs balanceadas)."""
    df = pd.concat(dfs, ignore_index=True)
    antes = len(df)
    df = df.drop_duplicates(subset="url").reset_index(drop=True)
    print(f"Unificado: {antes:,} filas -> {len(df):,} tras eliminar duplicados por URL")

    n_por_clase = n_total // 2
    phishing = df[df["label"] == LABEL_PHISHING]
    legit = df[df["label"] == LABEL_LEGIT]

    if len(phishing) < n_por_clase or len(legit) < n_por_clase:
        disponibles = min(len(phishing), len(legit))
        print(
            f"AVISO: no hay suficientes URLs para {n_total:,} balanceadas; "
            f"se usará el máximo balanceado disponible: {disponibles * 2:,}"
        )
        n_por_clase = disponibles

    phishing_sample = phishing.sample(n=n_por_clase, random_state=seed)
    legit_tranco = pd.DataFrame(columns=legit.columns)
    if pct_legit_tranco > 0:
        # Garantiza una proporcion de legitimas de Tranco (diversidad de dominios)
        es_tr = legit["fuente"] == "Tranco"
        n_tr = min(int(round(n_por_clase * pct_legit_tranco / 100)), int(es_tr.sum()))
        legit_tranco = legit[es_tr].sample(n=n_tr, random_state=seed)
        legit = legit[~es_tr]
        n_por_clase_resto = n_por_clase - n_tr
        print(f"Legitimas Tranco en la muestra: {n_tr:,} ({100 * n_tr / n_por_clase:.1f} %)")
    else:
        n_por_clase_resto = n_por_clase
    if pct_legit_con_ruta > 0:
        # Corrige el sesgo "legitima = dominio corto sin ruta": fuerza una proporcion
        # de legitimas CON ruta parecida a la de phishing (EDA: ~28 %).
        con = legit[legit["url"].map(tiene_ruta)]
        sin = legit[~legit["url"].map(tiene_ruta)]
        n_con = min(int(round(n_por_clase_resto * pct_legit_con_ruta / 100)), len(con))
        if n_con < int(round(n_por_clase_resto * pct_legit_con_ruta / 100)):
            print(
                f"AVISO: solo hay {len(con):,} legitimas con ruta (pedidas "
                f"{int(round(n_por_clase_resto * pct_legit_con_ruta / 100)):,}). Consigue mas fuentes (--kaggle-csv / --extra-legit-csv)."  # noqa: E501 (mensaje de consola)
            )
        legit_sample = pd.concat(
            [con.sample(n=n_con, random_state=seed), sin.sample(n=n_por_clase_resto - n_con, random_state=seed)]
        )
        print(f"Legitimas con ruta en la muestra: {n_con:,} ({100 * n_con / n_por_clase_resto:.1f} %)")
    else:
        legit_sample = legit.sample(n=n_por_clase_resto, random_state=seed)

    legit_sample = pd.concat([legit_sample, legit_tranco])

    balanced = pd.concat([phishing_sample, legit_sample], ignore_index=True)
    balanced = balanced.sample(frac=1, random_state=seed).reset_index(drop=True)  # shuffle
    print(f"Dataset balanceado final: {len(balanced):,} URLs ({n_por_clase:,} phishing + {n_por_clase:,} legítimas)")
    return balanced


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--n-total", type=int, default=80_000, help="Tamaño total del dataset balanceado (RNF6: mínimo 80,000)"
    )
    parser.add_argument("--out", type=str, default="data/raw/dataset_unificado.csv")
    parser.add_argument(
        "--kaggle-csv",
        type=str,
        default="data/raw/malicious_urls_kaggle.csv",
        help="Ruta opcional al CSV de Kaggle ya descargado manualmente",
    )
    parser.add_argument("--seed", type=int, default=RANDOM_SEED)
    parser.add_argument(
        "--descargar-kaggle",
        action="store_true",
        help="Intenta bajar Malicious URLs dataset con la CLI de Kaggle (necesita kaggle.json)",
    )
    parser.add_argument(
        "--extra-legit-csv",
        type=str,
        default=None,
        help="CSV con columna 'url' de legitimas con ruta (otra procedencia)",
    )
    parser.add_argument(
        "--pct-legit-con-ruta",
        type=float,
        default=0.0,
        help="Porcentaje de legitimas CON ruta en la muestra final (recomendado: 25-30)",
    )
    parser.add_argument(
        "--pct-legit-tranco",
        type=float,
        default=0.0,
        help="Porcentaje de legitimas de Tranco en la muestra (recomendado: 30, con --ruta-modo solo_host)",
    )
    parser.add_argument(
        "--tranco-rango",
        type=int,
        nargs=2,
        default=[1000, 50000],
        metavar=("DESDE", "HASTA"),
        help="Rango de ranking Tranco para ENTRENAR (la prueba externa usa otro: 50000-100000)",
    )
    parser.add_argument(
        "--limpiar-top",
        type=int,
        default=0,
        help="Descarta phishing cuyo host esta en el top-N de Tranco (recomendado: 5000)",
    )
    parser.add_argument("--tranco-file", type=str, default=None, help="Tranco local (pruebas offline)")
    args = parser.parse_args()

    if args.descargar_kaggle:
        descargar_kaggle_malicious(args.kaggle_csv)
    fuentes = [cargar_phiusiil()]
    lista_tr = None
    if args.pct_legit_tranco > 0 or args.limpiar_top > 0:
        lista_tr = leer_lista_tranco(args.tranco_file, max(args.tranco_rango[1], args.limpiar_top))
    if args.pct_legit_tranco > 0:
        fuentes.append(
            cargar_tranco(
                int(args.n_total * args.pct_legit_tranco / 100) * 2,
                args.tranco_rango[0],
                args.tranco_rango[1],
                args.tranco_file,
                args.seed,
                lista=lista_tr,
            )
        )
    if args.extra_legit_csv:
        fuentes.append(cargar_csv_generico(args.extra_legit_csv, LABEL_LEGIT))
    kaggle_df = cargar_kaggle_malicious_urls(args.kaggle_csv)
    if len(kaggle_df) > 0:
        fuentes.append(kaggle_df)

    if args.limpiar_top > 0:
        top = set(lista_tr.iloc[: args.limpiar_top]["dominio"])
        fuentes = [limpiar_contradictorios(f, top) for f in fuentes]
    balanced = unificar_y_balancear(
        fuentes,
        n_total=args.n_total,
        seed=args.seed,
        pct_legit_con_ruta=args.pct_legit_con_ruta,
        pct_legit_tranco=args.pct_legit_tranco,
    )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    balanced.to_csv(out_path, index=False)
    print(f"\nGuardado: {out_path} ({len(balanced):,} filas)")


if __name__ == "__main__":
    main()
