"""Archivo histórico NBA persistente en Supabase.

Mantiene la API pública del archivo SQLite anterior. Requiere secretos
SUPABASE_URL y SUPABASE_SECRET_KEY en Streamlit Secrets o variables de entorno.
No modifica otros módulos. No guarda silenciosamente en disco local.
"""
import json
import os
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen

import pandas as pd


def _config():
    url = os.environ.get('SUPABASE_URL', '').strip()
    key = os.environ.get('SUPABASE_SECRET_KEY', '').strip()
    if not url or not key:
        try:
            import streamlit as st
            url = url or str(st.secrets.get('SUPABASE_URL', '')).strip()
            key = key or str(st.secrets.get('SUPABASE_SECRET_KEY', '')).strip()
        except (ImportError, FileNotFoundError, KeyError):
            pass
    url = url.rstrip('/')
    if url.endswith('/rest/v1'):
        url = url[:-8]
    if not url.startswith('https://') or not key:
        raise RuntimeError('Faltan SUPABASE_URL o SUPABASE_SECRET_KEY en Streamlit Secrets.')
    return url, key


def _solicitud(tabla, metodo='GET', parametros=None, filas=None, conflicto=None, rango=None):
    url, key = _config()
    ruta = f'{url}/rest/v1/{quote(tabla)}'
    if parametros:
        ruta += '?' + urlencode(parametros)
    headers = {'apikey': key, 'Authorization': 'Bearer ' + key,
               'Accept': 'application/json'}
    if filas is not None:
        headers['Content-Type'] = 'application/json; charset=utf-8'
        headers['Prefer'] = 'resolution=merge-duplicates,return=minimal'
    if rango is not None:
        headers['Range-Unit'] = 'items'
        headers['Range'] = f'{rango[0]}-{rango[1]}'
    data = json.dumps(filas, ensure_ascii=False, allow_nan=False).encode('utf-8') if filas is not None else None
    req = Request(ruta, data=data, headers=headers, method=metodo)
    try:
        with urlopen(req, timeout=60) as response:
            contenido = response.read()
            return json.loads(contenido) if contenido else []
    except HTTPError as exc:
        detalle = exc.read().decode('utf-8', errors='replace')[:500]
        raise RuntimeError(f'Error Supabase ({tabla}, HTTP {exc.code}): {detalle}') from exc
    except URLError as exc:
        raise RuntimeError(f'No se pudo conectar con Supabase ({tabla}): {exc.reason}') from exc


