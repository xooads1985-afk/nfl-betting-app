
import shutil
import tempfile
import unittest
from pathlib import Path

from verificar_publicacion import REQUERIDOS, verificar


class TestPreflight(unittest.TestCase):

    def preparar_paquete(self, raiz):
        origen = Path(__file__).parent

        for nombre in REQUERIDOS:
            shutil.copy2(origen / nombre, raiz / nombre)

        carpeta = raiz / ".github" / "workflows"
        carpeta.mkdir(parents=True, exist_ok=True)

        contenido = """
laboratorio-nfl-validacion
historial-nfl-lab
descargar_original.py
orquestar_experimental.py
publicar_historial.py
git push origin HEAD:historial-nfl-lab
"""
        (carpeta / "laboratorio-nfl-integral.yml").write_text(
            contenido, encoding="utf-8"
        )

    def test_paquete_real(self):
        with tempfile.TemporaryDirectory() as temporal:
            raiz = Path(temporal)
            self.preparar_paquete(raiz)

            resultado = verificar(raiz)

            self.assertEqual(
                resultado["modulos_estables_incluidos"], 0
            )

    def test_faltantes_bloqueados(self):
        with tempfile.TemporaryDirectory() as temporal:
            with self.assertRaisesRegex(ValueError, "Faltan archivos"):
                verificar(temporal)

    def test_modulos_estables_bloqueados(self):
        with tempfile.TemporaryDirectory() as temporal:
            raiz = Path(temporal)
            self.preparar_paquete(raiz)

            (raiz / "main.py").write_text("", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "modulo estable"):
                verificar(raiz)


if __name__ == "__main__":
    unittest.main()
