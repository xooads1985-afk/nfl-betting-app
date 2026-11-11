import json
import unittest
from unittest.mock import patch
from nba_lab_fuente_remota import obtener_tarjeta_remota, obtener_tarjeta_segura

class TestFuenteRemota(unittest.TestCase):
    def setUp(self):
        self.card = dict(esquema='nba_tarjeta_futura_v1',partido_id='123',
            estado='experimental_prepartido',fecha_utc='2099-11-12T00:00:00+00:00',
            generado_utc='2099-11-11T12:00:00+00:00',local='A',visitante='B',
            proyeccion_local_ensemble=110,proyeccion_visitante_ensemble=112,
            total_ensemble=222,total_modelo_c=223,referencia_total_base=220,
            edge_total_vs_base=2,edge_total_modelo_c_vs_base=3,pace_prepartido=None)
    def test_valida_tarjeta(self):
        with patch('nba_lab_fuente_remota._descargar_json',side_effect=[{'tarjetas':[{'id':'123'}]},self.card]):
            d=obtener_tarjeta_remota('123',ahora_utc='2099-11-11T12:05:00+00:00')
        self.assertEqual(d['total_ensemble'],222)
    def test_id_no_publicado(self):
        with patch('nba_lab_fuente_remota._descargar_json',return_value={'tarjetas':[]}):
            d,e=obtener_tarjeta_segura('123')
        self.assertIsNone(d)
        self.assertIn('ausente',e)
    def test_id_malicioso(self):
        d,e=obtener_tarjeta_segura('../abc')
        self.assertIsNone(d)
    def test_tarjeta_vencida(self):
        self.card['generado_utc']='2099-11-08T12:00:00+00:00'
        with patch('nba_lab_fuente_remota._descargar_json',side_effect=[{'tarjetas':[{'id':'123'}]},self.card]):
            d,e=obtener_tarjeta_segura('123',ahora_utc='2099-11-11T12:05:00+00:00')
        self.assertIsNone(d)
        self.assertIn('vigente',e)
if __name__=='__main__': unittest.main()
