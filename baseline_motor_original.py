"""Referencia aislada basada en las 20 variables y el entrenamiento del modulo_nfl.py.
No importa Streamlit ni altera el motor original. Evalúa temporadas completas 2024/2025.
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import Ridge
from nfl_lab_precision import prepare
from baseline_20_variables import VARIABLES

def construir_original(calendario,pbp):
    df=prepare(calendario)
    req=['game_id','posteam','defteam','epa','success','play_type']
    if not set(req).issubset(pbp.columns): raise ValueError('Faltan columnas PBP')
    p=pbp[req].copy();p=p[p.play_type.isin(['pass','run'])]
    p['epa']=pd.to_numeric(p.epa,errors='coerce');p['success']=pd.to_numeric(p.success,errors='coerce')
    p=p.dropna(subset=['game_id','posteam','defteam','epa','success'])
    atk=p.groupby(['game_id','posteam'],as_index=False).agg(epa_of=('epa','mean'),sr_of=('success','mean'),jugadas=('epa','size'))
    de=p.groupby(['game_id','defteam'],as_index=False).agg(epa_def=('epa','mean'),sr_def=('success','mean'))
    equipos=atk.merge(de,left_on=['game_id','posteam'],right_on=['game_id','defteam'],how='inner')
    stats={(str(x.game_id),str(x.posteam)):x for x in equipos.itertuples(index=False)}
    historial={}; anterior={}; temporada_anterior=None; rows=[]; sin_cobertura=0
    def previo(team,fecha,ubicacion):
        juegos=historial.get(team,[])[-5:]
        if not juegos:return dict(pf=21.,pa=21.,victorias=.5,epa_of=0.,epa_def=0.,sr_of=.45,sr_def=.45,n=0,descanso=7,ubicacion_pf=21.)
        sub=[x for x in juegos if x['ubicacion']==ubicacion]
        return dict(pf=float(np.mean([x['pf'] for x in juegos])),pa=float(np.mean([x['pa'] for x in juegos])),
          victorias=float(np.mean([x['victoria'] for x in juegos])),
          epa_of=float(np.mean([x['epa_of'] for x in juegos])),epa_def=float(np.mean([x['epa_def'] for x in juegos])),
          sr_of=float(np.mean([x['sr_of'] for x in juegos])),sr_def=float(np.mean([x['sr_def'] for x in juegos])),
          n=len(juegos),descanso=int(np.clip((fecha-juegos[-1]['fecha']).days,0,21)),
          ubicacion_pf=float(np.mean([x['pf'] for x in sub])) if sub else 21.)
    for fecha,grupo in df.groupby('gameday',sort=True):
        temporadas=set(grupo.season.astype(int))
        if len(temporadas)!=1:raise ValueError('Temporadas distintas el mismo día')
        season=next(iter(temporadas))
        if season!=temporada_anterior:
            anterior={k:list(v[-5:]) for k,v in historial.items()};historial.clear();temporada_anterior=season
        pendientes=[]
        for g in grupo.itertuples(index=False):
            h=previo(str(g.home_team),fecha,'casa');a=previo(str(g.away_team),fecha,'fuera')
            vals=[h['pf'],h['pa'],h['victorias'],a['pf'],a['pa'],a['victorias'],
                  h['epa_of'],h['epa_def'],a['epa_of'],a['epa_def'],
                  h['sr_of'],h['sr_def'],a['sr_of'],a['sr_def'],h['n'],a['n'],
                  h['descanso'],a['descanso'],h['ubicacion_pf'],a['ubicacion_pf']]
            rows.append(dict(game_id=str(g.game_id),gameday=fecha,season=int(g.season),week=int(g.week),
               home_team=str(g.home_team),away_team=str(g.away_team),home_score=g.home_score,away_score=g.away_score,
               **dict(zip(VARIABLES,vals))))
            sh=stats.get((str(g.game_id),str(g.home_team)));sa=stats.get((str(g.game_id),str(g.away_team)))
            if sh is None or sa is None or sh.jugadas<10 or sa.jugadas<10:
                sin_cobertura+=1;continue
            for team,pf,pa,st,loc in [(str(g.home_team),g.home_score,g.away_score,sh,'casa'),
                                      (str(g.away_team),g.away_score,g.home_score,sa,'fuera')]:
                pendientes.append((team,dict(fecha=fecha,pf=float(pf),pa=float(pa),
                  victoria=float(pf>pa)+.5*float(pf==pa),ubicacion=loc,
                  epa_of=float(st.epa_of),epa_def=float(st.epa_def),sr_of=float(st.sr_of),sr_def=float(st.sr_def))))
        for team,record in pendientes:historial.setdefault(team,[]).append(record)
    if sin_cobertura:raise ValueError(f'Faltan PBP válidos para {sin_cobertura} juegos')
    return pd.DataFrame(rows)

def evaluar_original(calendario,pbp,temporadas=(2024,2025)):
    df=construir_original(calendario,pbp);out=[]
    for season in temporadas:
        train=df[(df.season>=2022)&(df.season<season)];test=df[df.season==season]
        if len(train)<200 or len(test)<100:raise ValueError(f'Muestra insuficiente para {season}')
        x=train[VARIABLES];z=test[VARIABLES]
        total=train.home_score+train.away_score;margen=train.home_score-train.away_score
        ridge=make_pipeline(StandardScaler(),Ridge(alpha=100.)).fit(x,total)
        boost=HistGradientBoostingRegressor(max_iter=110,max_leaf_nodes=12,learning_rate=.045,
                                              l2_regularization=8.,random_state=42).fit(x,margen)
        pt=ridge.predict(z);pm=boost.predict(z)
        for i,g in enumerate(test.itertuples(index=False)):
            actual={'total':g.home_score+g.away_score,'margin':g.home_score-g.away_score,
                    'home':g.home_score,'away':g.away_score}
            preds={'total':pt[i],'margin':pm[i],'home':(pt[i]+pm[i])/2,'away':(pt[i]-pm[i])/2}
            for target,pred in preds.items():
                out.append(dict(game_id=g.game_id,season=season,week=g.week,date=str(g.gameday.date()),
                 target=target,model='motor_original_replicado',actual=float(actual[target]),
                 predicted=float(pred),error=float(pred-actual[target]),train_n=len(train),
                 latest_train_date=str(train.gameday.max().date())))
    return pd.DataFrame(out)
