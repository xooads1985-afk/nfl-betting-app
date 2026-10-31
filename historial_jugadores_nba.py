"""Historial NBA por equipo y jugador. Fuente ESPN no oficial; sin datos simulados.

Instalación: junto a modulo_nba.py. Vista: mostrar_historial_jugadores_nba().
No modifica NFL ni los demás componentes NBA.
"""
from datetime import date, timedelta
import pandas as pd
import altair as alt
import streamlit as st
from nba_archivo_temporada import guardar_jugadores, leer_jugadores, registrar_consulta, leer_consultas, resumen_archivo
from modulo_nba import cargar_partidos, cargar_detalle, extraer_jugadores
from nba_control_cobertura import comparar_bloque

VERSION = '1.3.6 · Supabase · control de calidad'
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




def _clasificar_calidad(datos):
    """Clasifica sin modificar las estadísticas originales ni inferir ausencias."""
    salida = datos.copy()
    for metrica in METRICAS:
        if metrica not in salida.columns:
            salida[metrica] = float('nan')
        salida[metrica] = salida[metrica].map(_numero)
    minutos = salida['Minutos']
    hay_estadisticas = salida[[m for m in METRICAS if m != 'Minutos']].notna().any(axis=1)
    salida['estado_calidad'] = 'Pendiente: sin minutos ni estadísticas'
    salida.loc[minutos.eq(0), 'estado_calidad'] = 'Revisar: cero minutos'
    salida.loc[minutos.isna() & hay_estadisticas, 'estado_calidad'] = 'Revisar: estadísticas sin minutos'
    salida.loc[minutos.gt(0), 'estado_calidad'] = 'Participación confirmada'
    return salida


def _ids_desde_detalle(detalle):
    """Extrae IDs reales de ESPN sin alterar modulo_nba.extraer_jugadores."""
    ids = {}
    for bloque_equipo in detalle.get('boxscore', {}).get('players', []):
        equipo = bloque_equipo.get('team', {}).get('displayName', '')
        for bloque in bloque_equipo.get('statistics', []):
            for fila in bloque.get('athletes', []):
                if not isinstance(fila, dict):
                    continue
                atleta = fila.get('athlete') or {}
                nombre = str(atleta.get('displayName') or '').strip()
                identificador = atleta.get('id')
                if equipo and nombre and identificador is not None and str(identificador).strip():
                    ids[(equipo, nombre)] = str(identificador).strip()
    return ids


def _extraer_partido(id_partido, fecha, equipo):
    detalle = cargar_detalle(str(id_partido))
    box = extraer_jugadores(detalle)
    ids_reales = _ids_desde_detalle(detalle)
    if box.empty or 'jugador' not in box.columns or 'equipo' not in box.columns:
        return []
    if equipo != 'Todos':
        box = box.loc[box['equipo'].eq(equipo)]
    filas = []
    for _, atleta in box.iterrows():
        nombre = str(atleta.get('jugador', '')).strip()
        if not nombre or nombre == 'Desconocido':
            continue
        # El identificador se conserva cuando la fuente lo entrega; nunca se inventa.
        id_atleta = next((atleta.get(c) for c in ('jugador_id', 'athlete_id', 'player_id', 'id_jugador', 'id')
                          if c in box.columns and pd.notna(atleta.get(c)) and str(atleta.get(c)).strip()), None)
        id_atleta = str(id_atleta).strip() if id_atleta is not None else ''
        if not id_atleta:
            id_atleta = ids_reales.get((str(atleta.get('equipo', equipo)), nombre), '')
        fila = {'partido_id': str(id_partido), 'fecha': fecha, 'equipo': str(atleta.get('equipo', equipo)),
                'jugador': nombre, 'titular': bool(atleta.get('titular', False)),
                'jugador_id': id_atleta}
        for nombre_metrica, nombres_fuente in METRICAS.items():
            col = next((x for x in nombres_fuente if x in box.columns), None)
            fila[nombre_metrica] = _numero(atleta.get(col)) if col else float('nan')
        filas.append(fila)
    return filas


