"""Promedios y diferencias NBA: módulo independiente, descriptivo y sin apuestas.

Depende de modulo_nba.py y comparador_jugadores_nba.py. La cobertura depende
exclusivamente de los partidos finalizados consultados a ESPN (API no oficial).
"""
from datetime import date, timedelta
import pandas as pd
import streamlit as st

from modulo_nba import cargar_partidos
from comparador_jugadores_nba import _historial, METRICAS

VERSION = '1.1.0'


def calcular_promedios(datos, jugadores, metrica, ventana=5):
    """Calcula promedios observados y diferencia reciente vs. período anterior.

    No inventa partidos ni rellena datos ausentes con ceros. Si no existe un
    período anterior comparable, devuelve NA en lugar de una diferencia falsa.
    """
    if datos.empty or metrica not in datos.columns:
        return pd.DataFrame()
    registros = []
    for nombre in jugadores:
        df = datos.loc[datos['clave_jugador'].eq(nombre)].copy() if 'clave_jugador' in datos else datos.loc[datos['jugador'].eq(nombre)].copy()
        df[metrica] = pd.to_numeric(df[metrica], errors='coerce')
        df = df.dropna(subset=[metrica]).sort_values(['fecha', 'partido_id'])
        if df.empty:
            continue
        recientes = df.tail(ventana)
        anteriores = df.iloc[max(0, len(df) - 2 * ventana):max(0, len(df) - ventana)]
        media_total = df[metrica].mean()
        media_reciente = recientes[metrica].mean()
        media_anterior = anteriores[metrica].mean() if not anteriores.empty else float('nan')
        registros.append({
            'Jugador': nombre, 'Partidos con dato': len(df),
            'N reciente': len(recientes), 'N anterior': len(anteriores),
            'Tramos completos': len(recientes) == ventana and len(anteriores) == ventana,
            'Promedio período': media_total, 'Promedio reciente': media_reciente,
            'Promedio anterior': media_anterior,
            'Diferencia reciente-anterior': (media_reciente - media_anterior)
            if pd.notna(media_anterior) else float('nan'),
            'Máximo': df[metrica].max(), 'Mínimo': df[metrica].min(),
        })
    return pd.DataFrame(registros).round(2)


