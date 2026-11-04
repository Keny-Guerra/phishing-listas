"""
train.py
--------
Entrenamiento de la CNN de detección de phishing con validación cruzada
k-fold (k=10), tal como especifica la Ficha Técnica de la Práctica 1
("validación cruzada k-fold k=10"). Reporta accuracy, precision, recall,
F1 y AUC-ROC por fold, promedia resultados, y luego reentrena un modelo
final sobre todo el conjunto de entrenamiento+validación para evaluarlo
en el conjunto de prueba (test, 20% reservado y nunca usado en k-fold).

Uso (en Google Colab con GPU, o localmente si tienes TensorFlow instalado):
    python src/train.py --processed-dir data/processed --epochs 15 --batch-size 128

Salidas:
    models/cnn_phishing_kfold_metrics.json  (métricas por fold + promedio)
    models/cnn_phishing_final.keras         (modelo final reentrenado)
    models/cnn_phishing_final_test_metrics.json (métricas sobre test set)
"""

import argparse
import json
import time
from pathlib import Path

import numpy as np
import tensorflow as tf
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import StratifiedKFold

from model import build_cnn_model, compile_model

RANDOM_SEED = 42


def cargar_split(processed_dir: Path, nombre: str):
    data = np.load(processed_dir / f"{nombre}.npz")
    return data["X"], data["y"]


def evaluar(model, X, y, threshold=0.5):
    y_prob = model.predict(X, verbose=0).ravel()
    y_pred = (y_prob >= threshold).astype(int)
    return {
        "accuracy": float(accuracy_score(y, y_pred)),
        "precision": float(precision_score(y, y_pred, zero_division=0)),
        "recall": float(recall_score(y, y_pred, zero_division=0)),
        "f1": float(f1_score(y, y_pred, zero_division=0)),
        "auc_roc": float(roc_auc_score(y, y_prob)),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--processed-dir", type=str, default="data/processed")
    parser.add_argument("--models-dir", type=str, default="models")
    parser.add_argument("--epochs", type=int, default=15)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument(
        "--k-folds", type=int, default=10, help="k para validación cruzada (Ficha Técnica PRACT1: k=10)"
    )
    parser.add_argument("--embed-dim", type=int, default=32)
    parser.add_argument("--seed", type=int, default=RANDOM_SEED)
    args = parser.parse_args()

    tf.random.set_seed(args.seed)
    np.random.seed(args.seed)

    processed_dir = Path(args.processed_dir)
    models_dir = Path(args.models_dir)
    models_dir.mkdir(parents=True, exist_ok=True)

    meta = json.loads((processed_dir / "vocab_meta.json").read_text(encoding="utf-8"))
    vocab_size = meta["vocab_size"]
    maxlen = meta["maxlen"]

    X_train, y_train = cargar_split(processed_dir, "train")
    X_val, y_val = cargar_split(processed_dir, "val")
    X_test, y_test = cargar_split(processed_dir, "test")

    # Para k-fold se usa train+val juntos (el test se reserva SIEMPRE aparte,
    # solo para la evaluación final del modelo reentrenado)
    X_cv = np.concatenate([X_train, X_val], axis=0)
    y_cv = np.concatenate([y_train, y_val], axis=0)

    print(f"Datos para k-fold (train+val): {X_cv.shape[0]:,} | test reservado: {X_test.shape[0]:,}")
    print(f"vocab_size={vocab_size}, maxlen={maxlen}, k={args.k_folds}")

    skf = StratifiedKFold(n_splits=args.k_folds, shuffle=True, random_state=args.seed)
    fold_metrics = []
    oof_p = np.zeros(len(y_cv), dtype=np.float32)  # predicciones "fuera de muestra" de cada fold
    t0 = time.time()

    for fold_i, (idx_tr, idx_va) in enumerate(skf.split(X_cv, y_cv), start=1):
        print(f"\n=== Fold {fold_i}/{args.k_folds} ===")
        model = build_cnn_model(vocab_size, maxlen, embed_dim=args.embed_dim)
        model = compile_model(model)

        early_stop = tf.keras.callbacks.EarlyStopping(monitor="val_loss", patience=3, restore_best_weights=True)

        model.fit(
            X_cv[idx_tr],
            y_cv[idx_tr],
            validation_data=(X_cv[idx_va], y_cv[idx_va]),
            epochs=args.epochs,
            batch_size=args.batch_size,
            callbacks=[early_stop],
            verbose=2,
        )

        oof_p[idx_va] = model.predict(X_cv[idx_va], verbose=0).ravel()
        metrics = evaluar(model, X_cv[idx_va], y_cv[idx_va])
        metrics["fold"] = fold_i
        fold_metrics.append(metrics)
        print(f"Fold {fold_i} -> {metrics}")

    tiempo_total = time.time() - t0
    # Se guardan para elegir umbrales SIN usar datos que el modelo final ya vio al entrenar
    np.savez_compressed(models_dir / "oof_cv.npz", y=y_cv, p=oof_p)

    promedio = {
        k: float(np.mean([m[k] for m in fold_metrics])) for k in ["accuracy", "precision", "recall", "f1", "auc_roc"]
    }
    desviacion = {
        k: float(np.std([m[k] for m in fold_metrics])) for k in ["accuracy", "precision", "recall", "f1", "auc_roc"]
    }

    resultado_kfold = {
        "k_folds": args.k_folds,
        "por_fold": fold_metrics,
        "promedio": promedio,
        "desviacion_estandar": desviacion,
        "tiempo_total_segundos": tiempo_total,
    }
    (models_dir / "cnn_phishing_kfold_metrics.json").write_text(
        json.dumps(resultado_kfold, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("\n=== Promedio k-fold ===")
    for k, v in promedio.items():
        print(f"  {k}: {v:.4f} (+/- {desviacion[k]:.4f})")
    print(
        f"Verificación RNF2 (recall > 0.85 en amenazas emergentes, aprox. por recall de validación): "
        f"{'CUMPLE' if promedio['recall'] > 0.85 else 'NO CUMPLE — revisar hiperparámetros/dataset'}"
    )

    # --- Reentrenamiento final sobre train+val completo, evaluación en test ---
    print("\n=== Reentrenando modelo final sobre train+val completo ===")
    final_model = build_cnn_model(vocab_size, maxlen, embed_dim=args.embed_dim)
    final_model = compile_model(final_model)
    early_stop = tf.keras.callbacks.EarlyStopping(monitor="loss", patience=3, restore_best_weights=True)
    final_model.fit(
        X_cv,
        y_cv,
        epochs=args.epochs,
        batch_size=args.batch_size,
        callbacks=[early_stop],
        verbose=2,
    )

    test_metrics = evaluar(final_model, X_test, y_test)
    (models_dir / "cnn_phishing_final_test_metrics.json").write_text(
        json.dumps(test_metrics, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("\n=== Métricas en TEST (nunca antes visto) ===")
    for k, v in test_metrics.items():
        print(f"  {k}: {v:.4f}")

    final_model.save(models_dir / "cnn_phishing_final.keras")
    print(f"\nModelo final guardado en {models_dir / 'cnn_phishing_final.keras'}")


if __name__ == "__main__":
    main()
