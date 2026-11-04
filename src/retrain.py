"""
retrain.py
----------
Paso 3 del ciclo mensual: reentrena un modelo CANDIDATO con el corpus
actualizado (feeds + reportes verificados), lo mide con split TEMPORAL y
lo compara contra el modelo vigente (campeón) sobre el MISMO test futuro.

Por qué split temporal: con split aleatorio, URLs casi idénticas caen en
train y test y las métricas salen infladas. Aquí el test son las URLs más
recientes (fecha >= --cutoff) que el modelo nunca vio ni pudo "aprender
de memoria": mide si detecta phishing FUTURO.

Umbrales (calculados en validación, nunca en test):
  umbral_advertencia: el MÁS ALTO que mantiene recall >= --recall-objetivo
                      (RNF2: recall > 85 %). Entre advertencia y bloqueo la
                      extensión solo avisa (zona de duda).
  umbral_bloqueo:     el MÁS BAJO con tasa de falsos positivos <=
                      --fpr-bloqueo. Por encima, se bloquea.

Regla de promoción (decision.json):
  - recall del candidato >= 0.85 (RNF2), y
  - si hay campeón: recall >= recall_campeón - 0.005  Y
                    FPR <= FPR_campeón * 1.10 + 0.002
  Si no se cumple, NO se promueve (el modelo vigente se mantiene).

Salida: models/candidatos/<version>/{model.keras, metrics.json, decision.json}

Uso:
    python src/retrain.py --corpus data/corpus/corpus.csv --cutoff 2026-09-01
"""

from __future__ import annotations

import argparse
import json
import subprocess  # nosec B404 # se invoca con lista fija de argumentos, sin shell
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import tensorflow as tf

sys.path.insert(0, str(Path(__file__).resolve().parent))
from model import build_cnn_model, compile_model  # noqa: E402

RANDOM_SEED = 42
RECALL_MIN_RNF2 = 0.85


def calcular_umbrales(y_val, p_val, recall_objetivo: float, fpr_bloqueo: float) -> dict:
    grid = np.unique(np.round(np.concatenate([np.linspace(0.01, 0.99, 99), p_val]), 4))
    grid = grid[(grid > 0) & (grid < 1)]
    P, N = max((y_val == 1).sum(), 1), max((y_val == 0).sum(), 1)
    rec = np.array([((p_val >= t) & (y_val == 1)).sum() / P for t in grid])
    fpr = np.array([((p_val >= t) & (y_val == 0)).sum() / N for t in grid])
    ok_rec = grid[rec >= recall_objetivo]
    t_adv = float(ok_rec.max()) if len(ok_rec) else float(grid.min())
    ok_fpr = grid[fpr <= fpr_bloqueo]
    t_blq = float(ok_fpr.min()) if len(ok_fpr) else float(grid.max())
    t_blq = max(t_blq, t_adv)  # coherencia: bloqueo >= advertencia
    return {"umbral_advertencia": t_adv, "umbral_bloqueo": t_blq}


def metricas(y, p, umbral: float) -> dict:
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
        "recall": tp / max(tp + fn, 1),
        "precision": tp / max(tp + fp, 1),
        "fpr": fp / max(fp + tn, 1),
    }


def fpr_por_tipo(urls: pd.Series, y, p, umbral) -> dict:
    """FPR en legítimas solo-dominio vs con ruta: detecta el sesgo de
    'con ruta = sospechosa' que puede introducir Tranco."""
    legit = y == 0
    sin_ruta = urls.str.replace(r"^[a-z]+://", "", regex=True).str.strip("/").str.count("/") == 0
    out = {}
    for nombre, m in [
        ("legitimas_solo_dominio", legit & sin_ruta.values),
        ("legitimas_con_ruta", legit & ~sin_ruta.values),
    ]:
        out[nombre] = {"n": int(m.sum()), "fpr": float(((p >= umbral) & m).sum() / max(m.sum(), 1))}
    return out


