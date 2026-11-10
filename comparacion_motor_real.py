"""Comparación descriptiva entre motor original replicado y modelos del laboratorio.
No proclama superioridad: esquemas de entrenamiento distintos.
"""
import pandas as pd
from baseline_motor_original import evaluar_original
from nfl_lab_precision import backtest

def comparar_motor(calendario,pbp,min_train=150,simulations=10000):
    base=evaluar_original(calendario,pbp)
    lab=backtest(calendario,first_season=2024,min_train=min_train,simulations=simulations,pbp=pbp)
    if base.empty or lab.empty:raise ValueError('Sin datos comparables')
    lab=lab[lab.season.isin([2024,2025])]
    keys=['game_id','target']
    ids=set(map(tuple,base[keys].values.tolist()))
    ids &= set(map(tuple,lab[keys].values.tolist()))
    if not ids:raise ValueError('Sin juegos en común')
    out=pd.concat([base,lab],ignore_index=True)
    out=out[out[keys].apply(tuple,axis=1).isin(ids)].copy()
    if out.duplicated(keys+['model']).any():raise ValueError('Duplicados')
    if (out.groupby(keys).actual.nunique()>1).any():raise ValueError('Marcadores inconsistentes')
    metricas=out.groupby(['model','target'],as_index=False).agg(
      partidos=('game_id','nunique'),MAE=('error',lambda e:e.abs().mean()),
      RMSE=('error',lambda e:(e.pow(2).mean())**.5),sesgo=('error','mean'))
    return out,metricas
