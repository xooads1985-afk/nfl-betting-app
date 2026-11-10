"""Copia local de funciones del motor experimental NFL de GitHub.
Solo las funciones REQUIRED/FEATURES/prepare/features_before_games necesarias
para probar el predictor; el archivo completo del repositorio NO se sustituye.
"""
import numpy as np
import pandas as pd
REQUIRED=['game_id','season','week','gameday','home_team','away_team','home_score','away_score']
FEATURES=['elo_diff','home_pf','home_pa','away_pf','away_pa','home_form','away_form','home_n','away_n','home_rest','away_rest']
def prepare(schedule):
    df=schedule.copy()
    missing=set(REQUIRED)-set(df.columns)
    if missing: raise ValueError('Faltan columnas: '+', '.join(sorted(missing)))
    df['gameday']=pd.to_datetime(df.gameday,errors='coerce').dt.normalize()
    for c in ('home_score','away_score','season','week'):
        df[c]=pd.to_numeric(df[c],errors='coerce')
    df=df.dropna(subset=REQUIRED).copy()
    df=df[(df.home_score>=0)&(df.away_score>=0)&(df.home_team!=df.away_team)]
    if df.game_id.duplicated().any():
        raise ValueError('game_id duplicado: revisar fuente antes de entrenar')
    return df.sort_values(['gameday','game_id']).reset_index(drop=True)
def features_before_games(df):
    """Snapshots diarios: no usa resultados del mismo día ni de fechas posteriores."""
    teams,elo,rows={}, {}, []
    for day,games in df.groupby('gameday',sort=True):
        pending=[]
        for g in games.itertuples(index=False):
            h,a=str(g.home_team),str(g.away_team)
            hs,aw=teams.get(h,[]),teams.get(a,[])
            def mean(v,i):return float(np.mean([z[i] for z in v[-5:]])) if v else 22.
            def rest(v):return min(21,max(0,(day-v[-1][0]).days)) if v else 7
            eh,ea=elo.get(h,1500.),elo.get(a,1500.)
            x=[eh-ea+55,mean(hs,1),mean(hs,2),mean(aw,1),mean(aw,2),
               mean(hs,1)-mean(hs,2),mean(aw,1)-mean(aw,2),
               min(len(hs),16),min(len(aw),16),rest(hs),rest(aw)]
            rows.append(dict(game_id=str(g.game_id),season=int(g.season),week=int(g.week),
                gameday=day,home_team=h,away_team=a,home_score=float(g.home_score),
                away_score=float(g.away_score),**dict(zip(FEATURES,x))))
            pending.append((h,a,float(g.home_score),float(g.away_score),eh,ea))
        for h,a,ph,pa,eh,ea in pending:
            expected=1/(1+10**(-(eh-ea+55)/400))
            outcome=1. if ph>pa else .5 if ph==pa else 0.
            delta=18*(outcome-expected)
            elo[h],elo[a]=eh+delta,ea-delta
            teams.setdefault(h,[]).append((day,ph,pa))
            teams.setdefault(a,[]).append((day,pa,ph))
    return pd.DataFrame(rows)
