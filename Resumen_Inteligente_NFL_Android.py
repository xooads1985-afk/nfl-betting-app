"""Vista independiente de resumen NFL basada en funciones existentes de modulo_nfl."""
import pandas as pd
import streamlit as st
from modulo_nfl import (TEMPORADAS, cargar_calendario_rapido_v40,
                        cargar_jugadores_nfl_v39, _preparar_rendimiento_v49)


def _equipo_partidos(cal, equipo, temporada):
    d = cal[(cal['season'] == temporada) & ((cal['home_team'] == equipo) | (cal['away_team'] == equipo))].copy()
    d = d.dropna(subset=['home_score', 'away_score']).sort_values(['gameday', 'game_id'])
    d['PF'] = d['home_score'].where(d['home_team'] == equipo, d['away_score'])
    d['PC'] = d['away_score'].where(d['home_team'] == equipo, d['home_score'])
    d['Resultado'] = d.apply(lambda r: 'Victoria' if r.PF > r.PC else ('Derrota' if r.PF < r.PC else 'Empate'), axis=1)
    d['Rival'] = d['away_team'].where(d['home_team'] == equipo, d['home_team'])
    return d


def _mostrar_equipo(cal, equipo, temporada):
    d = _equipo_partidos(cal, equipo, temporada)
    st.markdown(f'#### {equipo}')
    if d.empty:
        st.info('Sin partidos finalizados para este equipo y temporada.')
        return
    ultimos = d.tail(5)
    a, b, c = st.columns(3)
    a.metric('Victorias', int((d['Resultado'] == 'Victoria').sum()))
    b.metric('Derrotas', int((d['Resultado'] == 'Derrota').sum()))
    c.metric('Empates', int((d['Resultado'] == 'Empate').sum()))
    a, b = st.columns(2)
    a.metric('Puntos a favor / partido', f"{d['PF'].mean():.1f}")
    b.metric('Puntos en contra / partido', f"{d['PC'].mean():.1f}")
    st.caption('Últimos cinco partidos finalizados (o los disponibles)')
    st.dataframe(ultimos[['gameday', 'Rival', 'PF', 'PC', 'Resultado']].iloc[::-1],
                 hide_index=True, use_container_width=True)
    st.line_chart(ultimos.set_index('gameday')[['PF', 'PC']])


def _mostrar_jugadores(temporada, equipos):
    st.subheader('⭐ Jugadores: temporada y últimos cinco partidos')
    st.caption('Los datos semanales publicados son la base del resumen. Una semana sin registro no se interpreta como cero.')
    try:
        bruto = cargar_jugadores_nfl_v39(temporada)
        semanal, metricas = _preparar_rendimiento_v49(bruto)
    except Exception as exc:
        st.warning(f'No se pudieron consultar las estadísticas semanales: {type(exc).__name__}: {exc}')
        return
    if semanal.empty:
        st.info('No hay estadísticas semanales disponibles.')
        return
    disponibles = semanal[semanal['Equipo'].isin(equipos)].copy()
    if disponibles.empty:
        st.info('La fuente no contiene jugadores asociados a los equipos seleccionados.')
        return
    ids = disponibles[['ID', 'Jugador', 'Equipo', 'Posición']].drop_duplicates('ID').sort_values(['Equipo', 'Jugador'])
    opciones = ids['ID'].tolist()
    seleccion = st.multiselect('Buscar y seleccionar jugadores (máximo 4)', opciones,
        format_func=lambda x: f"{ids.loc[ids.ID == x, 'Jugador'].iloc[0]} · {ids.loc[ids.ID == x, 'Equipo'].iloc[0]}",
        max_selections=4, key='resumen_nfl_jugadores')
    if not seleccion:
        st.info('Selecciona uno o varios jugadores para ver sus estadísticas.')
        return
    for ident in seleccion:
        d = disponibles[disponibles['ID'] == ident].sort_values('Semana')
        nombre = str(d['Jugador'].iloc[-1])
        with st.expander(f"{nombre} · {d['Equipo'].iloc[-1]}", expanded=True):
            ultimos = d.tail(5)
            filas = []
            for etiqueta, col in metricas.items():
                temporada_total = pd.to_numeric(d[col], errors='coerce').sum(min_count=1)
                recientes = pd.to_numeric(ultimos[col], errors='coerce')
                if pd.isna(temporada_total) and recientes.notna().sum() == 0:
                    continue
                filas.append({'Estadística': etiqueta,
                    'Total temporada': temporada_total,
                    'Promedio por juego': pd.to_numeric(d[col], errors='coerce').mean(),
                    'Promedio últimos 5': recientes.mean(),
                    'Juegos recientes con dato': int(recientes.notna().sum())})
            st.dataframe(pd.DataFrame(filas).round(2), hide_index=True, use_container_width=True)
            st.caption('Detalle de las últimas cinco semanas con registro')
            st.dataframe(ultimos[['Semana'] + list(dict.fromkeys(metricas.values()))].iloc[::-1],
                         hide_index=True, use_container_width=True)


def mostrar_resumen_inteligente_nfl():
    st.header('🏈 Resumen Inteligente NFL')
    st.caption('Vista descriptiva de equipos, partidos y jugadores · datos observados NFLverse')
    try:
        cal = cargar_calendario_rapido_v40()
    except Exception as exc:
        st.error(f'No se pudo cargar el calendario: {type(exc).__name__}: {exc}')
        return
    temporadas = sorted(set(pd.to_numeric(cal['season'], errors='coerce').dropna().astype(int)) & set(TEMPORADAS), reverse=True)
    if not temporadas:
        st.warning('No hay temporadas disponibles.')
        return
    temporada = st.selectbox('Temporada', temporadas, key='resumen_nfl_temporada')
    juegos = cal[cal['season'] == temporada].copy()
    equipos = sorted(set(juegos['home_team'].dropna()) | set(juegos['away_team'].dropna()))
    elegidos = st.multiselect('Escribe o selecciona uno o dos equipos', equipos, max_selections=2,
                              key='resumen_nfl_equipos')
    if not elegidos:
        st.info('Selecciona un equipo o dos para consultar su resumen.')
        return
    for equipo in elegidos:
        _mostrar_equipo(juegos, equipo, temporada)
    if len(elegidos) == 2:
        st.subheader('🏟️ Enfrentamientos entre ambos equipos')
        a, b = elegidos
        duelos = juegos[((juegos.home_team == a) & (juegos.away_team == b)) |
                       ((juegos.home_team == b) & (juegos.away_team == a))].sort_values('gameday', ascending=False)
        if duelos.empty:
            st.info('No hay enfrentamientos registrados entre estos equipos esta temporada.')
        else:
            labels = [f"Semana {int(r.week)} · {pd.Timestamp(r.gameday).date()} · {r.away_team} @ {r.home_team}" for r in duelos.itertuples()]
            indice = st.selectbox('Selecciona el partido', range(len(labels)), format_func=lambda i: labels[i],
                                  key='resumen_nfl_partido')
            partido = duelos.iloc[indice]
            if pd.notna(partido.home_score) and pd.notna(partido.away_score):
                st.metric('Marcador registrado', f"{partido.away_team} {int(partido.away_score)} – {int(partido.home_score)} {partido.home_team}")
            else:
                st.info('Partido programado: aún no hay marcador disponible.')
    _mostrar_jugadores(temporada, elegidos)
