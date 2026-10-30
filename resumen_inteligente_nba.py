"""Resumen Inteligente NBA v3.3.0.

Módulo independiente de NFL. Depende de modulo_nba.py y
comparador_jugadores_nba.py; fuente ESPN no oficial. No simula datos.
"""
from datetime import date, timedelta
from zoneinfo import ZoneInfo
import pandas as pd
import streamlit as st

from modulo_nba import cargar_partidos, cargar_detalle
from comparador_jugadores_nba import _historial, METRICAS
from historial_jugadores_nba import obtener_historial_compartido

VERSION = '3.3.0'


def _equipo_resultados(partidos, equipo):
    """Devuelve únicamente juegos finalizados con marcadores verificables."""
    if partidos.empty:
        return partidos.copy()
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



def _historial_equipo(partidos, equipo, antes=None):
    """Historial cronológico; conserva el esquema aun cuando no haya filas."""
    d = _equipo_resultados(partidos, equipo)
    # En la validación retrospectiva los primeros juegos pueden carecer
    # de antecedentes. No intentar acceder a columnas de un marco vacío.
    if d.empty:
        return d
    if 'fecha_utc' not in d.columns:
        return d.iloc[0:0].copy()
    if antes is not None:
        fechas = pd.to_datetime(d['fecha_utc'], utc=True, errors='coerce')
        d = d.loc[fechas.lt(antes)].copy()
    return d.sort_values('fecha_utc')


def _media_rango(serie, minimo=3):
    x = pd.to_numeric(pd.Series(serie), errors='coerce').dropna().tail(10)
    if len(x) < minimo:
        return None
    media = float(x.mean())
    sd = float(x.std(ddof=1)) if len(x) > 1 else 0.
    return {'media': media, 'bajo': max(0., media-sd), 'alto': media+sd, 'n': len(x)}


def _puntos_periodos(detalle):
    """Cuartos observados en ESPN summary, sin inventar desgloses."""
    comps = (detalle.get('header', {}).get('competitions') or [{}])[0].get('competitors', [])
    salida = {}
    for c in comps:
        equipo = c.get('team', {}).get('displayName')
        if not equipo:
            continue
        valores = {}
        for i, linea in enumerate(c.get('linescores') or []):
            numero = linea.get('period') or linea.get('periodNumber') or i + 1
            try:
                numero = int(numero)
                valor = float(linea.get('value', linea.get('displayValue')))
            except (ValueError, TypeError):
                continue
            if 1 <= numero <= 4 and valor >= 0:
                valores[numero] = valor
        if all(i in valores for i in (1, 2, 3, 4)):
            salida[equipo] = valores
    return salida


def _abreviatura_equipo(nombre):
    """Etiqueta corta de tabla; no modifica nombres de origen ni cálculos."""
    codigos = {
        'Atlanta Hawks': 'ATL', 'Boston Celtics': 'BOS', 'Brooklyn Nets': 'BKN',
        'Charlotte Hornets': 'CHA', 'Chicago Bulls': 'CHI', 'Cleveland Cavaliers': 'CLE',
        'Dallas Mavericks': 'DAL', 'Denver Nuggets': 'DEN', 'Detroit Pistons': 'DET',
        'Golden State Warriors': 'GSW', 'Houston Rockets': 'HOU', 'Indiana Pacers': 'IND',
        'LA Clippers': 'LAC', 'Los Angeles Clippers': 'LAC',
        'Los Angeles Lakers': 'LAL', 'Memphis Grizzlies': 'MEM', 'Miami Heat': 'MIA',
        'Milwaukee Bucks': 'MIL', 'Minnesota Timberwolves': 'MIN',
        'New Orleans Pelicans': 'NOP', 'New York Knicks': 'NYK',
        'Oklahoma City Thunder': 'OKC', 'Orlando Magic': 'ORL',
        'Philadelphia 76ers': 'PHI', 'Phoenix Suns': 'PHX',
        'Portland Trail Blazers': 'POR', 'Sacramento Kings': 'SAC',
        'San Antonio Spurs': 'SAS', 'Toronto Raptors': 'TOR',
        'Utah Jazz': 'UTA', 'Washington Wizards': 'WAS',
    }
    nombre = str(nombre).strip()
    return codigos.get(nombre, nombre[:3].upper())




def _validacion_historica_equipos(partidos, fecha_limite, detalles=None):
    """Validación cronológica con controles de datos y esquema estable."""
    columnas = ['Fecha', 'Partido', 'id', 'ataque', 'cuartos',
                'real_completo', 'real_reglamentario']
    if partidos.empty:
        return pd.DataFrame(columns=columnas)
    necesarias = {'id', 'local', 'visitante', 'fecha_utc', 'finalizado',
                  'puntos_local', 'puntos_visitante'}
    if not necesarias.issubset(partidos.columns):
        return pd.DataFrame(columns=columnas)
    d = partidos.loc[partidos['finalizado'].eq(True)].copy()
    d['fecha_dt'] = pd.to_datetime(d['fecha_utc'], utc=True, errors='coerce')
    d['puntos_local'] = pd.to_numeric(d['puntos_local'], errors='coerce')
    d['puntos_visitante'] = pd.to_numeric(d['puntos_visitante'], errors='coerce')
    d = d.dropna(subset=['fecha_dt', 'puntos_local', 'puntos_visitante'])
    d = d.loc[d['fecha_dt'].lt(fecha_limite)].sort_values(['fecha_dt', 'id'])
    d = d.drop_duplicates(subset=['id'], keep='first')
    filas = []
    for _, juego in d.iterrows():
        local, visita = str(juego['local']), str(juego['visitante'])
        fecha = juego['fecha_dt']
        anteriores = d.loc[d['fecha_dt'].lt(fecha)]
        historicos = {e: _historial_equipo(anteriores, e, fecha)
                      for e in (local, visita)}
        pred = {}
        for equipo, rival in ((local, visita), (visita, local)):
            propio_hist = historicos[equipo]
            rival_hist = historicos[rival]
            propio = (_media_rango(propio_hist['PF'])
                      if not propio_hist.empty and 'PF' in propio_hist else None)
            recibido = (_media_rango(rival_hist['PC'])
                        if not rival_hist.empty and 'PC' in rival_hist else None)
            if propio and recibido:
                pred[equipo] = (propio['media'] + recibido['media']) / 2
        ident = str(juego['id'])
        fila = {'Fecha': fecha.strftime('%Y-%m-%d'),
                'Partido': f'{visita} @ {local}', 'id': ident,
                'ataque': None, 'cuartos': None,
                'real_completo': float(juego['puntos_local'] + juego['puntos_visitante']),
                'real_reglamentario': None}
        if len(pred) == 2:
            fila['ataque'] = pred[local] + pred[visita]
        if detalles and ident in detalles:
            actual = detalles[ident]
            if isinstance(actual, dict) and local in actual and visita in actual:
                fila['real_reglamentario'] = (sum(actual[local].values()) +
                                             sum(actual[visita].values()))
                pron = {}
                for equipo in (local, visita):
                    observados = []
                    for _, ant in historicos[equipo].tail(10).iterrows():
                        par = detalles.get(str(ant['id']), {})
                        if isinstance(par, dict) and equipo in par:
                            observados.append(sum(par[equipo].values()))
                    media = _media_rango(observados)
                    if media:
                        pron[equipo] = media['media']
                if len(pron) == 2:
                    fila['cuartos'] = pron[local] + pron[visita]
        if fila['ataque'] is not None or fila['cuartos'] is not None:
            filas.append(fila)
    return pd.DataFrame(filas, columns=columnas)


def _diagnostico_cuartos_historicos(partidos, fecha_limite, detalles):
    """Cuenta cobertura y elegibilidad sin solicitar nuevos datos ni cambiar estimaciones."""
    requeridas = {'id', 'local', 'visitante', 'fecha_utc', 'finalizado',
                  'puntos_local', 'puntos_visitante'}
    if partidos.empty or not requeridas.issubset(partidos.columns):
        return {'error': 'Calendario vacío o sin columnas requeridas.'}
    base = partidos.loc[partidos['finalizado'].eq(True)].copy()
    base['fecha_dt'] = pd.to_datetime(base['fecha_utc'], utc=True, errors='coerce')
    base = base.dropna(subset=['fecha_dt'])
    base = base.loc[base['fecha_dt'].lt(fecha_limite)].sort_values(['fecha_dt', 'id'])
    base['id'] = base['id'].astype(str)
    base = base.drop_duplicates('id')
    detalles = detalles or {}
    ids_base = set(base['id'])
    completos = {}
    for _, fila in base.iterrows():
        ident = fila['id']
        dato = detalles.get(ident, {})
        local, visita = str(fila['local']), str(fila['visitante'])
        if not isinstance(dato, dict):
            continue
        equipos_validos = set()
        for nombre in (local, visita):
            periodos = dato.get(nombre)
            if isinstance(periodos, dict) and all(q in periodos for q in (1, 2, 3, 4)):
                equipos_validos.add(nombre)
        completos[ident] = equipos_validos
    completos_ambos = sum(len(completos.get(fila['id'], set())) == 2
                         for _, fila in base.iterrows())
    completos_uno = sum(len(completos.get(fila['id'], set())) == 1
                        for _, fila in base.iterrows())
    consultados = sum(ident in detalles for ident in ids_base)
    sin_consulta = len(base) - consultados
    elegibles = 0
    con_objetivo = 0
    sin_antecedentes = 0
    ejemplos = []
    for _, juego in base.iterrows():
        ident = juego['id']
        local, visita = str(juego['local']), str(juego['visitante'])
        if len(completos.get(ident, set())) != 2:
            continue
        con_objetivo += 1
        anteriores = base.loc[base['fecha_dt'].lt(juego['fecha_dt'])]
        cantidades = {}
        for equipo in (local, visita):
            previos = anteriores.loc[(anteriores['local'].eq(equipo)) |
                                     (anteriores['visitante'].eq(equipo))].tail(10)
            cantidades[equipo] = sum(equipo in completos.get(i, set()) for i in previos['id'])
        if min(cantidades.values()) >= 3:
            elegibles += 1
        else:
            sin_antecedentes += 1
            if len(ejemplos) < 5:
                ejemplos.append({'Partido': f'{visita} @ {local}',
                                 'Fecha': str(juego['fecha_dt'])[:10],
                                 'Previos local': cantidades[local],
                                 'Previos visitante': cantidades[visita]})
    return {'historicos': len(base), 'consultados': consultados,
            'sin_consulta': sin_consulta,
            'completos_ambos': completos_ambos, 'completos_uno': completos_uno,
            'consultados_sin_ambos': consultados - completos_ambos,
            'con_objetivo': con_objetivo, 'sin_antecedentes': sin_antecedentes,
            'elegibles': elegibles, 'ejemplos': ejemplos}


