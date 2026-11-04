"""
promote_model.py
----------------
Paso 4: promueve un candidato a modelo VIGENTE (o hace rollback).

Promover = exportar a ONNX, calcular SHA-256, escribir manifest.json (que
la extensión verifica antes de cargar el modelo: OWASP A08) y archivar el
vigente anterior en models/historial/ para poder revertir.

    python src/promote_model.py --candidato models/candidatos/v20261001
    python src/promote_model.py --candidato ... --force      # ignora decision.json
    python src/promote_model.py --rollback                   # vuelve a la versión anterior

Archivos publicables para la extensión (carpeta models/vigente/):
    model.onnx, manifest.json, vocab_meta.json, (allowlist_top.json)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess  # nosec B404 # se invoca con lista fija de argumentos, sin shell
import sys
from datetime import datetime
from pathlib import Path


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def registrar(models_dir: Path, evento: dict):
    reg = models_dir / "registro_versiones.json"
    datos = json.loads(reg.read_text(encoding="utf-8")) if reg.exists() else []
    datos.append({"momento": datetime.now().isoformat(timespec="seconds"), **evento})
    reg.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")


def archivar_vigente(models_dir: Path):
    vig = models_dir / "vigente"
    if not (vig / "manifest.json").exists():
        return None
    ver = json.loads((vig / "manifest.json").read_text(encoding="utf-8"))["version"]
    destino = models_dir / "historial" / ver
    if destino.exists():
        shutil.rmtree(destino)
    shutil.copytree(vig, destino)
    return ver


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--candidato", default=None)
    ap.add_argument("--models-dir", default="models")
    ap.add_argument("--processed-dir", default="data/processed_temporal")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--rollback", action="store_true")
    args = ap.parse_args()

    models_dir = Path(args.models_dir)
    vig = models_dir / "vigente"

    # ---------- ROLLBACK ----------
    if args.rollback:
        hist = models_dir / "historial"
        versiones = sorted([d for d in hist.glob("*") if (d / "manifest.json").exists()]) if hist.exists() else []
        if not versiones:
            raise SystemExit("No hay versiones en models/historial para revertir.")
        anterior = versiones[-1]
        actual = archivar_vigente(models_dir)
        if vig.exists():
            shutil.rmtree(vig)
        shutil.copytree(anterior, vig)
        registrar(models_dir, {"evento": "rollback", "de": actual, "a": anterior.name})
        print(f"Rollback: {actual} -> {anterior.name}")
        return

    # ---------- PROMOCIÓN ----------
    if not args.candidato:
        raise SystemExit("Indica --candidato <carpeta> o --rollback")
    cand = Path(args.candidato)
    metrics = json.loads((cand / "metrics.json").read_text(encoding="utf-8"))
    decision = json.loads((cand / "decision.json").read_text(encoding="utf-8"))
    if not decision["promover"] and not args.force:
        raise SystemExit(
            "El candidato NO cumple los criterios de promoción: "
            + "; ".join(decision["razones"])
            + "\n(usa --force solo con justificación documentada)"
        )

    here = Path(__file__).resolve().parent
    onnx_tmp = cand / "model.onnx"
    subprocess.run(  # nosec B603 # argumentos propios, sin shell
        [
            sys.executable,
            str(here / "export_onnx.py"),
            "--model",
            str(cand / "model.keras"),
            "--out",
            str(onnx_tmp),
            "--processed-dir",
            args.processed_dir,
        ],
        check=True,
    )

    anterior = archivar_vigente(models_dir)
    if vig.exists():
        shutil.rmtree(vig)
    vig.mkdir(parents=True)
    shutil.copy(cand / "model.keras", vig / "model.keras")
    shutil.copy(onnx_tmp, vig / "model.onnx")
    shutil.copy(Path(args.processed_dir) / "vocab_meta.json", vig / "vocab_meta.json")
    lat = cand / "latencia_onnx_metrics.json"
    lat_datos = json.loads(lat.read_text(encoding="utf-8")) if lat.exists() else None
    allow = models_dir / "allowlist_top.json"
    if allow.exists():
        shutil.copy(allow, vig / "allowlist_top.json")

    manifest = {
        "version": metrics["version"],
        "fecha": metrics["fecha"],
        "sha256_onnx": sha256(vig / "model.onnx"),
        "maxlen": metrics["maxlen"],
        "vocab_size": metrics["vocab_size"],
        "umbral_advertencia": metrics["umbral_advertencia"],
        "umbral_bloqueo": metrics["umbral_bloqueo"],
        "metricas_test_futuro": metrics["test_futuro_en_umbral_advertencia"],
        "latencia_onnx_cpu": lat_datos,
        "version_anterior": anterior,
    }
    (vig / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    registrar(
        models_dir,
        {
            "evento": "promocion",
            "version": metrics["version"],
            "anterior": anterior,
            "forzado": bool(args.force and not decision["promover"]),
        },
    )
    print(f"Promovido {metrics['version']} (anterior: {anterior}). SHA-256 ONNX: {manifest['sha256_onnx'][:16]}...")
    print(f"Publicar la carpeta {vig} (model.onnx + manifest.json + vocab_meta.json + allowlist_top.json).")


if __name__ == "__main__":
    main()
