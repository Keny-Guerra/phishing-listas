"""
export_onnx.py
---------------
Exporta el modelo Keras entrenado (models/cnn_phishing_final.keras) a
formato ONNX, para su ejecución on-device en la extensión de navegador
vía ONNX Runtime Web (decisión tomada en CU-06 "Exportar modelo a ONNX"
y en la Práctica 5, motor de inferencia = ONNX Runtime Web sobre
TensorFlow.js).

Valida además:
  - que el modelo ONNX produce las mismas predicciones (dentro de una
    tolerancia numérica) que el modelo Keras original;
  - la latencia de inferencia promedio, para verificar RNF1
    (<100ms en el 95% de las clasificaciones).

Uso:
    python src/export_onnx.py --model models/cnn_phishing_final.keras \
                               --out models/cnn_phishing.onnx
"""

import argparse
import json
import time
from pathlib import Path

import numpy as np
import tensorflow as tf


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=str, default="models/cnn_phishing_final.keras")
    parser.add_argument("--out", type=str, default="models/cnn_phishing.onnx")
    parser.add_argument("--processed-dir", type=str, default="data/processed")
    parser.add_argument("--opset", type=int, default=13)
    parser.add_argument(
        "--n-latencia", type=int, default=500, help="Número de inferencias individuales para medir latencia (RNF1)"
    )
    args = parser.parse_args()

    import onnx
    import onnxruntime as ort
    import tf2onnx  # requiere: pip install tf2onnx

    model_path = Path(args.model)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Cargando modelo Keras desde {model_path}...")
    keras_model = tf.keras.models.load_model(model_path)

    meta = json.loads((Path(args.processed_dir) / "vocab_meta.json").read_text(encoding="utf-8"))
    maxlen = meta["maxlen"]

    input_signature = [tf.TensorSpec([None, maxlen], tf.int32, name="url_tokens")]
    print(f"Convirtiendo a ONNX (opset {args.opset})...")
    try:
        onnx_model, _ = tf2onnx.convert.from_keras(keras_model, input_signature=input_signature, opset=args.opset)
    except Exception as exc:  # Keras 3 / TF reciente: ruta alternativa vía tf.function
        print(f"  from_keras falló ({type(exc).__name__}: {exc}); usando from_function...")

        @tf.function(input_signature=input_signature)
        def _fn(x):
            return keras_model(x, training=False)

        onnx_model, _ = tf2onnx.convert.from_function(_fn, input_signature=input_signature, opset=args.opset)
    onnx.save(onnx_model, str(out_path))
    print(f"Modelo ONNX guardado en {out_path} ({out_path.stat().st_size / 1024:.1f} KB)")

    # --- Validar equivalencia numérica Keras vs ONNX ---
    print("\nValidando equivalencia numérica Keras vs ONNX...")
    X_test = None
    test_npz = Path(args.processed_dir) / "test.npz"
    if test_npz.exists():
        data = np.load(test_npz)
        X_test = data["X"][:200]
    else:
        X_test = np.random.randint(0, meta["vocab_size"], size=(200, maxlen)).astype(np.int32)

    keras_pred = keras_model.predict(X_test, verbose=0).ravel()

    sess = ort.InferenceSession(str(out_path), providers=["CPUExecutionProvider"])
    input_name = sess.get_inputs()[0].name
    onnx_pred = sess.run(None, {input_name: X_test.astype(np.int32)})[0].ravel()

    diff_maxima = float(np.max(np.abs(keras_pred - onnx_pred)))
    print(f"  Diferencia máxima absoluta entre predicciones Keras y ONNX: {diff_maxima:.6f}")
    if diff_maxima < 1e-4:
        print("  OK: el modelo ONNX es numéricamente equivalente al modelo Keras.")
    else:
        print("  AVISO: diferencia mayor a la esperada, revisar la conversión.")

    # --- Medir latencia de inferencia individual (simula uso real: 1 URL a la vez) ---
    print(f"\nMidiendo latencia de inferencia individual ({args.n_latencia} muestras)...")
    muestra = (
        X_test[np.random.randint(0, len(X_test), size=args.n_latencia)]
        if len(X_test) > 0
        else np.random.randint(0, meta["vocab_size"], size=(args.n_latencia, maxlen)).astype(np.int32)
    )

    tiempos_ms = []
    for i in range(args.n_latencia):
        entrada = muestra[i : i + 1].astype(np.int32)
        t0 = time.perf_counter()
        sess.run(None, {input_name: entrada})
        tiempos_ms.append((time.perf_counter() - t0) * 1000)

    tiempos_ms = np.array(tiempos_ms)
    resultado_latencia = {
        "n_muestras": args.n_latencia,
        "latencia_media_ms": float(np.mean(tiempos_ms)),
        "latencia_p50_ms": float(np.percentile(tiempos_ms, 50)),
        "latencia_p95_ms": float(np.percentile(tiempos_ms, 95)),
        "latencia_p99_ms": float(np.percentile(tiempos_ms, 99)),
        "cumple_rnf1_p95_menor_100ms": bool(np.percentile(tiempos_ms, 95) < 100),
        "nota": (
            "Medido en CPU sobre el entorno de entrenamiento (Colab), NO dentro del "
            "navegador. La latencia real en la extensión (ONNX Runtime Web, WASM/WebGL) "
            "debe remedirse en el navegador de destino antes de dar RNF1 por verificado."
        ),
    }
    (Path(args.model).parent / "latencia_onnx_metrics.json").write_text(
        json.dumps(resultado_latencia, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"  Latencia p95: {resultado_latencia['latencia_p95_ms']:.2f} ms "
        f"({'CUMPLE' if resultado_latencia['cumple_rnf1_p95_menor_100ms'] else 'NO CUMPLE'} RNF1 en CPU local)"
    )
    print(f"\nGuardado: {Path(args.model).parent / 'latencia_onnx_metrics.json'}")


if __name__ == "__main__":
    main()
