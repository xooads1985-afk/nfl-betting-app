"""Auditoría NBA y exportación SQLite compatible desde el archivo Supabase.

No utiliza SQLite como almacenamiento principal. La exportación SQLite se crea
únicamente cuando el usuario solicita descargar un respaldo.
"""
from pathlib import Path
import sqlite3
import tempfile

import pandas as pd
from nba_archivo_temporada import leer_jugadores, _leer_todo


def comparar_bloque(calendario, equipo, desde, hasta):
    """Compara juegos finalizados visibles con jugadores archivados en Supabase.

    No certifica que el calendario externo contenga todos los juegos reales.
    """
    cols = ['id', 'fecha_utc', 'visitante', 'local']
    if calendario is None or calendario.empty:
        vacio = pd.DataFrame(columns=cols)
        return vacio.copy(), vacio.copy(), 0
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
    """Exporta las tres tablas de Supabase a un archivo SQLite descargable.

    La exportación no altera Supabase ni escribe una base SQLite permanente.
    Las tablas se consultan secuencialmente, no como snapshot transaccional.
    """
    partidos = _leer_todo('partidos', columnas='id,fecha,payload')
    jugadores = _leer_todo('jugadores', columnas='partido_id,equipo,identidad,fecha,payload')
    consultas = _leer_todo(
        'consultas',
        columnas='desde,hasta,equipo,consultado_utc,partidos,registros,incidencias,estado',
    )
    with tempfile.TemporaryDirectory() as carpeta:
        destino = Path(carpeta) / 'nba_temporada_respaldo.sqlite3'
        with sqlite3.connect(destino) as conn:
            conn.executescript('''
                CREATE TABLE partidos (
                    id TEXT PRIMARY KEY, fecha TEXT, payload TEXT NOT NULL
                );
                CREATE TABLE jugadores (
                    partido_id TEXT NOT NULL, equipo TEXT NOT NULL,
                    identidad TEXT NOT NULL, fecha TEXT, payload TEXT NOT NULL,
                    PRIMARY KEY(partido_id, equipo, identidad)
                );
                CREATE TABLE consultas (
                    desde TEXT NOT NULL, hasta TEXT NOT NULL, equipo TEXT NOT NULL,
                    consultado_utc TEXT NOT NULL, partidos INTEGER NOT NULL,
                    registros INTEGER NOT NULL, incidencias TEXT NOT NULL,
                    estado TEXT NOT NULL, PRIMARY KEY(desde, hasta, equipo)
                );
            ''')
            conn.executemany(
                'INSERT INTO partidos (id,fecha,payload) VALUES (?,?,?)',
                [(r['id'], r.get('fecha'), r['payload']) for r in partidos],
            )
            conn.executemany(
                'INSERT INTO jugadores (partido_id,equipo,identidad,fecha,payload) '
                'VALUES (?,?,?,?,?)',
                [(r['partido_id'], r['equipo'], r['identidad'], r.get('fecha'), r['payload'])
                 for r in jugadores],
            )
            conn.executemany(
                'INSERT INTO consultas (desde,hasta,equipo,consultado_utc,partidos,'
                'registros,incidencias,estado) VALUES (?,?,?,?,?,?,?,?)',
                [(r['desde'], r['hasta'], r['equipo'], r['consultado_utc'],
                  r['partidos'], r['registros'], r['incidencias'], r['estado'])
                 for r in consultas],
            )
            conn.commit()
        return destino.read_bytes()
