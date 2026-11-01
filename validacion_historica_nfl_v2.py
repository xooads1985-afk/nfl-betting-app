"""Auditoría histórica NFL, independiente de Streamlit y main.py.
Ejecutar: python validacion_historica_nfl_v2.py 2026
"""
import sys
import pandas as pd
from validacion_historica_nfl import extraer_periodos, _observaciones, PERIODOS


def _total(propio, rival):
    if len(propio) < 3 or len(rival) < 3:
        return None
    return max(0., float(.50 * propio['PF'].tail(5).mean() +
                         .25 * propio['PF'].mean() +
                         .25 * rival['PC'].tail(5).mean()))


def validar(df):
    registros = []
    df = df.sort_values(['gameday', 'game_id']).copy()
    for juego in df.itertuples(index=False):
        previo = df[df.gameday < juego.gameday]
        for lado, equipo, rival in [('home', juego.home_team, juego.away_team),
                                    ('away', juego.away_team, juego.home_team)]:
            propios = _observaciones(df, equipo, juego.gameday)
            rivales = _observaciones(df, rival, juego.gameday)
            if len(propios) < 3 or len(rivales) < 3:
                continue
            propios['PF'] = propios.home_score.where(propios.home_team.eq(equipo), propios.away_score)
            rivales['PC'] = rivales.away_score.where(rivales.home_team.eq(rival), rivales.home_score)
            total = _total(propios, rivales)
            bases = []
            for q in range(1, 5):
                pf = propios[f'favor_q{q}']
                pc = rivales[f'contra_q{q}']
                bases.append(max(0., float(.50 * pf.tail(5).mean() +
                                            .25 * pf.mean() +
                                            .25 * pc.tail(5).mean())))
            if total is None or sum(bases) <= 0:
                continue
            proyecciones = [total * x / sum(bases) for x in bases]
            reales = [getattr(juego, f'{lado}_q{i}') for i in range(1, 5)]
            periodos = [(f'Q{i}', [i-1]) for i in range(1, 5)] + [
                ('1.ª mitad', [0,1]), ('2.ª mitad', [2,3]),
                ('Partido completo', [0,1,2,3])]
            for periodo, indices in periodos:
                pred = sum(proyecciones[i] for i in indices)
                real = sum(reales[i] for i in indices)
                registros.append({'game_id': juego.game_id, 'fecha': juego.gameday,
                                  'equipo': equipo, 'periodo': periodo,
                                  'proyeccion': pred, 'real': real, 'error': pred-real})
    detalle = pd.DataFrame(registros)
    if detalle.empty:
        return detalle, pd.DataFrame(columns=['periodo','observaciones','partidos','MAE','sesgo'])
    resumen = (detalle.groupby('periodo').agg(
        observaciones=('error','size'), partidos=('game_id','nunique'),
        MAE=('error',lambda s: s.abs().mean()), sesgo=('error','mean'))
        .reindex(PERIODOS).reset_index())
    return detalle, resumen.round({'MAE':2, 'sesgo':2})


def ejecutar(temporada=2026):
    import nflreadpy as nfl
    calendario = nfl.load_schedules([int(temporada)])
    pbp = nfl.load_pbp([int(temporada)])
    datos, cobertura = extraer_periodos(pbp, calendario)
    detalle, resumen = validar(datos)
    resumen.to_csv(f'validacion_nfl_{temporada}_resumen.csv', index=False)
    detalle.to_csv(f'validacion_nfl_{temporada}_detalle.csv', index=False)
    print('Cobertura:', cobertura)
    print(resumen.to_string(index=False))

if __name__ == '__main__':
    ejecutar(int(sys.argv[1]) if len(sys.argv)>1 else 2026)
