"""Backtest cronológico Q1/1H: solo partidos anteriores al evaluado.
No cambia el modelo, la tarjeta ni el historial; produce reportes auditables.
"""
import argparse
import json
from pathlib import Path
import pandas as pd
from nba_pace_periodos_modelo import proyectar_periodos

COLUMNAS = {'q1': ('puntos_q1_local', 'puntos_q1_visitante'), 'mitad': ('puntos_mitad_local', 'puntos_mitad_visitante')}

def ejecutar(entrada, carpeta):
    df = pd.read_csv(entrada, dtype={'partido_id': str}, encoding='utf-8-sig')
    obligatorias = {'partido_id','fecha_utc','finalizado','local','visitante','posesiones_local','posesiones_visitante'} | {c for par in COLUMNAS.values() for c in par}
    faltantes = obligatorias - set(df.columns)
    if faltantes:
        raise ValueError('Columnas faltantes: ' + ', '.join(sorted(faltantes)))
    if df['partido_id'].duplicated().any():
        raise ValueError('IDs de partido duplicados')
    df['_fecha'] = pd.to_datetime(df['fecha_utc'], utc=True, errors='coerce')
    if df['_fecha'].isna().any():
        raise ValueError('Fechas inválidas')
    df = df.sort_values(['_fecha', 'partido_id'])
    filas=[]
    total_elegibles=0
    for _, juego in df.iterrows():
        if str(juego['finalizado']).lower() != 'true':
            continue
        total_elegibles+=1
        partido = {'id': juego['partido_id'], 'fecha_utc': juego['fecha_utc'], 'local': juego['local'], 'visitante': juego['visitante']}
        pred = proyectar_periodos(df, partido, ventana=10, minimo=5)
        if pred is None:
            continue
        for periodo,(col_local,col_visita) in COLUMNAS.items():
            reales={'local':float(juego[col_local]), 'visitante':float(juego[col_visita])}
            reales['total']=reales['local']+reales['visitante']
            for lado in ('local','visitante','total'):
                estimado=pred['periodos'][periodo][lado]
                real=reales[lado]
                filas.append({'partido_id':str(juego['partido_id']), 'fecha_utc':juego['fecha_utc'], 'local':juego['local'], 'visitante':juego['visitante'], 'periodo':periodo, 'campo':lado, 'proyectado':round(estimado,3), 'real':real, 'error':round(estimado-real,3), 'error_absoluto':round(abs(estimado-real),3), 'muestra_local':pred['muestras'][partido['local']], 'muestra_visitante':pred['muestras'][partido['visitante']]})
    if not filas:
        raise RuntimeError('No hubo partidos evaluables; no se publica validación vacía')
    auditoria=pd.DataFrame(filas)
    resumen=auditoria.groupby(['periodo','campo'],sort=True).agg(n=('error','size'),mae=('error_absoluto','mean'),sesgo=('error','mean')).reset_index()
    resumen[['mae','sesgo']]=resumen[['mae','sesgo']].round(3)
    carpeta=Path(carpeta);carpeta.mkdir(parents=True,exist_ok=True)
    auditoria.to_csv(carpeta/'nba_pace_periodos_backtest_detalle.csv',index=False)
    resumen.to_csv(carpeta/'nba_pace_periodos_backtest_resumen.csv',index=False)
    meta={'partidos_historial':len(df),'partidos_finalizados':total_elegibles,'partidos_evaluados':auditoria['partido_id'].nunique(),'metodo':'backtest cronológico; ventana 10; mínimo 5 por equipo; solo fechas anteriores','nota':'La validación histórica no sustituye el seguimiento prospectivo de predicciones guardadas.'}
    (carpeta/'nba_pace_periodos_backtest_metadata.json').write_text(json.dumps(meta,indent=2,ensure_ascii=False),encoding='utf-8')
    print(resumen.to_string(index=False));print(meta)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--entrada',default='nba_historial_pace_periodos_validado.csv');p.add_argument('--salida',default='reportes_pace_periodos');a=p.parse_args();ejecutar(a.entrada,a.salida)
