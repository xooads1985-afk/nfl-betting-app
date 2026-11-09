#!/usr/bin/env python3
"""Auditoría de resultados históricos NBA. Solo lectura; no entrena ni modifica el laboratorio."""
import argparse
from pathlib import Path
import numpy as np
import pandas as pd

MODELOS=['Base','Modelo C','Ridge','Bayesiano','Gradient Boosting','Ensemble','Regresión lineal','Binomial negativa']

def metricas(real,pred):
    valid=real.notna() & pred.notna()
    e=(pred[valid]-real[valid]).astype(float)
    return {'muestra':len(e),'MAE':round(e.abs().mean(),3) if len(e) else None,'RMSE':round(np.sqrt((e**2).mean()),3) if len(e) else None,'sesgo':round(e.mean(),3) if len(e) else None}

def auditar(entrada, salida):
    d=pd.read_csv(entrada,dtype={'partido':str})
    necesarios=['partido','equipo','fecha','real']
    faltantes=[c for c in necesarios if c not in d]
    if faltantes: raise ValueError('Faltan columnas: '+', '.join(faltantes))
    salida.mkdir(parents=True,exist_ok=True)
    d['fecha']=pd.to_datetime(d['fecha'],utc=True,errors='coerce')
    d['real']=pd.to_numeric(d['real'],errors='coerce')
    d['temporada']=d['fecha'].dt.year.where(d['fecha'].dt.month>=7,d['fecha'].dt.year-1).map(lambda y: f'{int(y)}-{str(int(y)+1)[-2:]}' if pd.notna(y) else 'Sin fecha')
    incidencias=[]
    dup=d.duplicated(['partido','equipo'],keep=False)
    if dup.any(): incidencias.append({'tipo':'Duplicado partido-equipo','cantidad':int(dup.sum())})
    if d['fecha'].isna().any(): incidencias.append({'tipo':'Fecha inválida','cantidad':int(d['fecha'].isna().sum())})
    if d['real'].isna().any(): incidencias.append({'tipo':'Resultado faltante','cantidad':int(d['real'].isna().sum())})
    conteos=d.groupby('partido').size()
    incompletos=conteos[conteos!=2]
    if len(incompletos): incidencias.append({'tipo':'Partidos sin exactamente 2 equipos','cantidad':len(incompletos)})
    if 'Entrenamiento' in d:
        n=pd.to_numeric(d['Entrenamiento'],errors='coerce')
        if (n<24).any(): incidencias.append({'tipo':'Entrenamiento menor que 24 observaciones','cantidad':int((n<24).sum())})
    if d['fecha'].notna().any():
        fecha_max=d['fecha'].max()
        if fecha_max>pd.Timestamp.now(tz='UTC'):
            incidencias.append({'tipo':'Predicciones con fecha futura','cantidad':int((d['fecha']>pd.Timestamp.now(tz='UTC')).sum())})
    validos=d.loc[~dup & d['real'].notna() & d['fecha'].notna()].copy()
    modelos=[m for m in MODELOS if m in validos]
    for m in modelos: validos[m]=pd.to_numeric(validos[m],errors='coerce')
    equipo=[]
    for periodo,g in [('Todas',validos),*list(validos.groupby('temporada'))]:
        for m in modelos: equipo.append({'temporada':periodo,'modelo':m,**metricas(g['real'],g[m])})
    pd.DataFrame(equipo).to_csv(salida/'metricas_por_equipo.csv',index=False)
    pares=validos.loc[validos['partido'].isin(validos.groupby('partido').size().loc[lambda x:x==2].index)].copy()
    agg={'real':'sum','fecha':'min','temporada':'first'}
    agg.update({m:'sum' for m in modelos})
    # Excluir sumas parciales por NaN: se usan solo pares con dos predicciones válidas por modelo.
    totals=pares.groupby('partido').agg(agg)
    totals=totals.rename(columns={'real':'total_real'})
    total_rows=[]
    for periodo,g in [('Todas',totals),*list(totals.groupby('temporada'))]:
        for m in modelos:
            ids=pares.loc[pares[m].notna()].groupby('partido').size()
            ok=g.index.isin(ids[ids==2].index)
            total_rows.append({'temporada':periodo,'modelo':m,**metricas(g.loc[ok,'total_real'],g.loc[ok,m])})
    pd.DataFrame(total_rows).to_csv(salida/'metricas_totales.csv',index=False)
    pd.DataFrame(incidencias,columns=['tipo','cantidad']).to_csv(salida/'incidencias.csv',index=False)
    resumen=[f'Filas: {len(d)}',f'Partidos únicos: {d.partido.nunique()}',f'Pares válidos: {len(totals)}',f'Incidencias detectadas: {len(incidencias)}','', 'Nota: la comprobación de ausencia de fuga temporal requiere además pruebas sobre el código y datos fuente.','Nota: el CSV actual no incluye local/visitante ni puntos por cuarto; no se infieren.']
    (salida/'LEEME_RESULTADOS.txt').write_text('\n'.join(resumen),encoding='utf-8')
    print('\n'.join(resumen))

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--entrada',default='nba_lab_resultados/algoritmos_predicciones.csv')
    p.add_argument('--salida',default='nba_lab_auditoria_resultados')
    a=p.parse_args()
    auditar(Path(a.entrada),Path(a.salida))
