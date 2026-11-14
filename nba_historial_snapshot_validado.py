"""Historial NBA versionado y verificado; no consulta ESPN ni altera módulos estables."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import pandas as pd

BASE = Path(__file__).resolve().parent / 'nba_cache_preparada'

def cargar_snapshot(desde, hasta):
    """Firma compatible con el cargador (desde, hasta) -> (tabla, incidencias).

    Rechaza snapshots desactualizados en vez de sustituir datos faltantes silenciosamente.
    """
    manifiesto = json.loads((BASE / 'manifiesto.json').read_text(encoding='utf-8'))
    archivo = BASE / 'historial_finalizados.csv'
    contenido = archivo.read_bytes()
    if hashlib.sha256(contenido).hexdigest() != manifiesto['sha256']:
        raise ValueError('SHA-256 del historial persistente no coincide')
    tabla = pd.read_csv(archivo, dtype={'id': str}, encoding='utf-8-sig')
    requeridas = {'id','fecha_utc','local','visitante','finalizado','puntos_local','puntos_visitante'}
    if not requeridas.issubset(tabla.columns):
        raise ValueError('Columnas del historial persistente incompletas')
    if len(tabla) != int(manifiesto['partidos']) or tabla['id'].isna().any() or tabla['id'].duplicated().any():
        raise ValueError('Cantidad o IDs del historial persistente inválidos')
    fechas = pd.to_datetime(tabla['fecha_utc'], utc=True, errors='coerce')
    if fechas.isna().any() or tabla[['puntos_local','puntos_visitante']].isna().any():
        raise ValueError('Fechas o marcadores del historial persistente inválidos')
    if not tabla['finalizado'].astype(str).str.lower().eq('true').all():
        raise ValueError('El snapshot contiene partidos sin finalizar')
    desde = pd.Timestamp(desde).date()
    hasta = pd.Timestamp(hasta).date()
    inicio = pd.Timestamp(manifiesto['desde']).date()
    fin = pd.Timestamp(manifiesto['hasta']).date()
    if desde < inicio:
        raise ValueError('El snapshot no cubre el inicio solicitado')
    # Requerimos cobertura hasta el día anterior al corte solicitado.
    # No basta con que el manifiesto diga "hasta": se necesita actualización diaria.
    if fin < hasta - pd.Timedelta(days=1):
        raise ValueError('Snapshot desactualizado; regenerar historial antes de calcular')
    tabla = tabla.loc[(fechas.dt.date >= desde) & (fechas.dt.date <= hasta)].copy()
    tabla['finalizado'] = True
    tabla['local_id'] = pd.NA
    tabla['visitante_id'] = pd.NA
    tabla['estado'] = 'STATUS_FINAL'
    return tabla, []
