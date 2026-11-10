"""Laboratorio NFL aislado. Backtesting cronológico; no modifica la app principal."""
import argparse
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import HistGradientBoostingRegressor, GradientBoostingRegressor

REQUIRED=['game_id','season','week','gameday','home_team','away_team','home_score','away_score']
FEATURES=['elo_diff','home_pf','home_pa','away_pf','away_pa','home_form','away_form','home_n','away_n','home_rest','away_rest']
MODELS=('ridge','boost','hybrid','ensemble','elo','mc_mean','quantile')
TARGETS=('total','margin','home','away')
EPA_FEATURES=['home_epa_off','home_epa_def','away_epa_off','away_epa_def','home_sr_off','home_sr_def','away_sr_off','away_sr_def']

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


def add_pbp_features(schedule_features,pbp):
    """Snapshots de EPA/SR anteriores a cada fecha, sin usar el partido objetivo.

    Entrada PBP nflverse: game_id, posteam, defteam, epa, success, play_type.
    Solo jugadas pass/run; se agregan primero por partido y equipo para evitar
    que partidos con más jugadas reciban mayor peso en los promedios históricos.
    """
    required={'game_id','posteam','defteam','epa','success','play_type'}
    missing=required-set(pbp.columns)
    if missing:raise ValueError('PBP: faltan columnas '+', '.join(sorted(missing)))
    plays=pbp.loc[pbp.play_type.isin(['pass','run']),list(required)].copy()
    plays['game_id']=plays.game_id.astype(str)
    plays['epa']=pd.to_numeric(plays.epa,errors='coerce')
    plays['success']=pd.to_numeric(plays.success,errors='coerce')
    plays=plays.dropna(subset=['game_id','posteam','defteam','epa','success'])
    # Media por partido/equipo en ofensiva y defensa.
    offense=plays.groupby(['game_id','posteam'],as_index=False).agg(epa=('epa','mean'),sr=('success','mean'))
    defense=plays.groupby(['game_id','defteam'],as_index=False).agg(epa=('epa','mean'),sr=('success','mean'))
    off={(str(r.game_id),str(r.posteam)):(float(r.epa),float(r.sr)) for r in offense.itertuples(index=False)}
    deff={(str(r.game_id),str(r.defteam)):(float(r.epa),float(r.sr)) for r in defense.itertuples(index=False)}
    history={};output=[]
    for day, games in schedule_features.groupby('gameday',sort=True):
        pending=[]
        for g in games.itertuples(index=False):
            row=g._asdict().copy()
            for prefix,team in [('home',str(g.home_team)),('away',str(g.away_team))]:
                old=history.get(team,[])[-8:]
                for index,label in enumerate(('epa_off','epa_def','sr_off','sr_def')):
                    row[f'{prefix}_{label}']=float(np.mean([x[index] for x in old])) if old else (0.0 if 'epa' in label else .45)
            output.append(row)
            for team in [str(g.home_team),str(g.away_team)]:
                o=off.get((str(g.game_id),team));d=deff.get((str(g.game_id),team))
                if o is not None and d is not None:pending.append((team,(o[0],d[0],o[1],d[1])))
        # Actualizar únicamente después de generar TODOS los snapshots del día.
        for team,values in pending:history.setdefault(team,[]).append(values)
    return pd.DataFrame(output)

def calibration_residuals(train, seed=42, features=None):
    features=features or FEATURES
    """Expanding-window, chronological, out-of-sample residual pairs.

    No observation is predicted by a model trained on its own outcome.
    Blocks use distinct dates, avoiding leakage between same-day games.
    """
    data=train.sort_values(['gameday','game_id']).reset_index(drop=True)
    dates=np.asarray(sorted(data.gameday.unique()))
    if len(dates)<12 or len(data)<80:
        return np.empty((0,2))
    # At most four contiguous validation blocks after the first 60% of dates.
    starts=np.linspace(int(len(dates)*.6),len(dates)-1,5,dtype=int)
    residual=[]
    for i in range(4):
        if starts[i]>=starts[i+1]:continue
        cutoff=dates[starts[i]]
        end=dates[starts[i+1]] if i<3 else dates[-1]+np.timedelta64(1,'D')
        past=data[data.gameday<cutoff]
        future=data[(data.gameday>=cutoff)&(data.gameday<end)]
        if len(past)<60 or future.empty:continue
        X=past[features].to_numpy(float)
        Z=future[features].to_numpy(float)
        total=past.home_score.to_numpy()+past.away_score.to_numpy()
        margin=past.home_score.to_numpy()-past.away_score.to_numpy()
        r=make_pipeline(StandardScaler(),Ridge(alpha=100)).fit(X,total)
        b=HistGradientBoostingRegressor(max_iter=110,max_leaf_nodes=12,
            learning_rate=.045,l2_regularization=8,random_state=seed).fit(X,margin)
        residual.extend(np.column_stack([
            future.home_score.to_numpy()+future.away_score.to_numpy()-r.predict(Z),
            future.home_score.to_numpy()-future.away_score.to_numpy()-b.predict(Z)
        ]).tolist())
    return np.asarray(residual).reshape(-1,2)

