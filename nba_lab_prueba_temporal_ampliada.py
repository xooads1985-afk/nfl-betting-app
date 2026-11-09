#!/usr/bin/env python3
"""Prueba temporal ampliada: múltiples fechas, características y Modelo C.
Solo lectura del historial; escribe un CSV y un resumen en la carpeta de auditoría.
"""
import argparse
from pathlib import Path
import numpy as np
import pandas as pd
from nba_lab_motor_offline import _nba_lab_ml_caracteristicas, _nba_lab_modelo_c

AJUSTES = {'forma': True, 'sede': True, 'descanso': True, 'pace': False, 'fuerza': True, 'regresion': True}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--historico', default='nba_lab_resultados/partidos_historicos.csv')
    parser.add_argument('--salida', default='nba_lab_auditoria_resultados')
    parser.add_argument('--fechas', type=int, default=20)
    args = parser.parse_args()
    if args.fechas < 2:
        raise ValueError('Se requieren al menos 2 fechas de prueba')
    d = pd.read_csv(args.historico, dtype={'id': str})
    required = {'fecha_utc', 'finalizado', 'id', 'local', 'visitante', 'puntos_local', 'puntos_visitante'}
    if not required.issubset(d.columns):
        raise ValueError(f'Faltan columnas: {sorted(required-set(d.columns))}')
    d['_fecha_ml'] = pd.to_datetime(d.fecha_utc, utc=True, errors='coerce')
    d = d.loc[d.finalizado.eq(True)].dropna(subset=['_fecha_ml']).sort_values('_fecha_ml').copy()
    fechas = d['_fecha_ml'].drop_duplicates().sort_values().tolist()
    if len(d) < 150 or len(fechas) < 30:
        raise ValueError('Historial insuficiente')
    # Fechas repartidas desde 25% hasta 90% del historial; cada una tiene juegos futuros.
    indices = np.unique(np.linspace(int(len(fechas)*.25), min(len(fechas)-2,int(len(fechas)*.90)), args.fechas, dtype=int))
    filas = []
    for idx in indices:
        fecha = fechas[int(idx)]
        previo = d.loc[d['_fecha_ml'].le(fecha)].copy()
        juegos = previo.loc[previo['_fecha_ml'].eq(fecha)]
        for _, juego in juegos.iterrows():
            fila = {'fecha':str(fecha),'partido':str(juego['id']),'estado':'OK','detalle':''}
            try:
                a = _nba_lab_ml_caracteristicas(previo,juego)
                b = _nba_lab_ml_caracteristicas(d,juego)
                if len(a)!=2 or len(b)!=2:
                    fila['estado']='OMITIDO';fila['detalle']='Características incompletas'
                elif any(x['equipo']!=y['equipo'] or not np.allclose(x['x'],y['x'],rtol=0,atol=1e-9,equal_nan=True) for x,y in zip(a,b)):
                    fila['estado']='ERROR';fila['detalle']='Características cambiaron al agregar futuro'
                else:
                    x = _nba_lab_modelo_c(previo,juego,AJUSTES)
                    y = _nba_lab_modelo_c(d,juego,AJUSTES)
                    if x is None or y is None:
                        fila['estado']='OMITIDO';fila['detalle']='Modelo C sin predicción'
                    elif set(x)!=set(y) or any(not np.isclose(x[k]['pred'],y[k]['pred'],rtol=0,atol=1e-9) for k in x):
                        fila['estado']='ERROR';fila['detalle']='Modelo C cambió al agregar futuro'
            except Exception as exc:
                fila['estado']='ERROR';fila['detalle']=f'{type(exc).__name__}: {str(exc)[:160]}'
            filas.append(fila)
    salida=Path(args.salida);salida.mkdir(parents=True,exist_ok=True)
    tabla=pd.DataFrame(filas)
    tabla.to_csv(salida/'prueba_temporal_ampliada.csv',index=False)
    conteos=tabla.estado.value_counts().to_dict()
    ok=conteos.get('OK',0);errors=conteos.get('ERROR',0);omitted=conteos.get('OMITIDO',0)
    resumen=(f'Fechas seleccionadas: {len(indices)}\nPartidos comprobados: {ok}\n'
             f'Partidos omitidos: {omitted}\nErrores: {errors}\n'
             'Alcance: características históricas y Modelo C. No verifica los demás algoritmos.\n')
    (salida/'prueba_temporal_ampliada_resumen.txt').write_text(resumen,encoding='utf-8')
    print(resumen)
    if errors or ok < len(indices):
        raise SystemExit('Validación temporal insuficiente o fallida: revisar CSV')

if __name__=='__main__':
    main()
