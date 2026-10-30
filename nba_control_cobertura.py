"""Auditoría de cobertura del bloque visible y respaldo consistente SQLite NBA."""
from pathlib import Path
import sqlite3
import tempfile
import pandas as pd
from nba_archivo_temporada import DB, leer_jugadores


def comparar_bloque(calendario, equipo, desde, hasta):
    """Compara IDs finalizados del calendario entregado con boxscores archivados.

    No certifica que el calendario ESPN contenga todos los partidos reales.
    """
    cols = ['id', 'fecha_utc', 'visitante', 'local']
    if calendario is None or calendario.empty:
        return pd.DataFrame(columns=cols), pd.DataFrame(columns=cols), 0
    df = calendario.copy()
    df = df.loc[df['finalizado'].eq(True)].copy()
    if equipo not in (None, 'Todos'):
        df = df.loc[df['local'].eq(equipo) | df['visitante'].eq(equipo)]
    df['id'] = df['id'].fillna('').astype(str).str.strip()
    df = df.loc[df['id'].ne('')].drop_duplicates('id')
    archivados = leer_jugadores(equipo, desde, hasta)
    ids = set(archivados['partido_id'].astype(str)) if not archivados.empty else set()
    faltantes = df.loc[~df['id'].isin(ids), cols].copy()
    presentes = df.loc[df['id'].isin(ids), cols].copy()
    return presentes.reset_index(drop=True), faltantes.reset_index(drop=True), len(df)


def respaldo_sqlite():
    """Copia coherente de la base usando SQLite backup API, sin modificar el original."""
    ruta = Path(DB)
    if not ruta.exists():
        raise FileNotFoundError('Aún no existe el archivo histórico SQLite')
    with tempfile.TemporaryDirectory() as carpeta:
        destino = Path(carpeta) / 'nba_temporada_respaldo.sqlite3'
        with sqlite3.connect(f'file:{ruta}?mode=ro', uri=True, timeout=10) as origen:
            with sqlite3.connect(destino, timeout=10) as copia:
                origen.backup(copia)
        return destino.read_bytes()
