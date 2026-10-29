"""Historial NBA por equipo y jugador. Fuente ESPN no oficial; sin datos simulados.

Instalación: junto a modulo_nba.py. Vista: mostrar_historial_jugadores_nba().
No modifica NFL ni los demás componentes NBA.
"""
from datetime import date, timedelta
import pandas as pd
import streamlit as st
from modulo_nba import cargar_partidos, cargar_detalle, extraer_jugadores

VERSION = '1.1.0'
METRICAS = {
    'Puntos': ('PTS', 'points'), 'Rebotes': ('REB', 'rebounds'),
    'Asistencias': ('AST', 'assists'), 'Robos': ('STL', 'steals'),
    'Tapones': ('BLK', 'blocks'), 'Pérdidas': ('TO', 'turnovers'),
    'Minutos': ('MIN', 'minutes'),
}


def _numero(valor):
    if valor is None or isinstance(valor, bool):
        return float('nan')
    s = str(valor).strip()
    if s.upper() in ('', '-', '--', 'DNP', 'N/A', 'DND', 'DID NOT PLAY'):
        return float('nan')
    if ':' in s:
        try:
            m, sec = s.split(':', 1)
            return int(m) + int(sec) / 60
        except (ValueError, TypeError):
            return float('nan')
    return pd.to_numeric(s.replace(',', ''), errors='coerce')


def _extraer_partido(id_partido, fecha, equipo):
    box = extraer_jugadores(cargar_detalle(str(id_partido)))
    if box.empty or 'jugador' not in box.columns or 'equipo' not in box.columns:
        return []
    box = box.loc[box['equipo'].eq(equipo)]
    filas = []
    for _, atleta in box.iterrows():
        nombre = str(atleta.get('jugador', '')).strip()
        if not nombre or nombre == 'Desconocido':
            continue
        fila = {'partido_id': str(id_partido), 'fecha': fecha, 'equipo': equipo,
                'jugador': nombre, 'titular': bool(atleta.get('titular', False))}
        for nombre_metrica, nombres_fuente in METRICAS.items():
            col = next((x for x in nombres_fuente if x in box.columns), None)
            fila[nombre_metrica] = _numero(atleta.get(col)) if col else float('nan')
        filas.append(fila)
    return filas


def _consultar_bloque(desde, hasta, equipo):
    """Solo boxscores de partidos finalizados del equipo seleccionado."""
    partidos, errores = cargar_partidos(desde.isoformat(), hasta.isoformat())
    if partidos.empty:
        return pd.DataFrame(), list(errores), 0
    juegos = partidos.loc[
        partidos['finalizado'].eq(True)
        & (partidos['local'].eq(equipo) | partidos['visitante'].eq(equipo))
    ].drop_duplicates('id').sort_values('fecha_utc')
    filas = []
    errores = list(errores)
    for juego in juegos.itertuples(index=False):
        try:
            extraidas = _extraer_partido(juego.id, str(juego.fecha_utc)[:10], equipo)
            if not extraidas:
                errores.append(f'{juego.id}: sin estadísticas individuales del equipo')
            filas.extend(extraidas)
        except Exception as exc:
            errores.append(f'{juego.id}: {type(exc).__name__}: {exc}')
    return pd.DataFrame(filas), errores, len(juegos)


def _unir_historial(actual, nuevo):
    if nuevo.empty:
        return actual.copy()
    junto = pd.concat([actual, nuevo], ignore_index=True) if not actual.empty else nuevo.copy()
    return junto.drop_duplicates(['partido_id', 'equipo', 'jugador'], keep='last').reset_index(drop=True)


