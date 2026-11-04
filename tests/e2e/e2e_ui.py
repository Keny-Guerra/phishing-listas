"""E2E de las 5 pantallas de la Práctica 7 en Chromium real con la extensión cargada. Genera capturas."""
import json, sys, tempfile
from pathlib import Path
from playwright.sync_api import sync_playwright

EXT = str(Path(__file__).resolve().parents[2] / "extension")
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp())
OUT.mkdir(parents=True, exist_ok=True)
res, errores = {}, []

def chk(nombre, cond): res[nombre] = bool(cond)

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(tempfile.mkdtemp(), headless=False, viewport={"width": 1000, "height": 800}, device_scale_factor=2,
        args=["--headless=new", f"--disable-extensions-except={EXT}", f"--load-extension={EXT}", "--no-sandbox"])
    sw = ctx.service_workers[0] if ctx.service_workers else ctx.wait_for_event("serviceworker", timeout=15000)
    eid = sw.url.split("/")[2]; base = f"chrome-extension://{eid}/ui/"
    def abrir(ruta, w=1000):
        pg = ctx.new_page(); pg.set_viewport_size({"width": w, "height": 800}); pg.on("pageerror", lambda e: errores.append(f"{ruta}: {e}"))
        pg.goto(base + ruta); pg.wait_for_timeout(900); return pg
    # manifest
    nombre = ctx.new_page(); nombre.goto(base + "opciones.html"); nombre.wait_for_timeout(700)
    chk("nombre_sin_ucsm", "UCSM" not in nombre.inner_text("#nombre") and nombre.inner_text("#nombre") == "Anzuelo Alerta"); nombre.close()
    # P01
    pg = abrir("bienvenida.html")
    chk("p01_activar_deshabilitado", pg.is_disabled("#activar"))
    pg.check("#acepto"); chk("p01_activar_habilita", not pg.is_disabled("#activar"))
    pg.screenshot(path=str(OUT / "P01_bienvenida.png"))
    pg.click("#activar"); pg.wait_for_timeout(1200)
    chk("p01_pasos_fijar", pg.is_visible("#fijar")); chk("p01_modelo_verificado", "verificado" in pg.inner_text("#msg"))
    pg.screenshot(path=str(OUT / "P01_activada.png")); pg.close()
    # P02 (se abre como pestaña normal: sin pestaña activa web, se muestra como no analizable) + estados con url directa
    pg = abrir("popup.html", 360)
    chk("p02_noanalizable", "no se analiza" in pg.inner_text("#texto")); chk("p02_reportar_deshab", pg.is_disabled("#reportar"))
    pg.screenshot(path=str(OUT / "P02_popup_no_analizable.png")); pg.close()
    for nom, u, esp in [("seguro", "https://www.google.com/", "Sin riesgo"), ("peligro", "http://secure-bcp-verificacion-cuenta.xyz/login", "Peligro"), ("precaucion", "https://bcp-peru-ayuda.com/", "")]:
        pg = abrir("popup.html?url=" + u.replace(":", "%3A").replace("/", "%2F"), 360); pg.wait_for_timeout(500)
        res[f"p02_{nom}"] = pg.inner_text("#texto")
        if esp: chk(f"p02_{nom}_texto", esp in pg.inner_text("#texto"))
        chk(f"p02_{nom}_barra", pg.is_visible("#bloque-puntaje"))
        pg.screenshot(path=str(OUT / f"P02_popup_{nom}.png")); pg.close()
    # P03 por navegación real
    nav = ctx.new_page(); nav.on("pageerror", lambda e: errores.append(str(e)))
    try: nav.goto("http://secure-bcp-verificacion-cuenta.xyz/login", timeout=8000)
    except Exception: pass
    nav.wait_for_timeout(2500)
    chk("p03_bloqueo_navegacion", "ui/advertencia.html" in nav.url)
    if "ui/advertencia.html" not in nav.url:
        nav.goto(base + "advertencia.html?destino=http%3A%2F%2Fsecure-bcp-verificacion-cuenta.xyz%2Flogin&motivo=modelo_sobre_umbral_bloqueo&score=97"); nav.wait_for_timeout(800)
    chk("p03_volver_foco", nav.evaluate("document.activeElement.id") == "volver")
    chk("p03_continuar_deshab", nav.is_disabled("#seguir"))
    nav.check("#entiendo"); chk("p03_continuar_habilita", not nav.is_disabled("#seguir"))
    chk("p03_texto_umbral", "de 100" in (nav.text_content("#detalle") or "") or "señales" in (nav.text_content("#detalle") or ""))
    nav.screenshot(path=str(OUT / "P03_advertencia.png"))
    nav.goto(base + "advertencia.html?destino=http%3A%2F%2Fbcp-peru-ayuda.com%2F&motivo=modelo_sobre_umbral_bloqueo&score=97&marca=bcp"); nav.wait_for_timeout(700)
    chk("p03_aviso_marca", "imitar a BCP" in nav.inner_text("#marca"))
    nav.uncheck("#entiendo"); nav.click("#falso"); nav.wait_for_timeout(900)
    chk("p03_a_p04", "reportar.html" in nav.url and "secure-bcp" in nav.inner_input_value("#dominio") if hasattr(nav, "inner_input_value") else "reportar.html" in nav.url)
    # P04
    chk("p04_dominio_precargado", nav.input_value("#dominio") == "bcp-peru-ayuda.com")
    chk("p04_tipo_falso_positivo", nav.is_checked("input[value=falso_positivo]"))
    chk("p04_compartir_deshab_sin_optin", nav.is_disabled("#compartir"))
    nav.fill("#dominio", "no valido"); chk("p04_error_dominio", "válido" in nav.inner_text("#err-dom"))
    nav.screenshot(path=str(OUT / "P04_reportar_error.png"))
    nav.fill("#dominio", "https://www.Sitio-Seguro.com/ruta?x=1"); nav.click("#guardar"); nav.wait_for_timeout(500)
    chk("p04_guardado", "Guardado" in nav.inner_text("#msg"))
    nav.close()
    # P05
    pg = abrir("opciones.html", 820)
    chk("p05_lista_allow", "sitio-seguro.com" in pg.inner_text("#ul-allow"))
    pg.fill("#in-block", "sitio-seguro.com"); pg.click("#add-block"); chk("p05_conflicto", "otra lista" in pg.inner_text("#err-block"))
    pg.fill("#in-block", "malo-ejemplo.xyz"); pg.click("#add-block"); chk("p05_agrega_block", "malo-ejemplo.xyz" in pg.inner_text("#ul-block"))
    pg.click("#ul-block button"); chk("p05_quita_block", "Sin sitios" in pg.inner_text("#ul-block"))
    chk("p05_modelo_v8", pg.inner_text("#m-ver") == "v8"); chk("p05_verificado", "✓" in pg.inner_text("#m-verif"))
    chk("p05_umbrales", "39" in pg.inner_text("#m-umb") and "95" in pg.inner_text("#m-umb"))
    pg.click("#actualizar"); pg.wait_for_timeout(1200)
    chk("p05_actualizar_sin_publicador", "servidor de actualizaciones" in pg.inner_text("#msg-act"))
    pg.once("dialog", lambda d: d.accept())
    pg.click("#optin"); pg.wait_for_timeout(500)
    chk("p05_optin_confirma", pg.locator("dialog").count() == 1)
    pg.click("dialog button.principal"); pg.wait_for_timeout(400); chk("p05_optin_activo", pg.is_checked("#optin"))
    pg.screenshot(path=str(OUT / "P05_opciones.png"), full_page=True)
    pg.click("#restablecer"); pg.wait_for_timeout(300); pg.click("dialog button.principal"); pg.wait_for_timeout(500)
    chk("p05_restablecer", "Sin sitios" in pg.inner_text("#ul-allow") and not pg.is_checked("#optin"))
    chk("p05_modelo_conservado", pg.inner_text("#m-ver") == "v8")
    pg.close()
    chk("sin_errores_js", not errores); res["errores_js"] = errores
    ctx.close()
fallos = [k for k, v in res.items() if v is False]
print(json.dumps(res, ensure_ascii=False, indent=1)); print("FALLOS:", fallos); sys.exit(1 if fallos else 0)
