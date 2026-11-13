"""Selección conservadora por MAE sobre métricas históricas auditadas."""
import csv
from math import isfinite
from pathlib import Path

MINIMO_EQUIPO = 100
MINIMO_TOTAL = 50


def _mejor(archivo, modelos, minimo):
    try:
        with Path(archivo).open(encoding='utf-8-sig', newline='') as f:
            filas = list(csv.DictReader(f))
    except (OSError, UnicodeError, csv.Error):
        return None
    candidatos = []
    for r in filas:
        if r.get('temporada') != 'Todas' or r.get('modelo') not in modelos:
            continue
        try:
            n, mae = int(r['muestra']), float(r['MAE'])
        except (ValueError, TypeError, KeyError):
            continue
        if n >= minimo and isfinite(mae) and mae >= 0:
            candidatos.append((r['modelo'], n, mae))
    # Todos los modelos participantes deben haber sido evaluados en la misma muestra.
    if len({x[0] for x in candidatos}) != len(candidatos) or len({x[1] for x in candidatos}) != 1:
        return None
    if len(candidatos) < 2:
        return None
    modelo, muestra, mae = min(candidatos, key=lambda x: (x[2], x[0]))
    return {'modelo': modelo, 'mae': mae, 'muestra': muestra}


def seleccionar(modelos, carpeta):
    disponibles = {r['modelo']: r for r in modelos}
    carpeta = Path(carpeta)
    por_equipo = _mejor(carpeta / 'metricas_por_equipo.csv', disponibles, MINIMO_EQUIPO)
    total = _mejor(carpeta / 'metricas_totales.csv', disponibles, MINIMO_TOTAL)
    if por_equipo:
        por_equipo = {**por_equipo, 'local': disponibles[por_equipo['modelo']]['local'],
                      'visitante': disponibles[por_equipo['modelo']]['visitante']}
    if total:
        total = {**total, 'valor': disponibles[total['modelo']]['total']}
    # El margen requiere backtest con localía; nunca declarar un ganador sin ella.
    return {'equipo': por_equipo, 'total': total, 'margen': None}