def _panel_validacion_historica(partidos, partido):
    with st.expander('🧪 Validación histórica de equipos · sin datos futuros'):
        st.caption('Cada evaluación usa únicamente partidos anteriores al encuentro evaluado. '
                   'Se requieren al menos 3 partidos anteriores por equipo. '
                   'La evaluación se limita al calendario consultado.')
        fecha = pd.to_datetime(partido['fecha_utc'], utc=True, errors='coerce')
        if pd.isna(fecha):
            st.info('No hay fecha verificable para la evaluación.')
            return
        clave = f"ri_nba_validacion_detalles_{partido['id']}"
        detalles = st.session_state.get(clave)
        # Para una evaluación cronológica hacen falta partidos antiguos:
        # consultar únicamente los 35 MÁS RECIENTES sesga la cobertura.
        base = partidos.loc[partidos['finalizado'].eq(True)].copy()
        base['fecha_dt'] = pd.to_datetime(base['fecha_utc'], utc=True, errors='coerce')
        base = base.dropna(subset=['fecha_dt'])
        base = base.loc[base['fecha_dt'].lt(fecha)].sort_values(['fecha_dt', 'id'])
        base['id'] = base['id'].astype(str)
        base = base.drop_duplicates('id')
        cantidad = st.selectbox(
            'Cobertura de detalles históricos (consultas máximas)',
            [35, 70, 100], index=1, key='ri_nba_validacion_cantidad',
            help='Se priorizan partidos antiguos para poder evaluar encuentros posteriores. '
                 'Una cobertura mayor puede tardar y recibir límites de ESPN.')
        disponibles = len(base)
        st.caption(f'Calendario disponible: {disponibles} partidos anteriores al encuentro. '
                   'Se consultarán primero los más antiguos, sin usar partidos futuros.')
        if st.button('📥 Consultar períodos para validación histórica',
                     key='ri_nba_validacion_btn'):
            seleccion = base.head(cantidad)
            # Reutilizar los resultados previamente recuperados y no repetir solicitudes.
            detalles = dict(detalles) if isinstance(detalles, dict) else {}
            fallos = 0
            nuevos = 0
            with st.spinner('Consultando períodos históricos disponibles...'):
                for identificador in seleccion['id']:
                    if identificador in detalles and detalles[identificador]:
                        continue
                    try:
                        datos_periodos = _puntos_periodos(cargar_detalle(identificador))
                        detalles[identificador] = datos_periodos
                        nuevos += 1
                    except Exception:
                        fallos += 1
            st.session_state[clave] = detalles
            st.session_state[clave + '_fallos'] = fallos
            st.session_state[clave + '_nuevos'] = nuevos
        if detalles is not None:
            with st.expander('🔎 Diagnóstico de cobertura por cuartos', expanded=True):
                diag = _diagnostico_cuartos_historicos(partidos, fecha, detalles)
                if 'error' in diag:
                    st.warning(diag['error'])
                else:
                    st.write(f"Partidos históricos en el calendario: **{diag['historicos']}**")
                    st.write(f"Partidos con detalle consultado: **{diag['consultados']}** · sin consultar: **{diag['sin_consulta']}**")
                    st.write(f"Cuatro cuartos completos de ambos equipos: **{diag['completos_ambos']}**")
                    st.write(f"Cuatro cuartos completos de un solo equipo: **{diag['completos_uno']}**")
                    st.write(f"Consultados sin los cuatro cuartos de ambos: **{diag['consultados_sin_ambos']}**")
                    st.write(f"Objetivos con marcador reglamentario verificable: **{diag['con_objetivo']}**")
                    st.write(f"Objetivos sin 3 antecedentes por equipo: **{diag['sin_antecedentes']}**")
                    st.write(f"Objetivos elegibles para validar cuartos: **{diag['elegibles']}**")
                    if diag['ejemplos']:
                        st.caption('Ejemplos de objetivos sin antecedentes suficientes:')
                        st.dataframe(pd.DataFrame(diag['ejemplos']), hide_index=True,
                                     use_container_width=True)
                    if diag['elegibles'] == 0:
                        if diag['sin_antecedentes']:
                            st.warning('Todavía no hay 3 partidos anteriores con cuartos completos '
                                       'para ambos equipos de un mismo encuentro evaluable. '
                                       'Al inicio de temporada puede ser normal; amplía el período '
                                       'del calendario y/o la cobertura de detalles.')
                        elif diag['sin_consulta']:
                            st.warning('Hay partidos anteriores sin consultar. Aumenta la cobertura '
                                       'de detalles históricos para intentar recuperar antecedentes.')
                        else:
                            st.info('No hay objetivos elegibles con los datos disponibles. '
                                    'No se calculará un MAE artificial.')
                    st.caption('La evaluación utiliza únicamente datos anteriores al partido. '
                               'La ventana de 10 partidos y el calendario consultado limitan la cobertura.')
        resultados = _validacion_historica_equipos(partidos, fecha, detalles)
        if resultados.empty:
            st.info('Aún no hay partidos con suficiente historial previo para validar los métodos.')
            return
        for titulo, pred, real in (
            ('Ataque y defensa · marcador completo', 'ataque', 'real_completo'),
            ('Cuartos 1–4 · tiempo reglamentario', 'cuartos', 'real_reglamentario'),
        ):
            validos = resultados.dropna(subset=[pred, real]).copy()
            st.markdown(f'**{titulo}**')
            if validos.empty:
                st.info('Sin evaluaciones suficientes para este método con los datos recuperados.')
                continue
            validos['Error'] = (validos[pred] - validos[real]).abs()
            st.metric('Error absoluto medio (MAE)', f"{validos['Error'].mean():.1f} pts")
            sesgo = float((validos[pred] - validos[real]).mean())
            st.metric('Sesgo promedio (estimado − observado)', f'{sesgo:+.1f} pts')
            st.caption('Sesgo positivo: sobreestimación promedio; negativo: subestimación. MAE no equivale a probabilidad de acierto.')
            if len(validos) < 20:
                st.info('Precisión provisional: menos de 20 evaluaciones históricas comparables.')
            st.caption(f"{len(validos)} evaluaciones cronológicas · mediana del error: {validos['Error'].median():.1f} pts")
            if len(validos) < 10:
                st.warning('Muestra pequeña: todavía no permite conclusiones firmes sobre precisión.')
            with st.expander(f'📋 Partidos evaluados · {titulo}'):
                tabla = validos[['Fecha', 'Partido', pred, real, 'Error']].copy()
                tabla.columns = ['Fecha', 'Partido', 'Estimado', 'Observado', 'Error']
                st.dataframe(tabla.round(1), hide_index=True, use_container_width=True)
        if detalles is None:
            st.caption('Para evaluar el método por cuartos, pulsa el botón de consulta de períodos históricos.')
        else:
            st.caption(f"Detalles históricos consultados: {len(detalles)} · fallos: {st.session_state.get(clave + '_fallos', 0)}. "
                       'Solo se utilizan períodos observados; cobertura parcial posible.')
        st.caption('Los errores de ambos métodos pueden proceder de partidos y objetivos distintos '
                   '(marcador completo frente a reglamentario). No son una comparación directa '
                   'si las muestras no coinciden. Los resultados no garantizan desempeño futuro.')


