"""Selecciona los partidos con predicción original de 2025-26 y ejecuta la comparación ESPN.
No escribe sobre módulos estables. Solo genera CSV temporal y artefactos de resultados.
"""
import argparse
from pathlib import Path
import pandas as pd
import nba_lab_comparar_2025
import sys

p=argparse.ArgumentParser()
p.add_argument('--historico',default='nba_lab_resultados/partidos_historicos.csv')
p.add_argument('--predicciones',default='nba_lab_resultados/algoritmos_predicciones.csv')
p.add_argument('--salida',default='nba_ampliacion_2025_resultados')
a=p.parse_args()
out=Path(a.salida);out.mkdir(parents=True,exist_ok=True)
h=pd.read_csv(a.historico,dtype={'id':str}); pred=pd.read_csv(a.predicciones,dtype={'partido':str})
h['fecha_utc']=pd.to_datetime(h['fecha_utc'],utc=True,errors='coerce')
pred['fecha']=pd.to_datetime(pred['fecha'],utc=True,errors='coerce')
ids=set(pred.loc[(pred.fecha>='2025-10-21')&(pred.fecha<'2026-07-01'),'partido'].dropna().astype(str))
sel=h[h.id.isin(ids)&(h.fecha_utc>='2025-10-21')&(h.fecha_utc<'2026-07-01')].copy()
sel=sel.sort_values('fecha_utc').drop_duplicates('id')
sel.to_csv(out/'historico_seleccionado.csv',index=False)
print('Partidos con predicciones de temporada 2025-26:',len(ids),'identificados en histórico:',len(sel),flush=True)
if len(sel)<1:raise SystemExit('No hay partidos coincidentes: revisar rutas o identificadores')
sys.argv=['nba_lab_comparar_2025.py','--historico',str(out/'historico_seleccionado.csv'),'--predicciones',a.predicciones,'--salida',str(out),'--max-partidos','1000']
nba_lab_comparar_2025.main()
