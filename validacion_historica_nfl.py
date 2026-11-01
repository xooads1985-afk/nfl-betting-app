"""Auditoría NFL independiente. No modifica la aplicación ni sus estimadores.

Uso en Python con nflreadpy, pandas:
    from validacion_historica_nfl import validar_temporada
    resultados, cobertura = validar_temporada(2026)

Los resultados son retrospectivos y no garantizan precisión futura.
"""
import pandas as pd

PERIODOS = ('Q1', 'Q2', 'Q3', 'Q4', '1.ª mitad', '2.ª mitad', 'Partido completo')


def _pandas(tabla):
    return tabla.to_pandas() if hasattr(tabla, 'to_pandas') else pd.DataFrame(tabla)


def extraer_periodos(pbp, calendario):
    """Extrae parciales y verifica sumas contra los marcadores oficiales finales.

    Solo conserva juegos con cuatro cuartos completos y sin puntos en prórroga.
    """
    pbp = _pandas(pbp).copy()
    calendario = _pandas(calendario).copy()
    pbp.columns = [str(c).lower() for c in pbp.columns]
    calendario.columns = [str(c).lower() for c in calendario.columns]
    requeridas = {'game_id', 'qtr', 'total_home_score', 'total_away_score'}
    if not requeridas.issubset(pbp.columns):
        raise ValueError(f'Faltan columnas PBP: {sorted(requeridas-set(pbp.columns))}')
    cols_cal = {'game_id', 'gameday', 'home_team', 'away_team', 'home_score', 'away_score'}
    if not cols_cal.issubset(calendario.columns):
        raise ValueError(f'Faltan columnas calendario: {sorted(cols_cal-set(calendario.columns))}')
    pbp['qtr'] = pd.to_numeric(pbp.qtr, errors='coerce')
    for col in ('total_home_score', 'total_away_score'):
        pbp[col] = pd.to_numeric(pbp[col], errors='coerce')
    cierre = (pbp[pbp.qtr.between(1, 4)].dropna(subset=['total_home_score','total_away_score'])
              .groupby(['game_id', 'qtr'], as_index=False)[['total_home_score', 'total_away_score']].max())
    filas = []
    for gid, grupo in cierre.groupby('game_id'):
        if set(grupo.qtr.astype(int)) != {1, 2, 3, 4}:
            continue
        grupo = grupo.set_index('qtr').sort_index()
        fila = {'game_id': gid}
        for lado, col in [('home', 'total_home_score'), ('away', 'total_away_score')]:
            acumulados = grupo[col].to_numpy(dtype=float)
            puntos = [acumulados[0]] + list(acumulados[1:] - acumulados[:-1])
            for q, val in enumerate(puntos, 1):
                fila[f'{lado}_q{q}'] = val
        filas.append(fila)
    parciales = pd.DataFrame(filas)
    base = calendario[list(cols_cal)].drop_duplicates('game_id').copy()
    base['gameday'] = pd.to_datetime(base.gameday, errors='coerce')
    base = base.dropna(subset=['gameday','home_score','away_score'])
    if parciales.empty:
        return base.iloc[0:0].copy(), {'finalizados':len(base), 'verificados':0, 'cobertura_pct':0.0}
    unido = base.merge(parciales, on='game_id', how='inner', validate='one_to_one')
    for lado in ('home', 'away'):
        cols = [f'{lado}_q{i}' for i in range(1,5)]
        unido = unido[(unido[cols].ge(0).all(axis=1)) &
                      ((unido[cols].sum(axis=1) - unido[f'{lado}_score']).abs() < 0.01)]
    return unido.sort_values(['gameday','game_id']).reset_index(drop=True), {
        'finalizados':len(base), 'verificados':len(unido),
        'cobertura_pct':round(100*len(unido)/len(base),1) if len(base) else 0.0}


def _observaciones(df, equipo, antes):
    d = df[(df.gameday < antes) & ((df.home_team == equipo) | (df.away_team == equipo))].copy()
    d = d.sort_values(['gameday','game_id'])
    for q in range(1,5):
        local = d.home_team.eq(equipo)
        d[f'favor_q{q}'] = d[f'home_q{q}'].where(local, d[f'away_q{q}'])
        d[f'contra_q{q}'] = d[f'away_q{q}'].where(local, d[f'home_q{q}'])
    return d


def _proyectar(df, equipo, rival, fecha):
    propios, oponentes = _observaciones(df,equipo,fecha), _observaciones(df,rival,fecha)
    if len(propios)<3 or len(oponentes)<3:
        return None
    valores = []
    for q in range(1,5):
        pf, pc = propios[f'favor_q{q}'], oponentes[f'contra_q{q}']
        valores.append(.50*pf.tail(5).mean()+.25*pf.mean()+.25*pc.tail(5).mean())
    return valores


def validar_datos(df):
    """Backtest temporal, sin usar el partido evaluado ni partidos posteriores."""
    registros=[]
    for juego in df.itertuples(index=False):
        fecha = juego.gameday
        for lado, equipo, rival in [('home',juego.home_team,juego.away_team),
                                    ('away',juego.away_team,juego.home_team)]:
            proy = _proyectar(df,equipo,rival,fecha)
            if proy is None:
                continue
            reales = [getattr(juego,f'{lado}_q{i}') for i in range(1,5)]
            bloques = [(f'Q{i}',[i-1]) for i in range(1,5)] + [
                ('1.ª mitad',[0,1]), ('2.ª mitad',[2,3]), ('Partido completo',[0,1,2,3])]
            for periodo, indices in bloques:
                pred = sum(proy[i] for i in indices)
                real = sum(reales[i] for i in indices)
                registros.append({'game_id':juego.game_id,'fecha':fecha,'equipo':equipo,
                                  'periodo':periodo,'proyeccion':pred,'real':real,
                                  'error':pred-real})
    detalle=pd.DataFrame(registros)
    if detalle.empty:
        return detalle, pd.DataFrame(columns=['periodo','observaciones','partidos','MAE','sesgo'])
    resumen=(detalle.groupby('periodo').agg(observaciones=('error','size'),
               partidos=('game_id','nunique'),MAE=('error',lambda s:s.abs().mean()),
               sesgo=('error','mean')).reindex(PERIODOS).reset_index())
    return detalle, resumen.round({'MAE':2,'sesgo':2})


def validar_temporada(temporada=2026):
    import nflreadpy as nfl
    calendario = _pandas(nfl.load_schedules([int(temporada)]))
    pbp = nfl.load_pbp([int(temporada)])
    datos, cobertura = extraer_periodos(pbp,calendario)
    detalle, resumen = validar_datos(datos)
    return resumen, cobertura
