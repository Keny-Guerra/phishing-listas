"""
listas_dia.py
-------------
Capa 1 del diseño (listas del día), lado del PUBLICADOR (fuera del dispositivo del usuario).

Toma los feeds completos (OpenPhish y Tranco), los procesa y genera archivos compactos que la
extensión descarga: huellas de 4 bytes ordenadas (primeros 4 bytes de SHA-256, big-endian) y un
manifest.json con la versión y el SHA-256 de cada archivo. Así el usuario nunca descarga los feeds.

Archivos generados en --salida:
    bloqueo.bin         huellas de hosts del feed que NO son compartidos ni populares
    bloqueo_urls.bin    huellas de la URL completa para hosts de alojamiento compartido o populares
    permitidos.bin      huellas de los N dominios más populares (Tranco)
    manifest.json       versiones, tamaños, huellas SHA-256 y (opcional) datos del modelo

Prueba previa a publicar (falla si no se cumple, y entonces no se publica nada):
    - el feed produjo al menos --min-feed URLs;
    - ningún host de `bloqueo.bin` está en el top de permitidos;
    - los conflictos por colisión de huella no superan --max-colisiones.

Uso:
    python src/listas_dia.py --phishing-file feed.txt --tranco-file top-1m.csv --salida publicado/
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import struct
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

SCHEMA = 1
HOSTING_COMPARTIDO = {
    "blogspot.com",
    "github.io",
    "gitlab.io",
    "weebly.com",
    "wixsite.com",
    "sites.google.com",
    "firebaseapp.com",
    "web.app",
    "netlify.app",
    "vercel.app",
    "pages.dev",
    "herokuapp.com",
    "000webhostapp.com",
    "glitch.me",
    "webflow.io",
    "wordpress.com",
    "godaddysites.com",
    "mystrikingly.com",
    "ipfs.io",
    "workers.dev",
    "onrender.com",
    "repl.co",
}


class PruebaPreviaError(RuntimeError):
    """La prueba previa a publicar falló: no se publica nada."""


def sin_www(host: str) -> str:
    return host[4:] if host.startswith("www.") else host


def host_de(url: str) -> str:
    u = url.strip()
    if "://" not in u:
        u = "http://" + u
    try:
        h = urlsplit(u).hostname or ""
    except ValueError:
        return ""
    return sin_www(h.lower().rstrip("."))


def url_normalizada(url: str) -> str:
    """Misma idea que normalize.js (modo completa): minúsculas, sin fragmento, esquema, www ni '/' final."""
    u = url.strip().lower().split("#")[0]
    if "://" in u:
        u = u.split("://", 1)[1]
    if u.startswith("www."):
        u = u[4:]
    return u.rstrip("/")


def huella(texto: str) -> int:
    return struct.unpack(">I", hashlib.sha256(texto.encode("utf-8")).digest()[:4])[0]


def a_bin(huellas) -> bytes:
    ordenadas = sorted(set(huellas))
    return b"".join(struct.pack(">I", h) for h in ordenadas)


def _es_compartido(host: str) -> bool:
    return any(host == d or host.endswith("." + d) for d in HOSTING_COMPARTIDO)


def leer_tranco(texto: str, n: int) -> list[str]:
    """CSV 'rank,dominio'. Devuelve los n primeros dominios (sin www)."""
    dominios = []
    for linea in texto.splitlines():
        partes = linea.strip().split(",")
        if len(partes) >= 2 and partes[0].isdigit():
            dominios.append(sin_www(partes[1].strip().lower()))
            if len(dominios) >= n:
                break
    return dominios


def construir(feed: str, tranco: str, n_top: int, min_feed: int, max_colisiones: float) -> dict:
    urls = [ln.strip() for ln in feed.splitlines() if ln.strip() and not ln.startswith("#")]
    if len(urls) < min_feed:
        raise PruebaPreviaError(f"el feed trae {len(urls)} URL (mínimo {min_feed})")
    top = leer_tranco(tranco, n_top)
    top_set = set(top)

    hosts_bloqueo, urls_bloqueo, descartados = set(), set(), 0
    for u in urls:
        h = host_de(u)
        if not h:
            descartados += 1
        elif h in top_set or _es_compartido(h):
            urls_bloqueo.add(url_normalizada(u))  # no se bloquea el host: se bloquea la URL
        else:
            hosts_bloqueo.add(h)

    if hosts_bloqueo & top_set:  # no debería pasar por construcción
        raise PruebaPreviaError("un host del top aparece en la lista de bloqueo")
    h_perm = {huella(d) for d in top}
    h_bloq = {huella(h) for h in hosts_bloqueo}
    colisiones = len(h_perm & h_bloq)
    if hosts_bloqueo and colisiones / len(hosts_bloqueo) > max_colisiones:
        raise PruebaPreviaError(f"{colisiones} colisiones de huella entre bloqueo y permitidos")

    return {
        "bloqueo": a_bin(h_bloq),
        "bloqueo_urls": a_bin(huella(u) for u in urls_bloqueo),
        "permitidos": a_bin(h_perm),
        "estadisticas": {
            "urls_feed": len(urls),
            "descartadas": descartados,
            "hosts_bloqueo": len(hosts_bloqueo),
            "urls_bloqueo": len(urls_bloqueo),
            "permitidos": len(top_set),
            "colisiones": colisiones,
        },
    }


def escribir(
    salida: Path, listas: dict, version: str, modelo: dict | None = None, estadisticas: dict | None = None
) -> dict:
    salida.mkdir(parents=True, exist_ok=True)
    manifest = {"schema": SCHEMA, "generado": version, "listas": {}}
    for nombre in ("bloqueo", "bloqueo_urls", "permitidos"):
        datos = listas[nombre]
        (salida / f"{nombre}.bin").write_bytes(datos)
        manifest["listas"][nombre] = {
            "version": version,
            "archivo": f"{nombre}.bin",
            "bytes": len(datos),
            "n": len(datos) // 4,
            "sha256": hashlib.sha256(datos).hexdigest(),
        }
    if modelo:
        manifest["modelo"] = modelo
    if estadisticas:
        manifest["estadisticas"] = estadisticas  # solo conteos: sin URLs ni dominios
    (salida / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest


def descriptor_modelo(onnx: Path, umbrales: Path, version: str) -> dict:
    datos = onnx.read_bytes()
    u = json.loads(umbrales.read_text(encoding="utf-8"))
    return {
        "version": version,
        "archivo": onnx.name,
        "bytes": len(datos),
        "sha256": hashlib.sha256(datos).hexdigest(),
        "umbral_advertencia": u["umbral_advertencia"],
        "umbral_bloqueo": u["umbral_bloqueo"],
    }


MAX_BYTES_LISTA = 5_000_000  # mismos límites que extension/src/config.js
MAX_BYTES_MODELO = 3_000_000


def verificar_salida(salida: Path, min_permitidos: int = 1000) -> list[str]:
    """Relee lo generado como lo hará la extensión: tamaños, SHA-256, orden de huellas y límites. [] = todo bien."""
    problemas: list[str] = []
    try:
        m = json.loads((salida / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return [f"manifest.json ilegible: {e}"]
    if m.get("schema") != SCHEMA:
        problemas.append("schema inesperado")
    descriptores = dict(m.get("listas", {}))
    if "modelo" in m:
        descriptores["modelo"] = m["modelo"]
    for nombre in ("bloqueo", "bloqueo_urls", "permitidos"):
        if nombre not in descriptores:
            problemas.append(f"falta la lista {nombre}")
    for nombre, d in descriptores.items():
        try:
            datos = (salida / d["archivo"]).read_bytes()
        except (OSError, KeyError):
            problemas.append(f"{nombre}: archivo ausente")
            continue
        limite = MAX_BYTES_MODELO if nombre == "modelo" else MAX_BYTES_LISTA
        if len(datos) != d["bytes"] or len(datos) > limite:
            problemas.append(f"{nombre}: tamaño incorrecto o excede el límite")
        if hashlib.sha256(datos).hexdigest() != d["sha256"]:
            problemas.append(f"{nombre}: SHA-256 distinto")
        if nombre != "modelo":
            hs = struct.unpack(f">{len(datos) // 4}I", datos) if len(datos) % 4 == 0 else None
            if hs is None or list(hs) != sorted(set(hs)):
                problemas.append(f"{nombre}: huellas desordenadas, repetidas o truncadas")
    if m.get("listas", {}).get("permitidos", {}).get("n", 0) < min_permitidos:
        problemas.append(f"permitidos tiene menos de {min_permitidos} dominios (¿falló Tranco?)")
    return problemas


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--phishing-file", required=True, help="feed de OpenPhish (texto plano, una URL por línea)")
    p.add_argument("--tranco-file", required=True, help="CSV rank,dominio de Tranco")
    p.add_argument("--salida", default="publicado")
    p.add_argument("--n-top", type=int, default=100_000)
    p.add_argument("--min-feed", type=int, default=50)
    p.add_argument("--min-permitidos", type=int, default=1000)
    p.add_argument("--max-colisiones", type=float, default=0.01)
    p.add_argument("--modelo-onnx")
    p.add_argument("--umbrales")
    p.add_argument("--version-modelo", default="v8")
    p.add_argument("--version", default=date.today().isoformat())
    a = p.parse_args(argv)
    try:
        r = construir(
            Path(a.phishing_file).read_text(encoding="utf-8", errors="ignore"),
            Path(a.tranco_file).read_text(encoding="utf-8", errors="ignore"),
            a.n_top,
            a.min_feed,
            a.max_colisiones,
        )
    except PruebaPreviaError as e:
        print(f"NO SE PUBLICA: {e}", file=sys.stderr)
        return 2
    modelo = (
        descriptor_modelo(Path(a.modelo_onnx), Path(a.umbrales), a.version_modelo)
        if a.modelo_onnx and a.umbrales
        else None
    )
    m = escribir(Path(a.salida), r, a.version, modelo, r["estadisticas"])
    if modelo:  # el manifiesto apunta al archivo: debe publicarse junto a las listas
        shutil.copyfile(a.modelo_onnx, Path(a.salida) / modelo["archivo"])
    problemas = verificar_salida(Path(a.salida), a.min_permitidos)
    if problemas:
        print("NO SE PUBLICA: " + "; ".join(problemas), file=sys.stderr)
        return 3
    print(
        json.dumps(
            {"estadisticas": r["estadisticas"], "bytes": {k: v["bytes"] for k, v in m["listas"].items()}}, indent=2
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
