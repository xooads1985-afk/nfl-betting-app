"""Migración manual de estadísticas NBA desde un bucket privado de Supabase.
No modifica archivos de la aplicación ni elimina datos existentes.
"""
import json
import os
import sqlite3
import tempfile
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

URL = os.environ['SUPABASE_URL'].rstrip('/')
KEY = os.environ['SUPABASE_SECRET_KEY']
BUCKET = 'nba-migracion-temporal'
OBJECT = 'nba_temporada_respaldo.sqlite3'


def request(method, path, payload=None, headers=None):
    h = {'apikey': KEY, 'Authorization': 'Bearer ' + KEY}
    if headers:
        h.update(headers)
    if payload is not None:
        h['Content-Type'] = 'application/json'
        payload = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    req = Request(URL + path, data=payload, headers=h, method=method)
    try:
        with urlopen(req, timeout=90) as r:
            return r.read(), r.headers
    except HTTPError as e:
        detail = e.read().decode('utf-8', errors='replace')[:600]
        raise RuntimeError(f'Supabase devolvió HTTP {e.code} en {method} {path}: {detail}') from e


def rows(con, table, columns):
    con.row_factory = sqlite3.Row
    return [dict(row) for row in con.execute(f'SELECT {columns} FROM {table}')]


def upsert(table, records, conflict):
    path = f'/rest/v1/{table}?on_conflict={quote(conflict, safe=",")}'
    for start in range(0, len(records), 50):
        request('POST', path, records[start:start+50],
                {'Prefer': 'resolution=merge-duplicates,return=minimal'})
        print(f'{table}: {min(start+50,len(records))}/{len(records)} enviados')


def count(table):
    _, headers = request('HEAD', f'/rest/v1/{table}?select=*',
                         headers={'Prefer': 'count=exact', 'Range-Unit': 'items', 'Range': '0-0'})
    content_range = headers.get('Content-Range', '')
    if '/' not in content_range:
        raise RuntimeError(f'No se pudo verificar el total de {table}: {content_range!r}')
    return int(content_range.rsplit('/', 1)[1])


def main():
    print('Descargando respaldo desde almacenamiento PRIVADO de Supabase...')
    data, _ = request('GET', f'/storage/v1/object/authenticated/{BUCKET}/{quote(OBJECT)}')
    with tempfile.TemporaryDirectory() as tmp:
        dbpath = os.path.join(tmp, 'nba.sqlite3')
        with open(dbpath, 'wb') as f:
            f.write(data)
        con = sqlite3.connect(f'file:{dbpath}?mode=ro', uri=True)
        try:
            if con.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('El respaldo SQLite no pasó la prueba de integridad.')
            games = rows(con, 'partidos', 'id, fecha, payload')
            players = rows(con, 'jugadores', 'partido_id, equipo, identidad, fecha, payload')
            checks = rows(con, 'consultas', 'desde, hasta, equipo, consultado_utc, partidos, registros, incidencias, estado')
        finally:
            con.close()
    print(f'Respaldo validado: {len(games)} partidos, {len(players)} jugadores, {len(checks)} consultas.')
    if (len(games), len(players), len(checks)) != (250, 1950, 0):
        raise RuntimeError('Los conteos del respaldo no coinciden con los esperados. No se importó nada.')
    upsert('partidos', games, 'id')
    upsert('jugadores', players, 'partido_id,equipo,identidad')
    if checks:
        upsert('consultas', checks, 'desde,hasta,equipo')
    for table, expected in [('partidos', 250), ('jugadores', 1950), ('consultas', 0)]:
        actual = count(table)
        print(f'Verificación {table}: {actual} registros (respaldo: {expected})')
        if actual < expected:
            raise RuntimeError(f'Faltan registros en {table}: {actual} < {expected}')
    print('MIGRACIÓN COMPLETADA. Verificar datos desde Supabase antes de retirar el archivo temporal.')


if __name__ == '__main__':
    main()
