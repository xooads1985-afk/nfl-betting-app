"""Comparación cronológica independiente: distribución por equipo vs. mezcla con liga.
No importa Streamlit ni modifica los módulos de la aplicación.
Uso: python comparar_cuartos_nfl.py 2026
Dependencias: pandas, nflreadpy, validacion_historica_nfl.py
"""
import sys
import pandas as pd
from validacion_historica_nfl import extraer_periodos, _observaciones


def comparar(datos):
    registros = []
    datos = datos.sort_values(['gameday', 'game_id']).copy()
    for juego in datos.itertuples(index=False):
        for lado, equipo, rival in [('home', juego.home_team, juego.away_team),
                                    ('away', juego.away_team, juego.home_team)]:
            propios = _observaciones(datos, equipo, juego.gameday)
            rivales = _observaciones(datos, rival, juego.gameday)
            if min(len(propios), len(rivales)) < 3:
                continue
            pf = propios.home_score.where(propios.home_team.eq(equipo), propios.away_score)
            pc = rivales.away_score.where(rivales.home_team.eq(rival), rivales.home_score)
            total = max(0.0, float(.50*pf.tail(5).mean()+.25*pf.mean()+.25*pc.tail(5).mean()))
            bases = []
            for q in range(1,5):
                anotados = propios[f'favor_q{q}']
                permitidos = rivales[f'contra_q{q}']
                bases.append(max(0.,float(.50*anotados.tail(5).mean()+.25*anotados.mean()+.25*permitidos.tail(5).mean())))
            if sum(bases) <= 0:
                continue
            # Referencia alternativa genuinamente diferente: suavizado hacia la
            # distribución de puntos por cuarto observada en toda la liga ANTES
            # del partido. No usa el partido evaluado ni información posterior.
            anteriores = datos[datos.gameday < juego.gameday]
            totales_liga = [float(anteriores[f'home_q{q}'].sum() +
                                   anteriores[f'away_q{q}'].sum()) for q in range(1, 5)]
            suma_liga = sum(totales_liga)
            if suma_liga <= 0:
                continue
            participaciones = [v / suma_liga for v in totales_liga]
            # Peso 70/30 fijado de antemano; NO optimizado con los resultados.
            mezcla = [.70*b + .30*total*participaciones[i]
                      for i,b in enumerate(bases)]
            metodos = {'Historico por equipo': bases,
                       'Mezcla 70% equipo 30% liga': mezcla}
            reales = [getattr(juego, f'{lado}_q{i}') for i in range(1,5)]
            bloques = [(f'Q{i}', [i-1]) for i in range(1,5)] + [('1.ª mitad',[0,1]), ('2.ª mitad',[2,3]), ('Partido completo',[0,1,2,3])]
            for metodo, valores in metodos.items():
                for periodo, indices in bloques:
                    proy = sum(valores[i] for i in indices)
                    real = sum(reales[i] for i in indices)
                    registros.append({'game_id':juego.game_id, 'fecha':juego.gameday, 'equipo':equipo,
                                     'metodo':metodo,'periodo':periodo,'proyeccion':proy,'real':real,'error':proy-real})
    detalle = pd.DataFrame(registros)
    if detalle.empty:
        raise RuntimeError('No hay partidos con historial suficiente para comparar.')
    resumen = (detalle.groupby(['periodo','metodo'], as_index=False)
               .agg(observaciones=('error','size'),partidos=('game_id','nunique'),
                    MAE=('error',lambda s:s.abs().mean()),sesgo=('error','mean')))
    resumen[['MAE','sesgo']] = resumen[['MAE','sesgo']].round(3)
    return detalle,resumen


def main(temporada):
    import nflreadpy as nfl
    calendario = nfl.load_schedules([temporada])
    pbp = nfl.load_pbp([temporada])
    datos, cobertura = extraer_periodos(pbp, calendario)
    detalle, resumen = comparar(datos)
    detalle.to_csv(f'comparacion_cuartos_nfl_{temporada}_detalle.csv', index=False)
    resumen.to_csv(f'comparacion_cuartos_nfl_{temporada}_resumen.csv', index=False)
    print('Cobertura:', cobertura)
    print(resumen.to_string(index=False))

if __name__ == '__main__':
    main(int(sys.argv[1]) if len(sys.argv)>1 else 2026)
