"""Puente aislado de Pace Q1/1H. No modifica predicciones de partido completo."""
from pathlib import Path
import pandas as pd
from nba_pace_periodos_modelo import proyectar_periodos

RUTA = Path(__file__).resolve().parent / 'nba_historial_pace_periodos_validado.csv'

def completar_filas(periodos, partido, ruta=RUTA):
    """Devuelve filas nuevas; conserva la fila Partido original sin modificar."""
    salida = [dict(fila) for fila in periodos]
    if not ruta.is_file():
        return salida, 'Historial Pace por períodos no disponible'
    try:
        historial = pd.read_csv(ruta, encoding='utf-8-sig', dtype={'partido_id':str})
        pred = proyectar_periodos(historial, partido, ventana=10, minimo=5)
    except (OSError, ValueError, KeyError, TypeError, pd.errors.ParserError) as exc:
        return salida, f'Períodos no disponibles: {type(exc).__name__}'
    if pred is None:
        return salida, 'Muestra previa insuficiente para Q1/1H'
    mapa = {'1.er cuarto':'q1','1.ª mitad':'mitad'}
    for fila in salida:
        periodo = mapa.get(fila['periodo'])
        if periodo:
            calculo = pred['periodos'][periodo]
            fila.update({'local':calculo['local'], 'visitante':calculo['visitante'],
                         'ambos':calculo['total']})
    return salida, ('Pace + Eficiencia · Q1/1H · muestra previa: '
                    + str(min(pred['muestras'].values())) + ' partidos por equipo')
