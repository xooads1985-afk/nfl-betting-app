"""Resumen Inteligente NBA v1.0.0.

Módulo independiente de NFL. Depende de modulo_nba.py y
comparador_jugadores_nba.py; fuente ESPN no oficial. No simula datos.
"""
from datetime import date, timedelta
import pandas as pd
import streamlit as st

from modulo_nba import cargar_partidos
from comparador_jugadores_nba import _historial, METRICAS

VERSION = '1.0.0'


def _equipo_resultados(partidos, equipo):
    """Devuelve únicamente juegos finalizados con marcadores verificables."""
    if partidos.empty:
        return pd.DataFrame()
    d = partidos.loc[(partidos['local'].eq(equipo) | partidos['visitante'].eq(equipo)) &
                     partidos['finalizado'].eq(True)].copy()
    d = d.dropna(subset=['puntos_local', 'puntos_visitante'])
    if d.empty:
        return d
    es_local = d['local'].eq(equipo)
    d['PF'] = d['puntos_local'].where(es_local, d['puntos_visitante'])
    d['PC'] = d['puntos_visitante'].where(es_local, d['puntos_local'])
    d['Rival'] = d['visitante'].where(es_local, d['local'])
    d['Sede'] = es_local.map({True: 'Local', False: 'Visitante'})
    d['Resultado'] = ['V' if a > b else 'D' if a < b else 'E'
                      for a, b in zip(d['PF'], d['PC'])]
    return d.sort_values('fecha_utc')


def _mostrar_equipo(partidos, equipo):
    d = _equipo_resultados(partidos, equipo)
    st.markdown(f'**{equipo}**')
    if d.empty:
        st.info('Sin partidos finalizados con marcador en el período consultado.')
        return
    c1, c2, c3 = st.columns(3)
    c1.metric('PJ', len(d))
    c2.metric('Victorias', int(d['Resultado'].eq('V').sum()))
    c3.metric('Diferencia', f"{(d['PF'] - d['PC']).mean():+.1f}")
    st.caption(f"Puntos a favor {d['PF'].mean():.1f} · En contra {d['PC'].mean():.1f} (promedios del período)")
    ultimos = d.tail(5).copy()
    ultimos['Fecha'] = ultimos['fecha_utc'].astype(str).str[:10]
    st.dataframe(ultimos[['Fecha', 'Rival', 'Sede', 'PF', 'PC', 'Resultado']],
                 hide_index=True, use_container_width=True)


def _proximo_partido(partidos, equipo):
    if partidos.empty:
        return None
    pendientes = partidos.loc[(partidos['local'].eq(equipo) |
                               partidos['visitante'].eq(equipo)) &
                              partidos['finalizado'].eq(False)].copy()
    if pendientes.empty:
        return None
    pendientes['fecha_dt'] = pd.to_datetime(pendientes['fecha_utc'], utc=True, errors='coerce')
    ahora = pd.Timestamp.now(tz='UTC')
    pendientes = pendientes.loc[pendientes['fecha_dt'].ge(ahora)].sort_values('fecha_dt')
    return pendientes.iloc[0] if not pendientes.empty else None


def _mostrar_jugadores(partidos, equipo, limite):
    finales = partidos.loc[partidos['finalizado'].eq(True)].copy()
    if equipo != 'Todos':
        finales = finales.loc[finales['local'].eq(equipo) | finales['visitante'].eq(equipo)]
    if finales.empty:
        st.info('No hay partidos finalizados para consultar jugadores.')
        return
    finales = finales.sort_values('fecha_utc', ascending=False).head(limite)
    ids = tuple((str(r.id), str(r.fecha_utc)[:10]) for r in finales.itertuples(index=False))
    with st.spinner('Cargando boxscores observados...'):
        datos, errores = _historial(ids)
    if errores:
        st.warning(f'{len(errores)} boxscores no pudieron procesarse; cobertura parcial.')
        with st.expander('Detalles de cobertura'):
            st.text('\n'.join(map(str, errores)))
    if datos.empty:
        st.info('No hay estadísticas individuales disponibles en estos partidos.')
        return
    if equipo != 'Todos':
        datos = datos.loc[datos['equipo'].eq(equipo)].copy()
    if datos.empty:
        st.info('No hay jugadores con estadísticas para este equipo y período.')
        return
    opciones = sorted(datos['jugador'].dropna().astype(str).unique().tolist())
    seleccion = st.multiselect('Hasta tres jugadores', opciones, max_selections=3,
                               key='ri_nba_jugadores')
    if not seleccion:
        st.info('Selecciona de uno a tres jugadores.')
        return
    seleccionados = datos.loc[datos['jugador'].isin(seleccion)].copy()
    disponibles = [m for m in METRICAS if m in seleccionados and seleccionados[m].notna().any()]
    if not disponibles:
        st.warning('No hay métricas numéricas disponibles para estos jugadores.')
        return
    metrica = st.selectbox('Métrica para la evolución', disponibles, key='ri_nba_metrica')
    for nombre in seleccion:
        d = seleccionados.loc[seleccionados['jugador'].eq(nombre)].sort_values(['fecha', 'partido_id'])
        st.markdown(f'**{nombre}**')
        cols = st.columns(3)
        cols[0].metric('PJ con registro', d['partido_id'].nunique())
        for i, m in enumerate(['Puntos', 'Rebotes'], start=1):
            serie = pd.to_numeric(d[m], errors='coerce') if m in d else pd.Series(dtype=float)
            cols[i].metric(f'{m}/partido', f'{serie.mean():.1f}' if serie.notna().any() else 'N/D')
        tabla = d[['fecha', 'equipo'] + disponibles].copy()
        st.dataframe(tabla.tail(10).iloc[::-1], hide_index=True, use_container_width=True)
    resumen = seleccionados.groupby('jugador', as_index=False).agg(
        **{m: (m, 'mean') for m in disponibles}, PJ=('partido_id', 'nunique'))
    st.markdown('**Comparación de promedios observados**')
    st.dataframe(resumen.round(2), hide_index=True, use_container_width=True)
    grafica = seleccionados.pivot_table(index='fecha', columns='jugador', values=metrica,
                                       aggfunc='mean').sort_index()
    if not grafica.empty:
        st.line_chart(grafica)
    st.download_button('⬇️ Exportar comparación CSV',
                       resumen.to_csv(index=False).encode('utf-8-sig'),
                       'resumen_inteligente_nba.csv', 'text/csv',
                       key='ri_nba_export', use_container_width=True)
    st.caption('PJ y promedios corresponden solo a los boxscores recuperados, no a toda la temporada.')