def _limpiar(valor):
    if isinstance(valor, dict):
        return {str(k): _limpiar(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_limpiar(v) for v in valor]
    try:
        faltante = pd.isna(valor)
        if isinstance(faltante, (bool,)) and faltante:
            return None
        if not isinstance(faltante, bool) and hasattr(faltante, 'item') and bool(faltante.item()):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(valor, 'item') and callable(valor.item):
        try:
            return _limpiar(valor.item())
        except (TypeError, ValueError):
            pass
    if isinstance(valor, (pd.Timestamp, datetime)):
        return valor.isoformat()
    if isinstance(valor, (str, int, float, bool)) or valor is None:
        return valor
    return str(valor)


def _texto(valor):
    valor = _limpiar(valor)
    return '' if valor is None else str(valor).strip()


def _insertar(tabla, registros, columnas_conflicto):
    for inicio in range(0, len(registros), 50):
        _solicitud(tabla, 'POST', {'on_conflict': columnas_conflicto}, registros[inicio:inicio + 50])
    return len(registros)


def _leer_todo(tabla, columnas='payload', filtros=None):
    resultados = []
    offset = 0
    while True:
        params = {'select': columnas}
        if filtros:
            params.update(filtros)
        bloque = _solicitud(tabla, parametros=params, rango=(offset, offset + 999))
        resultados.extend(bloque)
        if len(bloque) < 1000:
            break
        offset += len(bloque)
    return resultados


def guardar_partidos(df):
    if df is None or df.empty:
        return 0
    registros = []
    for fila in df.to_dict('records'):
        ident = _texto(fila.get('id'))
        if not ident:
            continue
        limpio = _limpiar(fila)
        registros.append({'id': ident, 'fecha': _texto(fila.get('fecha_utc')),
                          'payload': json.dumps(limpio, ensure_ascii=False, default=str)})
    return _insertar('partidos', registros, 'id')


def leer_partidos(desde=None, hasta=None):
    filas = [json.loads(f['payload']) for f in _leer_todo('partidos')]
    df = pd.DataFrame(filas)
    if df.empty:
        return df
    if 'fecha_utc' not in df:
        return df
    fecha = pd.to_datetime(df['fecha_utc'], utc=True, errors='coerce').dt.date
    if desde is not None:
        df = df.loc[fecha.ge(pd.Timestamp(desde).date())]
        fecha = fecha.loc[df.index]
    if hasta is not None:
        df = df.loc[fecha.le(pd.Timestamp(hasta).date())]
    return df.sort_values('fecha_utc').reset_index(drop=True)


def guardar_jugadores(df):
    if df is None or df.empty:
        return 0
    registros = []
    for fila in df.to_dict('records'):
        partido = _texto(fila.get('partido_id'))
        equipo = _texto(fila.get('equipo'))
        jugador = _texto(fila.get('jugador'))
        jugador_id = _texto(fila.get('jugador_id'))
        if not partido or not equipo or not jugador:
            continue
        identidad = 'id:' + jugador_id if jugador_id.lower() not in ('', 'nan', 'none') else 'nombre:' + jugador.casefold()
        limpio = _limpiar(fila)
        registros.append({'partido_id': partido, 'equipo': equipo, 'identidad': identidad,
                          'fecha': _texto(fila.get('fecha')),
                          'payload': json.dumps(limpio, ensure_ascii=False, default=str)})
    return _insertar('jugadores', registros, 'partido_id,equipo,identidad')


def leer_jugadores(equipo='Todos', desde=None, hasta=None):
    filtros = {}
    if equipo not in (None, 'Todos'):
        filtros['equipo'] = 'eq.' + str(equipo)
    if desde is not None:
        filtros['fecha'] = 'gte.' + str(desde)
    if hasta is not None:
        # PostgREST no admite dos condiciones del mismo campo con el mismo nombre
        # en un dict; se filtra la fecha superior en pandas abajo.
        if desde is None:
            filtros['fecha'] = 'lte.' + str(hasta)
    filas = [json.loads(f['payload']) for f in _leer_todo('jugadores', filtros=filtros)]
    df = pd.DataFrame(filas)
    if df.empty:
        return df
    if equipo not in (None, 'Todos'):
        df = df.loc[df['equipo'].eq(equipo)]
    if desde is not None:
        df = df.loc[df['fecha'].astype(str).ge(str(desde))]
    if hasta is not None:
        df = df.loc[df['fecha'].astype(str).le(str(hasta))]
    return df.sort_values(['fecha', 'partido_id']).reset_index(drop=True)


def registrar_consulta(desde, hasta, equipo, partidos, registros, incidencias, estado='parcial'):
    if estado not in ('sin_incidencias_reportadas', 'parcial'):
        raise ValueError('Estado de consulta inválido')
    fila = {'desde': str(desde), 'hasta': str(hasta), 'equipo': str(equipo),
            'consultado_utc': datetime.now(timezone.utc).isoformat(),
            'partidos': int(partidos), 'registros': int(registros),
            'incidencias': json.dumps(list(incidencias), ensure_ascii=False), 'estado': estado}
    _insertar('consultas', [fila], 'desde,hasta,equipo')


def leer_consultas(desde, hasta, equipo):
    columnas = ['desde', 'hasta', 'equipo', 'consultado_utc', 'partidos', 'registros', 'incidencias', 'estado']
    filas = _leer_todo('consultas', columnas=','.join(columnas))
    df = pd.DataFrame(filas, columns=columnas)
    if df.empty:
        return df
    filtro = (df['hasta'].astype(str).ge(str(desde)) &
              df['desde'].astype(str).le(str(hasta)) &
              (df['equipo'].eq(str(equipo)) | df['equipo'].eq('Todos')))
    return df.loc[filtro].sort_values(['desde', 'hasta']).reset_index(drop=True)


def resumen_archivo(equipo='Todos', desde=None, hasta=None):
    jugadores = leer_jugadores(equipo, desde, hasta)
    if jugadores.empty:
        return {'partidos_con_jugadores': 0, 'registros': 0}
    return {'partidos_con_jugadores': int(jugadores['partido_id'].nunique()),
            'registros': int(len(jugadores))}

