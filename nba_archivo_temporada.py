"""Archivo local incremental NBA. No implica persistencia garantizada en nubes efímeras."""
import json
import sqlite3
from pathlib import Path
import pandas as pd

DB = Path(__file__).resolve().parent / 'nba_temporada.sqlite3'

def _conexion():
    con = sqlite3.connect(DB, timeout=10)
    con.execute('PRAGMA busy_timeout=10000')
    con.execute('CREATE TABLE IF NOT EXISTS partidos (id TEXT PRIMARY KEY, fecha TEXT, payload TEXT NOT NULL)')
    con.execute('CREATE TABLE IF NOT EXISTS jugadores (partido_id TEXT NOT NULL, equipo TEXT NOT NULL, identidad TEXT NOT NULL, fecha TEXT, payload TEXT NOT NULL, PRIMARY KEY(partido_id,equipo,identidad))')
    return con

def guardar_partidos(df):
    if df is None or df.empty: return 0
    n = 0
    with _conexion() as con:
        for row in df.to_dict('records'):
            ident = str(row.get('id') or '').strip()
            if not ident: continue
            payload = json.dumps(row, ensure_ascii=False, default=str, allow_nan=False) if not any(pd.isna(v) for v in row.values()) else json.dumps({k:(None if pd.isna(v) else v) for k,v in row.items()}, ensure_ascii=False, default=str)
            con.execute('INSERT INTO partidos VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET fecha=excluded.fecha,payload=excluded.payload', (ident, str(row.get('fecha_utc','')), payload))
            n += 1
    return n

def leer_partidos(desde=None, hasta=None):
    with _conexion() as con:
        filas = [json.loads(r[0]) for r in con.execute('SELECT payload FROM partidos')]
    df = pd.DataFrame(filas)
    if df.empty: return df
    fecha = pd.to_datetime(df['fecha_utc'], utc=True, errors='coerce').dt.date
    if desde is not None: df = df.loc[fecha.ge(pd.Timestamp(desde).date())]
    if hasta is not None: df = df.loc[fecha.le(pd.Timestamp(hasta).date())]
    return df.sort_values('fecha_utc').reset_index(drop=True)

def guardar_jugadores(df):
    if df is None or df.empty: return 0
    n = 0
    with _conexion() as con:
        for row in df.to_dict('records'):
            partido = str(row.get('partido_id') or '').strip()
            equipo = str(row.get('equipo') or '').strip()
            jugador = str(row.get('jugador') or '').strip()
            jugador_id = str(row.get('jugador_id') or '').strip()
            if not partido or not equipo or not jugador: continue
            identidad = 'id:' + jugador_id if jugador_id and jugador_id.lower() != 'nan' else 'nombre:' + jugador.casefold()
            limpio = {k:(None if pd.isna(v) else v) for k,v in row.items()}
            con.execute('INSERT INTO jugadores VALUES (?,?,?,?,?) ON CONFLICT(partido_id,equipo,identidad) DO UPDATE SET fecha=excluded.fecha,payload=excluded.payload', (partido,equipo,identidad,str(row.get('fecha') or ''),json.dumps(limpio,ensure_ascii=False,default=str)))
            n += 1
    return n

def leer_jugadores(equipo='Todos', desde=None, hasta=None):
    with _conexion() as con:
        filas = [json.loads(r[0]) for r in con.execute('SELECT payload FROM jugadores')]
    df = pd.DataFrame(filas)
    if df.empty: return df
    if equipo not in (None,'Todos'): df = df.loc[df['equipo'].eq(equipo)]
    if desde is not None: df = df.loc[df['fecha'].astype(str).ge(str(desde))]
    if hasta is not None: df = df.loc[df['fecha'].astype(str).le(str(hasta))]
    return df.sort_values(['fecha','partido_id']).reset_index(drop=True)
