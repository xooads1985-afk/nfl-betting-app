"""Centro estadístico NBA independiente. Datos ESPN no oficiales; sin valores simulados."""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import requests
import pandas as pd
import streamlit as st

BASE = 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba'

@st.cache_data(ttl=900, show_spinner=False)
def _json(endpoint, params=None):
    r = requests.get(f'{BASE}/{endpoint}', params=params, timeout=18)
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, dict):
        raise ValueError('Respuesta de datos inesperada')
    return data

def _normalizar_partidos(df):
    """Depura partidos por ID y por encuentro real; preserva auditoría."""
    if df.empty:
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
            for evento in datos.get('events', []):
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
    df = pd.DataFrame(registros)
    df = _normalizar_partidos(df)
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
    fin = partidos[partidos.finalizado & partidos.puntos_local.notna() & partidos.puntos_visitante.notna()]
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
        st.warning(f'Hubo problemas de consulta en {len(errores)} día(s); el período está incompleto.')
        with st.expander('Ver errores de consulta'):
            st.code('\n'.join(errores))
    if partidos.empty:
        st.info('No se encontraron partidos en las fechas seleccionadas.')
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
    vistas = ['🏠 Inicio', '📅 Partidos', '🏟️ Equipos', '📊 Comparar equipos', '🏀 Enfrentamientos',
              '🏀 Centro por partido', '📊 Puntos históricos', '👥 Jugadores por partido',
              '📈 Rendimiento de jugadores', '🧠 Rendimiento avanzado', '👥 Jugadores',
              '🛰️ Estado', '🧪 Auditorías y análisis', '🧪 Pruebas']
    vista = st.selectbox('Sección NBA', vistas, key='nba_vista')
    finalizados = partidos[partidos.finalizado].copy()
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
                st.caption('Vista inicial por partido. El historial multijuego se habilitará al completar el motor de recopilación y validación de boxscores.')
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
        st.metric('Partidos con resultado completo',len(finalizados[finalizados.puntos_local.notna() & finalizados.puntos_visitante.notna()]))
        st.caption('La hora de consulta no demuestra que la fuente haya publicado datos nuevos. Caché de calendario: 30 minutos.')
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
        incompletos = finalizados[finalizados[['puntos_local','puntos_visitante']].isna().any(axis=1)]
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

