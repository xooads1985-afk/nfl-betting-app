"""Centro estadístico NBA independiente v1.5. Datos ESPN no oficiales; sin valores simulados."""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import requests
import json
import sqlite3
import time
from pathlib import Path
from urllib.parse import urlencode
import pandas as pd
import streamlit as st

BASE = 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba'

# Copia local de respuestas exitosas. El almacenamiento puede ser efímero en Streamlit Cloud.
_CACHE_DB = Path(__file__).resolve().parent / '.nba_respuestas_cache.sqlite3'
_CACHE_MAX_AGE = 72 * 3600  # Sólo rescate temporal; siempre se avisa al usuario.
_COLUMNAS_PARTIDOS = ['id', 'fecha_utc', 'local', 'visitante', 'local_id', 'visitante_id',
                     'puntos_local', 'puntos_visitante', 'estado', 'finalizado']


def _cache_guardar(clave, datos):
    try:
        with sqlite3.connect(_CACHE_DB, timeout=3) as con:
            con.execute('CREATE TABLE IF NOT EXISTS respuestas (clave TEXT PRIMARY KEY, guardado REAL NOT NULL, contenido TEXT NOT NULL)')
            con.execute('INSERT OR REPLACE INTO respuestas VALUES (?, ?, ?)',
                        (clave, time.time(), json.dumps(datos, ensure_ascii=False)))
    except (OSError, sqlite3.Error, TypeError, ValueError):
        pass  # Si el disco es de sólo lectura, el módulo sigue funcionando.


def _cache_recuperar(clave):
    try:
        with sqlite3.connect(_CACHE_DB, timeout=3) as con:
            fila = con.execute('SELECT guardado, contenido FROM respuestas WHERE clave=?', (clave,)).fetchone()
        if fila and 0 <= time.time() - fila[0] <= _CACHE_MAX_AGE:
            datos = json.loads(fila[1])
            if isinstance(datos, dict):
                return datos, round((time.time() - fila[0]) / 60)
    except (OSError, sqlite3.Error, ValueError, TypeError):
        pass
    return None, None


@st.cache_data(ttl=900, show_spinner=False)
def _json(endpoint, params=None):
    """Consulta ESPN; no reintenta 403 y recupera caché identificada si existe."""
    params = params or {}
    clave = endpoint + '?' + urlencode(sorted((str(k), str(v)) for k, v in params.items()))
    error = None
    for intento in range(2):
        try:
            r = requests.get(f'{BASE}/{endpoint}', params=params, timeout=18)
            r.raise_for_status()
            datos = r.json()
            if not isinstance(datos, dict):
                raise ValueError('Respuesta de datos inesperada')
            _cache_guardar(clave, datos)
            return datos
        except requests.HTTPError as exc:
            error = exc
            codigo = exc.response.status_code if exc.response is not None else None
            if codigo not in (429, 500, 502, 503, 504) or intento == 1:
                break
            time.sleep(1.0)
        except (requests.Timeout, requests.ConnectionError) as exc:
            error = exc
            if intento == 1:
                break
            time.sleep(1.0)
    # La caché NO disfraza una consulta fallida: la UI muestra la incidencia.
    if endpoint in ('scoreboard', 'summary'):
        datos, edad = _cache_recuperar(clave)
        if datos is not None:
            datos = dict(datos)
            datos['_nba_cache_rescate'] = {'minutos': edad, 'motivo': str(error)}
            return datos
    if error is not None:
        raise error
    raise RuntimeError('No fue posible consultar la fuente')