def mostrar_resumen_inteligente_nba():
    """Punto de entrada del Resumen Inteligente NBA."""
    st.title('🏠 Resumen Inteligente NBA')
    st.caption(f'v{VERSION} · Vista compacta · Fuente ESPN no oficial · Sin datos simulados')
    hoy = date.today()
    c1, c2 = st.columns(2)
    with c1:
        desde = st.date_input('Desde', hoy - timedelta(days=14), key='ri_nba_desde')
    with c2:
        hasta = st.date_input('Hasta', hoy + timedelta(days=7), key='ri_nba_hasta')
    if hasta < desde or (hasta - desde).days > 31:
        st.warning('Elige un intervalo válido de hasta 32 días inclusive.')
        return
    periodo = (desde.isoformat(), hasta.isoformat())
    if st.button('🔄 Consultar datos NBA', key='ri_nba_consultar', use_container_width=True):
        st.session_state['ri_nba_periodo'] = periodo
    if st.session_state.get('ri_nba_periodo') != periodo:
        st.info('Pulsa «Consultar datos NBA» para cargar el período seleccionado.')
        return
    try:
        with st.spinner('Consultando calendario NBA...'):
            partidos, errores = cargar_partidos(*periodo)
    except Exception as exc:
        st.error(f'No fue posible cargar el calendario: {type(exc).__name__}: {exc}')
        return
    if errores:
        st.warning(f'Cobertura parcial: {len(errores)} días con incidencias.')
        with st.expander('Ver incidencias'):
            st.text('\n'.join(map(str, errores)))
    if partidos.empty:
        st.info('No hay partidos disponibles en las fechas seleccionadas.')
        return
    equipos = sorted(set(partidos['local'].dropna()) | set(partidos['visitante'].dropna()))
    equipo = st.selectbox('Equipo', ['Todos'] + equipos, key='ri_nba_equipo')
    vista = st.radio('Vista', ['🏟️ Equipos', '👥 Jugadores', '📅 Calendario'],
                    key='ri_nba_vista', horizontal=False)
    if vista == '🏟️ Equipos':
        elegidos = st.multiselect('Comparar hasta tres equipos', equipos,
                                 default=[equipo] if equipo != 'Todos' else [],
                                 max_selections=3, key='ri_nba_equipos')
        for nombre in elegidos:
            _mostrar_equipo(partidos, nombre)
            proximo = _proximo_partido(partidos, nombre)
            if proximo is not None:
                rival = proximo['visitante'] if proximo['local'] == nombre else proximo['local']
                st.caption(f"Próximo partido listado: {str(proximo['fecha_utc'])[:16]} UTC · vs. {rival}")
        if not elegidos:
            st.info('Selecciona uno, dos o tres equipos.')
    elif vista == '👥 Jugadores':
        finales = partidos.loc[partidos['finalizado'].eq(True)]
        maximo = min(35, len(finales))
        if maximo == 0:
            st.info('No hay partidos finalizados con estadísticas individuales.')
        else:
            limite = st.slider('Máximo de boxscores a consultar', 1, maximo,
                               min(12, maximo), key='ri_nba_limite')
            _mostrar_jugadores(partidos, equipo, limite)
    else:
        vista_cal = partidos.copy()
        if equipo != 'Todos':
            vista_cal = vista_cal.loc[vista_cal['local'].eq(equipo) |
                                          vista_cal['visitante'].eq(equipo)]
        columnas = ['fecha_utc', 'visitante', 'local', 'estado',
                    'puntos_visitante', 'puntos_local']
        st.dataframe(vista_cal[columnas], hide_index=True, use_container_width=True)
    st.caption('Las estadísticas se limitan a las fechas y partidos consultados. '
               'La disponibilidad depende del proveedor externo.')
