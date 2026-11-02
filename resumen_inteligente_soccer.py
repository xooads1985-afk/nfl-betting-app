"""Resumen Inteligente Soccer - Etapa 3, fuente football-data.org y CSV.
Independiente de NFL, NBA y main.py. Requiere streamlit y requests.
"""
import os
from datetime import datetime, timezone
from io import BytesIO
import csv
import requests
import streamlit as st

COMPETICIONES = {
    '🇬🇧 Premier League': 'PL',
    '🇪🇸 LaLiga': 'PD',
    '🇮🇹 Serie A': 'SA',
    '🇩🇪 Bundesliga': 'BL1',
    '🇫🇷 Ligue 1': 'FL1',
    '🏆 UEFA Champions League': 'CL',
}
BASE = 'https://api.football-data.org/v4'


def _token():
    try:
        value = st.secrets.get('FOOTBALL_DATA_KEY', '')
    except Exception:
        value = ''
    return (value if isinstance(value, str) else '').strip() or os.getenv('FOOTBALL_DATA_KEY', '').strip()


@st.cache_data(ttl=3600, show_spinner=False)
def _consulta(ruta, token, temporada=None):
    params = {'season': int(temporada)} if temporada else {}
    try:
        r = requests.get(BASE + ruta, headers={'X-Auth-Token': token}, params=params, timeout=20)
    except requests.RequestException:
        raise ValueError('No se pudo conectar con el servidor. Comprueba la conexión e inténtalo más tarde.') from None
    if r.status_code == 401:
        raise ValueError('Clave no autorizada. Revisa FOOTBALL_DATA_KEY en Streamlit Secrets.')
    if r.status_code == 403:
        raise ValueError('Esta competición, temporada o consulta no está habilitada para tu plan.')
    if r.status_code == 404:
        raise ValueError('La competición o temporada solicitada no está disponible.')
    if r.status_code == 429:
        raise ValueError('Se alcanzó el límite temporal de solicitudes. Espera antes de volver a consultar.')
    if r.status_code >= 400:
        raise ValueError(f'El servidor rechazó la consulta (HTTP {r.status_code}).')
    try:
        payload = r.json()
    except ValueError:
        raise ValueError('El servidor devolvió datos no válidos.') from None
    if not isinstance(payload, dict):
        raise ValueError('La respuesta no tiene el formato esperado.')
    return payload


def _partidos(datos):
    rows = []
    for x in datos:
        home = x.get('homeTeam') or {}
        away = x.get('awayTeam') or {}
        score = x.get('score') or {}
        full = score.get('fullTime') or {}
        half = score.get('halfTime') or {}
        rows.append({
            'Fecha UTC': (x.get('utcDate') or '')[:16].replace('T', ' '),
            'Local': home.get('shortName') or home.get('name') or 'N/D',
            'Visitante': away.get('shortName') or away.get('name') or 'N/D',
            'Estado': x.get('status', 'N/D'),
            'Goles local': full.get('home'),
            'Goles visitante': full.get('away'),
            '1T local': half.get('home'),
            '1T visitante': half.get('away'),
        })
    return rows


def _resumen(rows):
    finalizados = [x for x in rows if x['Estado'] == 'FINISHED'
                   and isinstance(x['Goles local'], int) and isinstance(x['Goles visitante'], int)]
    if not finalizados:
        st.info('Todavía no hay resultados finalizados con marcadores completos en los datos cargados.')
        return
    total = sum(x['Goles local'] + x['Goles visitante'] for x in finalizados)
    a, b = st.columns(2)
    a.metric('Partidos finalizados', len(finalizados))
    b.metric('Goles por partido', f'{total / len(finalizados):.2f}')
    mitades = [x for x in finalizados if isinstance(x['1T local'], int) and isinstance(x['1T visitante'], int)]
    if mitades:
        g1 = sum(x['1T local'] + x['1T visitante'] for x in mitades)
        gfull = sum(x['Goles local'] + x['Goles visitante'] for x in mitades)
        a, b = st.columns(2)
        a.metric('Goles 1.ª mitad / partido', f'{g1 / len(mitades):.2f}')
        b.metric('Goles 2.ª mitad / partido', f'{(gfull-g1) / len(mitades):.2f}')
        st.caption(f'Promedios descriptivos sobre {len(mitades)} partidos con datos de ambas mitades; no son predicciones.')
    else:
        st.info('La fuente no devolvió marcadores por mitades para estos partidos.')


