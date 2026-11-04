"""
configurar_publicador.py
------------------------
Escribe la dirección pública de las listas (GitHub Pages) en extension/src/config.js.

Uso:
    python scripts/configurar_publicador.py TU_USUARIO_GITHUB [NOMBRE_DEL_REPOSITORIO]
    python scripts/configurar_publicador.py --url https://otro-alojamiento.example/listas/
    python scripts/configurar_publicador.py --comprobar        # solo muestra el valor actual

Después de cambiarla hay que volver a cargar la extensión en chrome://extensions.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

CONFIG = Path(__file__).resolve().parents[1] / "extension" / "src" / "config.js"
PATRON = re.compile(r'(export const URL_BASE = ")([^"]*)(";)')
USUARIO = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
REPO = re.compile(r"^[A-Za-z0-9._-]{1,100}$")


def url_pages(usuario: str, repo: str = "phishing-listas") -> str:
    if not USUARIO.match(usuario) or usuario.endswith("-") or "--" in usuario:
        raise ValueError("usuario de GitHub no válido (letras, números y guiones; sin guion al inicio/fin)")
    if not REPO.match(repo) or repo in {".", ".."}:
        raise ValueError("nombre de repositorio no válido")
    return f"https://{usuario.lower()}.github.io/{repo}/"


def validar_url(url: str) -> str:
    if not re.match(r"^https://[A-Za-z0-9.-]+(:\d+)?(/[A-Za-z0-9._~%-]*)*/$", url):
        raise ValueError("la dirección debe ser https://… y terminar en «/»")
    if "CAMBIAR" in url.upper():
        raise ValueError("la dirección todavía es el marcador de posición")
    return url


def escribir(url: str, ruta: Path = CONFIG) -> str:
    texto = ruta.read_text(encoding="utf-8")
    if not PATRON.search(texto):
        raise RuntimeError("no se encontró URL_BASE en config.js")
    ruta.write_text(PATRON.sub(lambda m: f"{m.group(1)}{url}{m.group(3)}", texto, count=1), encoding="utf-8")
    return url


def actual(ruta: Path = CONFIG) -> str:
    m = PATRON.search(ruta.read_text(encoding="utf-8"))
    return m.group(2) if m else ""


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("usuario", nargs="?")
    p.add_argument("repo", nargs="?", default="phishing-listas")
    p.add_argument("--url")
    p.add_argument("--comprobar", action="store_true")
    a = p.parse_args(argv)
    if a.comprobar:
        print(actual())
        return 0
    try:
        if a.url:
            url = validar_url(a.url)
        elif a.usuario:
            url = validar_url(url_pages(a.usuario, a.repo))
        else:
            p.error("indica tu usuario de GitHub o --url")
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    escribir(url)
    print(f"URL_BASE = {url}\nVuelve a cargar la extensión en chrome://extensions.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
