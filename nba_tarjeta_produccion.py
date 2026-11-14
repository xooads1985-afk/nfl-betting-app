"""Entrada aislada para tarjeta NBA; guardado explícito de proyecciones futuras."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import pandas as pd
import requests
import streamlit as st

TZ = ZoneInfo('America/Mazatlan')


def _agenda(dia):
    respuesta = requests.get('https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard',
                            params={'dates': dia.strftime('%Y%m%d'), 'limit': 100}, timeout=(3, 10))
    respuesta.raise_for_status()
    salida = []
    for evento in respuesta.json().get('events', []):
        competencias = evento.get('competitions') or []
        if not competencias:
            continue
        equipos = competencias[0].get('competitors') or []
        local = next((e for e in equipos if e.get('homeAway') == 'home'), None)
        visitante = next((e for e in equipos if e.get('homeAway') == 'away'), None)
        if not local or not visitante:
            continue
        fecha = evento.get('date')
        try:
            inicio = datetime.fromisoformat(fecha.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            continue
        if inicio <= datetime.now(timezone.utc) or evento.get('status', {}).get('type', {}).get('completed'):
            continue
        salida.append({'id': str(evento['id']), 'fecha_utc': fecha,
                       'local': local['team']['displayName'],
                       'visitante': visitante['team']['displayName'], 'finalizado': False})
    return salida


def mostrar_tarjeta_nba_produccion():
    st.subheader('🏀 Tarjeta Inteligente NBA · cuatro motores')
    st.caption('Partidos futuros · análisis estadístico · proyecciones originales protegidas')
    dia = st.date_input('Fecha de los encuentros', value=datetime.now(TZ).date(),
                        min_value=datetime.now(TZ).date(),
                        max_value=datetime.now(TZ).date() + timedelta(days=14),
                        key='nba_prod_fecha')
    if st.button('📅 Consultar partidos', key='nba_prod_agenda'):
        try:
            st.session_state['nba_prod_partidos'] = _agenda(dia)
            st.session_state['nba_prod_dia'] = dia.isoformat()
        except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
            st.session_state['nba_prod_partidos'] = []
            st.error('No se pudo consultar el calendario: ' + str(exc))
    partidos = st.session_state.get('nba_prod_partidos', []) if st.session_state.get('nba_prod_dia') == dia.isoformat() else []
    if not partidos:
        st.info('Consulta el calendario. Si no aparecen partidos, elige otro día.')
        return
    opciones = {p['id']: p for p in partidos}
    pid = st.selectbox('Selecciona un partido', list(opciones),
                       format_func=lambda k: f"{opciones[k]['visitante']} @ {opciones[k]['local']}",
                       key='nba_prod_partido')
    partido = opciones[pid]
    from nba_conexion_tarjeta import mostrar_tarjeta_conectada
    if st.button('🏀 Analizar partido', key='nba_prod_analizar'):
        st.session_state['nba_prod_analizado'] = pid
    if st.session_state.get('nba_prod_analizado') != pid:
        return
    # Vista previa de solo lectura, aunque se refresque la página.
    mostrar_tarjeta_conectada(partido, partidos=pd.DataFrame(partidos),
                             escritura_habilitada=False, historial_remoto_habilitado=False)
    st.caption('El guardado de los motores es una acción independiente y explícita.')
    confirmar = st.checkbox('Confirmo que deseo guardar las proyecciones de este partido antes de su inicio',
                            key='nba_prod_confirmar_'+pid)
    if st.button('💾 Guardar motores faltantes', disabled=not confirmar,
                 key='nba_prod_guardar_'+pid):
        inicio = datetime.fromisoformat(partido['fecha_utc'].replace('Z', '+00:00'))
        if datetime.now(timezone.utc) >= inicio:
            st.error('Partido iniciado: no se permite guardar proyecciones.')
            return
        resultado = mostrar_tarjeta_conectada(partido, partidos=pd.DataFrame(partidos),
                                               escritura_habilitada=True, historial_remoto_habilitado=False)
        estado = resultado.get('estado') if isinstance(resultado, dict) else None
        if estado == 'completo':
            st.success('Cuatro motores completos y verificados mediante consulta.')
        else:
            st.warning('Guardado no confirmado como completo. Estado: ' + str(estado))
