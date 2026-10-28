"""Resumen Inteligente NFL 1.9: vista compacta y descriptiva para móvil."""
import pandas as pd
import unicodedata
import re
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
    # El calendario puede publicarse con fechas UTC; no descartamos juegos pendientes
    # por comparación con el reloj del servidor. La última fecha jugada basta.
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



@st.cache_data(ttl=21600, show_spinner=False)
def _cargar_snaps_resumen(temporada):
    """Carga snaps NFLverse por temporada, sin modificar modulo_nfl.py."""
    import nflreadpy as nfl
    tabla = nfl.load_snap_counts(int(temporada))
    datos = tabla.to_pandas() if hasattr(tabla, 'to_pandas') else pd.DataFrame(tabla)
    datos.columns = [str(c).lower().strip() for c in datos.columns]
    necesarias = {'player', 'team', 'position', 'week', 'offense_pct'}
    faltan = necesarias - set(datos.columns)
    if faltan:
        raise ValueError('Columnas de snaps ausentes: ' + ', '.join(sorted(faltan)))
    datos['week'] = pd.to_numeric(datos['week'], errors='coerce')
    datos['offense_pct'] = pd.to_numeric(datos['offense_pct'], errors='coerce')
    if 'season' in datos.columns:
        datos = datos[pd.to_numeric(datos['season'], errors='coerce').eq(int(temporada))].copy()
    porcentajes = datos['offense_pct'].dropna()
    if not porcentajes.empty and porcentajes.quantile(.95) > 1.01:
        datos['offense_pct'] /= 100.0
    datos.loc[~datos['offense_pct'].between(0, 1), 'offense_pct'] = float('nan')
    datos = datos.dropna(subset=['week']).copy()
    for campo in ['player', 'team', 'position']:
        datos[campo] = datos[campo].fillna('').astype(str).str.strip()
    return datos


def _nombre_normalizado(nombre):
    nombre = unicodedata.normalize('NFKD', str(nombre))
    nombre = ''.join(c for c in nombre if not unicodedata.combining(c))
    nombre = re.sub(r'[^a-z0-9 ]', ' ', nombre.casefold())
    partes = [p for p in nombre.split() if p not in ('jr', 'sr', 'ii', 'iii', 'iv')]
    return ' '.join(partes)


def _participacion(d, snaps, error_snaps=None):
    """Cruce conservador por nombre completo, equipo y posición; nunca por yardas."""
    if snaps is None or snaps.empty:
        return '⚪ No disponible', 'Snaps no publicados o no accesibles para esta temporada.'
    nombre = _nombre_normalizado(d['Jugador'].iloc[-1])
    equipo = str(d['Equipo'].iloc[-1]).upper().strip()
    posicion = str(d['Posición'].iloc[-1]).upper().strip()
    if not nombre or not equipo or not posicion:
        return '⚪ No disponible', 'Identidad del jugador incompleta.'
    candidatos = snaps[
        snaps['team'].str.upper().eq(equipo) &
        snaps['position'].str.upper().eq(posicion)
    ].copy()
    if candidatos.empty:
        return '⚪ No disponible', 'Sin registros de snaps para este jugador y equipo.'
    candidatos['_nombre'] = candidatos['player'].map(_nombre_normalizado)
    candidatos = candidatos[candidatos['_nombre'].eq(nombre)]
    if candidatos.empty:
        return '⚪ No disponible', 'No se encontró coincidencia exacta de nombre, equipo y posición.'
    # Si la fuente expone IDs distintos bajo el mismo nombre, no mezclar jugadores.
    if 'pfr_player_id' in candidatos.columns and candidatos['pfr_player_id'].dropna().astype(str).nunique() > 1:
        return '⚪ No disponible', 'Coincidencia ambigua entre identificadores de jugador.'
    candidatos = candidatos.sort_values('week').drop_duplicates(['week', 'team'], keep='last')
    validos = candidatos.dropna(subset=['offense_pct']).tail(5)
    if validos.empty:
        return '⚪ No disponible', 'No hay porcentajes válidos de snaps ofensivos.'
    promedio = float(validos['offense_pct'].mean()) * 100
    nivel = '🟢 Alta' if promedio >= 65 else '🟡 Intermedia' if promedio >= 30 else '🔴 Baja'
    aviso = ' · muestra pequeña' if len(validos) < 3 else ''
    return f'{nivel} · {promedio:.1f}%', f'Snaps ofensivos: promedio de {len(validos)} partidos recientes{aviso}.'