def mostrar_promedios_diferencias():
    """Entrada pública para el futuro centro_estadistico_nba.py."""
    st.title('🏀 Promedios y diferencias NBA')
    st.caption('v' + VERSION + ' · Estadísticas observadas por partido; sin datos simulados.')
    hoy = date.today()
    c1, c2 = st.columns(2)
    with c1:
        desde = st.date_input('Desde', hoy - timedelta(days=14), key='pd_nba_desde')
    with c2:
        hasta = st.date_input('Hasta', hoy, key='pd_nba_hasta')
    if hasta < desde or (hasta - desde).days > 31:
        st.warning('Selecciona un intervalo válido de hasta 32 días inclusive.')
        return
    periodo = (desde.isoformat(), hasta.isoformat())
    if st.button('📥 Consultar partidos', key='pd_nba_cargar', use_container_width=True):
        st.session_state['pd_nba_periodo'] = periodo
    if st.session_state.get('pd_nba_periodo') != periodo:
        st.info('Pulsa «Consultar partidos» para cargar las estadísticas.')
        return
    try:
        partidos, errores_calendario = cargar_partidos(*periodo)
    except Exception as exc:
        st.error(f'No se pudo consultar el calendario: {type(exc).__name__}: {exc}')
        return
    if partidos.empty or 'finalizado' not in partidos:
        st.info('No hay partidos en el intervalo seleccionado.')
        return
    finalizados = partidos.loc[partidos['finalizado'].eq(True) &
        partidos['puntos_local'].notna() & partidos['puntos_visitante'].notna()].sort_values('fecha_utc', ascending=False)
    if finalizados.empty:
        st.info('Todavía no hay partidos finalizados en este intervalo.')
        return
    limite = st.slider('Partidos a consultar', 1, min(100, len(finalizados)),
                       min(12, len(finalizados)), key='pd_nba_limite')
    seleccion = finalizados.head(limite)
    ids = tuple((str(r.id), str(r.fecha_utc)[:10]) for r in seleccion.itertuples(index=False))
    with st.spinner('Recuperando estadísticas reales de los partidos...'):
        datos, errores_boxscore = _historial(ids)
    incidencias = errores_calendario + errores_boxscore
    if incidencias:
        st.warning(f'Cobertura parcial: {len(incidencias)} incidencias de consulta.')
        with st.expander('Ver incidencias'):
            st.text('\n'.join(map(str, incidencias)))
    if datos.empty:
        st.info('No se recibieron estadísticas de jugadores para los partidos consultados.')
        return
    equipos = sorted(datos['equipo'].dropna().unique().tolist())
    equipo = st.selectbox('Equipo', ['Todos'] + equipos, key='pd_nba_equipo')
    if equipo != 'Todos':
        datos = datos.loc[datos['equipo'].eq(equipo)].copy()
    if 'clave_jugador' not in datos.columns:
        st.error('El comparador instalado no proporciona IDs de jugadores. Se requiere Comparador NBA v1.2.')
        return
    datos = datos.drop_duplicates(['clave_jugador', 'partido_id'], keep='first').copy()
    catalogo = (datos[['clave_jugador', 'jugador', 'equipo', 'jugador_id']]
                .drop_duplicates('clave_jugador').sort_values(['jugador', 'equipo']))
    etiquetas = {r.clave_jugador: f'{r.jugador} · {r.equipo}' +
                 (f' · ID {r.jugador_id}' if r.jugador_id else ' · sin ID ESPN')
                 for r in catalogo.itertuples(index=False)}
    jugadores = catalogo['clave_jugador'].tolist()
    elegidos = st.multiselect('Selecciona hasta tres jugadores', jugadores,
                              max_selections=3, format_func=lambda x: etiquetas.get(x, x),
                              key='pd_nba_jugadores')
    if not elegidos:
        st.info('Selecciona al menos un jugador para ver sus promedios y diferencias.')
        return
    metricas = [m for m in METRICAS if m in datos.columns and
                pd.to_numeric(datos.loc[datos['clave_jugador'].isin(elegidos), m],
                              errors='coerce').notna().any()]
    if not metricas:
        st.warning('No hay métricas numéricas para los jugadores seleccionados.')
        return
    metrica = st.selectbox('Estadística', metricas, key='pd_nba_metrica')
    ventana = st.slider('Partidos por tramo reciente/anterior', 2, 10, 5, key='pd_nba_ventana')
    resumen = calcular_promedios(datos, elegidos, metrica, ventana)
    if resumen.empty:
        st.info('No hay registros válidos para calcular promedios.')
        return
    st.subheader(f'📊 Promedios y diferencias · {metrica}')
    resumen['Jugador'] = resumen['Jugador'].map(etiquetas).fillna(resumen['Jugador'])
    st.dataframe(resumen, hide_index=True, use_container_width=True)
    if not resumen['Tramos completos'].all():
        st.warning('Al menos un jugador no tiene dos tramos completos. La diferencia disponible es descriptiva y debe interpretarse con cautela.')
    st.caption('N reciente y N anterior muestran cuántos partidos válidos sustentan cada tramo. '
               'Cuando faltan partidos anteriores se usan los disponibles; sin tramo anterior, '
               'la diferencia queda vacía. No es una predicción.')
    grafico = resumen.set_index('Jugador')[['Promedio período', 'Promedio reciente']]
    st.bar_chart(grafico)
    st.subheader('📈 Historial observado')
    detalle = datos.loc[datos['clave_jugador'].isin(elegidos)].copy()
    detalle[metrica] = pd.to_numeric(detalle[metrica], errors='coerce')
    detalle = detalle.dropna(subset=[metrica]).sort_values(['fecha', 'partido_id'])
    if not detalle.empty:
        detalle['Fecha'] = pd.to_datetime(detalle['fecha'], errors='coerce')
        detalle = detalle.dropna(subset=['Fecha'])
        detalle['Jugador'] = detalle['clave_jugador'].map(etiquetas)
        etiquetas_cortas = {}
        for clave in elegidos:
            filas = detalle.loc[detalle['clave_jugador'].eq(clave)]
            if not filas.empty:
                nombre = str(filas['jugador'].iloc[0])
                repetidos = sum(not detalle.loc[detalle['clave_jugador'].eq(k) & detalle['jugador'].eq(nombre)].empty for k in elegidos)
                etiquetas_cortas[etiquetas[clave]] = nombre if repetidos == 1 else f'{nombre} · {clave}'
        detalle['Jugador'] = detalle['Jugador'].replace(etiquetas_cortas)
        st.scatter_chart(detalle, x='Fecha', y=metrica, color='Jugador', use_container_width=True)
        st.caption('Cada punto representa un partido observado; no se rellenan fechas sin partidos.')
        with st.expander('📋 Registros por partido'):
            st.dataframe(detalle[['fecha', 'partido_id', 'Jugador', 'equipo', metrica]],
                         hide_index=True, use_container_width=True)
    st.download_button('📥 Exportar promedios CSV',
                       resumen.to_csv(index=False).encode('utf-8-sig'),
                       'promedios_diferencias_nba.csv', 'text/csv',
                       key='pd_nba_csv', use_container_width=True)
    st.caption(f'Cobertura: {len(seleccion)} de {len(finalizados)} partidos finalizados '
               'del intervalo. Las métricas ausentes se excluyen del promedio. '
               'La fuente ESPN es no oficial y puede cambiar. '
               'Se utiliza ID de ESPN cuando está disponible; sin ID, nombre y equipo.')


if __name__ == '__main__':
    mostrar_promedios_diferencias()
