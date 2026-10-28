"""Panel independiente de participación ofensiva NFL (estadísticas descriptivas)."""
import pandas as pd
import streamlit as st


@st.cache_data(ttl=21600, show_spinner=False)
def cargar_snaps(temporada: int) -> pd.DataFrame:
    import nflreadpy as nfl
    df = nfl.load_snap_counts(temporada).to_pandas()
    requeridas = {'season', 'week', 'player', 'pfr_player_id', 'position', 'team', 'offense_snaps', 'offense_pct'}
    faltan = requeridas - set(df.columns)
    if faltan:
        raise ValueError('La fuente no contiene: ' + ', '.join(sorted(faltan)))
    df = df.copy()
    for col in ('week', 'offense_snaps', 'offense_pct'):
        df[col] = pd.to_numeric(df[col], errors='coerce')
    # La fuente expresa offense_pct habitualmente como fracción (0..1),
    # pero detectamos escala 0..100 si la distribución lo requiere.
    pct = df['offense_pct'].dropna()
    if not pct.empty and pct.quantile(.95) > 1.01:
        df['offense_pct'] = df['offense_pct'] / 100.0
    df.loc[~df['offense_pct'].between(0, 1), 'offense_pct'] = float('nan')
    df['player'] = df['player'].fillna('Sin nombre').astype(str)
    df['team'] = df['team'].fillna('SIN').astype(str)
    df['position'] = df['position'].fillna('—').astype(str)
    df['pfr_player_id'] = df['pfr_player_id'].fillna('').astype(str)
    df = df[df['pfr_player_id'].ne('')].copy()
    return df


def nivel_participacion(porcentaje, partidos):
    if pd.isna(porcentaje) or partidos == 0:
        return '⚪ Sin datos suficientes'
    if porcentaje >= .65:
        return '🟢 Alta'
    if porcentaje >= .30:
        return '🟡 Intermedia'
    return '🔴 Baja'


def mostrar_participacion_nfl():
    st.subheader('🏈 Participación ofensiva NFL')
    st.caption('Datos reales de snaps por partido. Los niveles son descriptivos; no confirman titularidad.')
    temporada = st.selectbox('Temporada', [2026, 2025, 2024, 2023, 2022], key='pnfl_temporada')
    try:
        datos = cargar_snaps(temporada)
    except Exception as exc:
        st.warning('No fue posible cargar los snaps. Revisa la conexión y la versión de nflreadpy.')
        st.caption(f'Detalle técnico: {type(exc).__name__}: {exc}')
        return
    if datos.empty:
        st.info('La fuente todavía no publicó registros para esta temporada.')
        return
    equipos = sorted(datos['team'].unique())
    equipo = st.selectbox('Equipo', equipos, key='pnfl_equipo')
    subset = datos[datos['team'].eq(equipo)].copy()
    jugadores = (subset[['pfr_player_id', 'player', 'position']]
                .drop_duplicates('pfr_player_id').sort_values('player'))
    opciones = dict(zip(jugadores['pfr_player_id'],
                       jugadores['player'] + ' · ' + jugadores['position']))
    ids = st.multiselect('Jugadores (hasta 3)', list(opciones),
                         format_func=lambda i: opciones[i], max_selections=3,
                         key='pnfl_jugadores')
    if not ids:
        st.info('Selecciona uno, dos o tres jugadores para ver su participación.')
        return
    for pid in ids:
        filas = subset[subset['pfr_player_id'].eq(pid)].copy()
        filas = filas.drop_duplicates(['season', 'week', 'team'], keep='last')
        filas = filas.sort_values('week')
        nombre = opciones[pid]
        validas = filas[filas['offense_pct'].notna()]
        promedio = validas['offense_pct'].mean() if not validas.empty else float('nan')
        with st.container(border=True):
            st.markdown(f'**{nombre} · {equipo}**')
            st.write('Participación:', nivel_participacion(promedio, len(validas)))
            st.write('Snaps ofensivos promedio:',
                     f'{promedio * 100:.1f} %' if pd.notna(promedio) else 'No disponible')
            st.write('Partidos con porcentaje registrado:', len(validas))
            st.write('Snaps ofensivos acumulados:',
                     f"{int(filas['offense_snaps'].sum()):,}" if filas['offense_snaps'].notna().any() else 'No disponible')
            if len(validas) < 3:
                st.caption('Muestra pequeña: el nivel puede cambiar con más partidos.')
            st.caption('El porcentaje es la proporción de jugadas ofensivas del equipo en las que participó.')
            detalle = filas[['week', 'offense_snaps', 'offense_pct']].copy()
            detalle.columns = ['Semana', 'Snaps ofensivos', 'Participación (%)']
            detalle['Participación (%)'] = (detalle['Participación (%)'] * 100).round(1)
            with st.expander('Ver semanas registradas'):
                st.dataframe(detalle, hide_index=True, use_container_width=True)
    st.caption('Fuente: nflreadpy / Pro Football Reference. La publicación puede tener retrasos.')


if __name__ == '__main__':
    mostrar_participacion_nfl()