def _normalizar_partidos(df):
    """Depura partidos por ID y por encuentro real; preserva auditoría."""
    if df.empty:
        df = pd.DataFrame(columns=_COLUMNAS_PARTIDOS)
        df.attrs['auditoria_duplicados'] = {'recibidos': 0, 'descartados_id': 0,
                                            'descartados_encuentro': 0, 'unicos': 0}
        return df
    trabajo = df.copy()
    recibidos = len(trabajo)
    # Evitar agrupar por un ID vacío: no identifica un encuentro.
    trabajo['id'] = trabajo['id'].fillna('').astype(str).str.strip()
    trabajo['_instante'] = pd.to_datetime(trabajo['fecha_utc'], utc=True, errors='coerce')
    trabajo['_fecha_minuto'] = trabajo['_instante'].dt.strftime('%Y-%m-%dT%H:%MZ')
    # La clave secundaria exige ambos equipos y hora de inicio. No usar solo la fecha.
    local = trabajo['local_id'].fillna('').astype(str).str.strip()
    visita = trabajo['visitante_id'].fillna('').astype(str).str.strip()
    local = local.where(local.ne(''), trabajo['local'].fillna('').astype(str).str.casefold().str.strip())
    visita = visita.where(visita.ne(''), trabajo['visitante'].fillna('').astype(str).str.casefold().str.strip())
    valida = trabajo['_fecha_minuto'].notna() & local.ne('') & visita.ne('')
    trabajo['_clave_encuentro'] = None
    trabajo.loc[valida, '_clave_encuentro'] = (
        trabajo.loc[valida, '_fecha_minuto'] + '|' + local.loc[valida] + '|' + visita.loc[valida]
    )
    # Elegir registro finalizado y con marcador antes que una versión parcial.
    trabajo['_prioridad'] = (trabajo['finalizado'].fillna(False).astype(int) * 10
        + trabajo['puntos_local'].notna().astype(int)
        + trabajo['puntos_visitante'].notna().astype(int))
    trabajo['_orden'] = range(len(trabajo))
    trabajo = trabajo.sort_values(['_prioridad', '_orden'], ascending=[False, False], kind='stable')
    ids_validos = trabajo['id'].ne('')
    por_id = trabajo.loc[ids_validos].drop_duplicates('id', keep='first')
    sin_id = trabajo.loc[~ids_validos]
    descartados_id = len(trabajo) - len(por_id) - len(sin_id)
    trabajo = pd.concat([por_id, sin_id], ignore_index=True)
    claves_validas = trabajo['_clave_encuentro'].notna()
    por_encuentro = trabajo.loc[claves_validas].drop_duplicates('_clave_encuentro', keep='first')
    sin_clave = trabajo.loc[~claves_validas]
    descartados_encuentro = len(trabajo) - len(por_encuentro) - len(sin_clave)
    trabajo = pd.concat([por_encuentro, sin_clave], ignore_index=True)
    trabajo = trabajo.sort_values('fecha_utc', kind='stable').drop(
        columns=['_instante', '_fecha_minuto', '_clave_encuentro', '_prioridad', '_orden']
    ).reset_index(drop=True)
    trabajo.attrs['auditoria_duplicados'] = {
        'recibidos': recibidos, 'descartados_id': descartados_id,
        'descartados_encuentro': descartados_encuentro, 'unicos': len(trabajo)
    }
    return trabajo


def _diagnostico_coincidencias(df):
    """Auditoría no destructiva: mismo enfrentamiento y fecha local, aun con IDs distintos."""
    columnas = ['id', 'fecha_utc', 'fecha_sinaloa', 'visitante', 'local',
                'puntos_visitante', 'puntos_local', 'estado', 'finalizado',
                'diferencia_minutos', 'tipo_coincidencia']
    if df.empty:
        return pd.DataFrame(columns=columnas), {'grupos': 0, 'registros': 0, 'ids_distintos': 0}
    t = df.copy()
    ts = pd.to_datetime(t['fecha_utc'], utc=True, errors='coerce')
    local_ts = ts.dt.tz_convert('America/Mazatlan')
    t['fecha_sinaloa'] = local_ts.dt.strftime('%d/%m/%Y %H:%M').fillna('Sin fecha')
    t['_dia'] = local_ts.dt.strftime('%Y-%m-%d')
    t['_minuto'] = ts.dt.floor('min')
    t['_visita'] = t['visitante'].fillna('').astype(str).str.casefold().str.strip()
    t['_local'] = t['local'].fillna('').astype(str).str.casefold().str.strip()
    t = t[t['_dia'].notna() & t['_visita'].ne('') & t['_local'].ne('')].copy()
    resultados = []
    grupos = 0
    ids_distintos = 0
    for _, grupo in t.groupby(['_dia', '_visita', '_local'], sort=False):
        if len(grupo) < 2:
            continue
        grupos += 1
        if grupo['id'].astype(str).nunique() > 1:
            ids_distintos += 1
        dif = (grupo['_minuto'].max() - grupo['_minuto'].min()).total_seconds() / 60
        exacto = grupo['_minuto'].nunique() == 1
        clase = ('Misma hora, equipos y día' if exacto else
                 'Mismos equipos y día; horarios distintos')
        for _, fila in grupo.iterrows():
            resultados.append({c: fila.get(c) for c in columnas if c not in
                               ('diferencia_minutos', 'tipo_coincidencia')}
                              | {'diferencia_minutos': round(dif, 1),
                                 'tipo_coincidencia': clase})
    tabla = pd.DataFrame(resultados, columns=columnas)
    if not tabla.empty:
        tabla = tabla.sort_values(['fecha_sinaloa', 'visitante', 'local', 'id'])
    return tabla, {'grupos': grupos, 'registros': len(tabla),
                   'ids_distintos': ids_distintos}


