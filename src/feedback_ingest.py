"""
feedback_ingest.py
------------------
Paso 2 del ciclo de retroalimentación: convierte los reportes de usuarios
(falsos positivos / falsos negativos) en etiquetas CONFIRMADAS, sin dejar
que cualquiera envenene el modelo.

Principio: un reporte NO es una etiqueta. Es una hipótesis que pasa por
cuarentena y se verifica antes de entrar al corpus de entrenamiento.

Formato de entrada (reportes.csv; lo genera el módulo opt-in de la
extensión, solo con consentimiento explícito — ver extension/src/feedback.js):
    dominio, tipo, reportero, fecha
    tipo = falso_negativo (el modelo dijo "legítima" y era phishing)
         | falso_positivo (el modelo dijo "phishing" y era legítima)
    reportero = identificador anónimo aleatorio (no es cuenta ni correo)

Reglas de verificación (todas configurables):
  1. Anti-spam: máximo --max-por-reportero-dia reportes por reportero y día.
  2. Quórum: al menos --min-reportes reporteros DISTINTOS por (dominio, tipo).
  3. Contraste con fuentes independientes:
       falso_negativo -> el dominio aparece en el feed de phishing vigente
       falso_positivo -> el dominio está en la allowlist Tranco y NO está
                         en el feed de phishing
  4. Conflicto (mismo dominio reportado como FP y FN) -> revisión manual.
  5. Revisión manual: --revision-manual CSV (dominio, decision) con
     decision = phishing | legitima; si existe, manda sobre las reglas 3.
Solo lo confirmado se agrega al corpus (fuente = feedback_verificado).
Lo no confirmado queda en cuarentena para el mes siguiente.

Hook pendiente (requiere API key propia, no incluido): consultar Google
Safe Browsing / VirusTotal en `verificar_externo()`.

Uso:
    python src/feedback_ingest.py --reportes data/feedback/reportes_nuevos.csv \
        --feed-phishing data/feedback/feed_phishing_actual.txt \
        --allowlist models/allowlist_top.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import corpus as C  # noqa: E402

TIPOS = {"falso_negativo": 1, "falso_positivo": 0}  # etiqueta verdadera resultante


def verificar_externo(dominio: str, tipo: str) -> bool | None:
    """Hook para Safe Browsing / VirusTotal. None = sin información."""
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reportes", required=True, help="CSV de reportes nuevos")
    ap.add_argument("--cuarentena", default="data/feedback/cuarentena.csv")
    ap.add_argument("--corpus", default="data/corpus/corpus.csv")
    ap.add_argument("--feed-phishing", default=None, help="Feed de phishing vigente (una URL por línea)")
    ap.add_argument("--allowlist", default="models/allowlist_top.json")
    ap.add_argument("--revision-manual", default=None)
    ap.add_argument("--min-reportes", type=int, default=3)
    ap.add_argument("--max-por-reportero-dia", type=int, default=20)
    ap.add_argument("--fecha", default=None)
    ap.add_argument("--pendientes-out", default="data/feedback/pendientes_revision.csv")
    args = ap.parse_args()

    hoy = args.fecha or date.today().isoformat()

    nuevos = pd.read_csv(args.reportes, dtype=str)
    if not {"dominio", "tipo", "reportero", "fecha"} <= set(nuevos.columns):
        raise ValueError("reportes.csv debe tener: dominio, tipo, reportero, fecha")
    nuevos = nuevos[nuevos["tipo"].isin(TIPOS)].copy()
    nuevos["dominio"] = nuevos["dominio"].str.strip().str.lower().str.strip(".")
    nuevos = nuevos[nuevos["dominio"].str.len() > 0]

    # 1) Anti-spam por reportero y día
    nuevos["_rank"] = nuevos.groupby(["reportero", "fecha"]).cumcount()
    spam = (nuevos["_rank"] >= args.max_por_reportero_dia).sum()
    nuevos = nuevos[nuevos["_rank"] < args.max_por_reportero_dia].drop(columns="_rank")
    if spam:
        print(f"Descartados por límite diario por reportero: {spam}")

    # Acumular en cuarentena (sin repetir mismo reportero/dominio/tipo)
    cpath = Path(args.cuarentena)
    cpath.parent.mkdir(parents=True, exist_ok=True)
    previa = pd.read_csv(cpath, dtype=str) if cpath.exists() else pd.DataFrame(columns=nuevos.columns)
    acum = pd.concat([previa, nuevos], ignore_index=True).drop_duplicates(subset=["dominio", "tipo", "reportero"])

    # Fuentes de contraste
    phishing_doms: set[str] = set()
    if args.feed_phishing and Path(args.feed_phishing).exists():
        phishing_doms = {
            C.dominio(ln)
            for ln in Path(args.feed_phishing).read_text(encoding="utf-8", errors="ignore").splitlines()
            if ln.strip()
        }
    allow: set[str] = set()
    if Path(args.allowlist).exists():
        allow = set(json.loads(Path(args.allowlist).read_text(encoding="utf-8"))["dominios"])
    manual: dict[str, str] = {}
    if args.revision_manual and Path(args.revision_manual).exists():
        m = pd.read_csv(args.revision_manual, dtype=str)
        manual = {r.dominio.strip().lower(): r.decision.strip().lower() for r in m.itertuples()}

    por = acum.groupby(["dominio", "tipo"])["reportero"].nunique().reset_index(name="n")
    tipos_por_dom = acum.groupby("dominio")["tipo"].nunique()

    confirmados, pendientes = [], []
    for r in por.itertuples():
        d, t, n = r.dominio, r.tipo, r.n
        etiqueta = TIPOS[t]
        motivo = None
        if d in manual:  # 5) manual manda
            if manual[d] == ("phishing" if etiqueta == 1 else "legitima"):
                motivo = "revision_manual"
        elif tipos_por_dom[d] > 1:  # 4) conflicto
            pendientes.append((d, t, n, "conflicto FP/FN: requiere revision manual"))
            continue
        elif n < args.min_reportes:  # 2) quórum
            pendientes.append((d, t, n, f"quorum insuficiente ({n}/{args.min_reportes})"))
            continue
        else:  # 3) contraste
            ext = verificar_externo(d, t)
            if t == "falso_negativo" and (d in phishing_doms or ext is True):
                motivo = "confirmado_en_feed_phishing"
            elif t == "falso_positivo" and d in allow and d not in phishing_doms:
                motivo = "confirmado_en_allowlist_tranco"
            else:
                pendientes.append((d, t, n, "sin confirmacion en fuente independiente"))
                continue
        if motivo:
            confirmados.append((d, etiqueta, motivo))

    # Persistir
    pend = pd.DataFrame(pendientes, columns=["dominio", "tipo", "reporteros", "motivo"])
    Path(args.pendientes_out).parent.mkdir(parents=True, exist_ok=True)
    pend.to_csv(args.pendientes_out, index=False)

    conf_dom = {d for d, _, _ in confirmados}
    # Lo confirmado sale de cuarentena; el resto se conserva
    acum[~acum["dominio"].isin(conf_dom)].to_csv(cpath, index=False)

    if confirmados:
        filas = pd.DataFrame(
            {
                "url": [f"https://{d}/" for d, _, _ in confirmados],
                "label": [e for _, e, _ in confirmados],
                "fecha": hoy,
                "fuente": "feedback_verificado",
            }
        )
        agregadas, dup = C.agregar(args.corpus, filas)
        pd.DataFrame(confirmados, columns=["dominio", "label", "motivo"]).to_csv(
            Path(args.cuarentena).parent / "confirmados.csv", index=False
        )
    else:
        agregadas, dup = 0, 0

    print(f"Reportes en cuarentena (acumulados): {len(acum):,}")
    print(f"Confirmados: {len(confirmados)} -> corpus (+{agregadas}, {dup} ya existían)")
    print(f"Pendientes: {len(pend)} -> {args.pendientes_out}")


if __name__ == "__main__":
    main()
