"""Auditoría de cobertura ESPN, independiente y sin modificar los motores NBA."""
from __future__ import annotations
import pandas as pd
from nba_pace_extractor import extraer_pace_desde_detalle


def auditar_partidos(partidos: pd.DataFrame, cargar_detalle, max_partidos: int = 10):
    """Sólo inspecciona partidos finalizados; no guarda ni reentrena modelos.

    cargar_detalle: función existente modulo_nba.cargar_detalle, inyectada por llamador.
    """
    if not callable(cargar_detalle):
        raise TypeError('cargar_detalle debe ser una función')
    if not isinstance(max_partidos, int) or not 1 <= max_partidos <= 50:
        raise ValueError('max_partidos debe estar entre 1 y 50')
    columnas = ['id', 'finalizado', 'fecha_utc', 'local', 'visitante']
    if not isinstance(partidos, pd.DataFrame) or not set(columnas).issubset(partidos.columns):
        raise ValueError('Faltan columnas del historial de partidos')
    juegos = partidos.loc[partidos['finalizado'].eq(True)].copy()
    juegos['id'] = juegos['id'].astype(str).str.strip()
    juegos = juegos.loc[juegos['id'].str.fullmatch(r'\d+')].drop_duplicates('id')
    juegos = juegos.sort_values('fecha_utc').tail(max_partidos)
    filas = []
    for _, juego in juegos.iterrows():
        pid = juego['id']
        try:
            r = extraer_pace_desde_detalle(cargar_detalle(pid), pid)
            base = {'partido_id': pid, 'fecha_utc': juego['fecha_utc'], 'local': juego['local'],
                    'visitante': juego['visitante'], 'estado': r['estado'],
                    'advertencias': '; '.join(r['advertencias'])}
            for t in r['equipos']:
                filas.append({**base, 'equipo_id': t['equipo_id'], 'equipo': t['equipo'],
                              'fga': t['estadisticas'].get('fga'), 'fta': t['estadisticas'].get('fta'),
                              'oreb': t['estadisticas'].get('oreb'), 'tov': t['estadisticas'].get('tov'),
                              'posesiones_estimadas': t['posesiones_estimadas'],
                              'faltantes': ', '.join(t['faltantes'])})
            if not r['equipos']:
                filas.append({**base, 'equipo_id': None, 'equipo': None, 'faltantes': 'boxscore de equipos no disponible'})
        except Exception as exc:
            filas.append({'partido_id': pid, 'fecha_utc': juego['fecha_utc'], 'local': juego['local'],
                          'visitante': juego['visitante'], 'estado': 'error',
                          'advertencias': f'{type(exc).__name__}: {exc}', 'faltantes': 'consulta fallida'})
    return pd.DataFrame(filas)


def resumen_cobertura(auditoria: pd.DataFrame):
    if auditoria.empty:
        return {'partidos_revisados': 0, 'partidos_completos': 0, 'cobertura_pct': None}
    grupos = auditoria.groupby('partido_id', sort=False)
    completos = sum(len(g) == 2 and g['estado'].eq('completo').all() and
                    g['posesiones_estimadas'].notna().all() for _, g in grupos)
    total = len(grupos)
    return {'partidos_revisados': total, 'partidos_completos': completos,
            'cobertura_pct': round(100 * completos / total, 1)}
