#!/usr/bin/env python3
"""Controles NBA independientes: localía, consistencia y prueba de invariancia temporal."""
import argparse
from pathlib import Path
import numpy as np
import pandas as pd

MODELOS = ['Base','Modelo C','Ridge','Bayesiano','Gradient Boosting','Ensemble','Regresión lineal','Binomial negativa']

def resumen_errores(d, etiqueta):
    filas=[]
    for modelo in MODELOS:
        if modelo not in d: continue
        z=d[['real',modelo]].apply(pd.to_numeric,errors='coerce').dropna()
        if z.empty: continue
        e=z[modelo]-z.real
        filas.append({'grupo':etiqueta,'modelo':modelo,'muestra':len(z),'MAE':round(e.abs().mean(),3),'RMSE':round(np.sqrt((e*e).mean()),3),'sesgo':round(e.mean(),3)})
    return filas

def ejecutar(predicciones,historico,salida):
    salida=Path(salida);salida.mkdir(parents=True,exist_ok=True)
    p=pd.read_csv(predicciones,dtype={'partido':str})
    h=pd.read_csv(historico,dtype={'id':str})
    needed_p={'partido','equipo','real','fecha'};needed_h={'id','local','visitante','puntos_local','puntos_visitante','fecha_utc'}
    if not needed_p.issubset(p) or not needed_h.issubset(h):raise ValueError('Columnas obligatorias faltantes')
    if h.id.duplicated().any():raise ValueError('IDs duplicados en historial')
    d=p.merge(h[['id','local','visitante','puntos_local','puntos_visitante','fecha_utc']],left_on='partido',right_on='id',how='left',validate='many_to_one',indicator=True)
    d['sede']=np.select([d.equipo.eq(d.local),d.equipo.eq(d.visitante)],['Local','Visitante'],default='Sin correspondencia')
    d['real_fuente']=np.where(d.sede.eq('Local'),d.puntos_local,np.where(d.sede.eq('Visitante'),d.puntos_visitante,np.nan))
    fecha_p=pd.to_datetime(d.fecha,utc=True,errors='coerce');fecha_h=pd.to_datetime(d.fecha_utc,utc=True,errors='coerce')
    problemas={
        'Partido no encontrado':int(d['_merge'].ne('both').sum()),
        'Equipo no corresponde':int(d.sede.eq('Sin correspondencia').sum()),
        'Marcador no coincide':int((pd.to_numeric(d.real,errors='coerce')-pd.to_numeric(d.real_fuente,errors='coerce')).abs().gt(1e-7).sum()),
        'Fecha no coincide':int((fecha_p.ne(fecha_h)).sum()),
        'Duplicado partido-equipo':int(p.duplicated(['partido','equipo'],keep=False).sum()),
        'Partidos sin dos registros':int(p.groupby('partido').size().ne(2).sum()),
    }
    pd.DataFrame([{'control':k,'incidencias':v} for k,v in problemas.items()]).to_csv(salida/'control_integridad.csv',index=False)
    if any(problemas.values()):raise ValueError(f'Integridad fallida: {problemas}')
    filas=[]
    d['temporada']=fecha_p.dt.year.where(fecha_p.dt.month>=7,fecha_p.dt.year-1).map(lambda y:f'{int(y)}-{str(int(y)+1)[-2:]}')
    for temporada,g in [('Todas',d),*list(d.groupby('temporada'))]:
        for sede,sub in g.groupby('sede'):
            for item in resumen_errores(sub,sede):filas.append({'temporada':temporada,**item})
    pd.DataFrame(filas).to_csv(salida/'metricas_localia.csv',index=False)
    (salida/'RESUMEN.txt').write_text(f'Predicciones verificadas: {len(d)}\nPartidos: {d.partido.nunique()}\nIncidencias: 0\nLa prueba de invariancia temporal se ejecuta aparte y no demuestra ausencia absoluta de fuga de datos.\n',encoding='utf-8')
    print(f'Integridad OK: {len(d)} filas, {d.partido.nunique()} partidos')

def prueba_temporal(historial,salida):
    """Prueba de regresión: agregar partidos futuros no cambia features ni predicciones de un juego previo."""
    from nba_lab_motor_offline import _nba_lab_ml_caracteristicas,_nba_lab_modelo_c
    d=pd.read_csv(historial,dtype={'id':str})
    d['_fecha_ml']=pd.to_datetime(d.fecha_utc,utc=True,errors='coerce')
    d=d.loc[d.finalizado.eq(True)].sort_values('_fecha_ml').copy()
    if len(d)<150:raise ValueError('Historial insuficiente para prueba temporal')
    fechas=d['_fecha_ml'].drop_duplicates().sort_values()
    corte=fechas.iloc[min(len(fechas)-2,max(1,int(len(fechas)*.60)))]
    previo=d.loc[d._fecha_ml.le(corte)].copy()
    candidatos=previo.loc[previo._fecha_ml.eq(corte)]
    ajustes={'forma':True,'sede':True,'descanso':True,'pace':False,'fuerza':True,'regresion':True}
    n=0
    for _,j in candidatos.iterrows():
        x=_nba_lab_ml_caracteristicas(previo,j);y=_nba_lab_ml_caracteristicas(d,j)
        if len(x)!=2 or len(y)!=2:continue
        for a,b in zip(x,y):
            if a['equipo']!=b['equipo'] or not np.allclose(a['x'],b['x'],rtol=0,atol=1e-9):raise AssertionError('Features alteradas por datos futuros')
        a=_nba_lab_modelo_c(previo,j,ajustes);b=_nba_lab_modelo_c(d,j,ajustes)
        if a is None or b is None:continue
        for equipo in a:
            if not np.isclose(a[equipo]['pred'],b[equipo]['pred'],atol=1e-9):raise AssertionError('Modelo C alterado por datos futuros')
        n+=1
    if n==0:raise ValueError('No se encontraron juegos válidos para prueba temporal')
    Path(salida).mkdir(parents=True,exist_ok=True)
    (Path(salida)/'prueba_temporal.txt').write_text(f'OK: {n} partidos evaluados; agregar partidos futuros no alteró features ni Modelo C.\nEsta prueba no cubre todos los modelos ni todas las fechas.\n',encoding='utf-8')
    print(f'Prueba temporal OK: {n} partidos')

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--predicciones',default='nba_lab_resultados/algoritmos_predicciones.csv');ap.add_argument('--historico',default='nba_lab_resultados/partidos_historicos.csv');ap.add_argument('--salida',default='nba_lab_auditoria_resultados');ap.add_argument('--temporal',action='store_true');args=ap.parse_args()
    ejecutar(args.predicciones,args.historico,args.salida)
    if args.temporal:prueba_temporal(args.historico,args.salida)
