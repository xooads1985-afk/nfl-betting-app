"""Motor prepartido experimental. Requiere nba_lab_motor_offline.py en la misma carpeta.
No escribe ni modifica la aplicación estable.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from nba_lab_motor_offline import (_nba_lab_ml_caracteristicas, _nba_lab_ml_entrenar,
    _nba_lab_ml_predecir, _nba_lab_modelo_c)

AJUSTES = {'forma': True, 'sede': True, 'descanso': True,
           'pace': False, 'fuerza': True, 'regresion': True}


def _fecha(x):
    v = pd.to_datetime(x, utc=True, errors='coerce')
    if pd.isna(v):
        raise ValueError('Fecha UTC inválida')
    return v


def predecir(historial: pd.DataFrame, local: str, visitante: str, fecha_utc: str,
             posesiones_historicas: pd.DataFrame | None = None):
    fecha = _fecha(fecha_utc)
    if not local or not visitante or local == visitante:
        raise ValueError('Especifica dos equipos diferentes')
    requeridas = {'id','fecha_utc','local','visitante','puntos_local','puntos_visitante','finalizado'}
    if requeridas - set(historial):
        raise ValueError('Faltan columnas: '+str(sorted(requeridas-set(historial))))
    h = historial.copy()
    h['_fecha_ml'] = pd.to_datetime(h['fecha_utc'], utc=True, errors='coerce')
    h['puntos_local'] = pd.to_numeric(h['puntos_local'], errors='coerce')
    h['puntos_visitante'] = pd.to_numeric(h['puntos_visitante'], errors='coerce')
    h['finalizado'] = h['finalizado'].astype(str).str.lower().eq('true')
    # Bloqueo estricto: solo partidos verificados anteriores al inicio objetivo.
    h = h.loc[(h['_fecha_ml'] < fecha) & h.finalizado].dropna(
        subset=['_fecha_ml','puntos_local','puntos_visitante']).sort_values(['_fecha_ml','id']).copy()
    if 'tipo_competicion' in h:
        h = h.loc[h.tipo_competicion.eq('regular')].copy()
    if h.empty:
        raise ValueError('No hay historial regular finalizado anterior al encuentro')
    # Los features de entrenamiento se construyen como se hizo en validación cronológica.
    entrenamiento_x, entrenamiento_y = [], []
    for juego in h.to_dict('records'):
        items = _nba_lab_ml_caracteristicas(h, juego)
        for item in items:
            entrenamiento_x.append(item['x'])
            entrenamiento_y.append(item['real'])
    if len(entrenamiento_y) < 24:
        raise ValueError('Historial insuficiente: se necesitan 24 observaciones entrenables')
    modelos = _nba_lab_ml_entrenar(entrenamiento_x, entrenamiento_y)
    # El juego objetivo NO contiene marcadores reales; cero es un valor técnico que
    # la función histórica adjunta al campo real, que nunca entra en el vector x.
    juego = {'id':'FUTURO', 'fecha_utc':fecha, 'local':local,
             'visitante':visitante, 'puntos_local':0., 'puntos_visitante':0.}
    features = _nba_lab_ml_caracteristicas(h, juego)
    if len(features) != 2:
        raise ValueError('Ambos equipos requieren al menos tres antecedentes previos')
    modelo_c = _nba_lab_modelo_c(h, juego, AJUSTES)
    if modelo_c is None:
        raise ValueError('Modelo C no pudo calcularse con el historial disponible')
    equipos = {}
    for item in features:
        nombre = item['equipo']
        ml = _nba_lab_ml_predecir(modelos, item['x'], item['base'], item['n'], item['liga'])
        if 'Ensemble' not in ml or not np.isfinite(ml['Ensemble']):
            raise ValueError('Ensemble no disponible para '+nombre)
        equipos[nombre] = {
            'ensemble':round(float(ml['Ensemble']),2),
            'modelo_c':round(float(modelo_c[nombre]['pred']),2),
            'referencia_base':round(float(item['base']),2),
            'edge_vs_base':round(float(ml['Ensemble']-item['base']),2),
            'partidos_previos':int(item['n'])}
    # No se utiliza la columna histórica de Pace de otros encuentros como si
    # fuese la predicción de este partido: necesita boxscores prepartido reales.
    pace = None
    if posesiones_historicas is not None:
        q = posesiones_historicas.copy()
        requeridas_pace = {'fecha_utc','equipo','posesiones'}
        if requeridas_pace - set(q):
            raise ValueError('Pace requiere columnas fecha_utc, equipo, posesiones')
        q['fecha_utc'] = pd.to_datetime(q.fecha_utc, utc=True, errors='coerce')
        q['posesiones'] = pd.to_numeric(q.posesiones, errors='coerce')
        q = q.loc[(q.fecha_utc < fecha) & q.posesiones.between(60,140)]
        ultimos = [q.loc[q.equipo.eq(e)].sort_values('fecha_utc').tail(10).posesiones for e in (local,visitante)]
        if all(len(v)>=3 for v in ultimos):
            pace = round(float(np.mean([v.mean() for v in ultimos])),2)
    total_c = round(sum(equipos[e]['modelo_c'] for e in (local,visitante)),2)
    total_base = round(sum(equipos[e]['referencia_base'] for e in (local,visitante)),2)
    return {'fecha_utc':fecha.isoformat(), 'local':local, 'visitante':visitante,
            'equipos':equipos, 'total_modelo_c':total_c,
            'total_ensemble':round(sum(equipos[e]['ensemble'] for e in (local,visitante)),2),
            'referencia_total_base':total_base,
            'edge_total_vs_base':round(sum(equipos[e]['ensemble'] for e in (local,visitante))-total_base,2),
            'edge_total_modelo_c_vs_base':round(total_c-total_base,2),
            'pace_prepartido':pace,
            'entrenamiento_observaciones':len(entrenamiento_y),
            'historial_partidos':len(h), 'origen':'prepartido_experimental',
            'nota':'Edge frente a Base es diferencia estadística; no representa cuotas. Pace sin datos se indica null.'}


def main():
    a=argparse.ArgumentParser()
    a.add_argument('--historial',type=Path,required=True)
    a.add_argument('--local',required=True)
    a.add_argument('--visitante',required=True)
    a.add_argument('--fecha-utc',required=True)
    a.add_argument('--posesiones',type=Path)
    a.add_argument('--salida',type=Path,default=Path('nba_lab_resultados_futuro/prediccion.json'))
    args=a.parse_args()
    h=pd.read_csv(args.historial,dtype={'id':str})
    q=pd.read_csv(args.posesiones) if args.posesiones else None
    r=predecir(h,args.local,args.visitante,args.fecha_utc,q)
    args.salida.parent.mkdir(parents=True,exist_ok=True)
    args.salida.write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(r,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
