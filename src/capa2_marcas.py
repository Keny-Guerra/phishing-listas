"""
capa2_marcas.py
---------------
Capa 2 del sistema: suplantación de marcas peruanas (y algunas globales).

Idea: si el dominio contiene el nombre de una marca, o un error de tipeo o
caracteres parecidos a ese nombre, y el dominio NO es uno de los oficiales de
esa marca, se marca como sospechoso. No usa red ni aprende: es una regla
transparente y auditable. La decisión en la extensión es ADVERTIR (no bloquear)
salvo que otra capa decida bloquear.

Reglas (de más a menos fuerte):
  tipeo        un segmento del dominio es la marca con 1 error (letra de más,
               de menos, cambiada o intercambiada), caracteres parecidos
               (0→o, 1→l/i, rn→m, vv→w, letras cirílicas/griegas) o letras repetidas.
  termino      el nombre de la marca aparece completo (modo "estricto": como
               segmento entero separado por guiones; modo "amplio": también
               dentro de una palabra más larga).
Severidad "alta" si además hay una palabra de engaño (login, verifica, clave…)
o si la marca es el dominio entero con otra terminación; "media" en otro caso.

Función principal: evaluar(host, marcas) -> dict | None
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

RUTA_MARCAS = Path(__file__).resolve().parents[1] / "config" / "marcas_peru.json"

PALABRAS_ENGANO = (
    "login", "log-in", "signin", "verific", "valida", "segur", "clave", "acceso", "cuenta", "banca",
    "soporte", "ayuda", "pago", "token", "bloque", "actualiz", "confirm", "clientes", "oficial",
    "app", "web", "online", "digital", "recompensa", "premio", "gratis", "beneficio", "cobro",
)
# palabras reales cercanas a una marca
EXCEPCIONES = {"ripple", "riley", "tapes", "plain", "plan", "plano", "claro", "apple"}

_HOMO = str.maketrans({
    "0": "o", "3": "e", "4": "a", "5": "s", "7": "t", "8": "b", "$": "s", "@": "a",
    "ı": "i", "ɩ": "i", "ο": "o", "ν": "v", "α": "a", "ε": "e", "ρ": "p", "τ": "t", "κ": "k",
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "х": "x", "у": "y",
    "і": "i", "ј": "j", "ѕ": "s", "һ": "h", "ԁ": "d",
})
_SUFIJOS_2 = {"com", "org", "net", "gob", "edu", "gov", "co", "ac", "or", "ne", "go", "mil", "nom"}


def cargar_marcas(ruta: str | Path = RUTA_MARCAS) -> list[dict]:
    return json.loads(Path(ruta).read_text(encoding="utf-8"))["marcas"]


def _punycode_a_unicode(etiqueta: str) -> str:
    if etiqueta.startswith("xn--"):
        try:
            return etiqueta.encode("ascii").decode("idna")
        except Exception:  # noqa: BLE001 - etiqueta mal formada: se deja tal cual
            return etiqueta
    return etiqueta


def normalizar_host(host: str) -> str:
    h = str(host).strip().lower().split("#", 1)[0]
    h = re.sub(r"^[a-z][a-z0-9+.\-]*://", "", h)
    h = re.split(r"[/?]", h, maxsplit=1)[0].split("@")[-1]
    h = re.sub(r":\d+$", "", h).rstrip(".")
    h = re.sub(r"^www\d*\.", "", h)
    return ".".join(_punycode_a_unicode(e) for e in h.split("."))


def _etiquetas_sin_sufijo(h: str) -> list[str]:
    p = h.split(".")
    if len(p) >= 3 and p[-2] in _SUFIJOS_2 and len(p[-1]) == 2:
        return p[:-2]
    return p[:-1] if len(p) >= 2 else p


def _formas(s: str) -> set[str]:
    """Formas 'aplanadas' de un segmento para comparar con el nombre de marca."""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.translate(_HOMO).replace("rn", "m").replace("vv", "w")
    return {s.replace("1", "l"), s.replace("1", "i")}


def _colapsa(s: str) -> str:
    return re.sub(r"(.)\1+", r"\1", s)


def _dl1(a: str, b: str) -> bool:
    """True si la distancia de Damerau-Levenshtein (adyacentes) entre a y b es exactamente 1."""
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        d = [i for i in range(len(a)) if a[i] != b[i]]
        if len(d) == 1:
            return True
        return len(d) == 2 and d[1] == d[0] + 1 and a[d[0]] == b[d[1]] and a[d[1]] == b[d[0]]
    c, largo = (a, b) if len(a) < len(b) else (b, a)
    i = 0
    while i < len(c) and c[i] == largo[i]:
        i += 1
    return c[i:] == largo[i + 1 :]


def _es_oficial(host: str, marca: dict) -> bool:
    return any(host == d or host.endswith("." + d) for d in marca["dominios"])


def _segmentos(etiquetas: list[str]) -> list[str]:
    seg = []
    for e in etiquetas:
        seg.append(e)
        seg.extend(x for x in e.split("-") if x)
    return seg


def evaluar(host: str, marcas: list[dict]) -> dict | None:
    h = normalizar_host(host)
    if not h or "." not in h:
        return None
    etiquetas = _etiquetas_sin_sufijo(h)
    segs = _segmentos(etiquetas)
    engano = any(w in h for w in PALABRAS_ENGANO)
    mejor = None
    for m in marcas:
        if any(_es_oficial(h, mm) for mm in marcas if mm["id"].split("_")[0] == m["id"].split("_")[0]):
            continue
        for t in m["terminos"]:
            hit = None
            for s in segs:
                if s in EXCEPCIONES:
                    continue
                if s == t:
                    hit = ("termino", s)
                    break
                if len(t) >= 6 and m["modo"] == "amplio" and t in s:
                    hit = ("termino", s)
                    break
                if len(s) >= 3:
                    for f in _formas(s):
                        fc, tc = _colapsa(f), _colapsa(t)
                        if f == t and s != t:
                            hit = ("tipeo", s)  # caracteres parecidos (0, 1, rn, cirílico…)
                        elif len(s) >= 4 and len(t) <= 5 and fc == tc and f != t:
                            hit = ("tipeo", s)  # letras repetidas
                        elif len(s) >= 4 and len(t) >= 6 and (_dl1(f, t) or (fc == tc and f != t)):
                            hit = ("tipeo", s)  # un error de tipeo en marcas de 6+ letras
                        if hit:
                            break
                if hit:
                    break
            if hit:
                regla, seg = hit
                entero = len(etiquetas) == 1 and etiquetas[0] == seg
                sev = "alta" if (regla == "tipeo" or engano or entero) else "media"
                r = {"marca": m["id"], "nombre": m["nombre"], "regla": regla, "severidad": sev, "segmento": seg}
                if mejor is None or (sev == "alta" and mejor["severidad"] != "alta"):
                    mejor = r
    return mejor