def obtener_historial_compartido(equipo=None, desde=None, hasta=None):
    """Devuelve una COPIA de los boxscores ya cargados en la vista Historial.

    Nunca consulta automáticamente la red ni mezcla equipos/períodos distintos.
    Devuelve (datos, cobertura), donde cobertura contiene el progreso real.
    """
    firma = st.session_state.get('hist_nba_firma')
    vacio = pd.DataFrame()
    if not firma or len(firma) != 3:
        return vacio, {'disponible': False, 'motivo': 'Aún no se ha cargado el historial.'}
    ini, fin, nombre_equipo = firma
    if equipo not in (None, 'Todos', nombre_equipo):
        return vacio, {'disponible': False, 'motivo': 'El historial cargado corresponde a otro equipo.'}
    if desde is not None and ini > str(desde):
        return vacio, {'disponible': False, 'motivo': 'El historial no cubre el inicio solicitado.'}
    if hasta is not None and fin < str(hasta):
        return vacio, {'disponible': False, 'motivo': 'El historial no cubre el final solicitado.'}
    datos = st.session_state.get('hist_nba_datos', vacio)
    if not isinstance(datos, pd.DataFrame):
        datos = vacio
    datos = datos.copy()
    if not datos.empty and desde is not None:
        datos = datos.loc[datos['fecha'].astype(str).ge(str(desde))]
    if not datos.empty and hasta is not None:
        datos = datos.loc[datos['fecha'].astype(str).le(str(hasta))]
    return datos, {
        'disponible': True, 'equipo': nombre_equipo, 'desde': ini, 'hasta': fin,
        'bloques': int(st.session_state.get('hist_nba_bloques', 0)),
        'siguiente': st.session_state.get('hist_nba_siguiente'),
        'errores': len(st.session_state.get('hist_nba_errores', [])),
        'completo': st.session_state.get('hist_nba_siguiente', date.fromisoformat(ini)) > date.fromisoformat(fin),
    }


