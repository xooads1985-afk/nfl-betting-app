import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
import pandas as pd
from orquestar_experimental import ejecutar

class Pruebas(unittest.TestCase):
    def datos(self):
        rows=[]
        for i in range(170):
            rows.append(dict(game_id=f'2024_{i}',season=2024,week=i//16+1,
                gameday=(pd.Timestamp('2024-09-01')+pd.Timedelta(days=i)).strftime('%Y-%m-%d'),
                gametime='13:00',home_team=['PIT','BAL','CLE','CIN'][i%4],
                away_team=['NYJ','MIA','BUF','NE'][i%4],home_score=20+i%18,away_score=14+i%14))
        rows.append(dict(game_id='2026_future',season=2026,week=12,gameday='2026-11-22',gametime='13:00',
            home_team='PIT',away_team='BAL',home_score=None,away_score=None))
        return pd.DataFrame(rows)
    def test_end_to_end(self):
        with TemporaryDirectory() as t:
            p=Path(t);self.datos().to_csv(p/'raw.csv',index=False)
            result=ejecutar(p/'raw.csv',p/'out','2026-11-10T10:00:00Z')
            self.assertEqual(result['predicciones'],2)
            pred=pd.read_csv(p/'out/prospectivas.csv')
            self.assertEqual(set(pred.model),{'ridge','ensemble'})
            self.assertTrue((pd.to_datetime(pred.generated_utc,utc=True)<pd.to_datetime(pred.kickoff_utc,utc=True)).all())
            self.assertTrue((abs(pred.home+pred.away-pred.total)<1e-6).all())
    def test_no_publica_si_no_hay_entrenamiento(self):
        with TemporaryDirectory() as t:
            p=Path(t);self.datos().tail(2).to_csv(p/'raw.csv',index=False)
            with self.assertRaises(ValueError):ejecutar(p/'raw.csv',p/'out','2026-11-10T10:00:00Z')
            self.assertFalse((p/'out').exists())
    def test_sin_partidos_futuros_genera_cero_y_preserva_historial(self):
        from publicar_historial import publicar
        with TemporaryDirectory() as t:
            p=Path(t)
            self.datos().iloc[:-1].to_csv(p/'raw.csv',index=False)
            resultado=ejecutar(p/'raw.csv',p/'out','2026-11-10T10:00:00Z')
            self.assertEqual(resultado['predicciones'],0)
            self.assertEqual(len(pd.read_csv(p/'out/prospectivas.csv')),0)
            historial=p/'historial.csv'
            historial.write_text('registro anterior\n',encoding='utf-8')
            self.assertEqual(publicar(p/'out/prospectivas.csv',historial)['nuevos'],0)
            self.assertEqual(historial.read_text(encoding='utf-8'),'registro anterior\n')
    def test_rechaza_marcador_futuro(self):
        with TemporaryDirectory() as t:
            p=Path(t);df=self.datos();df.loc[df.game_id=='2026_future','home_score']=10
            df.loc[df.game_id=='2026_future','away_score']=10
            df.to_csv(p/'raw.csv',index=False)
            with self.assertRaises(ValueError):ejecutar(p/'raw.csv',p/'out','2026-11-10T10:00:00Z')
            self.assertFalse((p/'out/prospectivas.csv').exists())

if __name__=='__main__':unittest.main()