def _mostrar_proyeccion_equipos(partidos, partido):
    """Estimaciones descriptivas por equipo, total y períodos con datos reales."""
    local, visita = str(partido['local']), str(partido['visitante'])
    fecha = pd.to_datetime(partido['fecha_utc'], utc=True, errors='coerce')
    st.markdown(f'### 🏀 Próximo encuentro: {visita} @ {local}')
    st.caption(f"Calendario consultado: {str(partido['fecha_utc'])[:16]} UTC. Solo se consideran resultados anteriores al encuentro.")
    datos = {e: _historial_equipo(partidos, e, fecha) for e in (local, visita)}
    # Auditoría informativa: no cambia las muestras ni las fórmulas existentes.
    with st.expander('🧪 Auditoría de datos de equipos'):
        for nombre in (local, visita):
            base = partidos.loc[(partidos['local'].eq(nombre) | partidos['visitante'].eq(nombre)) &
                                partidos['finalizado'].eq(True)].copy()
            fechas_base = pd.to_datetime(base['fecha_utc'], utc=True, errors='coerce')
            base = base.loc[fechas_base.lt(fecha)].copy()
            ids = base['id'].astype(str) if 'id' in base else pd.Series(dtype=str)
            duplicados_id = int(ids.duplicated().sum())
            columnas = ['fecha_utc', 'local', 'visitante']
            duplicados_encuentro = int(base.duplicated(subset=columnas).sum()) if all(c in base for c in columnas) else 0
            sin_marcador = int(base[['puntos_local', 'puntos_visitante']].isna().any(axis=1).sum())
            st.write(f'**{nombre}** · registros finalizados: {len(base)} · IDs repetidos: {duplicados_id} · coincidencias fecha/equipos: {duplicados_encuentro} · sin marcador: {sin_marcador}')
            if duplicados_id or duplicados_encuentro or sin_marcador:
                st.warning('Se detectaron incidencias en el calendario consultado. La auditoría no modifica automáticamente los registros.')
        st.caption('Esta revisión solo cubre el intervalo consultado; no certifica que ESPN incluya todos los partidos de la temporada.')
    for e in (local, visita):
        d = datos[e]
        st.markdown(f'**{e} · {len(d)} partidos disponibles**')
        if d.empty:
            st.info('Sin resultados anteriores en el período consultado.')
            continue
        c1, c2, c3 = st.columns(3)
        c1.metric('Victorias', int(d['Resultado'].eq('V').sum()))
        c2.metric('PF/PJ', f"{d['PF'].mean():.1f}")
        c3.metric('PC/PJ', f"{d['PC'].mean():.1f}")
        with st.expander(f'📈 Forma reciente · {e}'):
            for n in (5, 10, 20):
                ult = d.tail(n)
                st.write(f'Últimos {len(ult)} (ventana {n}): PF {ult["PF"].mean():.1f} · PC {ult["PC"].mean():.1f} · V {int(ult["Resultado"].eq("V").sum())}')
            sede = 'Local' if e == local else 'Visitante'
            ds = d[d['Sede'].eq(sede)]
            st.write(f'{sede}: {len(ds)} partidos · PF {ds["PF"].mean():.1f}' if len(ds) else f'{sede}: sin muestra')
    # Media de ataque y defensa del oponente, sin introducir datos futuros.
    estim = {}
    for e, rival in ((local, visita), (visita, local)):
        propios = _media_rango(datos[e]['PF']) if not datos[e].empty else None
        recibidos = _media_rango(datos[rival]['PC']) if not datos[rival].empty else None
        if propios and recibidos:
            estim[e] = {'media': (propios['media']+recibidos['media'])/2,
                        'n': min(propios['n'], recibidos['n'])}
    st.markdown('#### 📊 Puntos descriptivos · partido completo')
    if len(estim) == 2:
        c1, c2, c3 = st.columns(3)
        c1.metric('Local', f"{estim[local]['media']:.1f}")
        c2.metric('Visitante', f"{estim[visita]['media']:.1f}")
        c3.metric('Total', f"{sum(x['media'] for x in estim.values()):.1f}")
        st.caption('Media simple del ataque reciente de cada equipo y puntos recibidos por el rival (máximo 10 juegos). No es una predicción calibrada. Los marcadores finales históricos pueden incluir prórrogas.')
    else:
        st.info('Se requieren al menos 3 partidos con marcadores completos de cada equipo para estimar puntos del partido.')
    # La validación es auxiliar: un error no debe interrumpir el resumen de equipos.
    try:
        _panel_validacion_historica(partidos, partido)
    except (KeyError, ValueError, TypeError, IndexError) as exc:
        with st.expander('🧪 Validación histórica de equipos · diagnóstico'):
            st.warning('No fue posible completar la validación histórica. Las demás estadísticas siguen disponibles.')
            st.code(f'{type(exc).__name__}: {exc}', language='text')
            st.caption('Comparte este mensaje para identificar la causa exacta; no se inventan resultados.')
    with st.expander('⏱️ Cuartos y mitades · datos reales'):
        st.caption('Consulta automática de hasta 10 partidos finalizados por equipo; resultados reutilizados en esta sesión. ESPN puede limitar las consultas.')
        clave = f"ri_nba_periodos_{partido['id']}"
        # Recuperación automática, limitada y compartida entre partidos de la sesión.
        juegos = {}
        for e, d in datos.items():
            for fila in d.tail(10).itertuples(index=False):
                juegos[str(fila.id)] = fila
        cache = st.session_state.setdefault('ri_nba_cache_cuartos_v17', {})
        pendientes = [ident for ident in juegos if ident not in cache]
        if pendientes:
            with st.spinner(f'Recuperando automáticamente {len(pendientes)} boxscores de cuartos...'):
                for identificador in pendientes:
                    try:
                        cache[identificador] = _puntos_periodos(cargar_detalle(identificador))
                    except Exception:
                        cache[identificador] = None
        muestras = {e: [] for e in (local, visita)}
        errores = 0
        for identificador in juegos:
            info = cache.get(identificador)
            if not isinstance(info, dict) or not info:
                errores += 1
                continue
            for e in muestras:
                if e in info:
                    muestras[e].append(info[e])
        st.session_state[clave] = {'muestras': muestras, 'errores': errores}
        guardado = st.session_state.get(clave)
        if guardado:
            st.markdown('### 🏀 Estimación de puntos para el próximo partido')
            st.markdown(f'**{visita} 🆚 {local}**')
            fecha_utc = pd.to_datetime(partido['fecha_utc'], utc=True, errors='coerce')
            if pd.notna(fecha_utc):
                fecha_local = fecha_utc.tz_convert(ZoneInfo('America/Mazatlan'))
                st.caption(f"📅 Fecha programada: {fecha_local.strftime('%d/%m/%Y · %H:%M')} (Sinaloa) · {fecha_utc.strftime('%d/%m/%Y · %H:%M')} UTC")
            else:
                st.caption('📅 Fecha programada no disponible')
            st.markdown('**📊 Estimación estadística por cuartos, mitades y final reglamentario**')
            muestras = guardado['muestras']
            st.caption(f"Muestra de períodos: {len(muestras[local])} partidos de {local} · {len(muestras[visita])} de {visita}.")
            st.caption(f"Partidos con consulta fallida: {guardado['errores']}. No se sustituyen valores ausentes.")
            periodos = [('1.er cuarto', [1]), ('2.º cuarto', [2]), ('Primera mitad', [1,2]),
                        ('3.er cuarto', [3]), ('4.º cuarto', [4]), ('Segunda mitad', [3,4]),
                        ('Final reglamentario', [1,2,3,4])]
            # Encabezados breves para móvil; los nombres completos permanecen arriba.
            col_local = _abreviatura_equipo(local)
            col_visita = _abreviatura_equipo(visita)
            if col_local == col_visita:
                col_local, col_visita = 'Local', 'Visita'
            st.caption(f'{col_local} = {local} (local) · {col_visita} = {visita} (visitante)')
            filas = []
            for etiqueta, cuartos in periodos:
                resultados = {}
                for e in (local, visita):
                    observados = [sum(x[q] for q in cuartos) for x in muestras[e] if all(q in x for q in cuartos)]
                    resultados[e] = _media_rango(observados)
                a, b = resultados[local], resultados[visita]
                filas.append({'Período': etiqueta,
                              col_local: round(a['media'],1) if a else 'N/D',
                              col_visita: round(b['media'],1) if b else 'N/D',
                              'Total': round(a['media']+b['media'],1) if a and b else 'N/D'})
            st.dataframe(pd.DataFrame(filas), hide_index=True, use_container_width=True)
            with st.expander('🧪 Auditoría de estimaciones y cobertura'):
                st.write(f'Partidos con cuartos completos: {local} = {len(muestras[local])}; {visita} = {len(muestras[visita])}.')
                st.write(f'Consultas fallidas de detalle: {guardado["errores"]}.')
                st.caption('La tabla por cuartos utiliza medias de puntos observados en períodos reglamentarios; el cálculo de partido completo combina ataque y defensa y puede incluir prórrogas en los marcadores históricos.')
                if len(estim) == 2:
                    total_completo = sum(x['media'] for x in estim.values())
                    ult = filas[-1]
                    total_periodos = ult.get('Total')
                    if isinstance(total_periodos, (float, int)):
                        diferencia = total_completo - total_periodos
                        st.metric('Diferencia: cálculo completo menos suma de cuartos', f'{diferencia:+.1f} pts')
                        st.write(f'Partido completo (ataque/defensa): {total_completo:.1f} pts · Cuartos 1–4: {total_periodos:.1f} pts.')
                        st.caption('La diferencia no demuestra un error: las metodologías y las muestras son distintas. No se promedian ni se sustituyen entre sí.')
                    else:
                        st.info('No hay suficientes períodos observados para comparar los dos totales.')
                else:
                    st.info('No hay datos suficientes para comparar las dos estimaciones de partido completo.')
                if min(len(muestras[local]), len(muestras[visita])) < 10:
                    st.warning('Muestra limitada: los promedios pueden variar considerablemente con nuevos partidos.')
            st.caption('Estimaciones basadas en partidos anteriores: no son marcadores confirmados ni resultados garantizados. N/D = menos de 3 partidos con cuartos observados. Las medias por cuarto son descriptivas; la suma de medias no garantiza un marcador. Prórrogas excluidas de los cuartos 1–4.')
        else:
            st.info('No hay períodos completos suficientes para estimar cuartos; no se sustituyen valores ausentes.')


def _panel_equipos(partidos, elegidos):
    st.markdown('### 🏟️ Comparación y próximos encuentros')
    proximos = {}
    for nombre in elegidos:
        _mostrar_equipo(partidos, nombre)
        proximo = _proximo_partido(partidos, nombre)
        if proximo is not None:
            proximos[str(proximo['id'])] = proximo
            rival = proximo['visitante'] if proximo['local'] == nombre else proximo['local']
            st.caption(f"Próximo partido listado: {str(proximo['fecha_utc'])[:16]} UTC · vs. {rival}")
    if proximos:
        opciones = {f"{p['visitante']} @ {p['local']} · {str(p['fecha_utc'])[:10]}": p for p in proximos.values()}
        elegido = st.selectbox('Partido para análisis de puntos', list(opciones), key='ri_nba_partido_equipos')
        _mostrar_proyeccion_equipos(partidos, opciones[elegido])
    elif elegidos:
        st.info('No hay próximo encuentro programado para los equipos seleccionados en el período consultado.')

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




def _auditar_participacion(datos):
    """Devuelve registros anotados y válidos sin transformar ausencias en ceros."""
    d = datos.copy()
    d['partido_id'] = d['partido_id'].astype(str)
    d = d.drop_duplicates(['jugador', 'equipo', 'partido_id'], keep='last')
    metricas = [m for m in ('Puntos', 'Rebotes', 'Asistencias', 'Minutos', 'Robos', 'Tapones', 'Pérdidas') if m in d]
    for m in metricas:
        d[m] = pd.to_numeric(d[m], errors='coerce')
    if 'Minutos' in d:
        mins = d['Minutos']
        otros = [m for m in metricas if m != 'Minutos']
        con_estadisticas = d[otros].notna().any(axis=1) if otros else pd.Series(False, index=d.index)
        # Un cero explícito en minutos no acredita participación, aunque exista otra estadística.
        d['Motivo'] = 'Incluido'
        d.loc[mins.eq(0), 'Motivo'] = '0 minutos registrados'
        d.loc[mins.isna() & ~con_estadisticas, 'Motivo'] = 'Minutos y estadísticas ausentes'
        d.loc[mins.isna() & con_estadisticas, 'Motivo'] = 'Minutos ausentes; estadísticas observadas'
    else:
        d['Motivo'] = 'Minutos ausentes; revisar estadísticas'
    d['Incluido'] = ~d['Motivo'].isin(['0 minutos registrados', 'Minutos y estadísticas ausentes'])
    return d, d.loc[d['Incluido']].copy(), metricas


def _proyectar_puntos(historial, partidos, equipo):
    """Resumen descriptivo, sin garantía predictiva ni información futura."""
    if 'Puntos' not in historial:
        return {'error': 'No hay columna de puntos.'}
    d = historial.copy()
    d['fecha_dt'] = pd.to_datetime(d['fecha'], utc=True, errors='coerce')
    d = d.dropna(subset=['fecha_dt']).sort_values(['fecha_dt', 'partido_id'])
    proximo = _proximo_partido(partidos, equipo) if equipo != 'Todos' else None
    if proximo is not None:
        fecha_prox = pd.to_datetime(proximo['fecha_utc'], utc=True, errors='coerce')
        if pd.notna(fecha_prox):
            d = d.loc[d['fecha_dt'].lt(fecha_prox)].copy()
    d['Puntos'] = pd.to_numeric(d['Puntos'], errors='coerce')
    d = d.dropna(subset=['Puntos'])
    if len(d) < 5:
        return {'error': f'Muestra insuficiente: {len(d)} partidos con puntos (mínimo 5).'}
    puntos = d['Puntos']
    recientes = puntos.tail(min(10, len(puntos)))
    centro = float(recientes.mean())
    dispersion = float(recientes.std(ddof=1)) if len(recientes) > 1 else 0.0
    ventanas = {n: {'media': float(puntos.tail(n).mean()), 'n': min(n, len(puntos))}
                for n in (5, 10, 20)}
    minutos = None
    if 'Minutos' in d:
        m = pd.to_numeric(d['Minutos'], errors='coerce').dropna()
        if not m.empty:
            minutos = {'reciente': float(m.tail(5).mean()),
                       'historico': float(m.mean()), 'n': len(m)}
    # Validación cronológica: cada predicción usa únicamente partidos previos.
    errores = []
    valores = puntos.to_numpy(dtype=float)
    for i in range(5, len(valores)):
        estimado = float(valores[max(0, i-10):i].mean())
        errores.append(abs(estimado - float(valores[i])))
    validacion = {'n': len(errores), 'mae': float(sum(errores)/len(errores)) if errores else None}
    rival_info = None
    if proximo is not None:
        rival = str(proximo['visitante'] if proximo['local'] == equipo else proximo['local'])
        if not partidos.empty and {'finalizado', 'local', 'visitante', 'puntos_local', 'puntos_visitante'}.issubset(partidos.columns):
            anteriores = partidos.loc[partidos['finalizado'].eq(True) &
                (partidos['local'].eq(rival) | partidos['visitante'].eq(rival))].copy()
            fecha_prox = pd.to_datetime(proximo['fecha_utc'], utc=True, errors='coerce')
            anteriores['fecha_dt'] = pd.to_datetime(anteriores['fecha_utc'], utc=True, errors='coerce')
            anteriores = anteriores.loc[anteriores['fecha_dt'].lt(fecha_prox)].sort_values('fecha_dt')
            contra = anteriores['puntos_visitante'].where(anteriores['local'].eq(rival), anteriores['puntos_local'])
            contra = pd.to_numeric(contra, errors='coerce').dropna().tail(10)
            if not contra.empty:
                rival_info = {'rival': rival, 'media_recibida': float(contra.mean()), 'n': len(contra)}
    return {'centro': centro, 'bajo': max(0., centro-dispersion), 'alto': centro+dispersion,
            'n': len(recientes), 'total': len(puntos), 'proximo': proximo,
            'ventanas': ventanas, 'minutos': minutos, 'validacion': validacion,
            'rival_info': rival_info}