def _partidos_con_datos(d, metricas):
    posicion = str(d['Posición'].iloc[-1]).upper()
    principal = {'QB': 'Yardas de pase', 'RB': 'Yardas terrestres',
                 'WR': 'Yardas recibidas', 'TE': 'Yardas recibidas'}.get(posicion)
    if not principal or principal not in metricas:
        return 0
    return int(pd.to_numeric(d[metricas[principal]], errors='coerce').notna().sum())

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
            st.caption('No se encontró un próximo partido pendiente en los datos del calendario.')

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
    # El catálogo sigue a los equipos del partido, no a toda la NFL.
    if not elegidos:
        st.info('Selecciona primero uno o dos equipos para consultar sus jugadores.')
        return semanal.iloc[0:0].copy(), metricas, []
    semanal = semanal[semanal['Equipo'].isin(elegidos)].copy()
    if semanal.empty:
        st.info('No hay jugadores registrados de los equipos seleccionados.')
        st.session_state['ri15_jugadores_guardados'] = []
        return semanal, metricas, []
    # Cargar snaps solo una vez por temporada, con caché; un fallo no detiene estadísticas.
    try:
        snaps = _cargar_snaps_resumen(temporada)
        error_snaps = None
    except Exception as exc:
        snaps = None
        error_snaps = f'{type(exc).__name__}: {exc}'
    if error_snaps:
        st.caption('⚪ Participación no disponible: fuente de snaps inaccesible. ' + error_snaps)
    # Conservar jugadores de distintas posiciones al cambiar el filtro.
    completo = (semanal[['ID', 'Jugador', 'Equipo', 'Posición']]
                .drop_duplicates('ID').sort_values(['Equipo', 'Posición', 'Jugador']))
    todos_ids = completo.ID.tolist()
    clave = 'ri15_jugadores_guardados'
    clave_temporada = 'ri15_temporada_guardada'
    if st.session_state.get(clave_temporada) != temporada:
        st.session_state[clave] = []
        st.session_state[clave_temporada] = temporada
    # Eliminar selecciones de equipos que ya no están en el enfrentamiento.
    guardados = [x for x in st.session_state.get(clave, []) if x in todos_ids]
    st.session_state[clave] = guardados
    st.caption('Jugadores disponibles: ' + ' vs. '.join(elegidos))

    pos = st.selectbox('Filtrar posición para agregar', ['Todas', 'QB', 'RB', 'WR', 'TE'],
                       key='ri15_posicion')
    buscar = st.text_input('Buscar por nombre para agregar', placeholder='Ejemplo: Henry',
                           key='ri15_buscar').strip().casefold()
    candidatos = completo[~completo.ID.isin(guardados)]
    if pos != 'Todas':
        candidatos = candidatos[candidatos['Posición'].str.upper().eq(pos)]
    if buscar:
        candidatos = candidatos[candidatos.Jugador.str.casefold().str.contains(
            buscar, regex=False, na=False)]
    opciones = candidatos.ID.tolist()
    if len(guardados) < 3 and opciones:
        nuevo = st.selectbox('Agregar jugador', [None] + opciones,
                             format_func=lambda x: 'Selecciona un jugador…' if x is None
                             else _etiqueta(completo, x), key='ri15_agregar')
        if nuevo is not None and st.button('➕ Agregar a la selección', key='ri15_boton'):
            st.session_state[clave] = guardados + [nuevo]
            st.rerun()
    elif len(guardados) >= 3:
        st.caption('Ya seleccionaste tres jugadores. Quita uno para agregar otro.')
    else:
        st.caption('No hay jugadores que coincidan con la búsqueda.')

    seleccionados = st.session_state[clave]
    if seleccionados:
        st.caption(f'Seleccionados: {len(seleccionados)} de 3')
        for ident in seleccionados:
            d = semanal[semanal.ID.eq(ident)].sort_values('Semana')
            if d.empty:
                continue
            # Nombre y botón en la misma fila; sin repetir encabezado en la ficha.
            nombre_col, quitar_col = st.columns([0.84, 0.16], vertical_alignment='center')
            with nombre_col:
                st.markdown(f'**{_etiqueta(completo, ident)}**')
            with quitar_col:
                if st.button('✕', key=f'ri16_quitar_{ident}', help='Quitar jugador'):
                    st.session_state[clave] = [x for x in seleccionados if x != ident]
                    st.rerun()
            _ficha(d, metricas, cal, temporada, snaps)
            st.divider()
    else:
        st.info('Agrega hasta tres jugadores para consultar sus estadísticas.')
    return semanal, metricas, seleccionados

def _etiqueta(catalogo, ident):
    r = catalogo[catalogo.ID.eq(ident)].iloc[0]
    return f'{r.Jugador} · {r.Equipo} · {r["Posición"]}'

def _metricas_posicion(d, metricas):
    posicion = str(d['Posición'].iloc[-1]).upper()
    return [x for x in POSICIONES.get(posicion, ['Yardas terrestres', 'Yardas recibidas', 'Recepciones', 'Yardas de pase']) if x in metricas]

