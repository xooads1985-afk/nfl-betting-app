"""Persistencia de proyecciones originales. Solo servidor Streamlit; sin credenciales en código."""
import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import streamlit as st

class AlmacenError(RuntimeError):
    pass


def _config():
    try:
        url = str(st.secrets.get('SUPABASE_URL', '')).rstrip('/')
        key = str(st.secrets.get('SUPABASE_SECRET_KEY', ''))
    except Exception as exc:
        raise AlmacenError('No se pudieron leer los Secrets de Streamlit.') from exc
    if not url.startswith('https://') or not key:
        raise AlmacenError('Faltan SUPABASE_URL o SUPABASE_SECRET_KEY en Streamlit Secrets.')
    return url, key


def _request(method, query='', payload=None, prefer=None):
    url, key = _config()
    headers = {'apikey': key, 'Authorization': 'Bearer ' + key,
               'Content-Type': 'application/json', 'Accept': 'application/json'}
    if prefer:
        headers['Prefer'] = prefer
    data = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode('utf-8') if payload is not None else None
    req = Request(url + '/rest/v1/proyecciones_originales' + query,
                  data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=18) as response:
            body = response.read()
            return json.loads(body) if body else []
    except HTTPError as exc:
        raise AlmacenError(f'Supabase respondió HTTP {exc.code}. Revisa los permisos de la tabla y los Secrets.') from exc
    except (URLError, TimeoutError) as exc:
        raise AlmacenError('No se pudo contactar Supabase; comprueba la conexión.') from exc
    except (ValueError, TypeError) as exc:
        raise AlmacenError('Supabase devolvió una respuesta inesperada.') from exc


def leer(deporte):
    if deporte not in ('NFL', 'NBA'):
        raise AlmacenError('Deporte inválido.')
    salida = {}
    offset = 0
    while True:
        params = urlencode({'select': 'partido_id,datos', 'deporte': 'eq.' + deporte,
                            'order': 'id.asc', 'limit': 500, 'offset': offset})
        rows = _request('GET', '?' + params)
        if not isinstance(rows, list):
            raise AlmacenError('La respuesta de Supabase no contiene una lista de registros.')
        for row in rows:
            if isinstance(row.get('datos'), dict):
                salida[str(row['partido_id'])] = row['datos']
        if len(rows) < 500:
            break
        offset += 500
    return salida


def insertar_nuevos(deporte, registros, origen="automatico"):
    """Inserta sin sobrescribir; devuelve la cantidad realmente insertada."""
    if not isinstance(registros, dict):
        raise AlmacenError('El respaldo no es un diccionario válido.')
    existentes = leer(deporte)
    nuevos = []
    for clave, r in registros.items():
        if str(clave) in existentes or not isinstance(r, dict) or str(r.get('id')) != str(clave):
            continue
        local = r.get('local')
        visitante = r.get('visitante')
        if not isinstance(local, str) or not local or not isinstance(visitante, str) or not visitante:
            continue
        fecha = r.get('fecha_utc') if deporte == 'NBA' else None
        # NFL solo proporciona día del calendario, no una hora verificable.
        row = {'deporte': deporte, 'partido_id': str(clave),
               'temporada': r.get('temporada') if deporte == 'NFL' else None,
               'equipo_local': local, 'equipo_visitante': visitante,
               'fecha_partido': fecha,
               'verificacion_preinicio': r.get('verificacion_preinicio', 'No verificada'),
               'version_modulo': str(r.get('version', '')),
               'datos': r,
               'origen': origen}
        # La hora registrada es parte de los datos originales y no se reemplaza.
        if r.get('registrado_utc'):
            row['registrado_utc'] = r['registrado_utc']
        nuevos.append(row)
    if not nuevos:
        return 0
    # ON CONFLICT DO NOTHING; no sobreescribe la primera proyección, incluso ante carreras.
    total = 0
    for i in range(0, len(nuevos), 100):
        query = '?on_conflict=deporte,partido_id'
        inserted = _request('POST', query, nuevos[i:i+100],
                            prefer='resolution=ignore-duplicates,return=representation')
        if not isinstance(inserted, list):
            raise AlmacenError('Supabase no confirmó qué registros fueron insertados.')
        total += len(inserted)
    return total