def _diagnostico_y_validacion_individual(original, validos, nombre):
    """Cobertura por métrica y prueba cronológica, sin usar resultados futuros."""
    todos = original.loc[original['jugador'].eq(nombre)].copy()
    d = validos.loc[validos['jugador'].eq(nombre)].copy()
    if todos.empty:
        return
    st.markdown(f"**🔎 Cobertura y validación · {nombre}**")
    st.caption(f"Recuperados: {len(todos)} · participación válida: {len(d)} · excluidos: {len(todos)-len(d)}")
    filas = []
    for metrica in ('Puntos', 'Rebotes', 'Asistencias', 'Minutos'):
        if metrica not in d.columns:
            continue
        orden = d.sort_values(['fecha', 'partido_id']) if {'fecha', 'partido_id'}.issubset(d.columns) else d
        serie = pd.to_numeric(orden[metrica], errors='coerce').dropna()
        n = len(serie)
        if n >= 5:
            ultimos = serie.tail(10)
            media = float(ultimos.mean())
            desv = float(ultimos.std(ddof=1))
            errores = [
                abs(float(serie.iloc[i-10:i].mean()) - float(serie.iloc[i]))
                for i in range(5, n)
            ]
            filas.append({
                'Métrica': metrica, 'Válidos': n,
                'Media reciente': round(media, 1),
                'Rango bajo': round(max(0., media-desv), 1),
                'Rango alto': round(media+desv, 1),
                'MAE histórico': round(sum(errores)/len(errores), 1) if errores else None,
                'Evaluaciones': len(errores),
            })
        else:
            filas.append({'Métrica': metrica, 'Válidos': n,
                          'Media reciente': None, 'Rango bajo': None,
                          'Rango alto': None, 'MAE histórico': None,
                          'Evaluaciones': 0})
    if filas:
        evaluadas = [f for f in filas if f['Evaluaciones'] >= 5 and f['MAE histórico'] is not None]
        with st.expander('📐 Calidad y precisión de las estimaciones', expanded=True):
            st.caption('La calidad de muestra y el error retrospectivo no garantizan resultados futuros.')
            st.write(f'Métricas con estimación habilitada: **{sum(f["Válidos"] >= 5 for f in filas)}/{len(filas)}**.')
            st.write(f'Métricas con al menos 5 evaluaciones retrospectivas: **{len(evaluadas)}/{len(filas)}**.')
            if evaluadas:
                for f in evaluadas:
                    st.write(f'{f["Métrica"]}: MAE {f["MAE histórico"]:.1f} · {f["Evaluaciones"]} evaluaciones.')
            else:
                st.info('Precisión todavía no evaluable: se necesitan al menos 10 registros válidos para reunir 5 comparaciones cronológicas.')
            st.caption('MAE = distancia absoluta media entre estimación histórica y resultado real; no es una probabilidad de acierto.')
        st.dataframe(pd.DataFrame(filas).fillna('N/D'), hide_index=True, use_container_width=True)
        if any(f['Válidos'] < 5 for f in filas):
            st.info('Las métricas con menos de 5 registros válidos quedan sin estimación; sus promedios observados siguen disponibles en las tarjetas.')
        st.caption('Rango = media ± 1 desviación estándar (descriptivo, no intervalo calibrado). MAE = error medio al estimar cada partido con los 5–10 anteriores; requiere al menos 6 registros. Sin datos futuros.')
        csv = pd.DataFrame(filas).to_csv(index=False).encode('utf-8-sig')
        st.download_button('⬇️ Exportar diagnóstico CSV', csv,
                           f"diagnostico_nba_{str(nombre).replace(' ', '_')}.csv",
                           'text/csv', key=f"ri_nba_diag_{str(nombre)}")


def _pronostico_estadistico(serie, ventana=10):
    """Estimación retrospectiva sin fuga temporal; incertidumbre descriptiva."""
    v = pd.to_numeric(serie, errors='coerce').dropna().tail(ventana)
    if len(v) < 3:
        return None
    promedio = float(v.mean())
    desviacion = float(v.std(ddof=1)) if len(v) > 1 else 0.0
    # Intervalo descriptivo aproximado para el resultado individual, no IC formal.
    bajo = max(0., promedio - 1.28 * desviacion)
    alto = promedio + 1.28 * desviacion
    errores = []
    completos = pd.to_numeric(serie, errors='coerce').dropna()
    for i in range(5, len(completos)):
        pred = float(completos.iloc[max(0, i-10):i].mean())
        errores.append(abs(pred - float(completos.iloc[i])))
    return {'media': round(promedio, 1), 'bajo': round(bajo, 1),
            'alto': round(alto, 1), 'n': len(v),
            'mae': round(sum(errores)/len(errores), 2) if errores else None,
            'pruebas': len(errores)}


def _panel_proximo_jugador(historial, partidos, nombre):
    """Contexto del próximo encuentro con datos observados; no usa información futura."""
    if historial.empty or not {'equipo', 'fecha', 'partido_id'}.issubset(historial.columns):
        return
    d = historial.copy()
    d['fecha_dt'] = pd.to_datetime(d['fecha'], utc=True, errors='coerce')
    d = d.dropna(subset=['fecha_dt']).sort_values(['fecha_dt', 'partido_id'])
    if d.empty:
        return
    equipo = str(d['equipo'].iloc[-1])
    proximo = _proximo_partido(partidos, equipo)
    with st.expander(f'🗓️ Próximo encuentro · {nombre}', expanded=True):
        if proximo is None:
            st.info('No hay próximo encuentro futuro del equipo en el calendario consultado.')
        else:
            rival = str(proximo['visitante'] if str(proximo['local']) == equipo else proximo['local'])
            fecha = pd.to_datetime(proximo['fecha_utc'], utc=True, errors='coerce')
            if pd.notna(fecha):
                d = d.loc[d['fecha_dt'].lt(fecha)].copy()
            st.write(f'**{equipo} vs. {rival}**')
            st.caption(f"Fecha del encuentro: {str(proximo['fecha_utc'])[:16]} UTC")
        if d.empty:
            st.info('No hay antecedentes válidos anteriores al próximo encuentro.')
            return
        filas = []
        for metrica in ('Puntos', 'Rebotes', 'Asistencias', 'Minutos'):
            if metrica not in d:
                continue
            valores = pd.to_numeric(d[metrica], errors='coerce').dropna()
            ult = valores.tail(10)
            filas.append({'Estadística': metrica,
                          'Registros': len(valores),
                          'Últimos 5': round(float(valores.tail(5).mean()), 1) if len(valores) else None,
                          'Últimos 10': round(float(ult.mean()), 1) if len(ult) else None,
                          'Estimación descriptiva': round(float(ult.mean()), 1) if len(ult) >= 5 else None})
        st.markdown('**🏀 Proyección estadística · próximo partido**')
        pronosticos = []
        for metrica in ('Puntos', 'Rebotes', 'Asistencias'):
            if metrica not in d:
                continue
            p = _pronostico_estadistico(d[metrica])
            if p is None:
                pronosticos.append({'Estadística': metrica, 'Estimación': 'N/D',
                                    'Rango orientativo': 'N/D', 'Partidos': int(pd.to_numeric(d[metrica], errors='coerce').notna().sum()),
                                    'MAE histórico': 'N/D', 'Validaciones': 0, 'Calidad': 'Datos insuficientes'})
                continue
            pronosticos.append({'Estadística': metrica, 'Estimación': p['media'],
                                'Rango orientativo': f"{p['bajo']} – {p['alto']}",
                                'Partidos': p['n'],
                                'MAE histórico': p['mae'] if p['mae'] is not None else 'N/D',
                                'Validaciones': p['pruebas'],
                                'Calidad': 'Exploratoria' if p['n'] < 5 or p['pruebas'] < 3 else 'Con validación inicial'})
        if pronosticos:
            df_pron = pd.DataFrame(pronosticos)
            st.dataframe(df_pron, hide_index=True, use_container_width=True)
            st.download_button('📥 Exportar proyección del próximo partido CSV',
                               df_pron.to_csv(index=False).encode('utf-8-sig'),
                               'nba_v3_3_proyeccion_proximo_partido.csv', 'text/csv',
                               key=f'ri_nba_v33_proximo_{nombre}', use_container_width=True)
            st.caption('Media de hasta 10 juegos previos; rango descriptivo ±1.28 desviaciones estándar, '
                       'no probabilidad calibrada. MAE calculado en orden cronológico, '
                       'usando al menos cinco partidos previos. No incluye lesiones ni cambios de rol.')
        if filas:
            st.dataframe(pd.DataFrame(filas).fillna('N/D'), hide_index=True, use_container_width=True)
            st.caption('Las estimaciones requieren 5 registros válidos por métrica. '
                       'Los promedios no son probabilidades ni garantizan resultados. '
                       'Sin ajuste por lesiones o disponibilidad no confirmadas.')


def _id_jugador_boxscore(detalle, nombre, equipo):
    """Identificación estricta por nombre y equipo del boxscore; nunca por texto de jugada."""
    encontrados = set()
    for bloque in detalle.get('boxscore', {}).get('players', []):
        if str(bloque.get('team', {}).get('displayName', '')) != str(equipo):
            continue
        for grupo in bloque.get('statistics', []):
            for fila in grupo.get('athletes', []):
                atleta = fila.get('athlete') or {}
                if atleta.get('displayName') == nombre and atleta.get('id') is not None:
                    encontrados.add(str(atleta['id']))
    return next(iter(encontrados)) if len(encontrados) == 1 else None


