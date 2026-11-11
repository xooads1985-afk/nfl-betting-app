import json
import tempfile
import unittest
from pathlib import Path
from nba_lab_adaptador_visual import obtener_vista

class TestAdaptador(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.card = {
            'esquema':'nba_tarjeta_futura_v1','partido_id':'401909966',
            'estado':'experimental_prepartido',
            'fecha_utc':'2099-11-12T00:00:00+00:00',
            'generado_utc':'2099-11-11T12:00:00+00:00',
            'local':'Indiana Pacers','visitante':'Washington Wizards',
            'proyeccion_local_ensemble':113.44,
            'proyeccion_visitante_ensemble':112.07,
            'total_ensemble':225.51,'total_modelo_c':223.10,
            'referencia_total_base':222.05,
            'edge_total_vs_base':3.46,
            'edge_total_modelo_c_vs_base':1.05,
            'pace_prepartido':None,
        }
    def guardar(self):
        Path(self.temp.name,'tarjeta_401909966.json').write_text(json.dumps(self.card),encoding='utf-8')
    def leer(self):
        return obtener_vista(self.temp.name,'401909966',ahora_utc='2099-11-11T12:10:00+00:00')
    def test_vista(self):
        self.guardar()
        d=self.leer()
        self.assertEqual(d['total_ensemble'],225.51)
        self.assertEqual(d['edge_modelo_c'],1.05)
        self.assertIsNone(d['pace'])
    def test_ausente(self):
        with self.assertRaises(FileNotFoundError):self.leer()
    def test_id_erroneo(self):
        self.card['partido_id']='999';self.guardar()
        with self.assertRaises(ValueError):self.leer()
    def test_edge_inconsistente(self):
        self.card['edge_total_vs_base']=1.05;self.guardar()
        with self.assertRaises(ValueError):self.leer()
    def test_vencida(self):
        self.card['generado_utc']='2099-11-09T12:00:00+00:00';self.guardar()
        with self.assertRaises(ValueError):self.leer()

if __name__=='__main__': unittest.main()
