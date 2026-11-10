import csv
import tempfile
import unittest
from pathlib import Path
from evaluar_precision_nfl import evaluar,read

class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.p=Path(self.tmp.name);self.hist=self.p/'hist.csv';self.cal=self.p/'cal.csv';self.out=self.p/'out'
  self.pred={'game_id':'2026_01_A_B','fecha_partido_utc':'2026-09-11T00:00:00+00:00','modelo':'ridge','generado_utc':'2026-09-10T00:00:00+00:00','puntos_local':'20','puntos_visitante':'17','total':'37','margen':'3','version':'v1'}
  self.game={'game_id':'2026_01_A_B','gameday':'2026-09-10','gametime':'20:00','home_score':'24','away_score':'14'}
  self.save()
 def save(self):
  for path,row in ((self.hist,self.pred),(self.cal,self.game)):
   with path.open('w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(row));w.writeheader();w.writerow(row)
 def run_eval(self,cut='2026-09-13T00:00:00+00:00'):
  return evaluar(self.hist,self.cal,self.out,cut)
 def test_errors(self):
  a=self.run_eval();self.assertEqual(a['evaluados'],1)
  d=read(self.out/'detalle_validacion.csv')[0]
  self.assertEqual(float(d['error_local']),-4)
  self.assertEqual(float(d['error_visitante']),3)
  self.assertEqual(float(d['error_total']),-1)
  self.assertEqual(float(d['error_margen']),-7)
 def test_no_result_yet(self):
  a=self.run_eval('2026-09-10T12:00:00+00:00');self.assertEqual(a['pendientes'],1)
  self.assertEqual(len(read(self.out/'metricas_modelos.csv')),0)
 def test_recent(self):self.assertEqual(self.run_eval('2026-09-11T12:00:00+00:00')['recientes'],1)
 def test_missing_score(self):
  self.game['home_score']='';self.game['away_score']='';self.save();self.assertEqual(self.run_eval()['sin_marcador'],1)
 def test_partial_score_rejected(self):
  self.game['away_score']='';self.save()
  with self.assertRaisesRegex(ValueError,'Marcador parcial'):self.run_eval()
 def test_missing_score_wrong_kickoff_rejected(self):
  self.game['home_score']='';self.game['away_score']='';self.game['gametime']='19:00';self.save()
  with self.assertRaisesRegex(ValueError,'Kickoff'):self.run_eval()
 def test_bad_kickoff(self):
  self.game['gametime']='19:00';self.save()
  with self.assertRaisesRegex(ValueError,'Kickoff'):self.run_eval()
 def test_late_prediction(self):
  self.pred['generado_utc']=self.pred['fecha_partido_utc'];self.save()
  with self.assertRaisesRegex(ValueError,'posterior'):self.run_eval()
 def test_immutable(self):
  before=self.hist.read_bytes();self.run_eval();self.assertEqual(before,self.hist.read_bytes())
if __name__=='__main__':unittest.main()
