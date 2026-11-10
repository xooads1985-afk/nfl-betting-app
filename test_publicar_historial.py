import unittest,csv
from pathlib import Path
from tempfile import TemporaryDirectory
from publicar_historial import publicar,COLUMNAS
from historial_persistente import leer

class TestPublicacion(unittest.TestCase):
 def setUp(self):
  self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  self.base=Path(self.temp.name);self.pred=self.base/'pred.csv';self.hist=self.base/'hist.csv'
  self.row=dict(game_id='2026_12_PIT_BAL',kickoff_utc='2026-11-22T18:00:00+00:00',generated_utc='2026-11-10T10:00:00+00:00',model='ridge',version='v1',home='23',away='20',total='43',margin='3',train_n='170',last_train_kickoff_utc='2026-11-01T18:00:00+00:00')
 def write(self,rows):
  with self.pred.open('w',newline='') as f:
   w=csv.DictWriter(f,fieldnames=COLUMNAS);w.writeheader();w.writerows(rows)
 def test_dos_ejecuciones_y_reintento(self):
  self.write([self.row]);self.assertEqual(publicar(self.pred,self.hist)['nuevos'],1)
  self.assertEqual(publicar(self.pred,self.hist)['nuevos'],0)
  self.write([{**self.row,'model':'ensemble'}]);self.assertEqual(publicar(self.pred,self.hist)['total'],2)
 def test_conflicto_no_cambia_historial(self):
  self.write([self.row]);publicar(self.pred,self.hist);before=self.hist.read_bytes()
  self.write([{**self.row,'home':'24','total':'44','margin':'4'}])
  with self.assertRaises(ValueError):publicar(self.pred,self.hist)
  self.assertEqual(self.hist.read_bytes(),before)
 def test_rechaza_total_incoherente(self):
  self.write([{**self.row,'total':'99'}]);
  with self.assertRaises(ValueError):publicar(self.pred,self.hist)
  self.assertFalse(self.hist.exists())
 def test_rechaza_entrenamiento_futuro(self):
  self.write([{**self.row,'last_train_kickoff_utc':'2026-11-11T18:00:00+00:00'}]);
  with self.assertRaises(ValueError):publicar(self.pred,self.hist)
 def test_rechaza_duplicados(self):
  self.write([self.row,self.row]);
  with self.assertRaises(ValueError):publicar(self.pred,self.hist)
