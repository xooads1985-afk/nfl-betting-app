"""Proyecciones NFL experimentales: solo juegos finalizados y futuros.

Requiere calendario_prospectivo.py y nfl_lab_precision.py del laboratorio.
No escribe predicciones; el guardado se hace con registro_prospectivo.registrar.
"""
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import HistGradientBoostingRegressor
from calendario_prospectivo import separar
from nfl_lab_precision import FEATURES, features_before_games, prepare


def proyectar(calendario, ahora_utc=None, minimo_entrenamiento=150):
    """Devuelve proyecciones coherentes Ridge/Ensemble para próximos partidos.

    No utiliza marcadores futuros ni resultados del mismo día. Se entrena
    únicamente con partidos cuyo estado es FINAL y cuya fecha ya pasó.
    """
    completos, futuros, excluidos = separar(calendario, ahora_utc)
    if futuros.empty:
        return pd.DataFrame(columns=['game_id','kickoff_utc','modelo','puntos_local','puntos_visitante','total','margen','entrenamiento_n'])
    if len(completos) < minimo_entrenamiento:
        raise ValueError('Historial finalizado insuficiente para entrenar')
    historial = completos.rename(columns={'kickoff_utc':'fecha_original'}).copy()
    historial['gameday'] = historial['fecha_original'].dt.tz_convert('UTC').dt.tz_localize(None).dt.normalize()
    hist = prepare(historial)
    # Construir snapshots futuros individualmente: jamás actualizar el estado
    # con marcadores ficticios de otros partidos programados.
    train = features_before_games(hist)
    predictions = []
    for future in futuros.itertuples(index=False):
        day = pd.Timestamp(future.kickoff_utc).tz_convert('UTC').tz_localize(None).normalize()
        # Solo días estrictamente anteriores al objetivo (sin filtración intradía).
        past = hist.loc[hist.gameday < day].copy()
        training = train.loc[train.gameday < day].copy()
        if len(training) < minimo_entrenamiento:
            continue
        dummy = pd.DataFrame([dict(game_id=str(future.game_id),season=int(future.season),
            week=int(future.week),gameday=day,home_team=str(future.home_team),
            away_team=str(future.away_team),home_score=0.,away_score=0.)])
        snapshot = features_before_games(pd.concat([past,dummy],ignore_index=True))
        test = snapshot.loc[snapshot.game_id.eq(str(future.game_id))]
        if len(test)!=1:raise ValueError('No se pudo construir snapshot del partido')
        X=training[FEATURES].to_numpy(float)
        Z=test[FEATURES].to_numpy(float)
        yt=training.home_score.to_numpy(float)+training.away_score.to_numpy(float)
        ym=training.home_score.to_numpy(float)-training.away_score.to_numpy(float)
        outputs={}
        for target,y in [('total',yt),('margen',ym)]:
            ridge=make_pipeline(StandardScaler(),Ridge(alpha=100)).fit(X,y)
            boost=HistGradientBoostingRegressor(max_iter=110,max_leaf_nodes=12,
                learning_rate=.045,l2_regularization=8,random_state=42).fit(X,y)
            r=float(ridge.predict(Z)[0]);b=float(boost.predict(Z)[0])
            outputs[target]={'ridge':r,'ensemble':(r+b)/2}
        for modelo in ('ridge','ensemble'):
            total=outputs['total'][modelo]
            margen=outputs['margen'][modelo]
            local=max(0.,(total+margen)/2)
            visita=max(0.,(total-margen)/2)
            predictions.append(dict(game_id=str(future.game_id),
                kickoff_utc=pd.Timestamp(future.kickoff_utc).isoformat(),
                modelo=modelo,puntos_local=local,puntos_visitante=visita,
                total=local+visita,margen=local-visita,
                entrenamiento_n=len(training)))
    return pd.DataFrame(predictions)
