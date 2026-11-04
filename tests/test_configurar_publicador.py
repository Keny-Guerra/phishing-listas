import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import configurar_publicador as C  # noqa: E402

ORIGINAL = Path(__file__).resolve().parents[1] / "extension" / "src" / "config.js"


class PruebasConfigurar(unittest.TestCase):
    def test_url_pages(self):
        self.assertEqual(C.url_pages("KenyG", "mis-listas"), "https://kenyg.github.io/mis-listas/")
        for malo in ["", "-a", "a-", "a--b", "a b", "a/b", "x" * 40]:
            with self.assertRaises(ValueError):
                C.url_pages(malo)
        with self.assertRaises(ValueError):
            C.url_pages("kenyg", "../x")

    def test_validar_url(self):
        self.assertEqual(C.validar_url("https://a.github.io/x/"), "https://a.github.io/x/")
        for malo in ["http://a.io/", "https://a.io", "https://CAMBIAR-USUARIO.github.io/x/", "https://a.io/ x/"]:
            with self.assertRaises(ValueError):
                C.validar_url(malo)

    def test_escribe_solo_url_base(self):
        with tempfile.TemporaryDirectory() as d:
            copia = Path(d) / "config.js"
            shutil.copyfile(ORIGINAL, copia)
            antes = copia.read_text(encoding="utf-8")
            C.escribir("https://kenyg.github.io/phishing-listas/", copia)
            despues = copia.read_text(encoding="utf-8")
            self.assertEqual(C.actual(copia), "https://kenyg.github.io/phishing-listas/")
            self.assertEqual(antes.count("\n"), despues.count("\n"))
            self.assertIn("HORAS_ENTRE_COMPROBACIONES = 24", despues)


if __name__ == "__main__":
    unittest.main()
