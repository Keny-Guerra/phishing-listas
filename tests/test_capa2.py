import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import capa2_marcas as C  # noqa: E402

M = C.cargar_marcas()


class Capa2(unittest.TestCase):
    def test_oficiales_no_se_marcan(self):
        for m in M:
            for d in m["dominios"]:
                for h in (d, f"www.{d}", f"app.{d}"):
                    self.assertIsNone(C.evaluar(h, M), h)

    def test_suplantaciones(self):
        self.assertEqual(C.evaluar("bcp-verificacion.xyz", M)["marca"], "bcp")
        self.assertEqual(C.evaluar("yappe.pe", M)["regla"], "tipeo")
        self.assertEqual(C.evaluar("rnibanco.com.pe", M)["marca"], "mibanco")
        self.assertEqual(C.evaluar("login.interbank.pages.dev", M)["severidad"], "alta")
        self.assertEqual(C.evaluar("xn--80ak6ak.com", M)["marca"], "yape")

    def test_no_marca_lo_ajeno(self):
        for h in ("example.org", "ripple.com", "briggs-riley.com", "wikipedia.org"):
            self.assertIsNone(C.evaluar(h, M), h)

    def test_lista_de_marcas_valida(self):
        ids = [m["id"] for m in M]
        self.assertEqual(len(ids), len(set(ids)))
        for m in M:
            self.assertIn(m["estado"], ("confirmado", "por_confirmar", "global"))
            self.assertTrue(m["dominios"] and m["terminos"])


if __name__ == "__main__":
    unittest.main()