def _resumen_eventos_individuales(detalle, jugador_id):
    """Diagnóstico del play-by-play; no atribuye autorías ambiguas."""
    jugadas = detalle.get('plays')
    if not isinstance(jugadas, list):
        return None, 'Campo plays ausente o no es una lista'
    if not jugadas:
        return None, 'Sin jugadas individuales en el resumen ESPN'
    puntos = {q: 0 for q in range(1, 5)}
    ids_vistos, autores = set(), set()
    diag = {'Jugadas recibidas': len(jugadas), 'Jugadas únicas': 0,
            'Anotaciones': 0, 'Sin participantes': 0, 'Sin rol anotador': 0,
            'Sin ID anotador': 0, 'Anotaciones verificadas': 0,
            'Anotaciones del jugador': 0, 'Fuera de Q1–Q4': 0,
            'Puntos de prórroga': 0, 'Autor inferido por participante único': 0, 'Autor por orden ESPN (provisional)': 0, 'Esquemas participantes': set(),
            'Roles observados': set(), 'IDs observados': set()}
    for jugada in jugadas:
        if not isinstance(jugada, dict):
            continue
        identificador = str(jugada.get('id', '')).strip()
        if identificador and identificador in ids_vistos:
            continue
        if identificador:
            ids_vistos.add(identificador)
        diag['Jugadas únicas'] += 1
        if jugada.get('scoringPlay') is not True:
            continue
        diag['Anotaciones'] += 1
        try:
            periodo = int((jugada.get('period') or {}).get('number', 0))
            valor = int(jugada.get('scoreValue', 0))
        except (ValueError, TypeError, AttributeError):
            diag['Sin rol anotador'] += 1
            continue
        participantes = jugada.get('participants')
        if not isinstance(participantes, list) or not participantes:
            diag['Sin participantes'] += 1
            continue
        candidatos = []
        for p in participantes:
            if not isinstance(p, dict):
                continue
            diag['Esquemas participantes'].update(map(str, p.keys()))
            rol = str(p.get('type', p.get('role', ''))).lower()
            if rol:
                diag['Roles observados'].add(rol)
            atleta = p.get('athlete') or {}
            ident = atleta.get('id') if isinstance(atleta, dict) else None
            if ident is not None:
                diag['IDs observados'].add(str(ident))
            if rol in ('scorer', 'shooter', 'scoring', 'scoringplayer'):
                if ident is not None:
                    candidatos.append(str(ident))
                else:
                    diag['Sin ID anotador'] += 1
        # ESPN puede devolver un único participante {"athlete": {"id": ...}}
        # sin un campo role/type. Aceptamos ese ID solo como candidato
        # provisional; los cuartos se publican únicamente si el total
        # reconstruido coincide exactamente con el boxscore.
        if not candidatos:
            ids_participantes = {
                str(p['athlete']['id'])
                for p in participantes
                if isinstance(p, dict) and isinstance(p.get('athlete'), dict)
                and p['athlete'].get('id') is not None
            }
            if len(ids_participantes) == 1 and len(participantes) == 1:
                candidatos = list(ids_participantes)
                diag['Autor inferido por participante único'] += 1
            elif len(participantes) >= 2:
                # Diagnóstico CSV v2.6: en canastas con asistencia, ESPN suele
                # ordenar primero al anotador y después al asistente. Esta
                # atribución es PROVISIONAL y exige conciliar todo el boxscore.
                descripcion = str(jugada.get('text', ''))
                primer = participantes[0] if isinstance(participantes[0], dict) else {}
                atleta_primero = primer.get('athlete') or {}
                primero_id = atleta_primero.get('id') if isinstance(atleta_primero, dict) else None
                if primero_id is not None and (' makes ' in descripcion.lower() or
                                              ' made ' in descripcion.lower() or
                                              ' free throw ' in descripcion.lower()):
                    candidatos = [str(primero_id)]
                    diag['Autor por orden ESPN (provisional)'] += 1
        if len(set(candidatos)) != 1:
            diag['Sin rol anotador'] += 1
            continue
        diag['Anotaciones verificadas'] += 1
        if candidatos[0] == str(jugador_id):
            diag['Anotaciones del jugador'] += 1
            if periodo in puntos and valor in (1, 2, 3):
                puntos[periodo] += valor
            elif periodo > 4:
                diag['Puntos de prórroga'] += valor
            else:
                diag['Fuera de Q1–Q4'] += 1
    diag['IDs observados'] = ', '.join(sorted(diag['IDs observados'])[:8]) or 'N/D'
    diag['Roles observados'] = ', '.join(sorted(diag['Roles observados'])[:8]) or 'N/D'
    diag['Esquemas participantes'] = ', '.join(sorted(diag['Esquemas participantes'])[:12]) or 'N/D'
    return {'puntos': puntos, 'anotaciones': diag['Anotaciones'],
            'sin_autor_verificado': diag['Anotaciones']-diag['Anotaciones verificadas'],
            'diagnostico': diag}, None


def _muestras_anotaciones_ambiguas(detalle, jugador_id, partido_id, limite=35):
    """Ejemplos auditables de jugadas sin autor; no asigna puntos por heurísticas."""
    filas = []
    jugadas = detalle.get('plays') or []
    if not isinstance(jugadas, list):
        return filas
    vistos = set()
    for jugada in jugadas:
        if not isinstance(jugada, dict) or jugada.get('scoringPlay') is not True:
            continue
        clave = str(jugada.get('id', '')).strip()
        if clave and clave in vistos:
            continue
        if clave:
            vistos.add(clave)
        participantes = jugada.get('participants') or []
        if not isinstance(participantes, list):
            participantes = []
        ids = []
        roles = []
        for participante in participantes:
            if not isinstance(participante, dict):
                continue
            atleta = participante.get('athlete') or {}
            if isinstance(atleta, dict) and atleta.get('id') is not None:
                ids.append(str(atleta['id']))
            roles.append(str(participante.get('type') or participante.get('role') or 'N/D'))
        roles_autor = {'scorer', 'shooter', 'scoring', 'scoringplayer'}
        explicitos = [ident for ident, rol in zip(ids, roles) if rol.lower() in roles_autor]
        if len(set(explicitos)) == 1 or (len(participantes) == 1 and len(set(ids)) == 1):
            continue
        periodo = jugada.get('period') or {}
        reloj = jugada.get('clock') or {}
        filas.append({
            'Partido': partido_id, 'ID jugada': clave,
            'Cuarto': periodo.get('number') if isinstance(periodo, dict) else 'N/D',
            'Reloj': reloj.get('displayValue') if isinstance(reloj, dict) else 'N/D',
            'Puntos jugada': jugada.get('scoreValue'),
            'Descripción': str(jugada.get('text') or '')[:240],
            'Tipo': str((jugada.get('type') or {}).get('text') if isinstance(jugada.get('type'), dict) else jugada.get('type'))[:100],
            'Participantes': len(participantes), 'IDs participantes': ', '.join(ids),
            'Roles': ', '.join(roles), 'ID jugador': jugador_id,
            'Jugador entre participantes': str(jugador_id) in ids,
            'Campos jugada': ', '.join(sorted(map(str, jugada.keys()))),
        })
        if len(filas) >= limite:
            break
    return filas


def _motor_eventos_unificado(detalle, jugador_id):
    """Audita puntos/asistencias/rebotes con atribución conservadora y trazabilidad.

    Los datos de participantes se interpretan por texto y orden SOLO cuando
    corresponden a patrones claros; nunca se etiquetan como oficiales sin
    conciliar con el boxscore.
    """
    import re
    jugadas = detalle.get('plays') or []
    if not isinstance(jugadas, list):
        return pd.DataFrame(), 'plays no es una lista'
    filas, vistos = [], set()
    for j in jugadas:
        if not isinstance(j, dict):
            continue
        clave = str(j.get('id', '')).strip()
        if clave and clave in vistos:
            continue
        if clave:
            vistos.add(clave)
        periodo = j.get('period') or {}
        try:
            q = int(periodo.get('number', 0)) if isinstance(periodo, dict) else 0
        except (ValueError, TypeError):
            q = 0
        if q < 1:
            continue
        texto = str(j.get('text') or '')
        minus = texto.casefold()
        ps = j.get('participants') or []
        ids = [str(p['athlete']['id']) for p in ps
               if isinstance(p, dict) and isinstance(p.get('athlete'), dict)
               and p['athlete'].get('id') is not None]
        reloj = j.get('clock') or {}
        try:
            valor = int(j.get('scoreValue') or 0)
        except (TypeError, ValueError):
            valor = 0
        puntos = asistencias = rebotes = 0
        accion = 'Otra jugada'
        estado = 'No atribuida'
        # Las descripciones de ESPN indican explícitamente "makes" y "assists".
        # Solo asociar el primer ID al anotador si hay patrón textual claro.
        if j.get('scoringPlay') is True and valor in (1, 2, 3):
            accion = 'Anotación'
            if ids and re.search(r'\bmakes\b|\bmade\b', minus):
                if ids[0] == str(jugador_id):
                    puntos = valor
                estado = 'Candidato por texto y orden (sin conciliar)'
                if len(ids) >= 2 and ' assists)' in minus:
                    if ids[1] == str(jugador_id):
                        asistencias = 1
                    accion = 'Anotación con asistencia'
            else:
                estado = 'Anotador sin identificar'
        elif re.search(r'\brebound\b', minus):
            accion = 'Rebote'
            if ids and ids[0] == str(jugador_id) and not re.search(r'team rebound', minus):
                rebotes = 1
                estado = 'Candidato por texto y orden (sin conciliar)'
            elif 'team rebound' in minus:
                estado = 'Rebote de equipo, no individual'
        if puntos or asistencias or rebotes:
            filas.append({'ID jugada': clave, 'Cuarto': q,
                          'Reloj': reloj.get('displayValue', '') if isinstance(reloj, dict) else '',
                          'Acción': accion, 'Puntos': puntos, 'Asistencias': asistencias,
                          'Rebotes': rebotes, 'Estado': estado,
                          'IDs participantes': ', '.join(ids), 'Descripción': texto[:240]})
    return pd.DataFrame(filas, columns=['ID jugada','Cuarto','Reloj','Acción','Puntos',
                                        'Asistencias','Rebotes','Estado',
                                        'IDs participantes','Descripción']), None


