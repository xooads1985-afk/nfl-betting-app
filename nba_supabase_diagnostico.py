"""Diagnóstico de SOLO LECTURA para la tabla del Laboratorio Prospectivo NBA.
No inserta, actualiza ni borra datos. No imprime credenciales.
"""
import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

TABLA = 'nba_laboratorio_prospectivo'
CAMPOS = ('partido_id', 'equipo', 'modelo', 'proyeccion',
          'inicio_utc', 'registrado_utc', 'version')
MODELOS = ('Base', 'Modelo C', 'Ensemble', 'Pace + Eficiencia')


def diagnosticar(url, clave):
    if not isinstance(url, str) or not url.startswith('https://') or not clave:
        return {'lectura': False, 'detalle': 'Faltan credenciales válidas.',
                'escritura_confirmada': False, 'unicidad_confirmada': False}
    headers = {'apikey': clave, 'Authorization': 'Bearer ' + clave,
               'Accept': 'application/json', 'Range-Unit': 'items', 'Range': '0-0'}
    q = '?' + urlencode({'select': ','.join(CAMPOS), 'limit': '1'})
    req = Request(url.rstrip('/') + '/rest/v1/' + TABLA + q, headers=headers, method='GET')
    try:
        with urlopen(req, timeout=15) as response:
            muestra = json.loads(response.read().decode('utf-8') or '[]')
        return {'lectura': True, 'columnas_consultables': list(CAMPOS),
                'muestra_recibida': bool(muestra),
                'modelos_esperados': list(MODELOS),
                'escritura_confirmada': False, 'unicidad_confirmada': False,
                'nota': 'Una lectura exitosa NO demuestra permisos INSERT, restricciones UNIQUE ni que se admita el cuarto modelo.'}
    except HTTPError as exc:
        return {'lectura': False, 'codigo_http': exc.code,
                'detalle': 'La consulta de lectura falló. Revisar tabla, columnas, permisos o credenciales.',
                'escritura_confirmada': False, 'unicidad_confirmada': False}
    except (URLError, TimeoutError, ValueError) as exc:
        return {'lectura': False, 'detalle': f'No se pudo completar la lectura ({type(exc).__name__}).',
                'escritura_confirmada': False, 'unicidad_confirmada': False}


def mostrar_diagnostico():
    import streamlit as st
    st.subheader('🔎 Diagnóstico Supabase (solo lectura)')
    st.caption('No modifica registros y no muestra credenciales.')
    if st.button('Verificar lectura de la tabla experimental', use_container_width=True):
        resultado = diagnosticar(str(st.secrets.get('SUPABASE_URL', '')),
                                 str(st.secrets.get('SUPABASE_SECRET_KEY', '')))
        if resultado['lectura']:
            st.success('La tabla y las siete columnas requeridas responden a la consulta.')
        else:
            st.error('No se pudo confirmar la lectura de la tabla.')
        st.json(resultado)
        st.info('La escritura y el índice único siguen pendientes de verificación independiente.')
