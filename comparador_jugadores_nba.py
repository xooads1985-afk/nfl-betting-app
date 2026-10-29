"""Comparador descriptivo NBA, independiente de NFL.

Requiere modulo_nba.py, pandas y streamlit. Datos ESPN (endpoint no oficial).
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
    'Faltas': ('PF', 'fouls'), 'Minutos': ('MIN', 'minutes'),
}


def _numero(valor):
    """Convierte solo números válidos; nunca transforma ausencias en cero."""
    if valor is None or isinstance(valor, bool):
        return float('nan')
    cadena = str(valor).strip()
    if not cadena or cadena in ('--', '-', 'DNP', 'N/A'):
        return float('nan')
    if ':' in cadena:  # MM:SS en minutos jugados
        try:
            minutos, segundos = cadena.split(':', 1)
            return int(minutos) + int(segundos) / 60
        except (ValueError, TypeError):
            return float('nan')
    return pd.to_numeric(cadena.replace(',', ''), errors='coerce')


def _columna(df, alternativas):
    return next((col for col in alternativas if col in df.columns), None)


def _identidades_detalle(detalle):
    """Extrae ID de ESPN siguiendo el orden de las filas de extraer_jugadores."""
    identidades = []
    for equipo in detalle.get('boxscore', {}).get('players', []):
        for bloque in equipo.get('statistics', []):
            for jugador in bloque.get('athletes', []):
                if isinstance(jugador, dict):
                    atleta = jugador.get('athlete') or {}
                    identidades.append(str(atleta.get('id') or '').strip())
    return identidades


@st.cache_data(ttl=1800, show_spinner=False)
def _historial(ids_y_fechas):
    registros, errores = [], []
    for id_partido, fecha in ids_y_fechas:
        try:
            detalle = cargar_detalle(id_partido)
            df = extraer_jugadores(detalle)
            if df.empty or 'jugador' not in df.columns:
                errores.append(f'{fecha} · {id_partido}: sin boxscore de jugadores')
                continue
            identidades = _identidades_detalle(detalle)
            for posicion, (_, fila) in enumerate(df.iterrows()):
                nombre = str(fila.get('jugador', '')).strip()
                if not nombre or nombre == 'Desconocido':
                    continue
                equipo = str(fila.get('equipo', '')).strip()
                atleta_id = identidades[posicion] if posicion < len(identidades) else ''
                # Sin ID, nombre + equipo evitan mezclar homónimos de equipos distintos.
                clave = 'id:' + atleta_id if atleta_id else 'nombre_equipo:' + nombre.casefold() + '|' + equipo.casefold()
                registro = {'fecha': fecha, 'partido_id': id_partido,
                            'jugador_id': atleta_id, 'clave_jugador': clave,
                            'jugador': nombre, 'equipo': equipo}
                for etiqueta, alternativas in METRICAS.items():
                    columna = _columna(df, alternativas)
                    registro[etiqueta] = _numero(fila.get(columna)) if columna else float('nan')
                registros.append(registro)
        except Exception as exc:
            errores.append(f'{fecha} · {id_partido}: {type(exc).__name__}: {exc}')
    return pd.DataFrame(registros), errores


def mostrar_comparador():
    """Punto de entrada compatible con el centro estadístico NBA."""
    st.title('🏀 Comparador de jugadores NBA')
    st.caption('Versión ' + VERSION + ' · Datos observados de boxscores ESPN; sin estadísticas inventadas.')
    hoy = date.today()
    a, b = st.columns(2)
    with a:
        desde = st.date_input('Desde', hoy - timedelta(days=7), key='comp_nba_desde')
    with b:
        hasta = st.date_input('Hasta', hoy, key='comp_nba_hasta')
    if hasta < desde or (hasta - desde).days > 31:
        st.warning('Selecciona un intervalo de 1 a 32 días, inclusive.')
        return
    if st.button('📥 Cargar estadísticas NBA', key='comp_nba_cargar', use_container_width=True):
        st.session_state['comp_nba_periodo'] = (desde.isoformat(), hasta.isoformat())
    periodo = (desde.isoformat(), hasta.isoformat())
    if st.session_state.get('comp_nba_periodo') != periodo:
        st.info('Pulsa «Cargar estadísticas NBA» para consultar el período seleccionado.')
        return
    try:
        partidos, errores_calendario = cargar_partidos(*periodo)
    except Exception as exc:
        st.error(f'Error al consultar el calendario: {type(exc).__name__}: {exc}')
        return
    if partidos.empty:
        st.info('No hay partidos registrados para este período.')
        return
    completos = partidos[(partidos['finalizado'] == True) &
                         partidos['puntos_local'].notna() &
                         partidos['puntos_visitante'].notna()].copy()
    if completos.empty:
        st.info('No hay partidos finalizados con estadísticas disponibles.')
        return
    # Consultas limitadas para proteger la experiencia móvil; ampliar es opcional.
    completos = completos.sort_values('fecha_utc', ascending=False)
    maximo = min(100, len(completos))
    limite = st.slider('Partidos finalizados a consultar', 1, maximo,
                       min(12, maximo), key='comp_nba_limite')
    st.caption(f'Cobertura elegida: {limite} de {len(completos)} partidos con marcador completo. '
               'Aumentar el límite puede tardar más; el máximo por consulta es 100.')
    seleccion = completos.head(limite)
    ids = tuple((str(row.id), str(row.fecha_utc)[:10]) for row in seleccion.itertuples(index=False))
    with st.spinner('Consultando estadísticas por partido...'):
        datos, errores_boxscore = _historial(ids)
    if errores_calendario or errores_boxscore:
        st.warning(f'Información parcial: {len(errores_calendario)} fechas y '
                   f'{len(errores_boxscore)} boxscores con incidencias.')
        with st.expander('Ver incidencias'):
            st.text('\n'.join([str(x) for x in errores_calendario + errores_boxscore]))
    if datos.empty:
        st.info('La fuente no devolvió estadísticas individuales en los partidos consultados.')
        return
    equipos = sorted(datos['equipo'].dropna().unique().tolist())
    equipo = st.selectbox('Filtrar equipo', ['Todos'] + equipos, key='comp_nba_equipo')
    if equipo != 'Todos':
        datos = datos[datos['equipo'] == equipo].copy()
    catalogo = (datos[['clave_jugador', 'jugador', 'equipo', 'jugador_id']]
                .drop_duplicates('clave_jugador').sort_values(['jugador', 'equipo']))
    opciones = catalogo['clave_jugador'].tolist()
    if not opciones:
        st.info('No se encontraron jugadores para este filtro.')
        return
    etiquetas = {}
    for fila in catalogo.itertuples(index=False):
        etiquetas[fila.clave_jugador] = (f'{fila.jugador} · {fila.equipo}' +
                                        (f' · ID {fila.jugador_id}' if fila.jugador_id else ' · sin ID ESPN'))
    elegidos = st.multiselect('Selecciona hasta 3 jugadores', opciones,
                              max_selections=3, format_func=lambda x: etiquetas.get(x, x),
                              key='comp_nba_jugadores')
    if not elegidos:
        st.info('Selecciona uno, dos o tres jugadores para comenzar la comparación.')
        return
    filtrados = datos[datos['clave_jugador'].isin(elegidos)].copy()
    # Una sola observación por jugador/partido. No duplicar filas de la fuente.
    duplicados = int(filtrados.duplicated(['clave_jugador', 'partido_id']).sum())
    filtrados = filtrados.drop_duplicates(['clave_jugador', 'partido_id'], keep='first')
    filtrados['Jugador'] = filtrados['clave_jugador'].map(etiquetas)
    metricas = [m for m in METRICAS if filtrados[m].notna().any()]
    if not metricas:
        st.warning('No hay métricas numéricas comparables en estos boxscores.')
        return
    if duplicados:
        st.warning(f'Se encontraron {duplicados} registros repetidos por jugador y partido; '
                   'se conservaron una sola vez para la comparación.')
    resumen = filtrados.groupby('Jugador', as_index=False).agg(
        PJ=('partido_id', 'nunique'), **{m: (m, 'mean') for m in metricas}
    ).round(2)
    cobertura = filtrados.groupby('Jugador', as_index=False).agg(
        **{f'N {m}': (m, 'count') for m in metricas}
    )
    st.subheader('📊 Promedio por partido')
    st.dataframe(resumen, hide_index=True, use_container_width=True)
    st.caption('PJ = partidos con registro; N = partidos con valor válido para cada estadística.')
    with st.expander('🔍 Cobertura de cada promedio'):
        st.dataframe(cobertura, hide_index=True, use_container_width=True)
    metrica = st.selectbox('Métrica para comparar', metricas, key='comp_nba_metrica')
    st.bar_chart(resumen.set_index('Jugador')[[metrica]])
    st.subheader('📈 Evolución por partido')
    # Usar fecha + ID para no fusionar dos partidos distintos del mismo día.
    filtrados['Partido'] = filtrados['fecha'].astype(str) + ' · ' + filtrados['partido_id'].astype(str)
    serie = filtrados.pivot_table(index='Partido', columns='Jugador', values=metrica, aggfunc='first')
    if not serie.empty:
        st.line_chart(serie)
    with st.expander('📋 Estadísticas por partido'):
        columnas = ['fecha', 'partido_id', 'Jugador', 'equipo'] + metricas
        st.dataframe(filtrados[columnas].sort_values('fecha', ascending=False),
                     hide_index=True, use_container_width=True)
    st.download_button('📥 Exportar comparación CSV',
                       filtrados.to_csv(index=False).encode('utf-8-sig'),
                       'comparador_jugadores_nba.csv', 'text/csv',
                       key='comp_nba_exportar', use_container_width=True)
    st.caption(f'Cobertura: {len(seleccion)} partidos seleccionados de {len(completos)} '
               'finalizados con marcador completo en el período. No equivale a toda la temporada. '
               'Las ausencias no se convierten en cero. Cuando ESPN no proporciona ID, '
               'se utiliza nombre y equipo; aún pueden existir homónimos dentro del mismo equipo.')


if __name__ == '__main__':
    mostrar_comparador()