def _auditoria_periodos_individuales(historial, nombre):
    """Auditoría de eventos ESPN sin sustituir ausencias por cero."""
    if historial.empty:
        return
    with st.expander(f'⏱️ Cuartos y mitades individuales · {nombre}'):
        st.caption('Revisión del play-by-play y conciliación con el boxscore. '
                   'Se prueba también el orden de participantes de ESPN; solo se publican períodos si todas las anotaciones quedan identificadas y el total coincide con el boxscore.')
        limite_auditoria = st.slider('Partidos para auditar por períodos', 1, 15, 10,
                                   key=f'ri_nba_auditoria_limite_{nombre}',
                                   help='Se consultan solo los partidos ya recuperados del historial. ESPN puede limitar la cobertura.')
        muestra = (historial.sort_values(['fecha', 'partido_id'], ascending=False)
                   .drop_duplicates('partido_id').head(limite_auditoria))
        resultados = []
        muestras_ambiguas = []
        eventos_unificados = []
        conciliaciones = []
        auditoria_rebotes_q4 = []
        for fila in muestra.to_dict('records'):
            pid = str(fila.get('partido_id', ''))
            if not pid.isdigit():
                resultados.append({'Fecha': fila.get('fecha'), 'Partido': pid, 'Estado': 'ID inválido'})
                continue
            try:
                detalle = cargar_detalle(pid)
                jugador_id = _id_jugador_boxscore(detalle, nombre, fila.get('equipo'))
                if not jugador_id:
                    resultados.append({'Fecha': fila.get('fecha'), 'Partido': pid, 'Estado': 'Jugador sin ID único en boxscore'})
                    continue
                muestras_ambiguas.extend(_muestras_anotaciones_ambiguas(detalle, jugador_id, pid))
                # Diagnóstico no destructivo: conservar TODOS los eventos de rebote
                # del cuarto período, incluso cuando no se atribuyan al jugador.
                for jugada in (detalle.get('plays') or []):
                    if not isinstance(jugada, dict):
                        continue
                    per = jugada.get('period') or {}
                    try:
                        cuarto = int(per.get('number', 0)) if isinstance(per, dict) else 0
                    except (TypeError, ValueError):
                        cuarto = 0
                    if cuarto != 4:
                        continue
                    descripcion = str(jugada.get('text') or '')
                    tipo_obj = jugada.get('type') or {}
                    tipo = str(tipo_obj.get('text') or '') if isinstance(tipo_obj, dict) else str(tipo_obj)
                    if 'rebound' not in (descripcion + ' ' + tipo).casefold():
                        continue
                    participantes = jugada.get('participants') or []
                    ids = [str(p.get('athlete', {}).get('id')) for p in participantes
                           if isinstance(p, dict) and isinstance(p.get('athlete'), dict)
                           and p['athlete'].get('id') is not None]
                    nombres = [str(p.get('athlete', {}).get('displayName') or '') for p in participantes
                               if isinstance(p, dict) and isinstance(p.get('athlete'), dict)]
                    texto_minus = descripcion.casefold()
                    equipo = ('team rebound' in texto_minus or 'team defensive rebound' in texto_minus
                              or 'team offensive rebound' in texto_minus)
                    auditoria_rebotes_q4.append({
                        'Fecha': fila.get('fecha'), 'Partido': pid,
                        'ID jugada': str(jugada.get('id') or ''),
                        'Cuarto': cuarto,
                        'Reloj': (jugada.get('clock') or {}).get('displayValue', '')
                                 if isinstance(jugada.get('clock'), dict) else '',
                        'Descripción': descripcion[:300], 'Tipo': tipo,
                        'IDs participantes': ', '.join(ids),
                        'Nombres participantes': ', '.join(nombres),
                        'ID jugador buscado': str(jugador_id),
                        'Jugador presente': str(jugador_id) in ids,
                        'Jugador primer participante': bool(ids) and ids[0] == str(jugador_id),
                        'Rebote de equipo por texto': equipo,
                        'Campos ESPN': ', '.join(sorted(map(str, jugada.keys()))),
                    })
                acciones, error_motor = _motor_eventos_unificado(detalle, jugador_id)
                if error_motor:
                    st.warning(f'Partido {pid}: {error_motor}')
                elif not acciones.empty:
                    acciones.insert(0, 'Partido', pid)
                    acciones.insert(0, 'Fecha', fila.get('fecha'))
                    eventos_unificados.append(acciones)
                # Conciliación por métrica y partido, incluyendo prórrogas.
                # No se validan períodos solo porque coincida una suma parcial.
                for metrica in ('Puntos', 'Asistencias', 'Rebotes'):
                    oficial = pd.to_numeric(fila.get(metrica), errors='coerce')
                    if error_motor or acciones.empty:
                        calculado = None
                        estado_m = 'Sin eventos'
                    else:
                        calculado = int(pd.to_numeric(acciones[metrica], errors='coerce').fillna(0).sum())
                        estado_m = ('Sin dato boxscore' if pd.isna(oficial) else
                                    'Coincide con boxscore (atribución provisional)' if calculado == oficial
                                    else 'Diferencia con boxscore')
                    conciliaciones.append({'Fecha': fila.get('fecha'), 'Partido': pid,
                                          'Métrica': metrica,
                                          'Boxscore': int(oficial) if pd.notna(oficial) else None,
                                          'Eventos': calculado,
                                          'Diferencia': calculado - int(oficial) if calculado is not None and pd.notna(oficial) else None,
                                          'Estado': estado_m})
                evento, error = _resumen_eventos_individuales(detalle, jugador_id)
                if error:
                    resultados.append({'Fecha': fila.get('fecha'), 'Partido': pid, 'Estado': error})
                    continue
                total = sum(evento['puntos'].values())
                puntos_oficiales = pd.to_numeric(fila.get('Puntos'), errors='coerce')
                # Los totales incluyen posible prórroga; la conciliación sólo
                # es concluyente si no hay puntos de prórroga y el PBP es completo.
                verificado = (evento['sin_autor_verificado'] == 0 and
                              pd.notna(puntos_oficiales) and total == puntos_oficiales)
                resultado = {'Fecha': fila.get('fecha'), 'Partido': pid,
                             'Estado': 'Conciliado' if verificado else 'Sin conciliar',
                             'Jugadas sin autor': evento['sin_autor_verificado'],
                             'Puntos boxscore': puntos_oficiales,
                             'Puntos PBP Q1–Q4': total,
                              **evento['diagnostico']}
                for q in range(1, 5):
                    resultado[f'Q{q}'] = evento['puntos'][q] if verificado else None
                resultados.append(resultado)
            except Exception as exc:
                resultados.append({'Fecha': fila.get('fecha'), 'Partido': pid,
                                   'Estado': f'Consulta fallida ({type(exc).__name__})'})
        tabla = pd.DataFrame(resultados)
        st.dataframe(tabla.fillna('N/D'), hide_index=True, use_container_width=True)
        st.download_button('📥 Exportar diagnóstico detallado CSV',
                           tabla.to_csv(index=False).encode('utf-8-sig'),
                           'nba_v2_4_auditoria_eventos.csv', 'text/csv',
                           key=f'ri_nba_diag_eventos_{nombre}')
        if muestras_ambiguas:
            st.subheader('🔬 Ejemplos de anotaciones sin autor identificado')
            st.caption('Hasta 35 jugadas por partido, con texto, tipo y participantes. '
                       'Estas muestras permiten revisar el formato real de ESPN sin atribuir puntos arbitrariamente.')
            muestra_df = pd.DataFrame(muestras_ambiguas)
            st.dataframe(muestra_df, hide_index=True, use_container_width=True)
            st.download_button('📥 Exportar jugadas ambiguas CSV',
                               muestra_df.to_csv(index=False).encode('utf-8-sig'),
                               'nba_v2_6_jugadas_ambiguas.csv', 'text/csv',
                               key=f'ri_nba_ambiguas_{nombre}')
        else:
            st.caption('No se encontraron jugadas ambiguas en la muestra consultada.')
        st.subheader('🔎 Diagnóstico de rebotes del cuarto período · v3.3.0')
        st.caption('Se inspeccionan todos los rebotes Q4 de los partidos consultados, '
                   'incluidos los de rivales y equipo. No se modifica ninguna atribución.')
        if auditoria_rebotes_q4:
            rebotes_q4_df = pd.DataFrame(auditoria_rebotes_q4).drop_duplicates(
                ['Partido', 'ID jugada', 'Descripción'])
            st.metric('Jugadas de rebote Q4 recuperadas', len(rebotes_q4_df))
            st.metric('Jugadas Q4 con ID del jugador',
                      int(rebotes_q4_df['Jugador presente'].sum()))
            st.dataframe(rebotes_q4_df, hide_index=True, use_container_width=True)
            st.download_button('📥 Exportar diagnóstico de rebotes Q4 CSV',
                               rebotes_q4_df.to_csv(index=False).encode('utf-8-sig'),
                               'nba_v3_2_rebotes_q4.csv', 'text/csv',
                               key=f'ri_nba_rebotes_q4_v32_{nombre}')
        else:
            st.info('No se recuperaron eventos identificados como rebote en Q4. '
                    'Esto no demuestra que no existieran rebotes; revisa cobertura ESPN.')
        st.subheader('🧩 Motor unificado · puntos, asistencias y rebotes')
        st.caption('Reconstrucción exploratoria basada en descripciones y orden de participantes. '
                   'Los valores NO son estadísticas oficiales hasta conciliar cada métrica '
                   'con el boxscore del mismo partido. No se usan para proyecciones.')
        if eventos_unificados:
            eventos_df = pd.concat(eventos_unificados, ignore_index=True)
            resumen = (eventos_df.groupby(['Fecha', 'Partido', 'Cuarto'], as_index=False)
                       [['Puntos', 'Asistencias', 'Rebotes']].sum())
            st.dataframe(resumen, hide_index=True, use_container_width=True)
            with st.expander('Ver eventos individuales y trazabilidad'):
                st.dataframe(eventos_df, hide_index=True, use_container_width=True)
            st.download_button('📥 Exportar eventos unificados CSV',
                               eventos_df.to_csv(index=False).encode('utf-8-sig'),
                               'nba_v2_8_eventos_unificados.csv', 'text/csv',
                               key=f'ri_nba_eventos_unificados_{nombre}')
        else:
            st.info('No se recuperaron eventos atribuibles para el jugador seleccionado.')
        st.subheader('✅ Conciliación independiente por estadística')
        st.caption('Comparación automática de puntos, asistencias y rebotes con el boxscore. '
                   'Una coincidencia numérica no garantiza atribución correcta de cada evento; '
                   'los períodos se muestran como reconstrucción provisional.')
        if conciliaciones:
            conciliacion_df = pd.DataFrame(conciliaciones)
            st.dataframe(conciliacion_df.fillna('N/D'), hide_index=True, use_container_width=True)
            st.download_button('📥 Exportar conciliación por métrica CSV',
                               conciliacion_df.to_csv(index=False).encode('utf-8-sig'),
                               'nba_v2_9_conciliacion_metricas.csv', 'text/csv',
                               key=f'ri_nba_conciliacion_{nombre}')
            if eventos_unificados:
                periodo_df = (eventos_df.groupby(['Fecha', 'Partido', 'Cuarto'], as_index=False)
                              [['Puntos', 'Asistencias', 'Rebotes']].sum())
                filas_periodos = []
                for (fecha, pid), g in periodo_df.groupby(['Fecha', 'Partido']):
                    for metrica in ('Puntos', 'Asistencias', 'Rebotes'):
                        c = conciliacion_df[(conciliacion_df['Partido'].astype(str) == str(pid)) &
                                            (conciliacion_df['Métrica'] == metrica)]
                        coincide = bool(len(c) and c.iloc[0]['Estado'].startswith('Coincide'))
                        if not coincide:
                            continue
                        cuartos = {int(r['Cuarto']): int(r[metrica]) for _, r in g.iterrows()}
                        filas_periodos.append({'Fecha': fecha, 'Partido': pid, 'Métrica': metrica,
                                               'Q1': cuartos.get(1, 0), 'Q2': cuartos.get(2, 0),
                                               'H1': cuartos.get(1, 0) + cuartos.get(2, 0),
                                               'Q3': cuartos.get(3, 0), 'Q4': cuartos.get(4, 0),
                                               'H2': cuartos.get(3, 0) + cuartos.get(4, 0),
                                               'Prórroga': sum(v for k, v in cuartos.items() if k > 4),
                                               'Total': sum(cuartos.values()),
                                               'Estado': 'Reconstrucción provisional; total coincide'})
                if filas_periodos:
                    st.markdown('**⏱️ Cuartos, mitades y prórrogas · totales coincidentes**')
                    periodos_conciliados = pd.DataFrame(filas_periodos)
                    st.dataframe(periodos_conciliados, hide_index=True, use_container_width=True)
                    # Panel descriptivo: solo totales conciliados con boxscore.
                    # No extrapola períodos ni mezcla prórroga con tiempo reglamentario.
                    st.markdown('**📈 Perfil histórico por períodos (muestra conciliada)**')
                    resumen_perfil = []
                    for metrica in ('Puntos', 'Asistencias', 'Rebotes'):
                        sub = periodos_conciliados[periodos_conciliados['Métrica'] == metrica].copy()
                        sub = sub.drop_duplicates('Partido')
                        cantidad = len(sub)
                        for tramo in ('Q1', 'Q2', 'H1', 'Q3', 'Q4', 'H2', 'Prórroga', 'Total'):
                            serie = pd.to_numeric(sub[tramo], errors='coerce').dropna()
                            resumen_perfil.append({
                                'Métrica': metrica, 'Período': tramo,
                                'Partidos conciliados': int(len(serie)),
                                'Media observada': round(float(serie.mean()), 2) if len(serie) else 'N/D',
                                'Rango observado': (f'{int(serie.min())}–{int(serie.max())}' if len(serie) else 'N/D'),
                                'Muestra suficiente (≥5)': 'Sí' if len(serie) >= 5 else 'No',
                            })
                    perfil_df = pd.DataFrame(resumen_perfil)
                    st.dataframe(perfil_df, hide_index=True, use_container_width=True)
                    st.download_button('📥 Exportar perfil histórico por períodos CSV',
                                       perfil_df.to_csv(index=False).encode('utf-8-sig'),
                                       'nba_v3_0_perfil_periodos.csv', 'text/csv',
                                       key=f'ri_nba_perfil_v30_{nombre}')
                    st.markdown('**🔮 Estimación por cuartos y mitades · puntos, rebotes y asistencias**')
                    proy_periodos = []
                    for metrica in ('Puntos', 'Rebotes', 'Asistencias'):
                        parte = periodos_conciliados.loc[periodos_conciliados['Métrica'].eq(metrica)]
                        parte = parte.drop_duplicates('Partido').sort_values(['Fecha', 'Partido'])
                        fila_proy = {'Estadística': metrica, 'Partidos conciliados': len(parte),
                                     'Estado': 'Exploratorio' if len(parte) < 5 else 'Muestra inicial'}
                        for tramo in ('Q1', 'Q2', 'H1', 'Q3', 'Q4', 'H2', 'Prórroga', 'Total'):
                            vals = pd.to_numeric(parte[tramo], errors='coerce').dropna().tail(10)
                            fila_proy[tramo] = round(float(vals.mean()), 1) if len(vals) >= 3 else None
                        proy_periodos.append(fila_proy)
                    df_proy_periodos = pd.DataFrame(proy_periodos)
                    st.dataframe(df_proy_periodos.fillna('N/D'), hide_index=True, use_container_width=True)
                    st.download_button('📥 Exportar estimaciones por períodos CSV',
                                       df_proy_periodos.to_csv(index=False).encode('utf-8-sig'),
                                       'nba_v3_3_proyeccion_periodos.csv', 'text/csv',
                                       key=f'ri_nba_v33_periodos_{nombre}', use_container_width=True)
                    st.caption('Promedios exploratorios de hasta 10 partidos conciliados. '
                               'La atribución por período sigue siendo provisional; '
                               'no utilizar como pronóstico validado. La prórroga se muestra separada.')
                    # Auditoría específica de cobertura por cuarto: un cero puede ser real
                    # o deberse a un evento no atribuido. No se declara verificado.
                    st.markdown('**🔎 Cobertura de eventos por período · auditoría**')
                    audit_filas = []
                    for metrica in ('Puntos', 'Asistencias', 'Rebotes'):
                        parte = periodos_conciliados.loc[periodos_conciliados['Métrica'].eq(metrica)]
                        for cuarto in ('Q1', 'Q2', 'Q3', 'Q4', 'Prórroga'):
                            valores = pd.to_numeric(parte[cuarto], errors='coerce').dropna()
                            audit_filas.append({
                                'Métrica': metrica, 'Período': cuarto,
                                'Partidos con total conciliado': int(len(valores)),
                                'Partidos con ≥1 acción': int((valores > 0).sum()),
                                'Partidos con cero acciones': int((valores == 0).sum()),
                                'Acciones acumuladas': int(valores.sum()) if len(valores) else 0,
                                'Advertencia': ('Revisar atribución de eventos: todos los valores son cero'
                                                if len(valores) >= 3 and (valores == 0).all()
                                                and cuarto != 'Prórroga' else ''),
                            })
                    cobertura_df = pd.DataFrame(audit_filas)
                    st.dataframe(cobertura_df, hide_index=True, use_container_width=True)
                    st.download_button('📥 Exportar auditoría de cobertura CSV',
                                       cobertura_df.to_csv(index=False).encode('utf-8-sig'),
                                       'nba_v3_1_cobertura_periodos.csv', 'text/csv',
                                       key=f'ri_nba_cobertura_v31_{nombre}')
                    st.caption('Cero acciones no significa automáticamente que ESPN esté incompleto. '
                               'La coincidencia con el boxscore valida el total, no la ubicación temporal de cada evento.')

                    # Evaluación cronológica: predicción ingenua = media de los
                    # cinco partidos anteriores; nunca utiliza el partido evaluado.
                    st.markdown('**🧪 Evaluación cronológica de medias por período**')
                    eval_filas = []
                    for metrica in ('Puntos', 'Asistencias', 'Rebotes'):
                        parte = (periodos_conciliados.loc[periodos_conciliados['Métrica'].eq(metrica)]
                                 .drop_duplicates('Partido').copy())
                        parte['_orden_fecha'] = pd.to_datetime(parte['Fecha'], errors='coerce', utc=True)
                        parte = parte.sort_values(['_orden_fecha', 'Partido'])
                        for tramo in ('Q1', 'Q2', 'H1', 'Q3', 'Q4', 'H2', 'Total'):
                            serie = pd.to_numeric(parte[tramo], errors='coerce').tolist()
                            errores = []
                            for i in range(5, len(serie)):
                                anteriores = serie[max(0, i-5):i]
                                if pd.notna(serie[i]) and len(anteriores) == 5 and all(pd.notna(x) for x in anteriores):
                                    errores.append(abs(float(serie[i]) - sum(anteriores)/5))
                            eval_filas.append({'Métrica': metrica, 'Período': tramo,
                                               'Evaluaciones': len(errores),
                                               'MAE histórico': round(sum(errores)/len(errores), 2) if errores else 'N/D',
                                               'Estado': 'Exploratorio' if len(errores) >= 3 else 'Muestra insuficiente'})
                    eval_df = pd.DataFrame(eval_filas)
                    st.dataframe(eval_df, hide_index=True, use_container_width=True)
                    st.download_button('📥 Exportar validación cronológica CSV',
                                       eval_df.to_csv(index=False).encode('utf-8-sig'),
                                       'nba_v3_1_validacion_cronologica.csv', 'text/csv',
                                       key=f'ri_nba_validacion_v31_{nombre}')
                    st.caption('Referencia histórica: media de cinco juegos anteriores. '
                               'MAE es error absoluto medio, no probabilidad ni garantía. '
                               'Con menos de seis partidos no existen evaluaciones.')

                    st.caption('Perfil descriptivo, no pronóstico. Las medias usan únicamente '
                               'partidos con totales conciliados para cada métrica; la atribución '
                               'de eventos por período sigue siendo provisional. La prórroga se '
                               'muestra aparte. Con menos de cinco partidos no se habilita '
                               'una estimación individual por período.')

                    st.download_button('📥 Exportar períodos reconstruidos CSV',
                                       periodos_conciliados.to_csv(index=False).encode('utf-8-sig'),
                                       'nba_v2_9_periodos_provisionales.csv', 'text/csv',
                                       key=f'ri_nba_periodos_v29_{nombre}')
                else:
                    st.info('Ninguna métrica coincide con el boxscore; no se muestran períodos.')
        st.caption('Desliza la tabla horizontalmente para ver todas las columnas. Los IDs observados se limitan a ocho ejemplos.')
        n = int(tabla['Estado'].eq('Conciliado').sum()) if 'Estado' in tabla else 0
        st.caption(f'Partidos conciliados: {n}/{len(tabla)}. El límite de partidos es configurable; solo se incluyen juegos disponibles en el historial.')
        if n:
            aceptados = tabla.loc[tabla['Estado'].eq('Conciliado')]
            filas = []
            for etiqueta, columnas in [('1.er cuarto', ['Q1']), ('2.º cuarto', ['Q2']),
                                       ('Primera mitad', ['Q1','Q2']), ('3.er cuarto', ['Q3']),
                                       ('4.º cuarto', ['Q4']), ('Segunda mitad', ['Q3','Q4'])]:
                valores = aceptados[columnas].sum(axis=1)
                filas.append({'Período': etiqueta, 'Registros': len(valores),
                              'Media observada': round(float(valores.mean()), 1),
                              'Estimación': round(float(valores.mean()), 1) if len(valores) >= 5 else 'N/D'})
            st.dataframe(pd.DataFrame(filas), hide_index=True, use_container_width=True)
        else:
            st.info('Aún no hay partidos con anotaciones individuales conciliadas. '
                    'No se muestran cifras por cuarto sin respaldo suficiente.')
        st.caption('Esta integración reconstruye puntos, rebotes y asistencias de forma provisional. Los minutos por '
                   'período permanecen pendientes de una fuente y validación específicas. '
                   'El esquema de ESPN no es oficial y puede variar.')


