"""Experimento prospectivo NBA con pace; no altera los motores existentes.

Entradas: registros de partidos FINALIZADOS con fecha_utc, local, visitante,
 puntos_local, puntos_visitante, posesiones_local, posesiones_visitante.
 Las posesiones se estiman con boxscore (FGA+0.44*FTA-OREB+TOV).
 Si se proporciona minutos_partido=53 para prórroga de 5 min, normaliza a 48.
"""
from __future__ import annotations
import math
import pandas as pd

REQUIRED = ('fecha_utc','local','visitante','puntos_local','puntos_visitante',
            'posesiones_local','posesiones_visitante')

def _history(records, fecha):
    df = pd.DataFrame(records).copy()
    if any(c not in df.columns for c in REQUIRED):
        raise ValueError('Faltan columnas: ' + ', '.join(c for c in REQUIRED if c not in df))
    df['_fecha'] = pd.to_datetime(df['fecha_utc'], utc=True, errors='coerce')
    if 'finalizado' not in df:
        raise ValueError('Se requiere la columna finalizado')
    df = df.loc[df['_fecha'].notna() & (df['_fecha'] < fecha) & df['finalizado'].eq(True)].copy()
    for col in ('puntos_local','puntos_visitante','posesiones_local','posesiones_visitante'):
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df = df.dropna(subset=['puntos_local','puntos_visitante','posesiones_local','posesiones_visitante'])
    df = df.loc[(df['posesiones_local'].between(60,150)) & (df['posesiones_visitante'].between(60,150))]
    if 'minutos_partido' in df:
        minutos = pd.to_numeric(df['minutos_partido'], errors='coerce')
        df = df.loc[minutos.ge(48) & minutos.le(78)].copy()
        df['_factor'] = 48 / minutos.loc[df.index]
    else:
        # Sin duración verificada, descartar partidos con prórroga identificada.
        if 'prorroga' not in df:
            raise ValueError('Se requiere minutos_partido o prorroga para evitar sesgo por prórrogas')
        df = df.loc[df['prorroga'].eq(False)].copy()
        df['_factor'] = 1.0
    return df.sort_values('_fecha')

def predecir_pace(records, partido, ventana=10, minimo=3):
    """Predice puntos por equipo usando SOLO encuentros anteriores al objetivo.

    Devuelve None si faltan suficientes boxscores completos.
    Los ratings son puntos por 100 posesiones; pace son posesiones por 48 min.
    """
    fecha = pd.to_datetime(partido.get('fecha_utc'), utc=True, errors='coerce')
    if pd.isna(fecha):
        return None
    df = _history(records, fecha)
    equipos = (str(partido['local']), str(partido['visitante']))
    res = {}
    for equipo in equipos:
        x = df.loc[(df['local'].eq(equipo)) | (df['visitante'].eq(equipo))].tail(ventana)
        if len(x) < minimo:
            return None
        casa = x['local'].eq(equipo)
        pf = x['puntos_local'].where(casa, x['puntos_visitante'])
        pc = x['puntos_visitante'].where(casa, x['puntos_local'])
        pos = (x['posesiones_local'] + x['posesiones_visitante']) / 2
        if (pos <= 0).any():
            return None
        ritmo = pos * x['_factor']
        res[equipo] = {'pace': float(ritmo.mean()),
                       'ortg': float((pf / pos * 100).mean()),
                       'drtg': float((pc / pos * 100).mean()),
                       'muestra': len(x)}
    pace = (res[equipos[0]]['pace'] + res[equipos[1]]['pace']) / 2
    for equipo, rival in ((equipos[0],equipos[1]),(equipos[1],equipos[0])):
        # Para prórrogas históricas, el rating por posesión permanece válido;
        # el ritmo se normaliza a 48 minutos.
        puntos = pace * (res[equipo]['ortg'] + res[rival]['drtg']) / 200
        res[equipo]['prediccion'] = round(float(puntos), 3)
    return {'equipos':res, 'pace_48':round(pace,3),
            'total':round(sum(res[e]['prediccion'] for e in equipos),3),
            'fecha_objetivo_utc':fecha.isoformat()}

def comparar_con_base(records, predicciones_base, ventana=10, minimo=3):
    """Comparación pareada, sin recalibración retrospectiva.

    predicciones_base: filas {fecha_utc,local,visitante,puntos_local,puntos_visitante,
    pred_local,pred_visitante}; los puntos son resultados finales SOLO para evaluar.
    """
    filas=[]
    for p in predicciones_base:
        resultado=predecir_pace(records,p,ventana,minimo)
        if resultado is None:
            continue
        for equipo, real, base in ((p['local'],p['puntos_local'],p['pred_local']),
                                  (p['visitante'],p['puntos_visitante'],p['pred_visitante'])):
            pred=resultado['equipos'][equipo]['prediccion']
            if not all(math.isfinite(float(x)) for x in (pred,real,base)):
                continue
            filas.append({'fecha_utc':p['fecha_utc'],'equipo':equipo,'real':float(real),
                          'Base':float(base),'Pace':pred,'pace_48':resultado['pace_48']})
    d=pd.DataFrame(filas)
    if d.empty:
        return d,pd.DataFrame()
    resumen=[]
    for nombre in ('Base','Pace'):
        error=d[nombre]-d['real']
        resumen.append({'Modelo':nombre,'N':len(error),'MAE':round(error.abs().mean(),3),
                        'RMSE':round((error.pow(2).mean())**0.5,3),'Sesgo':round(error.mean(),3)})
    return d,pd.DataFrame(resumen)
