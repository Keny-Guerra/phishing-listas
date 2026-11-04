"""
01_smoke_test_ciclo.py
----------------------
Prueba de humo del CICLO DE RETROALIMENTACIÓN completo con datos SINTÉTICOS
(sin internet): corpus base -> feeds -> split temporal -> reentrenar ->
promover -> 2.º ciclo (comparación contra campeón) -> reportes de usuarios
-> rollback.

Valida que el código corre y que las reglas (quórum, conflicto, promoción)
se comportan como se documenta. NO produce métricas reales: con datos
sintéticos los números no significan nada.

    python notebooks/01_smoke_test_ciclo.py
"""
import random
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
SRC = RAIZ / "src"
sys.path.insert(0, str(RAIZ / "notebooks"))
from importlib import import_module  # noqa: E402

base = import_module("00_smoke_test")
random.seed(7)


def correr(*args, cwd):
    r = subprocess.run([sys.executable, *map(str, args)], cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-1500:], r.stderr[-1500:])
        raise SystemExit(f"FALLO: {' '.join(map(str, args))}")
    return r.stdout


def feeds_sinteticos(w: Path, n: int, tag: str):
    (w / f"feed_{tag}.txt").write_text("\n".join(base.url_phishing() for _ in range(n)), encoding="utf-8")
    doms = ["bcp.com.pe", "gob.pe", "google.com"] + [f"sitio{i}-{tag}.com" for i in range(n * 2)]
    (w / f"tranco_{tag}.csv").write_text("\n".join(f"{i+1},{d}" for i, d in enumerate(doms)), encoding="utf-8")


def main():
    with tempfile.TemporaryDirectory() as t:
        w = Path(t)
        # Corpus base (fecha antigua)
        df = base.generar_dataset_sintetico(1600)
        df["fecha"] = "2026-01-01"
        df[["url", "label", "fecha", "fuente"]].to_csv(w / "corpus_base.csv", index=False)
        (w / "data" / "corpus").mkdir(parents=True)
        (w / "corpus_base.csv").replace(w / "data" / "corpus" / "corpus.csv")

        for ciclo, (fecha, cutoff) in enumerate([("2026-10-01", "2026-09-01"), ("2026-11-01", "2026-10-15")], 1):
            print(f"\n######## CICLO {ciclo} ({fecha}) ########")
            feeds_sinteticos(w, 300, f"c{ciclo}")
            print(correr(SRC / "fetch_feeds.py", "--fecha", fecha, "--phishing-file", f"feed_c{ciclo}.txt",
                         "--tranco-file", f"tranco_c{ciclo}.csv", cwd=w))
            out = correr(SRC / "retrain.py", "--cutoff", cutoff, "--epochs", 3, "--version", f"v{fecha.replace('-', '')}", cwd=w)
            print(out[out.index("=== Candidato"):])
            cand = f"models/candidatos/v{fecha.replace('-', '')}"
            # Ciclo 2: --force para garantizar una versión en historial y poder probar el rollback
            extra = ["--force"] if ciclo == 2 else []
            print(correr(SRC / "promote_model.py", "--candidato", cand, *extra, cwd=w)[-400:])

        print("\n######## REPORTES DE USUARIOS ########")
        rep = []
        for u in ["u1", "u2", "u3"]:
            rep.append(("sitio0-c2.com", "falso_positivo", u, "2026-11-02"))   # 3 reporteros, está en allowlist -> confirma
            rep.append(("estafa-nueva.xyz", "falso_negativo", u, "2026-11-02"))  # 3 reporteros, NO está en feed -> pendiente
        rep += [("otro.com", "falso_negativo", "u1", "2026-11-02")]              # quórum insuficiente
        rep += [("conflicto.com", "falso_positivo", "u1", "2026-11-02"), ("conflicto.com", "falso_negativo", "u2", "2026-11-02")]
        # 25 reportes del mismo reportero el mismo día -> anti-spam
        rep += [(f"spam{i}.com", "falso_negativo", "bot", "2026-11-02") for i in range(25)]
        pd.DataFrame(rep, columns=["dominio", "tipo", "reportero", "fecha"]).to_csv(w / "reportes.csv", index=False)
        print(correr(SRC / "feedback_ingest.py", "--reportes", "reportes.csv", "--feed-phishing", "feed_c2.txt",
                     "--fecha", "2026-11-03", cwd=w))
        pend = pd.read_csv(w / "data" / "feedback" / "pendientes_revision.csv")
        conf = pd.read_csv(w / "data" / "feedback" / "confirmados.csv")
        assert list(conf["dominio"]) == ["sitio0-c2.com"], conf
        assert "estafa-nueva.xyz" in set(pend["dominio"]) and "conflicto.com" in set(pend["dominio"]), pend
        assert "otro.com" in set(pend["dominio"])
        assert not any(d.startswith("spam") and d != "spam0.com" for d in conf["dominio"])
        print("OK reglas de verificación: confirma solo lo contrastado; conflicto/quórum/sin-fuente quedan pendientes.")

        print("\n######## ROLLBACK ########")
        print(correr(SRC / "promote_model.py", "--rollback", cwd=w))
        reg = (w / "models" / "registro_versiones.json").read_text(encoding="utf-8")
        assert "rollback" in reg
        print("\nSMOKE TEST DEL CICLO: OK")


if __name__ == "__main__":
    main()