def decidir_promocion(cand: dict, camp: dict | None) -> dict:
    razones, ok = [], True
    if cand["recall"] < RECALL_MIN_RNF2:
        ok = False
        razones.append(f"recall {cand['recall']:.3f} < {RECALL_MIN_RNF2} (RNF2)")
    if camp is not None:
        if cand["recall"] < camp["recall"] - 0.005:
            ok = False
            razones.append(f"recall cae vs campeón ({cand['recall']:.3f} < {camp['recall']:.3f}-0.005)")
        if cand["fpr"] > camp["fpr"] * 1.10 + 0.002:
            ok = False
            razones.append(f"FPR sube vs campeón ({cand['fpr']:.4f} > {camp['fpr'] * 1.10 + 0.002:.4f})")
    else:
        razones.append("sin campeón previo: se evalúa solo contra RNF2")
    if ok:
        razones.append("cumple criterios de promoción")
    return {"promover": ok, "razones": razones}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", default="data/corpus/corpus.csv")
    ap.add_argument("--cutoff", required=True, help="fecha >= cutoff = test futuro (YYYY-MM-DD)")
    ap.add_argument("--processed-dir", default="data/processed_temporal")
    ap.add_argument("--models-dir", default="models")
    ap.add_argument("--maxlen", type=int, default=200)
    ap.add_argument("--epochs", type=int, default=15)
    ap.add_argument("--batch-size", type=int, default=128)
    ap.add_argument("--embed-dim", type=int, default=32)
    ap.add_argument("--recall-objetivo", type=float, default=0.90)
    ap.add_argument("--fpr-bloqueo", type=float, default=0.005)
    ap.add_argument("--version", default=None)
    ap.add_argument("--seed", type=int, default=RANDOM_SEED)
    args = ap.parse_args()

    tf.random.set_seed(args.seed)
    np.random.seed(args.seed)
    models_dir = Path(args.models_dir)
    version = args.version or f"v{date.today().strftime('%Y%m%d')}"
    cand_dir = models_dir / "candidatos" / version
    cand_dir.mkdir(parents=True, exist_ok=True)

    # 1) Preprocesar con split temporal (reutiliza preprocess.py)
    here = Path(__file__).resolve().parent
    subprocess.run(  # nosec B603 # argumentos propios, sin shell
        [
            sys.executable,
            str(here / "preprocess.py"),
            "--in",
            args.corpus,
            "--outdir",
            args.processed_dir,
            "--maxlen",
            str(args.maxlen),
            "--split-mode",
            "temporal",
            "--cutoff",
            args.cutoff,
        ],
        check=True,
    )
    pdir = Path(args.processed_dir)
    meta = json.loads((pdir / "vocab_meta.json").read_text(encoding="utf-8"))

    def ld(n):
        z = np.load(pdir / f"{n}.npz")
        return z["X"], z["y"]

    X_tr, y_tr = ld("train")
    X_va, y_va = ld("val")
    X_te, y_te = ld("test")
    urls_te = pd.read_csv(pdir / "test_urls.csv")["url"].astype(str)

    # 2) Entrenar candidato
    model = compile_model(build_cnn_model(meta["vocab_size"], meta["maxlen"], embed_dim=args.embed_dim))
    model.fit(
        X_tr,
        y_tr,
        validation_data=(X_va, y_va),
        epochs=args.epochs,
        batch_size=args.batch_size,
        verbose=2,
        callbacks=[tf.keras.callbacks.EarlyStopping(monitor="val_loss", patience=3, restore_best_weights=True)],
    )
    model.save(cand_dir / "model.keras")

    # 3) Umbrales (en validación) y métricas en test futuro
    p_va = model.predict(X_va, verbose=0).ravel()
    p_te = model.predict(X_te, verbose=0).ravel()
    umbrales = calcular_umbrales(y_va, p_va, args.recall_objetivo, args.fpr_bloqueo)
    m_adv = metricas(y_te, p_te, umbrales["umbral_advertencia"])
    m_blq = metricas(y_te, p_te, umbrales["umbral_bloqueo"])
    sesgo = fpr_por_tipo(urls_te, y_te, p_te, umbrales["umbral_advertencia"])

    # 4) Campeón sobre el MISMO test futuro
    camp_metricas = None
    vig = models_dir / "vigente"
    if (vig / "model.keras").exists() and (vig / "manifest.json").exists():
        man = json.loads((vig / "manifest.json").read_text(encoding="utf-8"))
        if man.get("maxlen") == meta["maxlen"] and man.get("vocab_size") == meta["vocab_size"]:
            champ = tf.keras.models.load_model(vig / "model.keras")
            p_c = champ.predict(X_te, verbose=0).ravel()
            camp_metricas = metricas(y_te, p_c, man["umbral_advertencia"])
            camp_metricas["version"] = man["version"]
        else:
            print("AVISO: el campeón usa otro vocabulario/maxlen; no es comparable.")

    decision = decidir_promocion(m_adv, camp_metricas)

    resultado = {
        "version": version,
        "fecha": date.today().isoformat(),
        "cutoff": args.cutoff,
        "n_train": int(len(y_tr)),
        "n_val": int(len(y_va)),
        "n_test_futuro": int(len(y_te)),
        "maxlen": meta["maxlen"],
        "vocab_size": meta["vocab_size"],
        **umbrales,
        "test_futuro_en_umbral_advertencia": m_adv,
        "test_futuro_en_umbral_bloqueo": m_blq,
        "sesgo_legitimas": sesgo,
        "campeon_en_mismo_test": camp_metricas,
    }
    (cand_dir / "metrics.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    (cand_dir / "decision.json").write_text(json.dumps(decision, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n=== Candidato {version} (test futuro: {len(y_te):,} URLs desde {args.cutoff}) ===")
    print(f"  umbrales: advertencia={umbrales['umbral_advertencia']:.3f}  bloqueo={umbrales['umbral_bloqueo']:.3f}")
    print(f"  @advertencia  recall={m_adv['recall']:.3f}  precision={m_adv['precision']:.3f}  FPR={m_adv['fpr']:.4f}")
    print(f"  @bloqueo      recall={m_blq['recall']:.3f}  precision={m_blq['precision']:.3f}  FPR={m_blq['fpr']:.4f}")
    if camp_metricas:
        print(
            f"  campeón {camp_metricas['version']}: recall={camp_metricas['recall']:.3f}  FPR={camp_metricas['fpr']:.4f}"  # noqa: E501 (mensaje de consola)
        )
    print(f"  DECISIÓN: {'PROMOVER' if decision['promover'] else 'NO PROMOVER'} — {'; '.join(decision['razones'])}")
    if decision["promover"]:
        print(f"  Siguiente: python src/promote_model.py --candidato {cand_dir}")
    else:
        print("  El modelo vigente se mantiene. Revisa metrics.json y el corpus (más datos recientes, balance).")


if __name__ == "__main__":
    main()