def _mostrar_auditoria_y_proyeccion(original, validos, metricas, seleccion, partidos, equipo):
    st.markdown('### 🧪 Auditoría de participación')
    st.caption('Los registros sin minutos pero con estadísticas observadas se incluyen con advertencia; los ceros explícitos de minutos se excluyen.')
    for nombre in seleccion:
        todos = original.loc[original['jugador'].eq(nombre)].copy()
        d = validos.loc[validos['jugador'].eq(nombre)].copy()
        if todos.empty:
            continue
        with st.expander(f'🔎 {nombre}: incluidos {len(d)} / recuperados {len(todos)}'):
            for motivo, cantidad in todos['Motivo'].value_counts().items():
                st.write(f'{motivo}: {cantidad}')
            columnas = [c for c in ['fecha', 'partido_id', 'Minutos', 'Puntos', 'Rebotes', 'Asistencias', 'Motivo', 'Incluido'] if c in todos]
            st.dataframe(todos[columnas].sort_values('fecha', ascending=False), hide_index=True, use_container_width=True)
            st.caption('Cobertura de cada promedio (valores numéricos disponibles):')
            st.write(' · '.join(f'{m}: {int(d[m].notna().sum())}/{len(d)}' for m in metricas))
        _diagnostico_y_validacion_individual(original, validos, nombre)
        _panel_proximo_jugador(d, partidos, nombre)
        _auditoria_periodos_individuales(d, nombre)
        st.markdown(f'#### 🏀 Puntos posibles en el siguiente partido · {nombre}')
        r = _proyectar_puntos(d, partidos, equipo if equipo != 'Todos' else str(d['equipo'].iloc[-1]) if not d.empty else 'Todos')
        if 'error' in r:
            st.info(r['error'])
            continue
        c1, c2 = st.columns(2)
        c1.metric('Estimación central', f"{r['centro']:.1f} pts")
        c2.metric('Rango descriptivo', f"{r['bajo']:.0f}–{r['alto']:.0f} pts")
        if r['proximo'] is not None:
            partido = r['proximo']
            rival = partido['visitante'] if partido['local'] == (equipo if equipo != 'Todos' else str(d['equipo'].iloc[-1])) else partido['local']
            st.caption(f"Próximo rival en calendario consultado: {rival} · {str(partido['fecha_utc'])[:16]} UTC")
        else:
            st.caption('Próximo rival no disponible en el calendario consultado; no se ajusta por rival.')
        st.caption(f"Basado en los últimos {r['n']} partidos con puntos válidos ({r['total']} disponibles). Rango = media ± 1 desviación estándar: descriptivo, no calibrado ni garantizado. No incorpora lesiones ni alineaciones.")
        # Resumen automático de otras métricas observadas; nunca rellena NaN con cero.
        extras = []
        historial_ordenado = d.copy()
        if 'fecha' in historial_ordenado:
            historial_ordenado = historial_ordenado.sort_values(['fecha', 'partido_id'])
        for metrica_extra in ('Rebotes', 'Asistencias', 'Minutos'):
            if metrica_extra not in historial_ordenado:
                continue
            serie = pd.to_numeric(historial_ordenado[metrica_extra], errors='coerce').dropna().tail(10)
            if len(serie) >= 5:
                extras.append({'Métrica': metrica_extra, 'Media últimos 10': round(float(serie.mean()), 1),
                               'Mín. descriptivo': round(max(0.0, float(serie.mean()-serie.std(ddof=1))), 1),
                               'Máx. descriptivo': round(float(serie.mean()+serie.std(ddof=1)), 1),
                               'Partidos válidos': len(serie)})
        if extras:
            st.markdown('**📊 Rebotes, asistencias y minutos · estimaciones descriptivas**')
            st.dataframe(pd.DataFrame(extras), hide_index=True, use_container_width=True)
            st.caption('Rangos = media ± desviación estándar; no son intervalos de confianza calibrados.')

        with st.expander('📊 Ventanas, minutos y calidad de datos'):
            for n, v in r['ventanas'].items():
                st.write(f"Últimos {n}: {v['media']:.1f} puntos/PJ · {v['n']} partidos")
            if r['minutos']:
                m = r['minutos']
                st.write(f"Minutos: últimos 5 = {m['reciente']:.1f} · historial = {m['historico']:.1f} ({m['n']} registros)")
            else:
                st.info('Minutos no disponibles para esta muestra.')
            if r['rival_info']:
                v = r['rival_info']
                st.write(f"{v['rival']}: puntos de equipo recibidos por partido = {v['media_recibida']:.1f} ({v['n']} partidos consultados). No es defensa individual ni ajusta la estimación.")
            else:
                st.caption('Sin muestra verificable del rival en el calendario consultado.')
            st.write(f"Cobertura de puntos: {r['total']} partidos válidos. Historial parcial posible.")
        with st.expander('🧪 Validación retrospectiva sin datos futuros'):
            v = r['validacion']
            if v['n']:
                st.metric('Error absoluto medio histórico', f"{v['mae']:.1f} pts")
                st.caption(f"{v['n']} evaluaciones cronológicas; cada estimación usa solo los 5–10 partidos anteriores. Es una prueba descriptiva sobre la muestra disponible, no una validación externa.")
            else:
                st.info('Se necesitan al menos 6 partidos con puntos válidos para evaluar errores históricos.')


