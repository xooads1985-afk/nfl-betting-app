import json
import tempfile
import unittest
from pathlib import Path
from nba_lab_lector_tarjetas import leer_tarjeta


class PruebasLector(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.t = {'esquema':'nba_tarjeta_futura_v1','partido_id':'401909966',
                  'estado':'experimental_prepartido','fecha_utc':'2099-11-12T00:00:00+00:00',
                  'generado_utc':'2099-11-11T12:00:00+00:00',
                  'local':'Indiana Pacers','visitante':'Washington Wizards',
                  'proyeccion_local_ensemble':113.44,'proyeccion_visitante_ensemble':112.07,
                  'total_ensemble':225.51,'total_modelo_c':223.10,
                  'referencia_total_base':222.05,'edge_total_vs_base':3.46,
                  'edge_total_modelo_c_vs_base':1.05,'pace_prepartido':None}

    def leer(self):
        Path(self.tmp.name,'tarjeta_401909966.json').write_text(json.dumps(self.t),encoding='utf-8')
        return leer_tarjeta(self.tmp.name,'401909966',ahora_utc='2099-11-11T12:10:00+00:00')

    def test_valida(self):
        self.assertEqual(self.leer()['edge_ensemble'],3.46)
    def test_edge_incorrecto(self):
        self.t['edge_total_vs_base']=1.05
        with self.assertRaisesRegex(ValueError,'Inconsistencia'):
            self.leer()
    def test_sin_sello(self):
        del self.t['generado_utc']
        with self.assertRaisesRegex(ValueError,'Fecha UTC ausente'):
            self.leer()
    def test_otro_id(self):
        self.t['partido_id']='123'
        with self.assertRaisesRegex(ValueError,'ID de tarjeta'):
            self.leer()
    def test_vencida(self):
        self.t['generado_utc']='2099-11-09T12:00:00+00:00'
        with self.assertRaisesRegex(ValueError,'no vigente'):
            self.leer()
    def test_partido_comenzado(self):
        self.t['fecha_utc']='2099-11-11T11:00:00+00:00'
        with self.assertRaisesRegex(ValueError,'ya comenzó'):
            self.leer()

if __name__=='__main__': unittest.main()