def _ficha(d, metricas, cal, temporada, snaps):
    nivel, detalle = _participacion(d)
    st.caption(f'**Participación:** {nivel}')
    st.caption(detalle)
    n_partidos = _partidos_con_datos(d, metricas)
    st.caption(f'**Base estadística:** {n_partidos} partidos con estadística de yardas registrada.')
    ult = d.tail(5)
    filas = []
    for nombre in _metricas_posicion(d, metricas):
        col = metricas[nombre]
        valores_temporada = pd.to_numeric(d[col], errors='coerce')
        reciente = pd.to_numeric(ult[col], errors='coerce')
        if valores_temporada.notna().sum() == 0:
            continue
        filas.append({'Estadística': nombre, 'Total temporada': round(float(valores_temporada.sum()), 1),
                      'Promedio últimos 5': round(float(reciente.mean()), 1) if reciente.notna().any() else None})
    if filas:
        st.caption('**Temporada | Promedio últimos 5 partidos**')
        for fila in filas:
            promedio = fila['Promedio últimos 5']
            valor = f'{promedio:g}' if promedio is not None else 'N/D'
            st.markdown(f"**{fila['Estadística']}**: {fila['Total temporada']:g} · {valor}")

    equipo = str(d.Equipo.iloc[-1])
    proximo = _proximo_partido(cal, equipo, temporada)
    if proximo:
        st.caption(f"Próximo: vs. {proximo['rival']} · {proximo['sede']} · "
                   f"{proximo['fecha']:%d/%m/%Y}")
        metrica, estimado = _estimacion_yardas(d, metricas)
        if estimado is not None:
            st.metric(f'🎯 {metrica} estimadas · próximo partido', f'{estimado:.1f}')
            st.caption('Estimación orientativa basada en los registros disponibles.')
        else:
            st.caption('Estimación de yardas no disponible: faltan al menos tres partidos '
                       'registrados o una métrica compatible.')
    else:
        st.caption('No se encontró un próximo partido pendiente en los datos del calendario; verifica su actualización.')

def _comparar(semanal, metricas, seleccionados):
    if semanal is None or semanal.empty:
        st.info('No hay registros de jugadores disponibles.')
        return
    if not seleccionados or len(seleccionados) < 2:
        st.info('Selecciona dos o tres jugadores en la sección anterior para compararlos.')
        return
    catalogo = semanal[['ID', 'Jugador', 'Equipo', 'Posición']].drop_duplicates('ID')
    disponibles = set(catalogo.ID.tolist())
    seleccionados = [ident for ident in seleccionados if ident in disponibles]
    if len(seleccionados) < 2:
        st.info('No hay suficientes jugadores seleccionados con datos.')
        return
    muestras = [semanal[semanal.ID.eq(ident)].sort_values('Semana').tail(5)
                for ident in seleccionados]
    comunes = _metricas_posicion(muestras[0], metricas)
    for muestra in muestras[1:]:
        compatibles = _metricas_posicion(muestra, metricas)
        comunes = [m for m in comunes if m in compatibles]
    if not comunes:
        comunes = [m for m in ['Yardas terrestres', 'Yardas recibidas', 'Recepciones',
                               'Yardas de pase'] if m in metricas]
    if not comunes:
        st.info('No hay estadísticas comparables disponibles.')
        return
    metrica = st.selectbox('Estadística para comparar', comunes, key='ri14_metrica')
    columna = metricas[metrica]
    filas = []
    for muestra in muestras:
        promedio = pd.to_numeric(muestra[columna], errors='coerce').mean()
        filas.append({'Jugador': str(muestra.Jugador.iloc[-1]),
                      'Equipo': str(muestra.Equipo.iloc[-1]),
                      'Promedio últimos 5': round(float(promedio), 1) if pd.notna(promedio) else None})
    st.dataframe(pd.DataFrame(filas), hide_index=True, use_container_width=True)
    st.caption('Promedios de hasta cinco partidos registrados. Sin gráficas.')

def mostrar_resumen_inteligente_nfl():
    st.header('🏈 Resumen Inteligente NFL 1.9')
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
        st.info('Selecciona uno o dos equipos para analizar sus jugadores y estadísticas.')
    with st.expander('🏈 1. Resumen de equipos', expanded=True):
        if elegidos:
            _equipos(juegos, temporada, elegidos)
        else:
            st.info('Selecciona un equipo arriba.')
    with st.expander('⭐ 2. Jugadores', expanded=False):
        semanal, metricas, seleccionados = _jugadores(temporada, elegidos, juegos)
    with st.expander('🔎 3. Comparación de jugadores', expanded=False):
        _comparar(semanal, metricas, seleccionados)

