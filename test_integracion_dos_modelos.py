import csv
import tempfile
import unittest
from pathlib import Path
from evaluar_precision_nfl import evaluar,read

class IntegracionDosModelos(unittest.TestCase):
    def test_dos_modelos_y_repeticion_sin_modificar_historial(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); hist=root/'hist.csv'; cal=root/'cal.csv'; out=root/'reportes'
            fields=['game_id','fecha_partido_utc','modelo','generado_utc','puntos_local','puntos_visitante','total','margen','version']
            base={'game_id':'2026_01_A_B','fecha_partido_utc':'2026-09-11T00:00:00+00:00','generado_utc':'2026-09-10T00:00:00+00:00','version':'v1'}
            rows=[dict(base,modelo='ridge',puntos_local='20',puntos_visitante='17',total='37',margen='3'),dict(base,modelo='ensemble',puntos_local='23',puntos_visitante='14',total='37',margen='9')]
            with hist.open('w',newline='') as f:
                w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
            with cal.open('w',newline='') as f:
                w=csv.DictWriter(f,fieldnames=['game_id','gameday','gametime','home_score','away_score']);w.writeheader();w.writerow({'game_id':'2026_01_A_B','gameday':'2026-09-10','gametime':'20:00','home_score':'24','away_score':'14'})
            before=hist.read_bytes()
            audit=evaluar(hist,cal,out,'2026-09-13T00:00:00+00:00')
            self.assertEqual(audit['evaluados'],2)
            metrics={r['modelo']:r for r in read(out/'metricas_modelos.csv')}
            self.assertEqual(set(metrics),{'ridge','ensemble'})
            self.assertEqual(float(metrics['ridge']['mae_total']),1)
            self.assertEqual(float(metrics['ensemble']['mae_total']),1)
            self.assertEqual(float(metrics['ridge']['mae_margen']),7)
            self.assertEqual(float(metrics['ensemble']['mae_margen']),1)
            self.assertEqual(before,hist.read_bytes())
            evaluar(hist,cal,out,'2026-09-13T00:00:00+00:00')
            self.assertEqual(len(read(out/'detalle_validacion.csv')),2)
            self.assertEqual(before,hist.read_bytes())

    def test_sin_finales_genera_reportes(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);hist=root/'hist.csv';cal=root/'cal.csv';out=root/'out'
            with hist.open('w',newline='') as f:
                w=csv.DictWriter(f,fieldnames=['game_id','fecha_partido_utc','modelo','generado_utc','puntos_local','puntos_visitante','total','margen','version']);w.writeheader();w.writerow({'game_id':'2026_10_A_B','fecha_partido_utc':'2026-11-15T18:00:00+00:00','modelo':'ridge','generado_utc':'2026-11-10T14:24:32+00:00','puntos_local':'20','puntos_visitante':'17','total':'37','margen':'3','version':'v1'})
            with cal.open('w',newline='') as f:
                w=csv.DictWriter(f,fieldnames=['game_id','gameday','gametime','home_score','away_score']);w.writeheader();w.writerow({'game_id':'2026_10_A_B','gameday':'2026-11-15','gametime':'13:00','home_score':'','away_score':''})
            a=evaluar(hist,cal,out,'2026-11-10T20:00:00+00:00')
            self.assertEqual(a['pendientes'],1)
            self.assertEqual(a['evaluados'],0)
            self.assertEqual(read(out/'metricas_modelos.csv'),[])
            self.assertTrue((out/'auditoria_validacion.json').is_file())

if __name__=='__main__':unittest.main()