def fit_predict(train,test,seed=42,simulations=10000,features=None):
    features=features or FEATURES
    X=train[features].to_numpy(float);Z=test[features].to_numpy(float)
    yt=train.home_score.to_numpy()+train.away_score.to_numpy()
    ym=train.home_score.to_numpy()-train.away_score.to_numpy()
    result={};rng=np.random.default_rng(seed)
    for target,y in (('total',yt),('margin',ym)):
        ridge=make_pipeline(StandardScaler(),Ridge(alpha=100)).fit(X,y)
        boost=HistGradientBoostingRegressor(max_iter=110,max_leaf_nodes=12,
            learning_rate=.045,l2_regularization=8,random_state=seed).fit(X,y)
        q=GradientBoostingRegressor(loss='quantile',alpha=.5,n_estimators=90,
            max_depth=2,min_samples_leaf=12,random_state=seed).fit(X,y)
        r,b=ridge.predict(Z),boost.predict(Z)
        hybrid=r if target=='total' else b
        result[target]={'ridge':r,'boost':b,'hybrid':hybrid,
            'ensemble':.5*r+.5*b,'quantile':q.predict(Z)}
        result[target]['residuals']=y-(ridge.predict(X) if target=='total' else boost.predict(X))
    e=train.elo_diff.to_numpy(float)
    slope=np.polyfit(e,ym,1)[0] if np.std(e)>1e-8 else 0.
    result['margin']['elo']=np.mean(ym)+slope*(test.elo_diff.to_numpy()-np.mean(e))
    result['total']['elo']=np.full(len(test),np.mean(yt))
    # Monte Carlo: calibrate uncertainty with chronological out-of-sample residuals.
    # Avoid optimistic in-sample training errors from boosted trees.
    residuals=calibration_residuals(train, seed, features=features)
    if len(residuals)<20:
        # Conservative fallback: only for very small datasets; disclose in report.
        residuals=np.column_stack([result['total']['residuals'],result['margin']['residuals']])
    for start in range(0,len(test),32):
        stop=min(len(test),start+32)
        picks=rng.integers(0,len(residuals),size=(stop-start,simulations))
        for target,index in (('total',0),('margin',1)):
            draws=result[target]['hybrid'][start:stop,None]+residuals[picks,index]
            for name,values in (('mc_mean',draws.mean(axis=1)),('mc_p10',np.quantile(draws,.1,axis=1)),('mc_p90',np.quantile(draws,.9,axis=1))):
                result[target].setdefault(name,[]).extend(values.tolist())
    for target in ('total','margin'):
        for name in ('mc_mean','mc_p10','mc_p90'):result[target][name]=np.asarray(result[target][name])
    for target,sign in (('home',1),('away',-1)):
        result[target]={}
        for model in MODELS:
            result[target][model]=(result['total'][model]+sign*result['margin'][model])/2
    return result

def backtest(df,first_season=2024,min_train=150,simulations=10000,pbp=None):
    feat=features_before_games(prepare(df));rows=[]
    features=FEATURES
    if pbp is not None:
        feat=add_pbp_features(feat,pbp)
        features=FEATURES+EPA_FEATURES
    for (season,week),test in feat.groupby(['season','week'],sort=True):
        if season<first_season:continue
        cutoff=test.gameday.min()
        # Every training observation must be earlier in date and season/week.
        train=feat[(feat.gameday<cutoff)&((feat.season<season)|((feat.season==season)&(feat.week<week)))]
        if len(train)<min_train:continue
        out=fit_predict(train,test,seed=42+int(season)*100+int(week),simulations=simulations,features=features)
        for i,g in enumerate(test.itertuples(index=False)):
            actuals={'total':g.home_score+g.away_score,'margin':g.home_score-g.away_score,
                     'home':g.home_score,'away':g.away_score}
            for target,actual in actuals.items():
                for model in MODELS:
                    prediction=float(out[target][model][i])
                    rows.append(dict(game_id=g.game_id,season=season,week=week,date=str(g.gameday.date()),
                        target=target,model=model,actual=actual,predicted=prediction,
                        error=prediction-actual,train_n=len(train),latest_train_date=str(train.gameday.max().date())))
    return pd.DataFrame(rows)

def summarize(results):
    if results.empty:return pd.DataFrame()
    return results.groupby(['target','model']).agg(games=('game_id','nunique'),
        MAE=('error',lambda x:float(np.mean(np.abs(x)))),
        RMSE=('error',lambda x:float(np.sqrt(np.mean(np.square(x))))),
        bias=('error','mean')).reset_index().sort_values(['target','MAE'])

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--csv',required=True);p.add_argument('--pbp-csv',default=None);p.add_argument('--output',default='nfl_lab_resultados')
    p.add_argument('--simulations',type=int,default=10000)
    p.add_argument('--first-season',type=int,default=2024)
    args=p.parse_args()
    if not 100<=args.simulations<=100000:raise ValueError('simulations fuera de rango')
    result=backtest(pd.read_csv(args.csv),first_season=args.first_season,simulations=args.simulations,
        pbp=pd.read_csv(args.pbp_csv) if args.pbp_csv else None)
    summary=summarize(result)
    dest=Path(args.output);dest.mkdir(parents=True,exist_ok=True)
    result.to_csv(dest/'predicciones.csv',index=False)
    summary.to_csv(dest/'metricas.csv',index=False)
    print(summary.to_string(index=False) if not summary.empty else 'Sin datos suficientes')
if __name__=='__main__':main()
