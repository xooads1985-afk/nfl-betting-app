"""Pace prospectivo experimental: no altera archivos estables.

La tabla existente nba_laboratorio_prospectivo admite una fila por
(partido_id, equipo, modelo), con modelo='Pace + Eficiencia'.
"""
from datetime import datetime, timezone
import math
import pandas as pd
from nba_pace_predictivo import predecir_pace

MODELO = 'Pace + Eficiencia'
VERSION = 'pace-prospectivo-1.0'


def preparar_prediccion(historial_pace, juego, ahora=None):
    """Solo encuentros futuros; usa boxscores terminados antes del inicio."""
    fecha = pd.to_datetime(juego.get('fecha_utc'), utc=True, errors='coerce')
    ahora = pd.Timestamp.now(tz='UTC') if ahora is None else pd.to_datetime(ahora, utc=True)
    if pd.isna(fecha) or fecha <= ahora:
        raise ValueError('Solo se permiten predicciones de partidos futuros.')
    if not str(juego.get('id', '')).strip():
        raise ValueError('Falta identificador de partido.')
    if not isinstance(historial_pace, pd.DataFrame) or historial_pace.empty:
        raise ValueError('Falta historial pace completo.')
    historial = historial_pace.copy()
    requeridas = {'fecha_utc', 'finalizado', 'partido_id'}
    if not requeridas.issubset(historial.columns):
        raise ValueError('El historial pace no tiene todas las columnas obligatorias.')
    fechas = pd.to_datetime(historial['fecha_utc'], utc=True, errors='coerce')
    completos = historial['finalizado'].astype(str).str.lower().eq('true')
    historial = historial.loc[fechas.lt(fecha) & completos].copy()
    if historial.empty:
        raise ValueError('No hay partidos finalizados anteriores al encuentro.')
    if 'partido_id' in historial:
        historial['partido_id'] = historial['partido_id'].astype(str)
        historial = historial.drop_duplicates('partido_id', keep='first')
        historial = historial.loc[historial['partido_id'].ne(str(juego['id']))]
    pred = predecir_pace(historial, juego, ventana=10, minimo=3)
    if pred is None:
        raise ValueError('Insuficientes antecedentes anteriores al partido para ambos equipos.')
    equipos = (str(juego['local']), str(juego['visitante']))
    valores = {equipo: float(pred['equipos'][equipo]['prediccion']) for equipo in equipos}
    if not all(math.isfinite(x) and 60 <= x <= 180 for x in valores.values()):
        raise ValueError('Proyección fuera de rango; revisar datos.')
    return {'partido_id': str(juego['id']), 'inicio_utc': fecha.isoformat(),
            'equipos': valores, 'pace_48': float(pred['pace_48']),
            'antecedentes': {e: int(pred['equipos'][e]['muestra']) for e in equipos}}


def preparar_filas_guardado(prediccion, ahora=None):
    ahora = datetime.now(timezone.utc) if ahora is None else pd.to_datetime(ahora, utc=True).to_pydatetime()
    fecha = pd.to_datetime(prediccion['inicio_utc'], utc=True)
    if pd.Timestamp(ahora) >= fecha:
        raise ValueError('El partido ya comenzó: no se puede guardar retrospectivamente.')
    return [{'partido_id': prediccion['partido_id'], 'equipo': equipo,
             'modelo': MODELO, 'proyeccion': valor,
             'inicio_utc': prediccion['inicio_utc'],
             'registrado_utc': ahora.isoformat(), 'version': VERSION}
            for equipo, valor in prediccion['equipos'].items()]


def guardar_pace(prediccion):
    """Reutiliza la tabla experimental, sin modificar predicciones previas."""
    from nba_laboratorio_prospectivo import _consulta
    filas = preparar_filas_guardado(prediccion)
    confirmados = _consulta('POST', '?on_conflict=partido_id,equipo,modelo', filas,
                            prefer='resolution=ignore-duplicates,return=representation')
    return len(confirmados)
