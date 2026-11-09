#!/usr/bin/env python3
"""Prueba de invariancia temporal de los modelos del laboratorio NBA; solo lectura."""
import argparse
from pathlib import Path
import numpy as np
import pandas as pd
from nba_lab_motor_offline import _nba_lab_ml_validacion

MODELOS = ['Base', 'Modelo C', 'Ridge', 'Bayesiano', 'Gradient Boosting', 'Ensemble', 'Regresión lineal', 'Binomial negativa']

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--historico', default='nba_lab_resultados/partidos_historicos.csv')
    ap.add_argument('--salida', default='nba_lab_auditoria_resultados')
    ap.add_argument('--fechas', type=int, default=4)
    args = ap.parse_args()
    d = pd.read_csv(args.historico, dtype={'id':str})
    d['_ts'] = pd.to_datetime(d.fecha_utc, utc=True, errors='coerce')
    d = d.loc[d.finalizado.eq(True)].dropna(subset=['_ts','puntos_local','puntos_visitante']).sort_values('_ts').copy()
    fechas = d['_ts'].drop_duplicates().sort_values().tolist()
    if len(fechas)<50: raise ValueError('Historial insuficiente')
    # Fechas posteriores al calentamiento y distribuidas por el historial.
    indices = np.unique(np.linspace(max(30, int(len(fechas)*.35)), max(31, int(len(fechas)*.90)), args.fechas, dtype=int))
    salida = Path(args.salida); salida.mkdir(parents=True, exist_ok=True)
    filas=[]
    for idx in indices:
        fecha = fechas[int(idx)]
        anterior = d.loc[d['_ts'].le(fecha)].drop(columns=['_ts'])
        completo = d.drop(columns=['_ts'])
        # Misma función real de validación en ambos escenarios.
        p, _ = _nba_lab_ml_validacion(anterior, fechas_objetivo=[fecha])
        f, _ = _nba_lab_ml_validacion(completo, fechas_objetivo=[fecha])
        if p.empty or f.empty: raise AssertionError(f'No se generaron predicciones para {fecha}')
        a = p.set_index(['partido','equipo']); b=f.set_index(['partido','equipo'])
        if set(a.index)!=set(b.index): raise AssertionError(f'Cambió el conjunto de equipos para {fecha}')
        for key in a.index:
            for modelo in MODELOS:
                if modelo not in a or modelo not in b: continue
                v1 = pd.to_numeric(pd.Series([a.loc[key,modelo]]),errors='coerce').iloc[0]
                v2 = pd.to_numeric(pd.Series([b.loc[key,modelo]]),errors='coerce').iloc[0]
                ok = (pd.isna(v1) and pd.isna(v2)) or (np.isfinite(v1) and np.isfinite(v2) and np.isclose(v1,v2,atol=1e-7,rtol=0))
                filas.append({'fecha':str(fecha),'partido':key[0],'equipo':key[1],'modelo':modelo,'estado':'OK' if ok else 'ERROR','pred_sin_futuro':v1,'pred_con_futuro':v2})
    tabla=pd.DataFrame(filas)
    if tabla.empty: raise ValueError('No hubo comparaciones válidas')
    tabla.to_csv(salida/'validacion_modelos_temporal.csv',index=False)
    errores=int(tabla.estado.eq('ERROR').sum())
    resumen=f'Fechas comprobadas: {len(indices)}\nComparaciones: {len(tabla)}\nErrores: {errores}\nAlcance: invariancia ante agregar partidos posteriores, en fechas muestreadas. No garantiza ausencia absoluta de filtraciones.\n'
    (salida/'validacion_modelos_temporal_resumen.txt').write_text(resumen,encoding='utf-8')
    print(resumen)
    if errores: raise SystemExit('ERROR: predicciones alteradas por partidos posteriores')

if __name__=='__main__': main()
