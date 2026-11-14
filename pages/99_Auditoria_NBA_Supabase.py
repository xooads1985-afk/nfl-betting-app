"""Auditoría de solo lectura de proyecciones NBA, sin exponer credenciales."""
import hashlib
import json
from collections import Counter
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import streamlit as st

MODELOS = ('Base', 'Modelo C', 'Ensemble', 'Pace + Eficiencia')


def leer(url, key, tabla, columnas, limite=500):
    salida = []
    for offset in range(0, 50000, limite):
        q = urlencode({'select': columnas, 'limit': limite, 'offset': offset})
        req = Request(f'{url.rstrip("/")}/rest/v1/{tabla}?{q}',
                      headers={'apikey': key, 'Authorization': f'Bearer {key}',
                               'Accept': 'application/json'}, method='GET')
        with urlopen(req, timeout=25) as resp:
            filas = json.load(resp)
        if not isinstance(filas, list):
            raise ValueError('Respuesta de Supabase no es una lista')
        salida.extend(filas)
        if len(filas) < limite:
            return salida
    raise ValueError('Límite de auditoría alcanzado; revisar paginación')


def diagnosticar(consolidados, prospectivos):
    resumen = {'consolidados': len(consolidados), 'prospectivos': len(prospectivos),
               'consolidados_validos': 0, 'consolidados_cuatro_motores': 0,
               'consolidados_incompletos': 0, 'huellas_incorrectas': 0,
               'prospectivos_por_motor': dict(Counter(str(x.get('modelo')) for x in prospectivos)),
               'partidos_prospectivos_completos': 0,
               'partidos_prospectivos_incompletos': 0}
    for fila in consolidados:
        reg = fila.get('registro')
        if not isinstance(reg, dict):
            resumen['consolidados_incompletos'] += 1
            continue
        canon = json.dumps(reg, sort_keys=True, ensure_ascii=False,
                           separators=(',', ':'), allow_nan=False)
        if hashlib.sha256(canon.encode('utf-8')).hexdigest() != fila.get('huella_sha256'):
            resumen['huellas_incorrectas'] += 1
            continue
        resumen['consolidados_validos'] += 1
        modelos = reg.get('cuatro_motores')
        if isinstance(modelos, list) and len(modelos) == 4 and {m.get('modelo') for m in modelos if isinstance(m, dict)} == set(MODELOS):
            resumen['consolidados_cuatro_motores'] += 1
        else:
            resumen['consolidados_incompletos'] += 1
    grupos = {}
    for fila in prospectivos:
        pid = str(fila.get('partido_id', ''))
        grupos.setdefault(pid, set()).add((str(fila.get('modelo')), str(fila.get('equipo'))))
    for pares in grupos.values():
        por_motor = {m: {equipo for modelo, equipo in pares if modelo == m} for m in MODELOS}
        if all(len(por_motor[m]) == 2 for m in MODELOS) and len({e for es in por_motor.values() for e in es}) == 2:
            resumen['partidos_prospectivos_completos'] += 1
        else:
            resumen['partidos_prospectivos_incompletos'] += 1
    return resumen

st.title('Auditoría NBA · Supabase')
st.caption('Solo lectura: GET. No modifica registros ni muestra credenciales.')
if st.button('Consultar cobertura real', type='primary'):
    url = str(st.secrets.get('SUPABASE_URL', ''))
    key = str(st.secrets.get('SUPABASE_SECRET_KEY', ''))
    if not url.startswith('https://') or not key:
        st.error('No están disponibles SUPABASE_URL y SUPABASE_SECRET_KEY en los secretos de Streamlit.')
    else:
        try:
            with st.spinner('Consultando registros existentes…'):
                consolidados = leer(url, key, 'nba_proyecciones_consolidadas', 'partido_id,huella_sha256,registro')
                prospectivos = leer(url, key, 'nba_laboratorio_prospectivo', 'partido_id,equipo,modelo')
                resultado = diagnosticar(consolidados, prospectivos)
            st.json(resultado)
            st.download_button('Descargar diagnóstico JSON', json.dumps(resultado, indent=2, ensure_ascii=False),
                               file_name='nba_cobertura_supabase.json', mime='application/json')
            st.info('Cobertura no equivale a evaluación de precisión. El MAE requiere marcadores finales verificados.')
        except (HTTPError, URLError, TimeoutError, ValueError, KeyError, TypeError) as exc:
            st.error(f'No se pudo completar la consulta: {type(exc).__name__}' +
                     (f' (HTTP {exc.code})' if isinstance(exc, HTTPError) else ''))