def _consultar_bloque(desde, hasta, equipo):
    """Consulta una sola vez cada boxscore, de un equipo o de todos."""
    partidos, errores = cargar_partidos(desde.isoformat(), hasta.isoformat())
    if partidos.empty:
        return pd.DataFrame(), list(errores), 0
    filtro = partidos['finalizado'].eq(True)
    if equipo != 'Todos':
        filtro = filtro & (partidos['local'].eq(equipo) | partidos['visitante'].eq(equipo))
    juegos = partidos.loc[filtro].drop_duplicates('id').sort_values('fecha_utc')
    filas = []
    errores = list(errores)
    for juego in juegos.itertuples(index=False):
        try:
            extraidas = _extraer_partido(juego.id, str(juego.fecha_utc)[:10], equipo)
            if not extraidas:
                errores.append(f'{juego.id}: sin estadísticas individuales disponibles')
            filas.extend(extraidas)
        except Exception as exc:
            errores.append(f'{juego.id}: {type(exc).__name__}: {exc}')
    return pd.DataFrame(filas), errores, len(juegos)


def _unir_historial(actual, nuevo):
    if nuevo.empty:
        return actual.copy()
    junto = pd.concat([actual, nuevo], ignore_index=True) if not actual.empty else nuevo.copy()
    if 'jugador_id' not in junto:
        junto['jugador_id'] = ''
    junto['jugador_id'] = junto['jugador_id'].fillna('').astype(str)
    # Cuando no hay ID real, el nombre es la única clave disponible.
    junto['_identidad'] = junto.apply(lambda r: 'id:' + r['jugador_id'] if r['jugador_id'] else 'nombre:' + str(r['jugador']), axis=1)
    junto = junto.drop_duplicates(['partido_id', 'equipo', '_identidad'], keep='last')
    return junto.drop(columns=['_identidad']).reset_index(drop=True)


