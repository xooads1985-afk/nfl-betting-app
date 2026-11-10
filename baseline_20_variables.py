"""Réplica experimental de la arquitectura NFL de 20 variables.
No sustituye al motor original: parámetros de entrenamiento pendientes de cotejo.
"""
import numpy as np
import pandas as pd
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import Ridge
from sklearn.ensemble import HistGradientBoostingRegressor
from nfl_lab_precision import prepare, features_before_games, add_pbp_features

VARIABLES = ['local_pf','local_pa','local_victorias','visitante_pf','visitante_pa',
'visitante_victorias','local_epa_of','local_epa_def','visitante_epa_of','visitante_epa_def',
'local_sr_of','local_sr_def','visitante_sr_of','visitante_sr_def','local_juegos',
'visitante_juegos','descanso_local','descanso_visitante','local_en_casa_pf','visitante_fuera_pf']

def construir(schedules,pbp):
    base=add_pbp_features(features_before_games(prepare(schedules)),pbp)
    historial={}; salida=[]
    for fecha,grupo in base.groupby('gameday',sort=True):
        pendientes=[]
        for g in grupo.itertuples(index=False):
            d=g._asdict(); h=historial.get(g.home_team,[]);a=historial.get(g.away_team,[])
            def victorias(rows):return sum(z['pf']>z['pa'] for z in rows)
            def media(rows,field,default=22.):return float(np.mean([z[field] for z in rows])) if rows else default
            def sede(rows,es_local):return media([z for z in rows if z['local']==es_local],'pf')
            vals=[g.home_pf,g.home_pa,victorias(h),g.away_pf,g.away_pa,victorias(a),
            g.home_epa_off,g.home_epa_def,g.away_epa_off,g.away_epa_def,
            g.home_sr_off,g.home_sr_def,g.away_sr_off,g.away_sr_def,
            len(h),len(a),g.home_rest,g.away_rest,sede(h,True),sede(a,False)]
            salida.append({**d,**dict(zip(VARIABLES,vals))})
            pendientes.extend([(g.home_team,{'pf':g.home_score,'pa':g.away_score,'local':True}),
                               (g.away_team,{'pf':g.away_score,'pa':g.home_score,'local':False})])
        for team,record in pendientes:historial.setdefault(team,[]).append(record)
    return pd.DataFrame(salida)

def validar_baseline(schedules,pbp,first_season=2024,min_train=150):
    df=construir(schedules,pbp); resultados=[]
    for (season,week),test in df.groupby(['season','week'],sort=True):
        if season<first_season:continue
        train=df[(df.gameday<test.gameday.min())&((df.season<season)|((df.season==season)&(df.week<week)))]
        if len(train)<min_train:continue
        x=train[VARIABLES].to_numpy(float); z=test[VARIABLES].to_numpy(float)
        total=train.home_score.to_numpy()+train.away_score.to_numpy()
        margen=train.home_score.to_numpy()-train.away_score.to_numpy()
        ridge=make_pipeline(StandardScaler(),Ridge(alpha=100)).fit(x,total)
        boost=HistGradientBoostingRegressor(max_iter=110,max_leaf_nodes=12,learning_rate=.045,
                                            l2_regularization=8,random_state=42).fit(x,margen)
        pt=ridge.predict(z);pm=boost.predict(z)
        for i,g in enumerate(test.itertuples(index=False)):
            preds={'total':pt[i],'margin':pm[i],'home':(pt[i]+pm[i])/2,'away':(pt[i]-pm[i])/2}
            real={'total':g.home_score+g.away_score,'margin':g.home_score-g.away_score,
                  'home':g.home_score,'away':g.away_score}
            for target,pred in preds.items():
                resultados.append(dict(game_id=g.game_id,season=season,week=week,date=str(g.gameday.date()),
                  target=target,model='baseline_20_experimental',actual=real[target],predicted=float(pred),
                  error=float(pred-real[target]),train_n=len(train),latest_train_date=str(train.gameday.max().date())))
    return pd.DataFrame(resultados)
