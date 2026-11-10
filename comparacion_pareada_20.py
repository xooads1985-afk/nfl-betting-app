"""Comparación pareada estricta; referencia de 20 variables aún experimental."""
import numpy as np
import pandas as pd
from baseline_20_variables import validar_baseline
from nfl_lab_precision import backtest

CLAVES=['game_id','target']

def comparar(calendario,pbp,first_season=2024,min_train=150,simulations=10000):
    base=validar_baseline(calendario,pbp,first_season,min_train)
    otros=backtest(calendario,first_season=first_season,min_train=min_train,
                   simulations=simulations,pbp=pbp)
    if base.empty or otros.empty:
        raise ValueError('No hay predicciones comparables')
    juntos=pd.concat([base,otros],ignore_index=True)
    required=CLAVES+['model','actual','predicted','error','date','latest_train_date']
    if not set(required).issubset(juntos):
        raise ValueError('Faltan columnas para comparar')
    if juntos[CLAVES+['model']].isna().any().any():
        raise ValueError('Identificadores nulos')
    if juntos.duplicated(CLAVES+['model']).any():
        raise ValueError('Predicciones duplicadas por partido, objetivo y modelo')
    if not np.isfinite(juntos[['actual','predicted','error']].to_numpy(dtype=float)).all():
        raise ValueError('Predicciones o resultados no finitos')
    if not np.allclose(juntos.error.to_numpy(float),juntos.predicted.to_numpy(float)-juntos.actual.to_numpy(float)):
        raise ValueError('Errores inconsistentes')
    fecha=pd.to_datetime(juntos.date,errors='coerce',utc=True)
    train=pd.to_datetime(juntos.latest_train_date,errors='coerce',utc=True)
    if fecha.isna().any() or train.isna().any() or not (train<fecha).all():
        raise ValueError('Fuga temporal o fechas inválidas')
    # Intersección de juegos/objetivos presentes en TODOS los modelos.
    nmodelos=juntos.model.nunique()
    comunes=juntos.groupby(CLAVES).model.nunique()
    comunes=comunes[comunes==nmodelos].index
    if len(comunes)==0:
        raise ValueError('Sin partidos/objetivos comunes')
    if len(comunes)!=juntos.groupby(CLAVES).ngroups:
        raise ValueError('Cobertura desigual entre modelos: comparación bloqueada')
    # Los resultados reales de un mismo encuentro/objetivo deben coincidir.
    if (juntos.groupby(CLAVES).actual.nunique()>1).any():
        raise ValueError('Resultados reales inconsistentes entre modelos')
    met=juntos.groupby(['model','target'],as_index=False).agg(
        partidos=('game_id','nunique'),MAE=('error',lambda x:abs(x).mean()),
        RMSE=('error',lambda x:(x.pow(2).mean())**.5),sesgo=('error','mean'))
    return juntos,met
