"""Resumen Inteligente NFL 1.2: vista compacta y descriptiva para móvil."""
from datetime import date
import pandas as pd
import streamlit as st
from modulo_nfl import TEMPORADAS, cargar_calendario_rapido_v40, cargar_jugadores_nfl_v39, _preparar_rendimiento_v49

POSICIONES = {
    'QB': ['Yardas de pase', 'TD de pase', 'Pases completos', 'Intentos de pase', 'Intercepciones lanzadas', 'Yardas terrestres'],
    'RB': ['Yardas terrestres', 'Acarreos', 'TD terrestres', 'Recepciones', 'Yardas recibidas', 'TD recibidos'],
    'WR': ['Yardas recibidas', 'Recepciones', 'Objetivos de pase', 'TD recibidos', 'Yardas terrestres'],
    'TE': ['Yardas recibidas', 'Recepciones', 'Objetivos de pase', 'TD recibidos'],
}

def _partidos(cal, equipo, temporada):
    d = cal[(cal.season.eq(temporada)) & (cal.home_team.eq(equipo) | cal.away_team.eq(equipo))].copy()
    d = d.dropna(subset=['home_score', 'away_score']).sort_values(['gameday', 'game_id'])
    d['PF'] = d.home_score.where(d.home_team.eq(equipo), d.away_score)
    d['PC'] = d.away_score.where(d.home_team.eq(equipo), d.home_score)
    d['Rival'] = d.away_team.where(d.home_team.eq(equipo), d.home_team)
    d['Resultado'] = ['V' if x > y else 'D' if x < y else 'E' for x, y in zip(d.PF, d.PC)]
    return d


def _proximo_partido(cal, equipo, temporada):
    """Busca el siguiente encuentro sin resultado, posterior al último disputado."""
    d = cal[(cal.season.eq(temporada)) &
            (cal.home_team.eq(equipo) | cal.away_team.eq(equipo))].copy()
    if d.empty:
        return None
    d['gameday'] = pd.to_datetime(d.gameday, errors='coerce')
    d = d.dropna(subset=['gameday']).sort_values('gameday')
    terminados = d.dropna(subset=['home_score', 'away_score'])
    pendientes = d[d.home_score.isna() | d.away_score.isna()]
    if not terminados.empty:
        pendientes = pendientes[pendientes.gameday > terminados.gameday.max()]
    if int(temporada) >= date.today().year:
        pendientes = pendientes[pendientes.gameday.dt.date >= date.today()]
    if pendientes.empty:
        return None
    juego = pendientes.iloc[0]
    rival = juego.away_team if juego.home_team == equipo else juego.home_team
    sede = 'Local' if juego.home_team == equipo else 'Visitante'
    return {'rival': rival, 'sede': sede, 'fecha': juego.gameday,
            'semana': juego['week']}


def _estimacion_puntos(cal, equipo, temporada, rival):
    propios = _partidos(cal, equipo, temporada)
    contrarios = _partidos(cal, rival, temporada)
    if len(propios) < 3 or len(contrarios) < 3:
        return None
    # Media de anotación reciente, de temporada y puntos permitidos por el rival.
    estimado = (0.50 * propios.PF.tail(5).mean() +
                0.25 * propios.PF.mean() +
                0.25 * contrarios.PC.tail(5).mean())
    return max(0.0, float(estimado))


def _estimacion_yardas(d, metricas):
    posicion = str(d['Posición'].iloc[-1]).upper()
    principal = {'QB': 'Yardas de pase', 'RB': 'Yardas terrestres',
                 'WR': 'Yardas recibidas', 'TE': 'Yardas recibidas'}.get(posicion)
    if not principal or principal not in metricas:
        return None, None
    serie = pd.to_numeric(d.sort_values('Semana')[metricas[principal]], errors='coerce').dropna()
    if len(serie) < 3:
        return principal, None
    estimado = 0.70 * serie.tail(5).mean() + 0.30 * serie.mean()
    return principal, max(0.0, float(estimado))

