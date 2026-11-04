"""
evaluate.py
-----------
Evaluación completa del modelo final sobre el TEST (nunca visto) y prueba de
robustez frente a "atajos" del dataset.

Genera (carpeta evidencias/):
  metricas_test.json, matriz_confusion.png, curva_roc.png, curva_pr.png,
  tabla_umbrales.csv, robustez.json, errores_falsos_negativos.csv,
  errores_falsos_positivos.csv

Honestidad metodológica (v2, tras la Corrección 1): el modelo se entrena con URLs
normalizadas (sin esquema ni "www."), así que esos atajos ya no existen. Aquí se
mide lo que queda: desempeño con/sin ruta, con la ruta quitada, y --externo
(CSV url,label de otra procedencia que el entrenamiento). También sugiere los
dos umbrales (advertencia / bloqueo) elegidos en validación.

Uso:
    python src/evaluate.py --model models/cnn_phishing_final.keras
"""

import argparse
import json
import re
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import tensorflow as tf
from sklearn.metrics import average_precision_score, confusion_matrix, precision_recall_curve, roc_auc_score, roc_curve

sys.path.insert(0, str(Path(__file__).resolve().parent))
from normalize import normalizar_url  # noqa: E402
from preprocess import tokenizar_url  # noqa: E402

NAVY, BLUE = "#1F3864", "#4472C4"


def resumen(y, p, umbral=0.5):
    pred = p >= umbral
    tp = int((pred & (y == 1)).sum())
    fp = int((pred & (y == 0)).sum())
    fn = int((~pred & (y == 1)).sum())
    tn = int((~pred & (y == 0)).sum())
    return {
        "umbral": umbral,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "accuracy": (tp + tn) / max(len(y), 1),
        "precision": tp / max(tp + fp, 1),
        "recall": tp / max(tp + fn, 1),
        "fpr": fp / max(fp + tn, 1),
        "f1": 2 * tp / max(2 * tp + fp + fn, 1),
        "auc_roc": float(roc_auc_score(y, p)),
    }


