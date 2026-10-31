"""Actualizador NBA independiente: ESPN (fuente no oficial) -> Supabase.

Uso: python actualizar_historial_nba.py --dias 7
No importa Streamlit ni modifica archivos de la aplicación.
"""
import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ESPN = 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba'
METRICAS = {
    'Puntos': ('PTS', 'points'), 'Rebotes': ('REB', 'rebounds'),
    'Asistencias': ('AST', 'assists'), 'Robos': ('STL', 'steals'),
    'Tapones': ('BLK', 'blocks'), 'Pérdidas': ('TO', 'turnovers'),
    'Minutos': ('MIN', 'minutes'),
}
LOG = logging.getLogger('nba_auto')


def solicitar_json(url, headers=None, intentos=3):
    for intento in range(intentos):
        try:
            with urlopen(Request(url, headers=headers or {'User-Agent': 'NBA-archive/1.0'}), timeout=25) as r:
                return json.load(r)
        except HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or intento == intentos - 1:
                raise
        except (URLError, TimeoutError):
            if intento == intentos - 1:
                raise
        time.sleep(2 ** intento)


def numero(valor):
    if valor is None or isinstance(valor, bool):
        return None
    s = str(valor).strip()
    if s.upper() in ('', '-', '--', 'DNP', 'N/A', 'DND', 'DID NOT PLAY'):
        return None
    try:
        if ':' in s:
            m, seg = s.split(':', 1)
            return int(m) + int(seg) / 60
        return float(s.replace(',', ''))
    except (ValueError, TypeError):
        return None


def obtener_partidos(dia):
    params = urlencode({'dates': dia.strftime('%Y%m%d'), 'limit': 100})
    data = solicitar_json(f'{ESPN}/scoreboard?{params}')
    if not isinstance(data.get('events'), list):
        raise ValueError('Calendario ESPN sin lista de eventos')
    return data['events']


def obtener_jugadores(evento, dia):
    partido_id = str(evento.get('id', '')).strip()
    if not partido_id.isdigit():
        raise ValueError('ID de partido inválido')
    params = urlencode({'event': partido_id})
    detalle = solicitar_json(f'{ESPN}/summary?{params}')
    bloques = detalle.get('boxscore', {}).get('players', [])
    if not bloques:
        raise ValueError('Boxscore no publicado')
    filas = []
    for equipo_data in bloques:
        equipo = str(equipo_data.get('team', {}).get('displayName', '')).strip()
        if not equipo:
            continue
        for bloque in equipo_data.get('statistics', []):
            etiquetas = bloque.get('labels', []) or bloque.get('names', [])
            for item in bloque.get('athletes', []):
                atleta = item.get('athlete') or {}
                nombre = str(atleta.get('displayName', '')).strip()
                if not nombre or nombre == 'Desconocido':
                    continue
                identificador = str(atleta.get('id') or '').strip()
                valores = dict(zip(etiquetas, item.get('stats', [])))
                fila = {'partido_id': partido_id, 'fecha': str(evento.get('date') or dia.isoformat())[:10],
                        'equipo': equipo, 'jugador': nombre, 'titular': bool(item.get('starter', False)),
                        'jugador_id': identificador}
                for metrica, posibles in METRICAS.items():
                    col = next((x for x in posibles if x in valores), None)
                    fila[metrica] = numero(valores[col]) if col else None
                filas.append(fila)
    # No sustituir registros existentes con un boxscore vacío o sin estadísticas.
    if not filas or not any(any(f[m] is not None for m in METRICAS) for f in filas):
        raise ValueError('Boxscore sin estadísticas numéricas verificables')
    return filas


def guardar_jugadores(filas, url, key):
    registros = []
    for fila in filas:
        jugador_id = fila['jugador_id']
        identidad = 'id:' + jugador_id if jugador_id else 'nombre:' + fila['jugador'].casefold()
        registros.append({'partido_id': fila['partido_id'], 'equipo': fila['equipo'],
                          'identidad': identidad, 'fecha': fila['fecha'],
                          'payload': json.dumps(fila, ensure_ascii=False)})
    endpoint = url.rstrip('/') + '/rest/v1/jugadores?on_conflict=partido_id%2Cequipo%2Cidentidad'
    headers = {'apikey': key, 'Authorization': 'Bearer ' + key,
               'Content-Type': 'application/json',
               'Prefer': 'resolution=merge-duplicates,return=minimal'}
    for i in range(0, len(registros), 50):
        datos = json.dumps(registros[i:i+50], ensure_ascii=False, allow_nan=False).encode('utf-8')
        req = Request(endpoint, data=datos, headers=headers, method='POST')
        with urlopen(req, timeout=40) as response:
            response.read()
    return len(registros)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dias', type=int, default=7, help='Días UTC anteriores, incluyendo hoy (1-31)')
    args = parser.parse_args()
    if not 1 <= args.dias <= 31:
        parser.error('--dias debe estar entre 1 y 31')
    url = os.environ.get('SUPABASE_URL', '').strip().rstrip('/')
    key = os.environ.get('SUPABASE_SECRET_KEY', '').strip()
    if not url.startswith('https://') or not key:
        LOG.error('Configura SUPABASE_URL y SUPABASE_SECRET_KEY como secretos de GitHub Actions.')
        return 2
    hoy = datetime.now(timezone.utc).date()
    total_partidos = total_registros = 0
    errores = []
    for dias_atras in range(args.dias - 1, -1, -1):
        dia = hoy - timedelta(days=dias_atras)
        try:
            eventos = obtener_partidos(dia)
        except Exception as exc:
            errores.append(f'{dia}: calendario: {type(exc).__name__}: {exc}')
            continue
        for evento in eventos:
            if not evento.get('status', {}).get('type', {}).get('completed', False):
                continue
            ident = str(evento.get('id', ''))
            try:
                filas = obtener_jugadores(evento, dia)
                total_registros += guardar_jugadores(filas, url, key)
                total_partidos += 1
                LOG.info('Partido %s: %d filas procesadas', ident, len(filas))
            except Exception as exc:
                errores.append(f'{dia} partido {ident}: {type(exc).__name__}: {exc}')
    LOG.info('Partidos procesados: %d | filas enviadas (no necesariamente nuevas): %d | incidencias: %d',
             total_partidos, total_registros, len(errores))
    for error in errores:
        LOG.warning(error)
    return 1 if errores else 0


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    sys.exit(main())