def _mostrar_jugadores(partidos, equipo, limite, historico=None):
    fuente_historial = historico if historico is not None else partidos
    finales = fuente_historial.loc[fuente_historial['finalizado'].eq(True)].copy()
    if equipo != 'Todos':
        finales = finales.loc[finales['local'].eq(equipo) | finales['visitante'].eq(equipo)]
    if finales.empty:
        st.info('No hay partidos finalizados para consultar jugadores.')
        return
    finales = finales.sort_values('fecha_utc', ascending=False).head(limite)
    ids = tuple((str(r.id), str(r.fecha_utc)[:10]) for r in finales.itertuples(index=False))
    # Reutiliza automáticamente el historial ya recuperado, sin duplicar consultas.
    datos_compartidos, cobertura = obtener_historial_compartido(equipo=equipo)
    if cobertura.get('disponible') and not datos_compartidos.empty:
        datos = datos_compartidos.copy()
        errores = []
        st.success('Historial de jugadores reutilizado automáticamente.')
        st.caption(f"Cobertura: {cobertura.get('desde', '?')} a {cobertura.get('hasta', '?')} · "
                   f"bloques: {cobertura.get('bloques', 0)}")
        if not cobertura.get('completo', False) or cobertura.get('errores', 0):
            st.warning('Historial parcial: las estimaciones solo representan registros disponibles.')
    else:
        with st.spinner('Recuperando automáticamente boxscores del calendario seleccionado...'):
            datos, errores = _historial(ids)
        st.caption(f'Boxscores consultados: {len(ids)} · límite de consulta: {limite}.')
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
    auditoria, seleccionados, metricas = _auditar_participacion(seleccionados)
    if not metricas or not any(seleccionados[m].notna().any() for m in metricas):
        st.warning('No se encontraron estadísticas numéricas válidas.')
        return
    excluidos = int((~auditoria['Incluido']).sum())
    if excluidos:
        st.caption(f'{excluidos} registros excluidos por participación no acreditada.')
    pendientes = int(auditoria['Motivo'].eq('Minutos ausentes; estadísticas observadas').sum())
    if pendientes:
        st.warning(f'{pendientes} registros tienen estadísticas pero no minutos; revisar la auditoría.')
    if seleccionados.empty:
        st.info('No hay partidos con participación verificable para los jugadores seleccionados.')
        return
    _mostrar_auditoria_y_proyeccion(auditoria, seleccionados, metricas, seleccion, partidos, equipo)
    st.markdown('### 👥 Tarjetas de jugadores')
    resumen_filas = []
    for nombre in seleccion:
        d = seleccionados.loc[seleccionados['jugador'].eq(nombre)].sort_values(['fecha', 'partido_id'])
        if d.empty:
            st.warning(f'{nombre}: sin partidos válidos recuperados.')
            continue
        pj = d['partido_id'].nunique()
        st.markdown(f'**🏀 {nombre}**')
        st.caption(f'{pj} partidos recuperados · {d["fecha"].min()} a {d["fecha"].max()}')
        cols = st.columns(2)
        for i, m in enumerate(('Puntos', 'Rebotes', 'Asistencias', 'Minutos')):
            serie = d[m] if m in d else pd.Series(dtype=float)
            valido = int(serie.notna().sum())
            cols[i % 2].metric(m + '/PJ', f'{serie.mean():.1f}' if valido else 'N/D')
            if valido < len(d):
                st.caption(f'{m}: {valido}/{len(d)} registros con valor disponible.')
        if 'titular' in d:
            conocidos = d['titular'].dropna()
            st.caption(f'Titularidades registradas: {int(conocidos.eq(True).sum())} / {len(conocidos)} datos disponibles')
        for n in (5, 10, 20):
            ult = d.tail(n)
            fila = {'Jugador': nombre, 'Ventana': f'Últimos {n}', 'PJ': ult['partido_id'].nunique()}
            for m in ('Puntos', 'Rebotes', 'Asistencias', 'Minutos'):
                if m in ult:
                    serie = ult[m]
                    fila[m] = round(float(serie.mean()), 2) if serie.notna().any() else None
                    fila[f'N {m}'] = int(serie.notna().sum())
            resumen_filas.append(fila)
        base = d['Puntos'].mean() if 'Puntos' in d else float('nan')
        recientes = d.tail(5)['Puntos'].mean() if 'Puntos' in d else float('nan')
        if pd.notna(base) and pd.notna(recientes):
            st.caption(f'Tendencia puntos últimos 5 vs historial recuperado: {recientes-base:+.1f} pts/PJ')
        with st.expander(f'📋 Partidos de {nombre}'):
            cols_tabla = ['fecha', 'equipo', 'partido_id'] + metricas
            st.dataframe(d[cols_tabla].tail(20).iloc[::-1], hide_index=True, use_container_width=True)
    if not resumen_filas:
        return
    st.markdown('### 📈 Ventanas recientes')
    st.caption('Cada ventana usa hasta N partidos recuperados. N Puntos/Rebotes/etc. indica cuántos valores válidos entraron al promedio.')
    for fila in resumen_filas:
        with st.expander(f"{fila['Jugador']} · {fila['Ventana']} · {fila['PJ']} PJ"):
            for m in ('Puntos', 'Rebotes', 'Asistencias', 'Minutos'):
                if m in fila:
                    st.write(f"{m}: {fila[m] if fila[m] is not None else 'N/D'} · datos válidos: {fila.get('N '+m, 0)}")
    st.markdown('### 📊 Comparación')
    comparacion = seleccionados.groupby('jugador', as_index=False).agg(
        **{m: (m, 'mean') for m in metricas}, PJ=('partido_id', 'nunique'))
    st.dataframe(comparacion.round(2), hide_index=True, use_container_width=True)
    disponibles = [m for m in metricas if seleccionados[m].notna().any()]
    metrica = st.selectbox('Métrica de evolución', disponibles, key='ri_nba_metrica')
    grafica = seleccionados.pivot_table(index='fecha', columns='jugador', values=metrica, aggfunc='mean').sort_index()
    if not grafica.empty:
        st.line_chart(grafica)
    st.download_button('⬇️ Exportar comparación CSV',
                       comparacion.to_csv(index=False).encode('utf-8-sig'),
                       'resumen_inteligente_nba.csv', 'text/csv',
                       key='ri_nba_export', use_container_width=True)
    st.caption('Solo boxscores recuperados. Los datos faltantes no se sustituyen por cero; las ventanas no garantizan temporada completa.')


@st.cache_data(ttl=1800, show_spinner=False)
def _calendario_proximos_nba(desde_iso, hasta_iso):
    """Consulta separada del calendario futuro; no altera el historial."""
    return cargar_partidos(desde_iso, hasta_iso)


def _combinar_calendarios_nba(historico, futuro):
    """Conserva juegos históricos y añade futuros sin repetir IDs."""
    if futuro is None or futuro.empty:
        return historico.copy()
    if historico is None or historico.empty:
        return futuro.copy()
    combinado = pd.concat([historico, futuro], ignore_index=True)
    if 'id' in combinado.columns:
        combinado['id'] = combinado['id'].astype(str)
        combinado = combinado.drop_duplicates(subset=['id'], keep='first')
    return combinado


def mostrar_resumen_inteligente_nba():
    """Punto de entrada del Resumen Inteligente NBA."""
    st.title('🏠 Resumen Inteligente NBA')
    st.caption('Motor estadístico automático: elige equipos o jugadores; los detalles disponibles se consultan y reutilizan sin botones adicionales.')
    st.caption(f'v{VERSION} · Consulta automática · Fuente ESPN no oficial · Sin datos simulados')
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
    if st.button('🔄 Actualizar datos NBA', key='ri_nba_consultar', use_container_width=True):
        st.session_state['ri_nba_periodo'] = periodo
    if st.session_state.get('ri_nba_periodo') != periodo:
        st.session_state['ri_nba_periodo'] = periodo
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
        st.info('No hay partidos históricos en las fechas seleccionadas; se buscarán próximos encuentros.')
    # El historial conserva el período elegido. Los próximos encuentros se
    # buscan por separado desde hoy, sin imponer cambios al selector de fechas.
    fecha_hoy = date.today()
    fin_futuro = fecha_hoy + timedelta(days=14)
    errores_futuro = []
    try:
        with st.spinner('Buscando próximos encuentros NBA...'):
            futuros, errores_futuro = _calendario_proximos_nba(
                fecha_hoy.isoformat(), fin_futuro.isoformat())
    except Exception as exc:
        futuros = pd.DataFrame(columns=partidos.columns)
        errores_futuro = [f'{type(exc).__name__}: {exc}']
    partidos_completos = _combinar_calendarios_nba(partidos, futuros)
    if errores_futuro:
        st.caption(f'Calendario futuro con incidencias ({len(errores_futuro)}); '
                   'el historial consultado permanece disponible.')
    st.caption('Historial: intervalo seleccionado · Próximos partidos: '
               'consulta automática de los siguientes 14 días (si ESPN los publica).')
    equipos = sorted(set(partidos_completos['local'].dropna()) | set(partidos_completos['visitante'].dropna()))
    equipo = st.selectbox('Equipo', ['Todos'] + equipos, key='ri_nba_equipo')
    vista = st.radio('Vista', ['🏟️ Equipos', '👥 Jugadores', '📅 Calendario'],
                    key='ri_nba_vista', horizontal=False)
    if vista == '🏟️ Equipos':
        elegidos = st.multiselect('Comparar hasta tres equipos', equipos,
                                 default=[equipo] if equipo != 'Todos' else [],
                                 max_selections=3, key='ri_nba_equipos')
        if elegidos:
            _panel_equipos(partidos_completos, elegidos)
        else:
            st.info('Selecciona uno, dos o tres equipos.')
    elif vista == '👥 Jugadores':
        finales = partidos.loc[partidos['finalizado'].eq(True)]
        maximo = min(35, len(finales))
        if maximo == 0:
            st.info('No hay partidos finalizados con estadísticas individuales.')
        else:
            limite = st.slider('Máximo de boxscores a consultar', 1, maximo,
                               min(12, maximo), key='ri_nba_limite')
            _mostrar_jugadores(partidos_completos, equipo, limite, historico=partidos)
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