@st.cache_data(ttl=1800, show_spinner=False)
def cargar_partidos(desde, hasta):
    inicio, fin = date.fromisoformat(str(desde)), date.fromisoformat(str(hasta))
    if fin < inicio or (fin - inicio).days > 31:
        raise ValueError('El intervalo debe tener entre 1 y 32 días.')
    registros, errores = [], []
    for i in range((fin - inicio).days + 1):
        dia = inicio + timedelta(days=i)
        try:
            datos = _json('scoreboard', {'dates': dia.strftime('%Y%m%d'), 'limit': 100})
            rescate = datos.get('_nba_cache_rescate')
            if rescate:
                errores.append(f"{dia}: fuente no disponible; copia local de hace {rescate['minutos']} min. Motivo: {rescate['motivo']}")
            eventos = datos.get('events', [])
            if not isinstance(eventos, list):
                raise ValueError('ESPN devolvió eventos en formato inesperado')
            for evento in eventos:
                if not isinstance(evento, dict):
                    continue
                competicion = (evento.get('competitions') or [{}])[0]
                equipos = competicion.get('competitors', [])
                local = next((x for x in equipos if x.get('homeAway') == 'home'), {})
                visita = next((x for x in equipos if x.get('homeAway') == 'away'), {})
                estado = evento.get('status', {}).get('type', {})
                registros.append({
                    'id': str(evento.get('id', '')), 'fecha_utc': evento.get('date', ''),
                    'local': local.get('team', {}).get('displayName', ''),
                    'visitante': visita.get('team', {}).get('displayName', ''),
                    'local_id': str(local.get('team', {}).get('id', '')),
                    'visitante_id': str(visita.get('team', {}).get('id', '')),
                    'puntos_local': pd.to_numeric(local.get('score'), errors='coerce'),
                    'puntos_visitante': pd.to_numeric(visita.get('score'), errors='coerce'),
                    'estado': estado.get('description', estado.get('name', 'Desconocido')),
                    'finalizado': bool(estado.get('completed', False)),
                })
        except (requests.RequestException, ValueError, KeyError) as exc:
            errores.append(f'{dia}: {type(exc).__name__}: {exc}')
    df_bruto = pd.DataFrame(registros, columns=_COLUMNAS_PARTIDOS)
    diagnostico, resumen = _diagnostico_coincidencias(df_bruto)
    df = _normalizar_partidos(df_bruto)
    df.attrs['diagnostico_coincidencias'] = diagnostico
    df.attrs['resumen_coincidencias'] = resumen
    return df, errores

@st.cache_data(ttl=900, show_spinner=False)
def cargar_detalle(id_partido):
    if not str(id_partido).isdigit():
        raise ValueError('Identificador de partido inválido')
    return _json('summary', {'event': str(id_partido)})

def extraer_jugadores(detalle):
    filas = []
    for equipo in detalle.get('boxscore', {}).get('players', []):
        nombre_equipo = equipo.get('team', {}).get('displayName', 'Equipo')
        for bloque in equipo.get('statistics', []):
            etiquetas = bloque.get('labels', []) or bloque.get('names', [])
            for jugador in bloque.get('athletes', []):
                if not isinstance(jugador, dict):
                    continue
                fila = {'equipo': nombre_equipo,
                        'jugador': jugador.get('athlete', {}).get('displayName', 'Desconocido'),
                        'titular': jugador.get('starter', False)}
                valores = jugador.get('stats', [])
                fila.update({str(k): v for k, v in zip(etiquetas, valores)})
                filas.append(fila)
    return pd.DataFrame(filas)

