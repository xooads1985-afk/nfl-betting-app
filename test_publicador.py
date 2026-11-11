import json
import tempfile
import unittest
from pathlib import Path
from nba_lab_publicador import publicar

class TestPublicador(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.root=Path(self.t.name)
        self.o=self.root/'origen'
        self.d=self.root/'publicado'
        self.o.mkdir()
        self.card={'esquema':'nba_tarjeta_futura_v1','partido_id':'123',
            'estado':'experimental_prepartido','fecha_utc':'2099-11-12T00:00:00+00:00',
            'generado_utc':'2099-11-11T12:00:00+00:00','local':'A','visitante':'B',
            'proyeccion_local_ensemble':110,'proyeccion_visitante_ensemble':112,
            'total_ensemble':222,'total_modelo_c':223,'referencia_total_base':220,
            'edge_total_vs_base':2,'edge_total_modelo_c_vs_base':3,'pace_prepartido':None}
        (self.o/'tarjeta_123.json').write_text(json.dumps(self.card))
        self.index={'tarjetas':[{'id':'123','archivo':'tarjeta_123.json'}],'errores':[]}
        self.write_index()
    def write_index(self):
        (self.o/'indice_tarjetas.json').write_text(json.dumps(self.index))
    def publish(self):
        return publicar(self.o,self.d,ahora_utc='2099-11-11T12:05:00+00:00')
    def test_publica_y_lee(self):
        i=self.publish()
        self.assertEqual(i['cantidad'],1)
        self.assertTrue((self.d/'tarjeta_123.json').exists())
    def test_no_publica_si_errores(self):
        self.index['errores']=[{'id':'x','error':'error'}];self.write_index()
        with self.assertRaises(ValueError):self.publish()
        self.assertFalse(self.d.exists())
    def test_no_publica_si_inconsistente(self):
        self.card['edge_total_vs_base']=99
        (self.o/'tarjeta_123.json').write_text(json.dumps(self.card))
        with self.assertRaises(ValueError):self.publish()
        self.assertFalse(self.d.exists())
    def test_no_publica_si_duplicados(self):
        self.index['tarjetas'].append({'id':'123','archivo':'tarjeta_123.json'})
        self.write_index()
        with self.assertRaises(ValueError):self.publish()
    def test_elimina_tarjetas_viejas(self):
        self.d.mkdir()
        (self.d/'tarjeta_999.json').write_text('{}')
        self.publish()
        self.assertFalse((self.d/'tarjeta_999.json').exists())

if __name__=='__main__':unittest.main()