def variante(url: str, modo: str) -> str:
    u = str(url).strip()
    if modo in ("sin_esquema", "sin_esquema_ni_www", "solo_dominio"):
        u = re.sub(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", "", u)
    if modo in ("sin_esquema_ni_www", "solo_dominio"):
        u = re.sub(r"^www\.", "", u, flags=re.I)
    if modo == "solo_dominio":
        u = re.split(r"[/?#]", u, maxsplit=1)[0]
    return u


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default="models/cnn_phishing_final.keras")
    ap.add_argument("--processed-dir", default="data/processed")
    ap.add_argument("--out", default="evidencias")
    ap.add_argument(
        "--externo",
        default=None,
        help="CSV (url,label) de OTRA procedencia que el entrenamiento, p. ej. OpenPhish reciente + legitimas con ruta",
    )
    ap.add_argument("--recall-objetivo", type=float, default=0.90)
    ap.add_argument("--fpr-bloqueo", type=float, default=0.005)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    pdir = Path(a.processed_dir)

    meta = json.loads((pdir / "vocab_meta.json").read_text(encoding="utf-8"))
    d = np.load(pdir / "test.npz")
    X, y = d["X"], d["y"]
    _tu = pd.read_csv(pdir / "test_urls.csv")
    urls = _tu["url"].astype(str).reset_index(drop=True)
    fuentes_test = _tu["fuente"].astype(str).to_numpy() if "fuente" in _tu.columns else None
    model = tf.keras.models.load_model(a.model)
    p = model.predict(X, verbose=0).ravel()

    m = resumen(y, p, 0.5)
    (out / "metricas_test.json").write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
    print("=== TEST (umbral 0.5) ===")
    for k in ["accuracy", "precision", "recall", "fpr", "f1", "auc_roc"]:
        print(f"  {k:9s}: {m[k]:.4f}")
    print(f"  TP={m['tp']:,} FP={m['fp']:,} FN={m['fn']:,} TN={m['tn']:,}")
    print(f"  RNF2 (recall > 0.85): {'CUMPLE' if m['recall'] > 0.85 else 'NO CUMPLE'}")

    # Matriz de confusión
    cm = confusion_matrix(y, p >= 0.5)
    fig, ax = plt.subplots(figsize=(4.6, 4.2), dpi=200)
    ax.imshow(cm, cmap="Blues")
    for i in range(2):
        for j in range(2):
            ax.text(
                j,
                i,
                f"{cm[i, j]:,}",
                ha="center",
                va="center",
                color="white" if cm[i, j] > cm.max() / 2 else NAVY,
                fontsize=13,
                fontweight="bold",
            )
    ax.set_xticks([0, 1])
    ax.set_yticks([0, 1])
    ax.set_xticklabels(["Legítima", "Phishing"])
    ax.set_yticklabels(["Legítima", "Phishing"])
    ax.set_xlabel("Predicción")
    ax.set_ylabel("Real")
    ax.set_title("Matriz de confusión (test)", color=NAVY, fontweight="bold")
    fig.tight_layout()
    fig.savefig(out / "matriz_confusion.png")
    plt.close(fig)

    # ROC y PR
    fpr, tpr, _ = roc_curve(y, p)
    fig, ax = plt.subplots(figsize=(4.8, 4.2), dpi=200)
    ax.plot(fpr, tpr, color=NAVY, lw=2)
    ax.plot([0, 1], [0, 1], ls="--", color="#999")
    ax.set_xlabel("Tasa de falsos positivos")
    ax.set_ylabel("Recall")
    ax.set_title(f"Curva ROC (AUC = {m['auc_roc']:.4f})", color=NAVY, fontweight="bold")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out / "curva_roc.png")
    plt.close(fig)
    pr, rc, _ = precision_recall_curve(y, p)
    fig, ax = plt.subplots(figsize=(4.8, 4.2), dpi=200)
    ax.plot(rc, pr, color=NAVY, lw=2)
    ax.set_xlabel("Recall")
    ax.set_ylabel("Precisión")
    ax.set_title(
        f"Curva precisión–recall (AP = {average_precision_score(y, p):.4f})", color=NAVY, fontweight="bold", fontsize=10
    )
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out / "curva_pr.png")
    plt.close(fig)

    # Tabla de umbrales
    filas = [resumen(y, p, t) for t in np.round(np.arange(0.05, 1.0, 0.05), 2)]
    pd.DataFrame(filas)[["umbral", "recall", "precision", "fpr", "f1", "fp", "fn"]].round(4).to_csv(
        out / "tabla_umbrales.csv", index=False
    )

    modo_ruta = meta.get("normalizacion", {}).get("modo", "completa")
    print(f"\n(Normalizacion del modelo: {meta.get('normalizacion', 'v1 SIN normalizar (modelo antiguo)')})")

    # --- Atajos que sobreviven a la normalizacion: desempeño por tipo de URL ---
    # Si las legitimas del corpus no traen ruta, el modelo puede aprender "con ruta = phishing".
    # Se mide el FPR/recall por subgrupo y con la ruta quitada (solo_host).
    def con_ruta(u):
        t = normalizar_url(u, "completa")
        return "/" in t or "?" in t

    mask_ruta = np.array([con_ruta(u) for u in urls])
    sub = {}
    for nombre, mk in [("con_ruta", mask_ruta), ("sin_ruta", ~mask_ruta)]:
        yy, pp = y[mk], p[mk]
        sub[nombre] = {
            "n": int(mk.sum()),
            "n_phishing": int((yy == 1).sum()),
            "n_legitimas": int((yy == 0).sum()),
            "recall": float(((pp >= 0.5) & (yy == 1)).sum() / max((yy == 1).sum(), 1)) if (yy == 1).any() else None,
            "fpr": float(((pp >= 0.5) & (yy == 0)).sum() / max((yy == 0).sum(), 1)) if (yy == 0).any() else None,
        }
    por_fuente = {}
    if fuentes_test is not None:
        print("\n=== Desempeño por FUENTE (si una fuente rinde muy distinto, el modelo aprende su 'estilo') ===")
        for f in sorted(set(fuentes_test)):
            mk = fuentes_test == f
            yy, pp = y[mk], p[mk]
            r_ = float(((pp >= 0.5) & (yy == 1)).sum() / max((yy == 1).sum(), 1)) if (yy == 1).any() else None
            f_ = float(((pp >= 0.5) & (yy == 0)).sum() / max((yy == 0).sum(), 1)) if (yy == 0).any() else None
            por_fuente[f] = {
                "n": int(mk.sum()),
                "n_phishing": int((yy == 1).sum()),
                "n_legitimas": int((yy == 0).sum()),
                "recall": r_,
                "fpr": f_,
            }
            print(
                f"  {f:22s} n={int(mk.sum()):>6,} phishing={int((yy == 1).sum()):>5,} legit={int((yy == 0).sum()):>5,}  "  # noqa: E501 (mensaje de consola)
                f"recall={'n/a' if r_ is None else f'{r_:.3f}'}  FPR={'n/a' if f_ is None else f'{f_:.3f}'}"
            )
    Xh = np.array([tokenizar_url(u, meta["vocab"], meta["maxlen"], "solo_host") for u in urls], dtype=np.int32)
    ph = model.predict(Xh, verbose=0).ravel()
    mh = resumen(y, ph, 0.5)
    rob = {
        "original": {k: m[k] for k in ["recall", "fpr", "precision", "auc_roc"]},
        "solo_host_(sin_ruta)": {k: mh[k] for k in ["recall", "fpr", "precision", "auc_roc"]},
        "por_subgrupo": sub,
        "por_fuente": por_fuente,
    }
    print("\n=== Atajos tras normalizar: desempeño por tipo de URL ===")
    for nombre, v in sub.items():
        r_ = "n/a" if v["recall"] is None else f"{v['recall']:.4f}"
        f_ = "n/a" if v["fpr"] is None else f"{v['fpr']:.4f}"
        print(
            f"  {nombre:9s} n={v['n']:>6,} (phishing={v['n_phishing']:,}, legitimas={v['n_legitimas']:,})  recall={r_}  FPR={f_}"  # noqa: E501 (mensaje de consola)
        )
    print(f"  solo_host (se quita la ruta): recall={mh['recall']:.4f} FPR={mh['fpr']:.4f} AUC={mh['auc_roc']:.4f}")
    caida = m["auc_roc"] - mh["auc_roc"]
    rob["caida_auc_sin_ruta"] = round(float(caida), 4)
    rob["interpretacion"] = (
        "Sin legitimas con ruta en el test, el FPR 'con_ruta' no es medible: agrega legitimas con ruta "
        "(--kaggle-csv / --extra-legit-csv --pct-legit-con-ruta 25) o entrena con --ruta-modo solo_host."
        if sub["con_ruta"]["n_legitimas"] < 50
        else "Hay legitimas con ruta en el test: compara el FPR de 'con_ruta' contra 'sin_ruta'. "
        "Si con_ruta es mucho mayor, el modelo todavia castiga las rutas."
    )
    print("  ->", rob["interpretacion"])

    # --- Prueba EXTERNA (otra procedencia que el entrenamiento) ---
    if a.externo:
        ext = pd.read_csv(a.externo).dropna(subset=["url", "label"])
        Xe = np.array([tokenizar_url(u, meta["vocab"], meta["maxlen"], modo_ruta) for u in ext["url"]], dtype=np.int32)
        ye = ext["label"].astype(int).to_numpy()
        pe = model.predict(Xe, verbose=0).ravel()
        me = resumen(ye, pe, 0.5) if len(set(ye)) > 1 else None
        rob["externa"] = me if me else {"aviso": "el CSV externo tiene una sola clase; agrega legitimas Y phishing"}
        print(f"\n=== PRUEBA EXTERNA ({a.externo}, n={len(ext):,}) ===")
        if me:
            for k in ["accuracy", "precision", "recall", "fpr", "f1", "auc_roc"]:
                print(f"  {k:9s}: {me[k]:.4f}")
            print(f"  TP={me['tp']:,} FP={me['fp']:,} FN={me['fn']:,} TN={me['tn']:,}")
            det_e = pd.DataFrame({"url": ext["url"].values, "real": ye, "prob_phishing": pe})
            det_e[(det_e.real == 1) & (det_e.prob_phishing < 0.5)].to_csv(
                out / "externa_falsos_negativos.csv", index=False
            )
            det_e[(det_e.real == 0) & (det_e.prob_phishing >= 0.5)].to_csv(
                out / "externa_falsos_positivos.csv", index=False
            )
        else:
            print("  Una sola clase en el CSV externo; no se puede calcular.")

    # --- Umbrales sugeridos ---
    # Se eligen con predicciones FUERA DE MUESTRA (oof_cv.npz, del k-fold). NO se usa 'val': el modelo
    # final se reentrena con train+val, asi que val ya fue visto y daria umbrales demasiado optimistas.
    oof_path = Path(a.model).parent / "oof_cv.npz"
    if oof_path.exists():
        oo = np.load(oof_path)
        yv, pv = oo["y"], oo["p"]
        origen = "oof_kfold"
    else:
        dv = np.load(pdir / "val.npz")
        yv = dv["y"]
        pv = model.predict(dv["X"], verbose=0).ravel()
        origen = "val (OPTIMISTA: el modelo ya vio val; reentrena con la version nueva de train.py)"
    grid = np.round(np.arange(0.01, 1.0, 0.01), 2)
    t_adv = max([t for t in grid if resumen(yv, pv, t)["recall"] >= a.recall_objetivo] or [0.5])
    t_blq = min([t for t in grid if resumen(yv, pv, t)["fpr"] <= a.fpr_bloqueo] or [0.99])
    sug = {
        "umbral_advertencia": float(t_adv),
        "umbral_bloqueo": float(t_blq),
        "elegidos_con": origen,
        "test_en_advertencia": {k: resumen(y, p, t_adv)[k] for k in ["recall", "fpr", "precision"]},
        "test_en_bloqueo": {k: resumen(y, p, t_blq)[k] for k in ["recall", "fpr", "precision"]},
        "criterio": f"advertencia: mayor umbral con recall>={a.recall_objetivo}; bloqueo: menor umbral con FPR<={a.fpr_bloqueo} (en {origen})",  # noqa: E501 (mensaje de consola)
    }
    (out / "umbrales_sugeridos.json").write_text(json.dumps(sug, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nUmbrales sugeridos ({origen}): advertencia={t_adv:.2f}  bloqueo={t_blq:.2f}")
    print(
        f"  en test -> advertencia: recall={sug['test_en_advertencia']['recall']:.4f} FPR={sug['test_en_advertencia']['fpr']:.4f} | "  # noqa: E501 (mensaje de consola)
        f"bloqueo: recall={sug['test_en_bloqueo']['recall']:.4f} FPR={sug['test_en_bloqueo']['fpr']:.4f}"
    )
    (out / "robustez.json").write_text(json.dumps(rob, ensure_ascii=False, indent=2), encoding="utf-8")

    # Errores para análisis cualitativo
    det = pd.DataFrame({"url": urls, "real": y, "prob_phishing": p})
    det[(det.real == 1) & (det.prob_phishing < 0.5)].sort_values("prob_phishing").head(30).to_csv(
        out / "errores_falsos_negativos.csv", index=False
    )
    det[(det.real == 0) & (det.prob_phishing >= 0.5)].sort_values("prob_phishing", ascending=False).head(30).to_csv(
        out / "errores_falsos_positivos.csv", index=False
    )
    print(f"\nGuardado en {out}/ (incluye errores_falsos_negativos.csv y errores_falsos_positivos.csv)")


if __name__ == "__main__":
    main()
