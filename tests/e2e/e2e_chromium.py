"""Prueba de extremo a extremo en Chromium real: carga la extensión, puntúa URLs con ONNX Runtime Web
(offscreen) y mide la latencia real dentro del navegador. Uso: python3 tests/e2e/e2e_chromium.py"""

import json
import statistics
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

EXT = str(Path(__file__).resolve().parents[2] / "extension")
CASOS = [
    ("https://www.google.com/", "permitir"),
    ("https://secure-bcp-verificacion-cuenta.xyz/login", "bloquear_o_advertir"),
]

with sync_playwright() as p, tempfile.TemporaryDirectory() as ud:
    ctx = p.chromium.launch_persistent_context(
        ud,
        headless=False,
        args=["--headless=new", f"--disable-extensions-except={EXT}", f"--load-extension={EXT}", "--no-sandbox"],
    )
    sw = ctx.service_workers[0] if ctx.service_workers else ctx.wait_for_event("serviceworker", timeout=15000)
    ext_id = sw.url.split("/")[2]
    page = ctx.new_page()
    page.goto(f"chrome-extension://{ext_id}/ui/opciones.html")
    out = {"ext_id": ext_id, "casos": [], "latencias_ms": []}
    js = "(u)=>chrome.runtime.sendMessage({destino:'background',tipo:'evaluar',url:u})"
    for url, esperado in CASOS:
        t = time.time()
        r = page.evaluate(js, url)
        out["casos"].append(
            {"url": url, "esperado": esperado, "obtenido": r, "ms_primera": round((time.time() - t) * 1000, 1)}
        )
    # latencia de puntuación directa vía offscreen (sin cache): URLs distintas
    for i in range(300):
        t = time.perf_counter()
        page.evaluate(js, f"https://sitio{i}-ejemplo-{i * 7}.com/")
        out["latencias_ms"].append((time.perf_counter() - t) * 1000)
    lat = sorted(out["latencias_ms"])
    out["p50_ms"] = round(statistics.median(lat), 2)
    out["p95_ms"] = round(lat[int(0.95 * len(lat)) - 1], 2)
    del out["latencias_ms"]
    print(json.dumps(out, ensure_ascii=False, indent=1))
    ctx.close()
