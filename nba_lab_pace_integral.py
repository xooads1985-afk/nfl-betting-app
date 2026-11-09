"""Evaluación experimental de Pace con boxscores prepartido, sin alterar modelos estables.
Entrada boxscores CSV: id,fecha_utc,local,visitante,puntos_local,puntos_visitante,
fga_local,fta_local,orb_local,tov_local,fga_visitante,fta_visitante,orb_visitante,tov_visitante.
"""
import argparse
from pathlib import Path
import numpy as np
import pandas as pd

NECESARIAS=['id','fecha_utc','local','visitante','puntos_local','puntos_visitante']
STATS=['fga','fta','orb','tov']

def evaluar(boxscores, salida, minimo=5, ventana=10):
    d=pd.read_csv(boxscores,dtype={'id':str})
    req=NECESARIAS+[f'{s}_{lado}' for s in STATS for lado in ('local','visitante')]
    faltan=set(req)-set(d.columns)
    if faltan: raise ValueError('Columnas faltantes: '+', '.join(sorted(faltan)))
    if d.id.duplicated().any(): raise ValueError('IDs duplicados')
    d['fecha_utc']=pd.to_datetime(d.fecha_utc,utc=True,errors='coerce')
    for c in req:
        if c not in ('id','fecha_utc','local','visitante'):
            d[c]=pd.to_numeric(d[c],errors='coerce')
    d=d.dropna(subset=req).sort_values(['fecha_utc','id'])
    if d.empty: raise ValueError('No hay boxscores completos')
    for lado in ('local','visitante'):
        d[f'poss_{lado}']=d[f'fga_{lado}']+0.44*d[f'fta_{lado}']-d[f'orb_{lado}']+d[f'tov_{lado}']
        if not d[f'poss_{lado}'].between(60,140).all():
            raise ValueError('Posesiones fuera de rango plausible: revisar boxscores')
    # Una posesión compartida por partido evita discrepancias en estimaciones por equipo.
    d['poss']=(d.poss_local+d.poss_visitante)/2
    historial={}
    filas=[]
    for fecha, grupo in d.groupby('fecha_utc',sort=True):
        pendientes=[]
        for _,j in grupo.iterrows():
            local,visitante=j.local,j.visitante
            h=historial.get(local,[])[-ventana:]
            v=historial.get(visitante,[])[-ventana:]
            if len(h)>=minimo and len(v)>=minimo:
                pace=(np.mean([x['poss'] for x in h])+np.mean([x['poss'] for x in v]))/2
                for equipo, propio, rival, real in [(local,h,v,j.puntos_local),(visitante,v,h,j.puntos_visitante)]:
                    ortg=np.mean([100*x['pf']/x['poss'] for x in propio])
                    drtg=np.mean([100*x['pc']/x['poss'] for x in rival])
                    pred=float(np.clip(pace*(ortg+drtg)/200,60,180))
                    filas.append({'fecha':fecha,'partido':j.id,'equipo':equipo,'real':real,'Pace + eficiencia':pred,'pace_estimado':pace,'ortg':ortg,'drtg_rival':drtg,'muestra_equipo':len(propio),'muestra_rival':len(rival)})
            pendientes.append(j)
        # Actualizar historial únicamente DESPUÉS de predecir todos los juegos del timestamp.
        for j in pendientes:
            historial.setdefault(j.local,[]).append({'poss':j.poss,'pf':j.puntos_local,'pc':j.puntos_visitante})
            historial.setdefault(j.visitante,[]).append({'poss':j.poss,'pf':j.puntos_visitante,'pc':j.puntos_local})
    salida=Path(salida);salida.mkdir(parents=True,exist_ok=True)
    p=pd.DataFrame(filas,columns=['fecha','partido','equipo','real','Pace + eficiencia','pace_estimado','ortg','drtg_rival','muestra_equipo','muestra_rival'])
    p.to_csv(salida/'pace_predicciones.csv',index=False)
    if p.empty:
        resumen=pd.DataFrame([{'modelo':'Pace + eficiencia','muestra':0,'MAE':np.nan,'RMSE':np.nan,'sesgo':np.nan}])
    else:
        err=p['Pace + eficiencia']-p.real
        resumen=pd.DataFrame([{'modelo':'Pace + eficiencia','muestra':len(p),'MAE':err.abs().mean(),'RMSE':np.sqrt((err**2).mean()),'sesgo':err.mean()}])
    resumen.to_csv(salida/'pace_resumen.csv',index=False)
    print(resumen.to_string(index=False))
    return p

if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--boxscores',required=True)
    ap.add_argument('--salida',default='nba_lab_pace_resultados')
    ap.add_argument('--minimo',type=int,default=5)
    ap.add_argument('--ventana',type=int,default=10)
    a=ap.parse_args()
    if a.minimo<3 or a.ventana<a.minimo: raise ValueError('Mínimo o ventana inválidos')
    evaluar(a.boxscores,a.salida,a.minimo,a.ventana)