def mostrar_historial_jugadores_nba():
    st.title('🏀 Historial de jugadores NBA')
    st.caption('Versión ' + VERSION + ' · Boxscores ESPN no oficiales. Carga por bloques de hasta 31 días; los datos pueden ser parciales.')
    hoy = date.today()
    inicio_sugerido = date(hoy.year if hoy.month >= 10 else hoy.year - 1, 10, 1)
    inicio_sugerido = min(inicio_sugerido, hoy)
    desde = st.date_input('Inicio del período', inicio_sugerido, key='hist_nba_desde')
    hasta = st.date_input('Fin del período', hoy, key='hist_nba_hasta')
    if desde > hasta or hasta > hoy:
        st.warning('Selecciona fechas válidas, sin incluir días futuros.')
        return
    # Obtener equipos del calendario del bloque inicial, no de listas simuladas.
    bloque_inicio = desde
    bloque_fin = min(desde + timedelta(days=30), hasta)
    try:
        inicial, fallas_iniciales = cargar_partidos(bloque_inicio.isoformat(), bloque_fin.isoformat())
    except Exception as exc:
        st.error(f'No se pudo consultar el calendario: {type(exc).__name__}: {exc}')
        return
    if inicial.empty:
        st.info('No hay partidos en el primer bloque. Cambia la fecha de inicio.')
        return
    equipos = sorted((set(inicial['local'].dropna()) | set(inicial['visitante'].dropna())) - {''})
    if not equipos:
        st.info('No hay equipos identificados en el calendario.')
        return
    equipo = st.selectbox('Equipo', equipos, key='hist_nba_equipo')
    firma = (desde.isoformat(), hasta.isoformat(), equipo)
    if st.session_state.get('hist_nba_firma') != firma:
        st.session_state['hist_nba_firma'] = firma
        st.session_state['hist_nba_datos'] = pd.DataFrame()
        st.session_state['hist_nba_siguiente'] = desde
        st.session_state['hist_nba_errores'] = []
        st.session_state['hist_nba_juegos'] = 0
        st.session_state['hist_nba_bloques'] = 0
    siguiente = st.session_state['hist_nba_siguiente']
    if siguiente <= hasta:
        cierre = min(siguiente + timedelta(days=30), hasta)
        st.caption(f'Próximo bloque: {siguiente:%d/%m/%Y} a {cierre:%d/%m/%Y}')
        if st.button('📥 Cargar siguiente bloque', key='hist_nba_cargar', use_container_width=True):
            with st.spinner('Consultando partidos finalizados y boxscores del equipo...'):
                try:
                    nuevos, fallas, cantidad = _consultar_bloque(siguiente, cierre, equipo)
                except Exception as exc:
                    st.error(f'No se pudo cargar el bloque: {type(exc).__name__}: {exc}')
                else:
                    st.session_state['hist_nba_datos'] = _unir_historial(st.session_state['hist_nba_datos'], nuevos)
                    st.session_state['hist_nba_errores'].extend(fallas)
                    st.session_state['hist_nba_juegos'] += cantidad
                    st.session_state['hist_nba_bloques'] += 1
                    st.session_state['hist_nba_siguiente'] = cierre + timedelta(days=1)
                    st.rerun()
    else:
        st.success('Todos los bloques solicitados fueron consultados. Comprueba las incidencias antes de considerar completo el historial.')
    datos = st.session_state['hist_nba_datos']
    errores = st.session_state['hist_nba_errores']
    st.metric('Bloques consultados', st.session_state['hist_nba_bloques'])
    st.metric('Partidos finalizados consultados', st.session_state['hist_nba_juegos'])
    st.metric('Registros individuales', len(datos))
    if fallas_iniciales or errores:
        st.warning(f'Datos potencialmente incompletos: {len(fallas_iniciales) + len(errores)} incidencias de consulta.')
        with st.expander('🔍 Incidencias de cobertura'):
            st.text('\n'.join(map(str, fallas_iniciales + errores)))
    if datos.empty:
        st.info('Carga un bloque para obtener estadísticas individuales. No se muestran promedios sin datos.')
        return
    opciones = sorted(datos['jugador'].dropna().unique().tolist())
    jugadores = st.multiselect('Selecciona hasta 3 jugadores', opciones, max_selections=3, key='hist_nba_jugadores')
    if not jugadores:
        st.info('Selecciona jugadores para consultar su historial.')
        return
    seleccion = datos.loc[datos['jugador'].isin(jugadores)].copy()
    seleccion['fecha'] = pd.to_datetime(seleccion['fecha'], errors='coerce')
    seleccion = seleccion.sort_values(['jugador', 'fecha', 'partido_id'])
    ventana = st.selectbox('Partidos recientes por jugador', ['Todos los recuperados', 5, 10, 20], key='hist_nba_ventana')
    if isinstance(ventana, int):
        seleccion = seleccion.groupby('jugador', group_keys=False).tail(ventana)
    metricas = [m for m in METRICAS if m in seleccion and seleccion[m].notna().any()]
    if not metricas:
        st.warning('No hay estadísticas numéricas válidas en los boxscores consultados.')
        return
    # No contar DNP como partido jugado si se dispone de minutos explícitos = 0.
    jugados = seleccion.loc[seleccion['Minutos'].isna() | seleccion['Minutos'].gt(0)].copy()
    if jugados.empty:
        st.info('No hay partidos con participación comprobable para los jugadores seleccionados.')
        return
    resumen = jugados.groupby('jugador').agg(
        PJ=('partido_id', 'nunique'), Titularidades=('titular', 'sum'),
        **{m: (m, 'mean') for m in metricas}
    ).round(2).reset_index()
    st.subheader('📊 Promedios de partidos recuperados')
    st.dataframe(resumen, hide_index=True, use_container_width=True)
    st.caption('PJ es el número de partidos recuperados con registro del jugador, no necesariamente toda su temporada. Los valores ausentes no se convierten en cero.')
    metrica = st.selectbox('Métrica de evolución', metricas, key='hist_nba_metrica')
    grafico = jugados.pivot_table(index='fecha', columns='jugador', values=metrica, aggfunc='mean')
    if not grafico.empty:
        st.line_chart(grafico)
    with st.expander('📋 Historial por partido'):
        columnas = ['fecha', 'jugador', 'equipo', 'partido_id', 'titular'] + metricas
        st.dataframe(jugados[columnas].sort_values('fecha', ascending=False), hide_index=True, use_container_width=True)
    st.download_button('📥 Descargar historial CSV', datos.to_csv(index=False).encode('utf-8-sig'),
                       'historial_jugadores_nba.csv', 'text/csv', key='hist_nba_csv')


if __name__ == '__main__':
    mostrar_historial_jugadores_nba()
