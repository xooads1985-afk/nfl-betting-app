"""Adaptador de lectura del historial NBA desde modulo_nba, sin modificar módulos estables."""
from datetime import date, timedelta
import pandas as pd


def cargar_historial_bloques(desde, hasta, *, cargar_partidos=None):
    """Consulta bloques de hasta 32 días; devuelve (DataFrame, incidencias).

    Ante fallos parciales devuelve incidencias para que el motor no entrene
    silenciosamente con una muestra incompleta.
    """
    if cargar_partidos is None:
        from modulo_nba import cargar_partidos
    inicio = date.fromisoformat(str(desde))
    fin = date.fromisoformat(str(hasta))
    if fin < inicio:
        raise ValueError('Rango histórico invertido')
    bloques, incidencias = [], []
    cursor = inicio
    while cursor <= fin:
        cierre = min(cursor + timedelta(days=31), fin)
        try:
            tabla, errores = cargar_partidos(cursor, cierre)
            if errores:
                incidencias.extend(f'{cursor}/{cierre}: {e}' for e in errores)
            if tabla is None or not isinstance(tabla, pd.DataFrame):
                incidencias.append(f'{cursor}/{cierre}: respuesta sin tabla')
            else:
                bloques.append(tabla)
        except Exception as exc:
            incidencias.append(f'{cursor}/{cierre}: {type(exc).__name__}: {exc}')
        cursor = cierre + timedelta(days=1)
    if not bloques:
        return pd.DataFrame(), incidencias or ['No se obtuvo historial']
    historial = pd.concat(bloques, ignore_index=True)
    if 'id' in historial.columns:
        historial = historial.drop_duplicates('id', keep='last')
    return historial, incidencias
