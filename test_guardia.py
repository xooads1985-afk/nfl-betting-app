"""Pruebas rápidas de la guardia; ejecutar con python -m unittest test_guardia.py."""
import unittest
from unittest.mock import patch
import pandas as pd
from nba_lab_puente_seguro import preparar_tarjeta_segura

CAL = pd.DataFrame([{'id':'999','fecha_utc':'2099-11-11T01:00:00Z','local':'A','visitante':'B','finalizado':False,'estado':'Scheduled'}])
H = pd.DataFrame([
 {'id':'1','fecha_utc':'2099-11-01T01:00:00Z','local':'A','visitante':'B','finalizado':True,'puntos_local':100,'puntos_visitante':99,'tipo_competicion':'regular'},
 {'id':'2','fecha_utc':'2099-11-02T01:00:00Z','local':'A','visitante':'B','finalizado':True,'puntos_local':110,'puntos_visitante':90,'tipo_competicion':'postemporada'},
 {'id':'3','fecha_utc':'2099-11-12T01:00:00Z','local':'A','visitante':'B','finalizado':True,'puntos_local':120,'puntos_visitante':90,'tipo_competicion':'regular'},
])
class Guardia(unittest.TestCase):
 def test_filtrado_estricto(self):
  with patch('nba_lab_puente_seguro.preparar_tarjeta',return_value={'esquema':'nba_tarjeta_futura_v1'}) as mock:
   result=preparar_tarjeta_segura(CAL,H,'999',ahora_utc='2099-11-01T00:00:00Z')
   hist=mock.call_args.args[1]
   self.assertEqual(hist['id'].tolist(),['1'])
   self.assertEqual(result['auditoria_guardia']['historial_regular_anterior'],1)
 def test_sin_clasificacion_rechazado(self):
  with self.assertRaisesRegex(ValueError,'tipo_competicion'):
   preparar_tarjeta_segura(CAL,H.drop(columns=['tipo_competicion']),'999')
 def test_sin_id_rechazado(self):
  with self.assertRaisesRegex(ValueError,'ID del partido'):
   preparar_tarjeta_segura(CAL,H,'no-existe')
if __name__=='__main__':unittest.main()
