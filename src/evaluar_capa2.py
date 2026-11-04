"""
evaluar_capa2.py — evalúa la Capa 2 (marcas) y deja evidencia en JSON.

Uso:
  python src/evaluar_capa2.py --v7 <carpeta con train/val/test_urls.csv> \
      [--feed openphish_AAAA-MM-DD.txt] [--scores-feed scores.csv] --salida docs/calidad/capa2_evaluacion.json

Mide: (1) falsos positivos sobre legítimas, (2) cuánto phishing real marca,
(3) cuántos de los casos que el modelo NO detectó (si se da --scores-feed con
columnas host,score) rescata, (4) cobertura de las reglas sobre variantes
sintéticas (NO es una medida de desempeño real: las variantes salen de las
mismas familias de error que las reglas) y (5) que ningún dominio oficial se marque.
"""
import argparse
import glob
import json
import random
from collections import Counter
from pathlib import Path

import pandas as pd

import capa2_marcas as C

TLDS = (".com", ".xyz", ".top", ".pe", ".com.pe", ".net", ".online")
PALABRAS = ("login", "verificacion", "seguro", "clientes", "soporte", "acceso")
HOMO = {"o": "0", "l": "1", "i": "1", "e": "3", "a": "4", "s": "5", "m": "rn", "w": "vv"}


def variantes(term: str, rng: random.Random):
    out = {"omision": [], "duplicada": [], "intercambio": [], "caracter_parecido": [], "marca_mas_palabra": [], "marca_en_subdominio": []}
    if len(term) >= 4:
        i = rng.randrange(1, len(term) - 1)
        out["omision"].append(term[:i] + term[i + 1:])
        out["duplicada"].append(term[:i] + term[i] + term[i:])
        j = rng.randrange(1, len(term) - 2) if len(term) > 3 else 1
        out["intercambio"].append(term[:j] + term[j + 1] + term[j] + term[j + 2:])
        pos = [k for k, ch in enumerate(term) if ch in HOMO]
        if pos:
            k = rng.choice(pos)
            out["caracter_parecido"].append(term[:k] + HOMO[term[k]] + term[k + 1:])
    out["marca_mas_palabra"].append(f"{term}-{rng.choice(PALABRAS)}")
    out["marca_en_subdominio"].append(f"{term}.{rng.choice(['pages','vercel','web'])}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--v7", required=True)
    ap.add_argument("--feed", default=None)
    ap.add_argument("--scores-feed", default=None)
    ap.add_argument("--salida", required=True)
    a = ap.parse_args()
    M = C.cargar_marcas()
    res = {"marcas": len(M), "estados": dict(Counter(m["estado"] for m in M))}

    df = pd.concat([pd.read_csv(f) for f in glob.glob(str(Path(a.v7) / "**" / "*_urls.csv"), recursive=True)], ignore_index=True)
    df["host"] = df.url.map(C.normalizar_host)
    df = df.drop_duplicates("host")
    leg, phi = df[df.label == 0], df[df.label == 1]
    fl = leg.host.map(lambda h: C.evaluar(h, M))
    fp = phi.host.map(lambda h: C.evaluar(h, M))
    res["legitimas"] = {"n": int(len(leg)), "marcadas": int(fl.notna().sum()), "fpr_%": round(100 * fl.notna().mean(), 3),
                        "ejemplos": [h for h, r in zip(leg.host, fl, strict=True) if r][:15],
                        "por_regla": dict(Counter(r["regla"] for r in fl if r))}
    res["phishing_v7"] = {"n": int(len(phi)), "marcadas": int(fp.notna().sum()), "%": round(100 * fp.notna().mean(), 2),
                          "por_marca": dict(Counter(r["marca"] for r in fp if r).most_common(10))}

    if a.feed:
        hosts = sorted({C.normalizar_host(u) for u in Path(a.feed).read_text().split("\n") if u.startswith("http")})
        fr = {h: C.evaluar(h, M) for h in hosts}
        res["feed"] = {"n": len(hosts), "marcadas": sum(1 for r in fr.values() if r),
                       "marcadas_sin_roblox": sum(1 for r in fr.values() if r and r["marca"] != "roblox"),
                       "ejemplos": [(h, r["marca"], r["regla"]) for h, r in fr.items() if r][:15]}
        if a.scores_feed:
            sc = pd.read_csv(a.scores_feed)
            miss = [h for h, s in zip(sc.host, sc.score, strict=True) if s < 0.386]
            resc = [h for h in miss if C.evaluar(h, M)]
            res["feed"].update({"perdidos_por_modelo": len(miss), "rescatados_por_capa2": len(resc),
                                "rescatados_sin_roblox": sum(1 for h in resc if C.evaluar(h, M)["marca"] != "roblox"),
                                "ejemplos_rescatados": resc[:10]})

    rng = random.Random(42)  # nosec B311: semilla fija para muestreo reproducible, no es criptografía
    cats = {}
    for m in M:
        if m["estado"] == "global":
            continue
        for t in m["terminos"]:
            for cat, lst in variantes(t, rng).items():
                for v in lst:
                    for tld in rng.sample(TLDS, 2):
                        h = v + tld if cat != "marca_en_subdominio" else v + ".dev"
                        ok = bool(C.evaluar(h, M))
                        c = cats.setdefault(cat, [0, 0]); c[0] += ok; c[1] += 1
    res["sinteticas_cobertura_de_reglas"] = {k: {"detectadas": v[0], "n": v[1], "%": round(100 * v[0] / v[1], 1)} for k, v in cats.items()}

    oficiales = [d for m in M for d in m["dominios"]]
    malos = [d for d in oficiales if C.evaluar(d, M)] + [f"www.{d}" for d in oficiales if C.evaluar("www." + d, M)] + [f"app.{d}" for d in oficiales if C.evaluar("app." + d, M)]
    res["oficiales_marcados_por_error"] = malos
    Path(a.salida).parent.mkdir(parents=True, exist_ok=True)
    Path(a.salida).write_text(json.dumps(res, ensure_ascii=False, indent=2))
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