def tabla_equipos(partidos):
    if partidos.empty:
        return pd.DataFrame()
    fin = partidos[partidos.finalizado & partidos.puntos_local.notna() & partidos.puntos_visitante.notna()
                   & (partidos.puntos_local >= 0) & (partidos.puntos_visitante >= 0)]
    filas = []
    for g in fin.itertuples(index=False):
        filas += [
            {'equipo': g.local, 'PF': g.puntos_local, 'PC': g.puntos_visitante, 'victoria': int(g.puntos_local > g.puntos_visitante), 'ubicacion': 'Local'},
            {'equipo': g.visitante, 'PF': g.puntos_visitante, 'PC': g.puntos_local, 'victoria': int(g.puntos_visitante > g.puntos_local), 'ubicacion': 'Visitante'},
        ]
    if not filas:
        return pd.DataFrame()
    df = pd.DataFrame(filas)
    return df.groupby('equipo', as_index=False).agg(PJ=('victoria','size'), V=('victoria','sum'), PF=('PF','mean'), PC=('PC','mean')).assign(
        D=lambda x: x.PF-x.PC, **{'%V': lambda x: 100*x.V/x.PJ}
    ).sort_values(['V','D'], ascending=False).round(2)

def _fecha_sinaloa(valor):
    """Convierte fecha ISO UTC a hora de Sinaloa (sin DST desde 2022)."""
    try:
        ts = pd.to_datetime(valor, utc=True)
        if pd.isna(ts):
            return 'Fecha no disponible'
        return ts.tz_convert(ZoneInfo('America/Mazatlan')).strftime('%d/%m/%Y · %H:%M')
    except (ValueError, TypeError, OverflowError):
        return 'Fecha no disponible'


def _estado_partido(fila):
    if bool(fila.finalizado):
        return '✅ Finalizado'
    texto = str(fila.estado or '').lower()
    if any(x in texto for x in ('progress', 'live', 'halftime', 'quarter', 'in progress')):
        return '🔴 En vivo'
    if any(x in texto for x in ('postpon', 'cancel', 'delay', 'suspend')):
        return '⚠️ ' + str(fila.estado)
    if any(x in texto for x in ('scheduled', 'pre', 'not started')):
        return '🗓️ Programado'
    return 'ℹ️ ' + str(fila.estado)


def _tarjetas_partidos(partidos, clave, limite=100):
    """Tarjetas verticales aptas para pantallas pequeñas; preserva datos de origen."""
    if partidos.empty:
        st.info('No hay partidos para mostrar con estos filtros.')
        return
    ordenados = partidos.sort_values('fecha_utc', ascending=False)
    if len(ordenados) > limite:
        st.caption(f'Mostrando {limite} de {len(ordenados)} partidos. El CSV conserva todos.')
    for fila in ordenados.head(limite).itertuples(index=False):
        st.markdown(f'**🏀 {fila.visitante} @ {fila.local}**')
        st.caption(f'📅 {_fecha_sinaloa(fila.fecha_utc)} · Sinaloa  |  {_estado_partido(fila)}')
        if fila.finalizado and pd.notna(fila.puntos_visitante) and pd.notna(fila.puntos_local):
            st.markdown(f'**{int(fila.puntos_visitante)} – {int(fila.puntos_local)}**  (visitante – local)')
        elif pd.notna(fila.puntos_visitante) and pd.notna(fila.puntos_local) and 'En vivo' in _estado_partido(fila):
            st.write(f'Marcador parcial: {int(fila.puntos_visitante)} – {int(fila.puntos_local)}')
        else:
            st.caption('Sin marcador final disponible')
        st.divider()