def _archivo_csv():
    st.subheader('📂 Archivo histórico CSV (opcional)')
    st.caption('Puedes consultar un CSV propio sin utilizar ninguna API. Se muestran las columnas originales, sin inventar datos.')
    archivo = st.file_uploader('Selecciona un archivo CSV', type=['csv'], key='soc_csv')
    if archivo is None:
        return
    if archivo.size > 5 * 1024 * 1024:
        st.error('El archivo supera 5 MB. Selecciona uno más pequeño.')
        return
    try:
        raw = archivo.getvalue().decode('utf-8-sig')
    except UnicodeDecodeError:
        try:
            raw = archivo.getvalue().decode('latin-1')
        except UnicodeError:
            st.error('No se pudo leer la codificación del archivo.')
            return
    try:
        dialect = csv.Sniffer().sniff(raw[:4096], delimiters=',;\t')
        reader = csv.DictReader(raw.splitlines(), dialect=dialect)
        rows = list(reader)
    except (csv.Error, ValueError):
        st.error('El CSV no tiene un formato válido.')
        return
    if not rows:
        st.warning('El archivo no contiene registros.')
        return
    st.success(f'Registros cargados: {len(rows)}')
    st.dataframe(rows[:200], hide_index=True, use_container_width=True)
    st.caption('Vista limitada a 200 registros. Las estadísticas automáticas se habilitarán tras validar las columnas disponibles.')


def mostrar_resumen_inteligente_soccer():
    st.title('⚽ Resumen Inteligente Soccer')
    st.caption('Etapa 3 · Estadísticas reales · Diseño móvil · Sin API-Football')
    fuente = st.radio('Fuente de datos', ['football-data.org', 'CSV local'], horizontal=True, key='soc_fuente_v3')
    if fuente == 'CSV local':
        _archivo_csv()
        return
    token = _token()
    if not token:
        st.warning('Falta configurar FOOTBALL_DATA_KEY en los Secrets de esta aplicación.')
        st.info('Obtén una clave gratuita en football-data.org y guárdala en Streamlit Cloud → Settings → Secrets como FOOTBALL_DATA_KEY = "tu_clave". No compartas tu clave.')
        st.caption('Puedes usar «CSV local» mientras configuras la nueva fuente.')
        return
    st.success('Nueva fuente configurada. Clave detectada sin mostrar su valor.')
    st.caption('Consultas únicamente al pulsar botones; caché de una hora. La cobertura depende del plan y la temporada.')
    nombre = st.selectbox('Competición', list(COMPETICIONES), key='soc_comp_v3')
    codigo = COMPETICIONES[nombre]
    temporada = st.selectbox('Temporada (año de inicio)', [2026, 2025, 2024, 2023], key='soc_season_v3')
    st.caption('La Champions League utiliza el código CL. Algunas temporadas o competiciones pueden estar restringidas.')
    if st.button('📅 Cargar partidos', key='soc_matches_v3'):
        try:
            data = _consulta(f'/competitions/{codigo}/matches', token, temporada)
            st.session_state['soc_partidos_v3'] = (codigo, temporada, data.get('matches', []))
            st.success(f"Partidos recibidos: {len(data.get('matches', []))}")
        except ValueError as exc:
            st.error(str(exc))
    saved = st.session_state.get('soc_partidos_v3')
    if saved and saved[:2] == (codigo, temporada):
        rows = _partidos(saved[2])
        if rows:
            estados = ['Todos', 'Finalizados', 'Programados']
            vista = st.selectbox('Mostrar partidos', estados, key='soc_vista_v3')
            if vista == 'Finalizados':
                rows_view = [x for x in rows if x['Estado'] == 'FINISHED']
            elif vista == 'Programados':
                rows_view = [x for x in rows if x['Estado'] in ('SCHEDULED', 'TIMED')]
            else:
                rows_view = rows
            st.dataframe(rows_view[:100], hide_index=True, use_container_width=True)
            st.caption(f'Se muestran {min(100, len(rows_view))} de {len(rows_view)} partidos. Horario UTC.')
            st.subheader('📊 Estadísticas históricas')
            _resumen(rows)
        else:
            st.info('La API no devolvió partidos para la competición y temporada elegidas.')
    if st.button('👥 Cargar equipos', key='soc_teams_v3'):
        try:
            data = _consulta(f'/competitions/{codigo}/teams', token, temporada)
            st.session_state['soc_equipos_v3'] = (codigo, temporada, data.get('teams', []))
            st.success(f"Equipos recibidos: {len(data.get('teams', []))}")
        except ValueError as exc:
            st.error(str(exc))
    teams = st.session_state.get('soc_equipos_v3')
    if teams and teams[:2] == (codigo, temporada):
        st.dataframe([{'Equipo': x.get('name', 'N/D'), 'País': x.get('area', {}).get('name', 'N/D')}
                      for x in teams[2]], hide_index=True, use_container_width=True)
    st.divider()
    st.caption('Córners y estadísticas individuales: pendientes de fuente verificada. No se muestran cifras inventadas.')


if __name__ == '__main__':
    mostrar_resumen_inteligente_soccer()