def _equipos(cal, temporada, elegidos):
    for equipo in elegidos:
        d = _partidos(cal, equipo, temporada)
        st.markdown(f'**{equipo}**')
        if d.empty:
            st.info('Sin resultados finalizados disponibles.')
            continue
        v, p, u = st.columns(3)
        v.metric('Récord V-D-E', f"{sum(d.Resultado.eq('V'))}-{sum(d.Resultado.eq('D'))}-{sum(d.Resultado.eq('E'))}")
        p.metric('Puntos a favor', f'{d.PF.mean():.1f}')
        u.metric('Puntos en contra', f'{d.PC.mean():.1f}')
        ult = d.tail(5)
        st.caption('Últimos 5: ' + ' · '.join(f"{r.Resultado} {r.Rival} {int(r.PF)}-{int(r.PC)}" for r in ult.itertuples()))
        proximo = _proximo_partido(cal, equipo, temporada)
        if proximo:
            st.caption(f"Próximo: vs. {proximo['rival']} · {proximo['sede']} · "
                       f"{proximo['fecha']:%d/%m/%Y} · Semana {int(proximo['semana'])}")
            estimado = _estimacion_puntos(cal, equipo, temporada, proximo['rival'])
            if estimado is not None:
                st.metric('🎯 Puntos estimados · próximo partido', f'{estimado:.1f}')
                st.caption('Estimación orientativa: anotación reciente y de temporada, '
                           'más puntos permitidos recientemente por el rival.')
            else:
                st.caption('Estimación no disponible: faltan partidos registrados del equipo o rival.')
        else:
            st.caption('No hay próximo partido confirmado en el calendario disponible.')

def _jugadores(temporada, elegidos, cal):
    try:
        bruto = cargar_jugadores_nfl_v39(temporada)
        semanal, metricas = _preparar_rendimiento_v49(bruto)
    except Exception as exc:
        st.error(f'No se pudieron cargar los jugadores: {type(exc).__name__}: {exc}')
        return None, None, None
    if semanal.empty:
        st.info('Sin registros semanales disponibles.')
        return None, None, None
    semanal = semanal[semanal.Equipo.isin(elegidos)].copy()
    if semanal.empty:
        st.info('Sin jugadores disponibles para estos equipos.')
        return None, None, None
    pos = st.selectbox('Posición', ['Todas', 'QB', 'RB', 'WR', 'TE'], key='ri11_posicion')
    buscar = st.text_input('Buscar por nombre', placeholder='Ejemplo: Henry', key='ri11_buscar').strip().casefold()
    catalogo = semanal[['ID', 'Jugador', 'Equipo', 'Posición']].drop_duplicates('ID')
    if pos != 'Todas':
        catalogo = catalogo[catalogo['Posición'].str.upper().eq(pos)]
    if buscar:
        catalogo = catalogo[catalogo.Jugador.str.casefold().str.contains(buscar, regex=False, na=False)]
    catalogo = catalogo.sort_values(['Equipo', 'Posición', 'Jugador'])
    if catalogo.empty:
        st.info('No hay jugadores que coincidan con los filtros.')
        return semanal, metricas, None
    ids = catalogo.ID.tolist()
    seleccionado = st.selectbox('Jugador', ids, format_func=lambda x: _etiqueta(catalogo, x), key='ri11_jugador')
    d = semanal[semanal.ID.eq(seleccionado)].sort_values('Semana')
    _ficha(d, metricas, cal, temporada)
    return semanal, metricas, seleccionado

def _etiqueta(catalogo, ident):
    r = catalogo[catalogo.ID.eq(ident)].iloc[0]
    return f'{r.Jugador} · {r.Equipo} · {r["Posición"]}'

def _metricas_posicion(d, metricas):
    posicion = str(d['Posición'].iloc[-1]).upper()
    return [x for x in POSICIONES.get(posicion, ['Yardas terrestres', 'Yardas recibidas', 'Recepciones', 'Yardas de pase']) if x in metricas]

def _ficha(d, metricas, cal, temporada):
    st.markdown(f'**{d.Jugador.iloc[-1]} · {d.Equipo.iloc[-1]} · {d["Posición"].iloc[-1]}**')
    ult = d.tail(5)
    filas = []
    for nombre in _metricas_posicion(d, metricas):
        col = metricas[nombre]
        temporada = pd.to_numeric(d[col], errors='coerce')
        reciente = pd.to_numeric(ult[col], errors='coerce')
        if temporada.notna().sum() == 0:
            continue
        filas.append({'Estadística': nombre, 'Total temporada': round(float(temporada.sum()), 1),
                      'Promedio últimos 5': round(float(reciente.mean()), 1) if reciente.notna().any() else None})
    if filas:
        st.dataframe(pd.DataFrame(filas), hide_index=True, use_container_width=True)
    st.caption('Promedios de hasta cinco partidos con registro; no se inventan partidos ausentes.')
    equipo = str(d.Equipo.iloc[-1])
    proximo = _proximo_partido(cal, equipo, temporada)
    if proximo:
        st.caption(f"Próximo: vs. {proximo['rival']} · {proximo['sede']} · "
                   f"{proximo['fecha']:%d/%m/%Y}")
        metrica, estimado = _estimacion_yardas(d, metricas)
        if estimado is not None:
            st.metric(f'🎯 {metrica} estimadas · próximo partido', f'{estimado:.1f}')
            st.caption('Estimación orientativa: 70 % promedio últimos cinco partidos '
                       'y 30 % promedio de temporada. No incorpora lesiones ni disponibilidad.')
        else:
            st.caption('Estimación de yardas no disponible: faltan al menos tres partidos '
                       'registrados o una métrica compatible.')
    else:
        st.caption('No hay próximo partido confirmado para proyectar yardas.')

