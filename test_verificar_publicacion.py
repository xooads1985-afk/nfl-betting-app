import tempfile
import unittest
from pathlib import Path
from verificar_publicacion import verificar

class TestPreflight(unittest.TestCase):
    def test_paquete_real(self):
        self.assertEqual(verificar(Path(__file__).parent)['modulos_estables_incluidos'],0)
    def test_faltantes_bloqueados(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,'Faltan archivos'):
                verificar(d)
    def test_modulos_estables_bloqueados(self):
        with tempfile.TemporaryDirectory() as d:
            import shutil
            raiz=Path(d)
            original=Path(__file__).parent
            for n in ('descargar_original.py','orquestar_experimental.py','publicar_historial.py','generar_prospectivas.py','proyeccion_prospectiva.py','puente_calendario_real.py','preparar_calendario.py','registro_prospectivo.py','historial_persistente.py','nfl_lab_precision.py'):
                shutil.copy2(original/n,raiz/n)
            (raiz/'main.py').write_text('')
            with self.assertRaisesRegex(ValueError,'modulo estable'):
                verificar(raiz)

if __name__=='__main__':unittest.main()
