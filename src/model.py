"""
model.py
--------
Arquitectura CNN a nivel de caracteres para clasificación binaria de URLs
(phishing=1 / legítima=0), según la decisión arquitectónica tomada en la
Matriz de decisión multicriterio de la Práctica 3 (extensión local sin
backend; CNN elegida por latencia <100ms y tamaño de modelo reducido,
sobre LSTM/DistilBERT).

Referencia de diseño: Aldakheel et al. (2023) usa CNN+LSTM híbrido sobre
ISCX-URL2016 con AUC-ROC 0.993; aquí se usa CNN pura (sin la rama LSTM)
para minimizar latencia y tamaño, conforme a lo decidido en la Práctica 3.
"""

import tensorflow as tf
from tensorflow.keras import layers, models


def build_cnn_model(vocab_size: int, maxlen: int, embed_dim: int = 32) -> tf.keras.Model:
    """CNN de caracteres para URLs.

    Arquitectura:
      Embedding -> [Conv1D + BatchNorm + ReLU + MaxPool] x3 (kernels 3,5,7,
      capturando patrones locales de distinta longitud: subcadenas típicas
      de ofuscación como '-verificacion', IPs numéricas, TLDs sospechosos)
      -> GlobalMaxPooling1D -> Dense(64, relu) -> Dropout(0.3)
      -> Dense(1, sigmoid)

    Pensada para ser liviana: ~200-400K parámetros, exportable a ONNX y
    ejecutable en <100ms dentro de la extensión de navegador (RNF1).
    """
    inputs = layers.Input(shape=(maxlen,), dtype="int32", name="url_tokens")

    x = layers.Embedding(input_dim=vocab_size, output_dim=embed_dim, mask_zero=False, name="char_embedding")(inputs)

    # Tres ramas convolucionales en paralelo con distinto kernel_size,
    # concatenadas (patrón multi-escala tipo Kim (2014) para clasificación
    # de texto, adaptado a nivel de carácter)
    ramas = []
    for k in (3, 5, 7):
        c = layers.Conv1D(filters=64, kernel_size=k, padding="same", name=f"conv_k{k}")(x)
        c = layers.BatchNormalization(name=f"bn_k{k}")(c)
        c = layers.Activation("relu", name=f"relu_k{k}")(c)
        c = layers.GlobalMaxPooling1D(name=f"gmp_k{k}")(c)
        ramas.append(c)

    concat = layers.Concatenate(name="concat_multiescala")(ramas)
    d = layers.Dense(64, activation="relu", name="dense_64")(concat)
    d = layers.Dropout(0.3, name="dropout")(d)
    out = layers.Dense(1, activation="sigmoid", name="salida_phishing")(d)

    model = models.Model(inputs=inputs, outputs=out, name="cnn_phishing_detector")
    return model


def compile_model(model: tf.keras.Model, lr: float = 1e-3) -> tf.keras.Model:
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=lr),
        loss="binary_crossentropy",
        metrics=[
            "accuracy",
            tf.keras.metrics.Precision(name="precision"),
            tf.keras.metrics.Recall(name="recall"),
            tf.keras.metrics.AUC(name="auc_roc"),
        ],
    )
    return model


if __name__ == "__main__":
    # Smoke test de la arquitectura (no requiere datos, solo valida que
    # el grafo se construye y compila correctamente)
    m = build_cnn_model(vocab_size=61, maxlen=200)
    m = compile_model(m)
    m.summary()
    print(f"\nParámetros totales: {m.count_params():,}")
