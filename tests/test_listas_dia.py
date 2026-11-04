import hashlib
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import listas_dia as L  # noqa: E402

TRANCO = "\n".join(f"{i},{d}" for i, d in enumerate(["google.com", "www.facebook.com", "github.io", "bcp.com.pe"], 1))
FEED = "\n".join(
    [
        "http://secure-bcp-verificacion.xyz/login",
        "https://www.Banco-Falso.top/a?b=1#x",
        "https://usuario.github.io/paypal-login",
        "https://mi-tienda.blogspot.com/fraude",
        "https://google.com/redirect?u=evil",
        "http://203.0.113.9/promo",
        "ftp://raro.example/x",
        "# comentario",
        "",
    ]
)


class PruebasListas(unittest.TestCase):
    def test_huella_y_orden(self):
        h = L.huella("example.com")
        self.assertEqual(h, struct.unpack(">I", hashlib.sha256(b"example.com").digest()[:4])[0])
        datos = L.a_bin([5, 1, 3, 3])
        self.assertEqual(struct.unpack(">3I", datos), (1, 3, 5))

    def test_host_y_url_normalizada(self):
        self.assertEqual(L.host_de("https://WWW.Banco-Falso.top:8080/a?b=1#x"), "banco-falso.top")
        self.assertEqual(L.url_normalizada("https://www.Banco-Falso.top/a/#x"), "banco-falso.top/a")

    def test_hosting_compartido_y_populares_van_por_url(self):
        r = L.construir(FEED, TRANCO, 100, 3, 0.5)
        self.assertEqual(r["estadisticas"]["hosts_bloqueo"], 4)  # bcp-falso, banco-falso, ip, raro.example
        self.assertEqual(r["estadisticas"]["urls_bloqueo"], 3)  # github.io, blogspot, google.com
        bloqueo = set(struct.unpack(f">{len(r['bloqueo']) // 4}I", r["bloqueo"]))
        self.assertNotIn(L.huella("github.io"), bloqueo)
        self.assertNotIn(L.huella("google.com"), bloqueo)
        self.assertIn(L.huella("banco-falso.top"), bloqueo)

    def test_prueba_previa_feed_pequeno(self):
        with self.assertRaises(L.PruebaPreviaError):
            L.construir(FEED, TRANCO, 100, 50, 0.5)

    def test_manifest_con_huellas(self):
        r = L.construir(FEED, TRANCO, 100, 3, 0.5)
        with tempfile.TemporaryDirectory() as d:
            m = L.escribir(Path(d), r, "2026-10-23")
            for desc in m["listas"].values():
                datos = (Path(d) / desc["archivo"]).read_bytes()
                self.assertEqual(desc["sha256"], hashlib.sha256(datos).hexdigest())
                self.assertEqual(desc["bytes"], len(datos))
            self.assertEqual(json.loads((Path(d) / "manifest.json").read_text())["schema"], L.SCHEMA)

    def test_fixture_compartido_con_javascript(self):
        """El mismo archivo lo lee extension/tests/listas.test.js: garantiza la paridad Python <-> JS."""
        hosts = ["secure-bcp-verificacion.xyz", "banco-falso.top", "ejemplo.pe"]
        datos = L.a_bin(L.huella(h) for h in hosts)
        ruta = Path(__file__).resolve().parents[1] / "extension" / "tests" / "fixtures" / "bloqueo_ejemplo.bin"
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_bytes(datos)
        self.assertEqual(len(datos), 12)


if __name__ == "__main__":
    unittest.main()


class PruebasVerificacion(unittest.TestCase):
    def _generar(self, d):
        r = L.construir(FEED, TRANCO, 100, 3, 0.5)
        L.escribir(Path(d), r, "2026-11-04", None, r["estadisticas"])

    def test_salida_correcta_y_estadisticas_sin_urls(self):
        with tempfile.TemporaryDirectory() as d:
            self._generar(d)
            self.assertEqual(L.verificar_salida(Path(d), 1), [])
            m = json.loads((Path(d) / "manifest.json").read_text(encoding="utf-8"))
            self.assertIn("urls_feed", m["estadisticas"])
            self.assertNotIn("banco-falso", json.dumps(m))

    def test_detecta_archivo_alterado_y_permitidos_chico(self):
        with tempfile.TemporaryDirectory() as d:
            self._generar(d)
            (Path(d) / "bloqueo.bin").write_bytes(b"\x00\x00\x00\x02\x00\x00\x00\x01")
            problemas = L.verificar_salida(Path(d), 1)
            self.assertTrue(any("SHA-256" in p for p in problemas))
            self.assertTrue(any("permitidos tiene menos" in p for p in L.verificar_salida(Path(d), 1000)))

    def test_main_con_modelo_publica_v8(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as o:
            (Path(d) / "f.txt").write_text(FEED, encoding="utf-8")
            (Path(d) / "t.csv").write_text(TRANCO, encoding="utf-8")
            ext = Path(__file__).resolve().parents[1] / "extension" / "models"
            args = ["--phishing-file", str(Path(d) / "f.txt"), "--tranco-file", str(Path(d) / "t.csv"), "--salida", o]
            args += ["--min-feed", "3", "--min-permitidos", "1", "--modelo-onnx", str(ext / "cnn_phishing.onnx")]
            args += ["--umbrales", str(ext / "umbrales_sugeridos.json")]
            rc = L.main(args)
            self.assertEqual(rc, 0)
            m = json.loads((Path(o) / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(m["modelo"]["version"], "v8")
            self.assertEqual(m["modelo"]["sha256"], json.loads((ext / "huella.json").read_text())["sha256"])