def _comparar(semanal, metricas, primero):
    if semanal is None or semanal.empty:
        st.info('Primero consulta los jugadores.')
        return
    catalogo = semanal[['ID', 'Jugador', 'Equipo', 'Posición']].drop_duplicates('ID').sort_values(['Equipo', 'Posición', 'Jugador'])
    ids = catalogo.ID.tolist()
    if len(ids) < 2:
        st.info('Se necesitan dos jugadores disponibles.')
        return
    a = st.selectbox('Jugador A', ids, index=ids.index(primero) if primero in ids else 0,
                     format_func=lambda x: _etiqueta(catalogo, x), key='ri11_a')
    b_ids = [x for x in ids if x != a]
    b = st.selectbox('Jugador B', b_ids, format_func=lambda x: _etiqueta(catalogo, x), key='ri11_b')
    da = semanal[semanal.ID.eq(a)].sort_values('Semana').tail(5)
    db = semanal[semanal.ID.eq(b)].sort_values('Semana').tail(5)
    comunes = [m for m in _metricas_posicion(da, metricas) if m in _metricas_posicion(db, metricas)]
    if not comunes:
        st.info('Los jugadores tienen posiciones sin métricas comparables. Selecciona otros jugadores.')
        return
    metrica = st.selectbox('Estadística', comunes, key='ri11_metrica')
    col = metricas[metrica]
    a_media = pd.to_numeric(da[col], errors='coerce').mean()
    b_media = pd.to_numeric(db[col], errors='coerce').mean()
    c1, c2 = st.columns(2)
    c1.metric(str(da.Jugador.iloc[-1]), f'{a_media:.1f}' if pd.notna(a_media) else 'N/D')
    c2.metric(str(db.Jugador.iloc[-1]), f'{b_media:.1f}' if pd.notna(b_media) else 'N/D')
    st.caption('Promedios de hasta cinco partidos registrados por jugador. Sin gráficas.')

def mostrar_resumen_inteligente_nfl():
    st.header('🏈 Resumen Inteligente NFL 1.2')
    st.caption('Datos observados y estimaciones orientativas para el próximo partido.')
    try:
        cal = cargar_calendario_rapido_v40()
    except Exception as exc:
        st.error(f'No se pudo cargar el calendario: {type(exc).__name__}: {exc}')
        return
    temporadas = sorted(set(pd.to_numeric(cal.season, errors='coerce').dropna().astype(int)) & set(TEMPORADAS), reverse=True)
    if not temporadas:
        st.info('Sin temporadas disponibles.')
        return
    temporada = st.selectbox('Temporada', temporadas, key='ri11_temporada')
    juegos = cal[cal.season.eq(temporada)]
    equipos = sorted(set(juegos.home_team.dropna()) | set(juegos.away_team.dropna()))
    elegidos = st.multiselect('Equipos (máximo 2)', equipos, max_selections=2, key='ri11_equipos')
    if not elegidos:
        st.info('Selecciona uno o dos equipos para empezar.')
        return
    with st.expander('🏈 1. Resumen de equipos', expanded=True):
        _equipos(juegos, temporada, elegidos)
    with st.expander('⭐ 2. Jugadores', expanded=False):
        semanal, metricas, seleccionado = _jugadores(temporada, elegidos, juegos)
    # Carga independiente para que la comparación funcione aun con la sección de jugadores cerrada.
    with st.expander('🔎 3. Comparación de jugadores', expanded=False):
        try:
            bruto = cargar_jugadores_nfl_v39(temporada)
            semanal, metricas = _preparar_rendimiento_v49(bruto)
            semanal = semanal[semanal.Equipo.isin(elegidos)] if not semanal.empty else semanal
            _comparar(semanal, metricas, st.session_state.get('ri11_jugador'))
        except Exception as exc:
            st.error(f'No se pudo preparar la comparación: {type(exc).__name__}: {exc}')