def _tabla_partidos_legible(partidos):
    columnas = ['fecha_utc','visitante','local','puntos_visitante','puntos_local','estado']
    tabla = partidos[columnas].copy()
    tabla.insert(0, 'fecha_sinaloa', tabla.fecha_utc.map(_fecha_sinaloa))
    tabla = tabla.rename(columns={'fecha_sinaloa':'Fecha · Sinaloa', 'visitante':'Visitante',
        'local':'Local', 'puntos_visitante':'Pts visita', 'puntos_local':'Pts local', 'estado':'Estado'})
    return tabla.drop(columns='fecha_utc')


def mostrar_modulo_nba():
    st.title('🏀 Centro Estadístico NBA')
    st.caption('Datos consultados en ESPN (interfaz no oficial). Sin cifras de demostración. Los promedios se calculan únicamente sobre el período seleccionado.')
    hoy = date.today()
    a, b = st.columns(2)
    with a:
        inicio = st.date_input('Desde', value=hoy-timedelta(days=6), key='nba_fecha_desde')
    with b:
        fin = st.date_input('Hasta', value=hoy, key='nba_fecha_hasta')
    if inicio > fin:
        st.error('La fecha inicial no puede ser posterior a la fecha final.')
        return
    if (fin - inicio).days > 31:
        st.error('Selecciona un intervalo máximo de 32 días por consulta.')
        return
    if st.button('🔄 Actualizar datos NBA', use_container_width=True):
        cargar_partidos.clear()
        _json.clear()
        cargar_detalle.clear()
        st.rerun()
    try:
        partidos, errores = cargar_partidos(inicio.isoformat(), fin.isoformat())
    except Exception as exc:
        st.error(f'No fue posible cargar NBA: {exc}')
        return
    if errores:
        st.warning(f'Incidencias en {len(errores)} día(s). Algunas fechas pueden usar copias locales; verifica los detalles. La cobertura puede ser parcial.')
        with st.expander('Ver errores de consulta'):
            st.code('\n'.join(errores))
    if partidos.empty:
        st.info('No se recuperaron partidos en las fechas seleccionadas. Si hubo errores de consulta, no significa que no se hayan disputado encuentros.')
        return
    st.caption('Horarios mostrados en la zona America/Mazatlan (Sinaloa).')
    auditoria = partidos.attrs.get('auditoria_duplicados', {})
    with st.expander('🔍 Control de duplicados y cobertura'):
        st.write('Registros recibidos:', auditoria.get('recibidos', 'No disponible'))
        st.write('Descartados por ID repetido:', auditoria.get('descartados_id', 'No disponible'))
        st.write('Descartados por mismo partido (fecha, hora y equipos):',
                 auditoria.get('descartados_encuentro', 'No disponible'))
        st.write('Partidos únicos mostrados:', len(partidos))
        st.caption('Se comparan fechas de inicio UTC al minuto y equipos local/visitante. '
                   'No se garantiza cobertura total ni exactitud de la fuente.')
    with st.expander('🧪 Auditoría avanzada NBA v1.4 — coincidencias'):
        st.caption('Análisis diagnóstico de los registros originales, ANTES de eliminar duplicados. '
                   'No elimina partidos adicionales ni altera los cálculos.')
        resumen = partidos.attrs.get('resumen_coincidencias', {})
        coincidencias = partidos.attrs.get('diagnostico_coincidencias', pd.DataFrame())
        st.metric('Grupos con mismos equipos y fecha local', resumen.get('grupos', 0))
        st.metric('Registros involucrados', resumen.get('registros', 0))
        st.metric('Grupos con IDs diferentes', resumen.get('ids_distintos', 0))
        if coincidencias.empty:
            st.success('No se encontraron coincidencias por equipos y día local en los datos recibidos.')
        else:
            st.warning('Coincidencias para revisar: NO son duplicados confirmados.')
            st.dataframe(coincidencias, hide_index=True, use_container_width=True)
            st.download_button('📥 Descargar diagnóstico CSV',
                coincidencias.to_csv(index=False).encode('utf-8-sig'),
                'nba_v1_4_diagnostico.csv', 'text/csv', key='nba_v14_csv')
            st.caption('Revisa ID, horario UTC, marcador y estado. Dos partidos del mismo día '
                       'no deben eliminarse automáticamente sin verificar la fuente.')
    vistas = ['🏠 Inicio', '📅 Partidos', '🏟️ Equipos', '📊 Comparar equipos', '🏀 Enfrentamientos',
              '🏀 Centro por partido', '📊 Puntos históricos', '👥 Jugadores por partido',
              '📈 Rendimiento de jugadores', '🧠 Rendimiento avanzado', '👥 Jugadores',
              '🛰️ Estado', '🧪 Auditorías y análisis', '🧪 Pruebas']
    vista = st.selectbox('Sección NBA', vistas, key='nba_vista')
    finalizados = partidos[partidos.finalizado & partidos.puntos_local.notna()
                           & partidos.puntos_visitante.notna()
                           & (partidos.puntos_local >= 0) & (partidos.puntos_visitante >= 0)].copy()
    tabla = tabla_equipos(partidos)
    if vista == '🏠 Inicio':
        st.metric('Partidos recuperados', len(partidos))
        c1,c2 = st.columns(2)
        c1.metric('Finalizados', len(finalizados))
        c2.metric('Equipos con resultados', len(tabla))
        st.caption('Partidos recuperados = registros únicos devueltos por la fuente; no garantiza cobertura completa.')
        _tarjetas_partidos(partidos, 'nba_inicio')
        with st.expander('📋 Ver tabla completa'):
            st.dataframe(_tabla_partidos_legible(partidos), use_container_width=True, hide_index=True)
    elif vista == '📅 Partidos':
        equipos = sorted(set(partidos.local) | set(partidos.visitante))
        eq = st.selectbox('Filtrar equipo', ['Todos']+equipos, key='nba_filtro_eq')
        ver = partidos if eq == 'Todos' else partidos[(partidos.local == eq)|(partidos.visitante == eq)]
        _tarjetas_partidos(ver, 'nba_partidos')
        with st.expander('📋 Ver tabla completa'):
            st.dataframe(_tabla_partidos_legible(ver), use_container_width=True, hide_index=True)
        st.download_button('📥 Descargar partidos', ver.to_csv(index=False).encode('utf-8-sig'), 'nba_partidos.csv', 'text/csv')
    elif vista in ['🏟️ Equipos','📊 Comparar equipos','🧠 Rendimiento avanzado']:
        if tabla.empty:
            st.info('No hay partidos finalizados con marcadores completos en el período.')
        elif vista == '🏟️ Equipos':
            st.dataframe(tabla, use_container_width=True, hide_index=True)
            st.caption('PF/PC: puntos anotados/permitidos por partido. D: diferencia media. No equivalen a ratings por 100 posesiones.')
        elif vista == '📊 Comparar equipos':
            opciones = tabla.equipo.tolist()
            elegidos = st.multiselect('Selecciona hasta 3 equipos', opciones, max_selections=3, key='nba_comparar_equipos')
            if elegidos:
                st.dataframe(tabla[tabla.equipo.isin(elegidos)], hide_index=True, use_container_width=True)
        else:
            st.info('Eficiencia por posesión, pace y métricas avanzadas requieren posesiones y boxscores completos; no se sustituyen por valores estimados.')
            st.dataframe(tabla, hide_index=True, use_container_width=True)
    elif vista == '🏀 Enfrentamientos':
        equipos = sorted(set(partidos.local)|set(partidos.visitante))
        x = st.selectbox('Equipo A', equipos, key='nba_h2h_a')
        y = st.selectbox('Equipo B', [e for e in equipos if e != x], key='nba_h2h_b') if len(equipos)>1 else None
        if y:
            h = partidos[((partidos.local==x)&(partidos.visitante==y))|((partidos.local==y)&(partidos.visitante==x))]
            _tarjetas_partidos(h, 'nba_h2h')
    elif vista in ['🏀 Centro por partido','👥 Jugadores por partido','📈 Rendimiento de jugadores','👥 Jugadores']:
        opciones = {f"{g.fecha_utc[:10]} · {g.visitante} @ {g.local} · {g.estado} [{g.id}]":g.id for g in partidos.itertuples(index=False)}
        etiqueta = st.selectbox('Partido',list(opciones),key='nba_partido_detalle')
        try:
            detalle = cargar_detalle(opciones[etiqueta])
            if detalle.get('_nba_cache_rescate'):
                rescate = detalle['_nba_cache_rescate']
                st.warning(f"Detalle recuperado de copia local ({rescate['minutos']} min de antigüedad); ESPN no respondió.")
            jugadores = extraer_jugadores(detalle)
            if vista == '🏀 Centro por partido':
                st.subheader(etiqueta)
                st.write('Estadísticas individuales disponibles en la fuente:')
            if jugadores.empty:
                st.info('No hay boxscore de jugadores disponible para este partido.')
            else:
                equipos = sorted(jugadores.equipo.dropna().unique())
                eq = st.selectbox('Equipo', ['Todos']+equipos,key='nba_equipo_detalle')
                ver = jugadores if eq=='Todos' else jugadores[jugadores.equipo==eq]
                st.dataframe(ver, use_container_width=True, hide_index=True)
                st.download_button('📥 Descargar boxscore',ver.to_csv(index=False).encode('utf-8-sig'),'nba_boxscore.csv','text/csv')
            if vista in ['📈 Rendimiento de jugadores','👥 Jugadores']:
                st.caption('Esta sección presenta el boxscore del partido seleccionado. El historial multijuego se consulta en el módulo independiente Historial de jugadores NBA.')
        except Exception as exc:
            st.error(f'No se pudo cargar el detalle: {exc}')
    elif vista == '📊 Puntos históricos':
        if finalizados.empty:
            st.info('Sin resultados finalizados.')
        else:
            graf = finalizados[['fecha_utc','puntos_local','puntos_visitante']].copy()
            graf['fecha_utc'] = pd.to_datetime(graf.fecha_utc, utc=True)
            graf['total'] = graf.puntos_local + graf.puntos_visitante
            st.line_chart(graf.set_index('fecha_utc')['total'])
            st.caption('Total de puntos de cada partido finalizado, en orden cronológico.')
    elif vista == '🛰️ Estado':
        st.write('Consulta UTC:', datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'))
        st.write('Período consultado:', str(inicio), 'a', str(fin))
        st.metric('Días con error de consulta',len(errores))
        st.metric('Partidos únicos recuperados',len(partidos))
        st.metric('Partidos programados o en curso',len(partidos)-len(finalizados))
        st.metric('Partidos con resultado completo',len(finalizados))
        st.caption('La hora de consulta no demuestra que la fuente haya publicado datos nuevos. Caché en memoria: 15 minutos. Rescate local: máximo 72 horas, identificado como incidencia.')
    elif vista == '🧪 Auditorías y análisis':
        fallas = []
        if partidos.id[partidos.id.ne('')].duplicated().any(): fallas.append('IDs duplicados')
        if auditoria.get('descartados_id', 0) or auditoria.get('descartados_encuentro', 0):
            st.info(f"Duplicados descartados: {auditoria.get('descartados_id', 0)} por ID y "
                    f"{auditoria.get('descartados_encuentro', 0)} por fecha/hora/equipos.")
        if partidos.id.eq('').any(): fallas.append('Partidos sin identificador')
        if partidos.fecha_utc.eq('').any(): fallas.append('Partidos sin fecha')
        if (partidos.local==partidos.visitante).any(): fallas.append('Local y visitante idénticos')
        if (partidos[['puntos_local','puntos_visitante']]<0).any().any(): fallas.append('Puntos negativos')
        incompletos = partidos[partidos.finalizado & partidos[['puntos_local','puntos_visitante']].isna().any(axis=1)]
        if not incompletos.empty: fallas.append(f'{len(incompletos)} finalizados sin marcador completo')
        if errores: fallas.append(f'{len(errores)} días con fallas de consulta')
        if fallas:
            for f in fallas: st.warning(f)
        else: st.success('Sin anomalías detectadas en los controles básicos.')
        st.caption('Estos controles no garantizan exactitud de la fuente.')
    else:
        st.write('Pruebas de consistencia de datos:')
        st.write({'IDs únicos': bool(partidos.id.is_unique), 'Partidos recuperados': len(partidos),
                  'Fechas de consulta válidas': inicio<=fin, 'Marcadores completos en finalizados':
                  bool(finalizados[['puntos_local','puntos_visitante']].notna().all().all())})

if __name__ == '__main__':
    mostrar_modulo_nba()

