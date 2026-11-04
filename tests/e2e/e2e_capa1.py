"""E2E de la Capa 1 real: servidor local con CORS -> la extensión descarga, verifica y aplica las listas.

Uso: python tests/e2e/e2e_capa1.py CARPETA_SALIDA_LISTAS FEED.txt SCORES_FEED.csv [CARPETA_CAPTURAS]
"""
import csv, hashlib, http.server, json, re, shutil, sys, tempfile, threading
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright

RAIZ = Path(__file__).resolve().parents[2]
SALIDA, FEED, SCORES = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
CAPT = Path(sys.argv[4]) if len(sys.argv) > 4 else Path(tempfile.mkdtemp())
CAPT.mkdir(parents=True, exist_ok=True)
PLATAFORMAS = ("pages.dev", "workers.dev", "vercel.app", "github.io", "netlify.app", "blogspot.com", "web.app", "firebaseapp.com")
pedidos = []

class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k): super().__init__(*a, directory=str(SALIDA), **k)
    def log_message(self, *a): pass
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*"); self.send_header("Access-Control-Allow-Headers", "*"); self.send_header("Cache-Control", "no-cache")
        super().end_headers()
    def do_OPTIONS(self): self.send_response(204); self.end_headers()
    def do_GET(self):
        pedidos.append(self.path)
        if self.path == "/manifest.json":
            cuerpo = (SALIDA / "manifest.json").read_bytes(); etag = '"' + hashlib.sha256(cuerpo).hexdigest()[:16] + '"'
            if self.headers.get("If-None-Match") == etag: self.send_response(304); self.send_header("ETag", etag); self.end_headers(); return
            self.send_response(200); self.send_header("ETag", etag); self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Expose-Headers", "ETag"); self.send_header("Content-Length", str(len(cuerpo))); self.end_headers(); self.wfile.write(cuerpo); return
        super().do_GET()

srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H); puerto = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()

# Copia de la extensión apuntando al servidor local (la original no se toca).
ext = Path(tempfile.mkdtemp()) / "ext"
shutil.copytree(RAIZ / "extension", ext, ignore=shutil.ignore_patterns("node_modules", "tests"))
cfg = ext / "src" / "config.js"
cfg.write_text(re.sub(r'URL_BASE = "[^"]*"', f'URL_BASE = "http://127.0.0.1:{puerto}/"', cfg.read_text(encoding="utf-8")), encoding="utf-8")

# Casos reales del feed: hosts que el modelo puntúa BAJO y que no son plataformas -> solo la lista puede detenerlos.
bajos = [r["host"] for r in csv.DictReader(open(SCORES)) if float(r["score"]) < 0.30 and not r["host"].endswith(PLATAFORMAS)]
urls_feed = [u.strip() for u in FEED.read_text().splitlines() if u.strip()]
en_plataforma = next(u for u in urls_feed if urlsplit(u).hostname.endswith("pages.dev") and urlsplit(u).path not in ("", "/"))
res, errores = {"hosts_bajos_disponibles": len(bajos)}, []
def chk(n, c): res[n] = bool(c)

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(tempfile.mkdtemp(), headless=False, viewport={"width": 1000, "height": 800}, device_scale_factor=2,
        args=["--headless=new", f"--disable-extensions-except={ext}", f"--load-extension={ext}", "--no-sandbox"])
    sw = ctx.service_workers[0] if ctx.service_workers else ctx.wait_for_event("serviceworker", timeout=15000)
    eid = sw.url.split("/")[2]; base = f"chrome-extension://{eid}/ui/"
    pg = ctx.new_page(); pg.on("pageerror", lambda e: errores.append(str(e)))
    pg.goto(base + "opciones.html"); pg.wait_for_timeout(1500)  # onInstalled ya intentó actualizar
    pg.reload(); pg.wait_for_timeout(1000)
    chk("listas_descargadas_al_instalar", "3 lista" in pg.inner_text("#m-listas"))
    chk("modelo_incluido_no_se_vuelve_a_bajar", not any(".onnx" in x for x in pedidos))
    chk("modelo_sigue_v8_incluido", pg.inner_text("#m-ver") == "v8" and "✓" in pg.inner_text("#m-verif"))
    pg.click("#actualizar"); pg.wait_for_timeout(1500)
    chk("boton_sin_cambios_304", "más recientes" in pg.inner_text("#msg-act"))
    pg.screenshot(path=str(CAPT / "P05_con_listas.png"), full_page=True)

    def navegar(url):
        t = ctx.new_page()
        try: t.goto(url, timeout=6000)
        except Exception: pass
        t.wait_for_timeout(1800); return t
    bloqueados = 0
    for h in bajos[:8]:
        t = navegar(f"http://{h}/"); bloqueados += "ui/advertencia.html" in t.url
        if h == bajos[0]: mostrado = t.inner_text("#porque") if "advertencia.html" in t.url else ""; t.screenshot(path=str(CAPT / "P03_bloqueo_por_lista.png"))
        t.close()
    res["probados_hosts_bajos"] = min(8, len(bajos)); res["bloqueados_por_lista"] = bloqueados
    chk("todos_los_hosts_bajos_bloqueados", bloqueados == min(8, len(bajos)) and bloqueados > 0)
    chk("motivo_lista_del_dia", "lista de sitios fraudulentos del día" in mostrado)
    t = navegar(en_plataforma); chk("url_en_plataforma_bloqueada", "ui/advertencia.html" in t.url); t.close()
    # Misma plataforma, otra ruta: la lista de URLs NO debe bloquear por sí sola todo el host (el modelo es quien decide).
    # Popup sobre un sitio popular: lo decide la lista de permitidos.
    pu = ctx.new_page(); pu.goto(base + "popup.html?url=https%3A%2F%2Fwww.bcp.com.pe%2F"); pu.wait_for_timeout(900)
    chk("popular_permitido_por_lista", "Sitio popular" in pu.inner_text("#motivo")); pu.screenshot(path=str(CAPT / "P02_popular_por_lista.png")); pu.close()
    pb = ctx.new_page(); pb.goto(base + "popup.html?url=" + f"http%3A%2F%2F{bajos[0]}%2F"); pb.wait_for_timeout(900)
    chk("popup_peligro_por_lista", "Peligro" in pb.inner_text("#texto") and "del día" in pb.inner_text("#motivo")); pb.screenshot(path=str(CAPT / "P02_peligro_por_lista.png")); pb.close()
    chk("sin_errores_js", not errores); res["errores_js"] = errores
    ctx.close()
res["pedidos_al_servidor"] = len(pedidos)
fallos = [k for k, v in res.items() if v is False]
print(json.dumps(res, ensure_ascii=False, indent=1)); print("FALLOS:", fallos); sys.exit(1 if fallos else 0)