def obtener_historial_compartido(equipo=None, desde=None, hasta=None):
    """Devuelve una COPIA de los boxscores ya cargados en la vista Historial.

    Nunca consulta automáticamente la red ni mezcla equipos/períodos distintos.
    Devuelve (datos, cobertura), donde cobertura contiene el progreso real.
    """
    # El archivo persistente puede reutilizar registros de otras sesiones; no afirma cobertura total.
    try:
        archivados = leer_jugadores(equipo, desde, hasta)
    except Exception:
        archivados = pd.DataFrame()
    firma = st.session_state.get('hist_nba_firma')
    vacio = pd.DataFrame()
    if not firma or len(firma) != 3:
        return archivados, {'disponible': not archivados.empty, 'completo': False, 'origen': 'archivo persistente parcial'}
    ini, fin, nombre_equipo = firma
    if equipo not in (None, 'Todos', nombre_equipo) and nombre_equipo != 'Todos':
        return vacio, {'disponible': False, 'motivo': 'El historial cargado corresponde a otro equipo.'}
    if equipo == 'Todos' and nombre_equipo != 'Todos':
        return vacio, {'disponible': False, 'motivo': 'Solo se cargó un equipo; no se dispone de todos.'}
    if desde is not None and ini > str(desde):
        return vacio, {'disponible': False, 'motivo': 'El historial no cubre el inicio solicitado.'}
    if hasta is not None and fin < str(hasta):
        return vacio, {'disponible': False, 'motivo': 'El historial no cubre el final solicitado.'}
    datos = st.session_state.get('hist_nba_datos', vacio)
    if not isinstance(datos, pd.DataFrame):
        datos = vacio
    datos = _unir_historial(archivados, datos)
    if not datos.empty and equipo not in (None, 'Todos'):
        datos = datos.loc[datos['equipo'].eq(equipo)].copy()
    if not datos.empty and desde is not None:
        datos = datos.loc[datos['fecha'].astype(str).ge(str(desde))]
    if not datos.empty and hasta is not None:
        datos = datos.loc[datos['fecha'].astype(str).le(str(hasta))]
    return datos, {
        'disponible': not datos.empty, 'equipo': equipo if equipo not in (None, 'Todos') else nombre_equipo, 'desde': ini, 'hasta': fin,
        'bloques': int(st.session_state.get('hist_nba_bloques', 0)),
        'siguiente': st.session_state.get('hist_nba_siguiente'),
        'errores': len(st.session_state.get('hist_nba_errores', [])),
        'completo': False,  # No inferir cobertura completa a partir de bloques recorridos.
        'pendientes': len(st.session_state.get('hist_nba_pendientes', {})),
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
    equipo = st.selectbox('Equipos a consultar', ['Todos'] + equipos, key='hist_nba_equipo')
    st.caption('Elige «Todos» para comparar hasta 3 jugadores de distintos equipos. Cada partido se consulta una sola vez. Para periodos largos, carga los bloques progresivamente.')
    firma = (desde.isoformat(), hasta.isoformat(), equipo)
    claves_sesion = ('hist_nba_datos', 'hist_nba_siguiente', 'hist_nba_errores',
                     'hist_nba_juegos', 'hist_nba_bloques', 'hist_nba_pendientes',
                     'hist_nba_correctos')
    if (st.session_state.get('hist_nba_firma') != firma
            or any(clave not in st.session_state for clave in claves_sesion)):
        st.session_state['hist_nba_firma'] = firma
        try:
            st.session_state['hist_nba_datos'] = leer_jugadores(equipo, desde, hasta)
        except Exception:
            st.session_state['hist_nba_datos'] = pd.DataFrame()
        st.session_state['hist_nba_siguiente'] = desde
        st.session_state['hist_nba_errores'] = []
        st.session_state['hist_nba_juegos'] = 0
        st.session_state['hist_nba_bloques'] = 0
        st.session_state['hist_nba_pendientes'] = {}
        st.session_state['hist_nba_correctos'] = 0
    siguiente = st.session_state['hist_nba_siguiente']
    if siguiente <= hasta:
        cierre = min(siguiente + timedelta(days=30), hasta)
        st.caption(f'Próximo bloque: {siguiente:%d/%m/%Y} a {cierre:%d/%m/%Y}')
        if st.button('📥 Cargar siguiente bloque', key='hist_nba_cargar', use_container_width=True):
            with st.spinner('Consultando partidos finalizados y boxscores sin repetir encuentros...'):
                try:
                    nuevos, fallas, cantidad = _consultar_bloque(siguiente, cierre, equipo)
                except Exception as exc:
                    st.error(f'No se pudo cargar el bloque: {type(exc).__name__}: {exc}')
                else:
                    # Persistir primero; si falla, conservar datos en sesión pero avisar.
                    guardado_ok = True
                    try:
                        guardar_jugadores(nuevos)
                    except Exception as exc:
                        guardado_ok = False
                        fallas.append(f'Supabase: {type(exc).__name__}: {exc}')
                        st.warning(f'No se pudo guardar en Supabase: {type(exc).__name__}: {exc}')
                    st.session_state['hist_nba_datos'] = _unir_historial(st.session_state['hist_nba_datos'], nuevos)
                    try:
                        registrar_consulta(siguiente.isoformat(), cierre.isoformat(), equipo,
                                          cantidad, len(nuevos), fallas,
                                          'sin_incidencias_reportadas' if not fallas and guardado_ok else 'parcial')
                    except Exception as exc:
                        st.warning(f'No se pudo registrar la auditoría de consulta: {exc}')
                    st.session_state['hist_nba_errores'].extend(fallas)
                    # Registrar IDs con incidencia para permitir reintento puntual.
                    for fallo in fallas:
                        clave = str(fallo).split(':', 1)[0].strip()
                        if clave.isdigit():
                            st.session_state['hist_nba_pendientes'][clave] = (siguiente.isoformat(), equipo)
                    st.session_state['hist_nba_correctos'] += max(0, cantidad - sum(
                        1 for f in fallas if str(f).split(':', 1)[0].strip().isdigit()))
                    st.session_state['hist_nba_juegos'] += cantidad
                    st.session_state['hist_nba_bloques'] += 1
                    st.session_state['hist_nba_siguiente'] = cierre + timedelta(days=1)
                    st.rerun()
    else:
        st.info('Se recorrieron los bloques de esta sesión. La cobertura total NO está verificada; revisa la auditoría y los datos archivados.')
    pendientes = st.session_state.get('hist_nba_pendientes', {})
    if pendientes:
        st.warning(f'{len(pendientes)} partidos con incidencia identificada. Puedes reintentarlos sin repetir todos los bloques.')
        if st.button('🔄 Reintentar partidos pendientes', key='hist_nba_reintentar', use_container_width=True):
            recuperados = []
            for partido_id, (_, equipo_p) in list(pendientes.items()):
                try:
                    # Recuperar fecha real del calendario del bloque antes del boxscore.
                    fecha_ini = date.fromisoformat(pendientes[partido_id][0])
                    fecha_fin = min(fecha_ini + timedelta(days=30), hasta)
                    calendario, _ = cargar_partidos(fecha_ini.isoformat(), fecha_fin.isoformat())
                    coincidencias = calendario.loc[calendario['id'].astype(str).eq(partido_id)] if not calendario.empty else pd.DataFrame()
                    if coincidencias.empty:
                        continue
                    fecha_real = str(coincidencias.iloc[0]['fecha_utc'])[:10]
                    filas = _extraer_partido(partido_id, fecha_real, equipo_p)
                    if filas:
                        recuperados.extend(filas)
                        del pendientes[partido_id]
                except Exception:
                    pass
            if recuperados:
                st.session_state['hist_nba_datos'] = _unir_historial(st.session_state['hist_nba_datos'], pd.DataFrame(recuperados))
                try:
                    guardar_jugadores(pd.DataFrame(recuperados))
                except Exception as exc:
                    st.warning(f'No se pudo guardar la recuperación: {type(exc).__name__}: {exc}')
                st.session_state['hist_nba_correctos'] += len(set(f['partido_id'] for f in recuperados))
            st.rerun()
    datos = st.session_state['hist_nba_datos']
    errores = st.session_state['hist_nba_errores']
    st.caption('Historial persistente en Supabase. La existencia de registros no demuestra cobertura completa; revisa incidencias y auditoría.')
    st.caption('Los contadores de sesión se reinician al recargar; los del archivo reflejan los registros persistidos.')
    st.metric('Bloques consultados en esta sesión', st.session_state['hist_nba_bloques'])
    st.metric('Partidos consultados en esta sesión', st.session_state['hist_nba_juegos'])
    try:
        almacen = resumen_archivo(equipo, desde, hasta)
        st.metric('Partidos con jugadores guardados en Supabase', almacen['partidos_con_jugadores'])
        st.metric('Registros individuales guardados en Supabase', almacen['registros'])
        consultas = leer_consultas(desde, hasta, equipo)
        if not consultas.empty:
            with st.expander('🧪 Auditoría de bloques archivados'):
                st.dataframe(consultas.drop(columns=['incidencias']), hide_index=True, use_container_width=True)
                st.caption('Sin incidencias reportadas NO equivale a cobertura completa verificada.')
    except Exception as exc:
        st.warning(f'No se pudo consultar el estado del archivo Supabase: {exc}')
    # Auditoría del bloque inicial que se ha consultado para poblar el selector.
    # No extrapolar esta cobertura a fechas fuera de ese bloque.
    with st.expander('🔎 Cobertura y recuperación incremental (primer bloque)'):
        try:
            presentes, faltantes, total_finalizados = comparar_bloque(
                inicial, equipo, bloque_inicio.isoformat(), bloque_fin.isoformat())
            st.metric('Finalizados detectados en calendario del bloque', total_finalizados)
            st.metric('Con jugadores archivados', len(presentes))
            st.metric('Sin jugadores archivados', len(faltantes))
            st.caption('Comparación solo del primer bloque de hasta 31 días. '
                       'No confirma cobertura de ESPN ni de toda la temporada.')
            if fallas_iniciales:
                st.warning('Hay incidencias en el calendario: esta comparación puede omitir partidos.')
            if not faltantes.empty:
                st.dataframe(faltantes, hide_index=True, use_container_width=True)
                if st.button('🔄 Recuperar solo partidos faltantes de este bloque',
                             key='hist_nba_solo_faltantes', use_container_width=True):
                    recuperados, errores_incrementales = [], []
                    for juego in faltantes.itertuples(index=False):
                        try:
                            filas = _extraer_partido(juego.id, str(juego.fecha_utc)[:10], equipo)
                            if filas:
                                recuperados.extend(filas)
                            else:
                                errores_incrementales.append(f'{juego.id}: boxscore vacío')
                        except Exception as exc:
                            errores_incrementales.append(f'{juego.id}: {type(exc).__name__}: {exc}')
                    if recuperados:
                        try:
                            guardar_jugadores(pd.DataFrame(recuperados))
                            st.session_state['hist_nba_datos'] = _unir_historial(
                                st.session_state['hist_nba_datos'], pd.DataFrame(recuperados))
                        except Exception as exc:
                            st.error(f'No se pudieron guardar los registros: {exc}')
                        else:
                            st.success(f'Registros recuperados: {len(recuperados)}')
                    if errores_incrementales:
                        st.warning(f'{len(errores_incrementales)} partidos no recuperados; revisa las incidencias.')
                        st.code('\n'.join(errores_incrementales))
        except Exception as exc:
            st.warning(f'No se pudo comprobar cobertura: {type(exc).__name__}: {exc}')
    with st.expander('💾 Exportación del historial NBA'):
        st.caption('El historial se almacena en Supabase. Puedes exportar los registros visibles en CSV desde la sección inferior. No se genera un respaldo SQLite local.')
    st.metric('Registros visibles (sesión + archivo)', len(datos))
    st.metric('Partidos con incidencia pendiente', len(pendientes))
    st.caption('Bloques consultados ≠ cobertura completa. Los errores de calendario pueden impedir detectar partidos; revisa las incidencias. Con «Todos», se recuperan jugadores de ambos equipos por partido.')
    if fallas_iniciales or errores:
        st.warning(f'Datos potencialmente incompletos: {len(fallas_iniciales) + len(errores)} incidencias de consulta.')
        with st.expander('🔍 Incidencias de cobertura'):
            st.text('\n'.join(map(str, fallas_iniciales + errores)))
    if datos.empty:
        st.info('Carga un bloque para obtener estadísticas individuales. No se muestran promedios sin datos.')
        return
    datos = datos.copy()
    if 'jugador_id' not in datos:
        datos['jugador_id'] = ''
    datos['jugador_id'] = datos['jugador_id'].fillna('').astype(str)
    datos = _clasificar_calidad(datos)
    datos['_clave'] = datos.apply(lambda r: 'id:' + r['jugador_id'] if r['jugador_id'] else 'nombre:' + str(r['jugador']), axis=1)
    with st.expander('🧪 Calidad de datos del historial visible'):
        conteos = datos['estado_calidad'].value_counts().rename_axis('Clasificación').reset_index(name='Registros')
        st.dataframe(conteos, hide_index=True, use_container_width=True)
        st.caption('La clasificación no modifica Supabase. Sin minutos no equivale a ausencia confirmada; los casos pendientes requieren contrastar ESPN.')
    etiquetas = {}
    for clave, grupo in datos.groupby('_clave'):
        nombre = str(grupo.iloc[-1]['jugador'])
        etiquetas[clave] = f'{nombre} · ID {grupo.iloc[-1]["jugador_id"]}' if grupo.iloc[-1]['jugador_id'] else nombre
    opciones = sorted(etiquetas, key=lambda x: etiquetas[x])
    jugadores = st.multiselect('Selecciona hasta 3 jugadores', opciones, format_func=lambda x: etiquetas[x],
                              max_selections=3, key='hist_nba_jugadores')
    if not jugadores:
        st.info('Selecciona jugadores para consultar su historial.')
        return
    seleccion = datos.loc[datos['_clave'].isin(jugadores)].copy()
    seleccion['_etiqueta'] = seleccion['_clave'].map(etiquetas)
    seleccion['fecha'] = pd.to_datetime(seleccion['fecha'], errors='coerce')
    seleccion = seleccion.sort_values(['_clave', 'fecha', 'partido_id'])
    ventana = st.selectbox('Partidos recientes por jugador', ['Todos los recuperados', 5, 10, 20], key='hist_nba_ventana')
    # La ventana de partidos jugados se aplica después de comprobar participación.
    # Los DNP o registros incompletos no desplazan partidos efectivamente jugados.
    jugados = seleccion.loc[seleccion['estado_calidad'].eq('Participación confirmada')].copy()
    if isinstance(ventana, int):
        jugados = jugados.groupby('_clave', group_keys=False).tail(ventana)
    st.caption('Calidad de los jugadores seleccionados (en todo el período recuperado):')
    st.dataframe(seleccion['estado_calidad'].value_counts().rename_axis('Clasificación').reset_index(name='Registros'),
                 hide_index=True, use_container_width=True)
    casos_revision = seleccion.loc[seleccion['estado_calidad'].ne('Participación confirmada')]
    if not casos_revision.empty:
        with st.expander(f'⚠️ Registros por verificar ({len(casos_revision)})'):
            cols = ['fecha', 'jugador', 'equipo', 'partido_id', 'estado_calidad', 'Minutos', 'Puntos', 'Rebotes', 'Asistencias']
            st.dataframe(casos_revision[cols], hide_index=True, use_container_width=True)
            st.caption('No se eliminan registros ni se convierten valores faltantes en cero.')
    metricas = [m for m in METRICAS if m in jugados and jugados[m].notna().any()]
    if jugados.empty or not metricas:
        st.info('No hay partidos con participación y estadísticas comprobables para los jugadores seleccionados.')
        st.download_button('📥 Descargar historial CSV', datos.drop(columns=['_clave'], errors='ignore').to_csv(index=False).encode('utf-8-sig'),
                           'historial_jugadores_nba.csv', 'text/csv', key='hist_nba_csv')
        return
    resumen = jugados.groupby('_etiqueta').agg(
        PJ=('partido_id', 'nunique'), Titularidades=('titular', 'sum'),
        **{m: (m, 'mean') for m in metricas}
    ).round(2).reset_index().rename(columns={'_etiqueta': 'Jugador'})
    st.subheader('📊 Promedios de partidos recuperados')
    st.dataframe(resumen, hide_index=True, use_container_width=True)
    st.caption('PJ cuenta únicamente partidos recuperados con minutos positivos. La ventana 5/10/20 se aplica a partidos jugados, no a registros sin participación comprobada. Los valores ausentes no se convierten en cero.')
    metrica = st.selectbox('Métrica de evolución', metricas, key='hist_nba_metrica')
    grafico = jugados.dropna(subset=['fecha', metrica]).copy()
    if not grafico.empty:
        grafico['Fecha'] = grafico['fecha'].dt.strftime('%Y-%m-%d')
        grafico['Jugador'] = grafico['_etiqueta'].map(lambda x: str(x).split(' · ID ')[0])
        puntos = alt.Chart(grafico).mark_circle(size=110).encode(
            x=alt.X('fecha:T', title='Fecha'),
            y=alt.Y(metrica + ':Q', title=metrica, scale=alt.Scale(zero=True)),
            color=alt.Color('Jugador:N'),
            tooltip=['Fecha:N', 'Jugador:N', 'partido_id:N', alt.Tooltip(metrica + ':Q')]
        ).properties(height=310)
        st.altair_chart(puntos, use_container_width=True)
        st.caption('Cada punto es un partido observado. No se unen fechas sin partidos ni se inventan registros.')
    with st.expander('📋 Historial por partido'):
        columnas = ['fecha', 'jugador', 'equipo', 'partido_id', 'titular'] + metricas
        tabla = jugados[columnas].sort_values('fecha', ascending=False).copy()
        tabla['fecha'] = tabla['fecha'].dt.strftime('%d/%m/%Y')
        st.dataframe(tabla, hide_index=True, use_container_width=True)
    st.download_button('📥 Descargar historial CSV', datos.drop(columns=['_clave'], errors='ignore').to_csv(index=False).encode('utf-8-sig'),
                       'historial_jugadores_nba.csv', 'text/csv', key='hist_nba_csv')


if __name__ == '__main__':
    mostrar_historial_jugadores_nba()

