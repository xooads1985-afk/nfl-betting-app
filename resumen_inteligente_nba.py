"""Resumen Inteligente NBA v1.5.5.

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

VERSION = '1.5.5'


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



def _historial_equipo(partidos, equipo, antes=None):
    d = _equipo_resultados(partidos, equipo)
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
    """Walk-forward por partido; solo encuentros previos a cada fecha objetivo."""
    if partidos.empty:
        return pd.DataFrame()
    d = partidos.loc[partidos['finalizado'].eq(True)].copy()
    d['fecha_dt'] = pd.to_datetime(d['fecha_utc'], utc=True, errors='coerce')
    d = d.dropna(subset=['fecha_dt', 'puntos_local', 'puntos_visitante'])
    d = d.loc[d['fecha_dt'].lt(fecha_limite)].sort_values(['fecha_dt', 'id'])
    # Un mismo evento solo puede evaluarse una vez.
    d = d.drop_duplicates(subset=['id'], keep='first')
    filas = []
    for _, juego in d.iterrows():
        local, visita = str(juego['local']), str(juego['visitante'])
        fecha = juego['fecha_dt']
        anteriores = d.loc[d['fecha_dt'].lt(fecha)]
        historicos = {e: _historial_equipo(anteriores, e, fecha) for e in (local, visita)}
        pred = {}
        for equipo, rival in ((local, visita), (visita, local)):
            propio = _media_rango(historicos[equipo]['PF']) if not historicos[equipo].empty else None
            recibido = _media_rango(historicos[rival]['PC']) if not historicos[rival].empty else None
            if propio and recibido:
                pred[equipo] = (propio['media'] + recibido['media']) / 2
        ident = str(juego['id'])
        fila = {'Fecha': fecha.strftime('%Y-%m-%d'), 'Partido': f'{visita} @ {local}',
                'id': ident, 'ataque': None, 'cuartos': None,
                'real_completo': float(juego['puntos_local'] + juego['puntos_visitante']),
                'real_reglamentario': None}
        if len(pred) == 2:
            fila['ataque'] = pred[local] + pred[visita]
        # Solo evaluar cuartos si existen marcadores reales de ambos equipos
        # para el juego objetivo Y para sus juegos históricos.
        if detalles and ident in detalles:
            actual = detalles[ident]
            if local in actual and visita in actual:
                fila['real_reglamentario'] = sum(actual[local].values()) + sum(actual[visita].values())
                pron = {}
                for equipo in (local, visita):
                    observados = []
                    for _, ant in historicos[equipo].tail(10).iterrows():
                        par = detalles.get(str(ant['id']), {})
                        if equipo in par:
                            observados.append(sum(par[equipo].values()))
                    media = _media_rango(observados)
                    if media:
                        pron[equipo] = media['media']
                if len(pron) == 2:
                    fila['cuartos'] = pron[local] + pron[visita]
        if fila['ataque'] is not None or fila['cuartos'] is not None:
            filas.append(fila)
    return pd.DataFrame(filas)


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
        if st.button('📥 Consultar períodos para validación histórica',
                     key='ri_nba_validacion_btn'):
            base = partidos.loc[partidos['finalizado'].eq(True)].copy()
            base['fecha_dt'] = pd.to_datetime(base['fecha_utc'], utc=True, errors='coerce')
            base = base.loc[base['fecha_dt'].lt(fecha)].drop_duplicates('id')
            # Limitar las llamadas para proteger el proveedor; sin datos falsos.
            base = base.sort_values('fecha_dt').tail(35)
            detalles = {}
            fallos = 0
            with st.spinner('Consultando períodos históricos disponibles...'):
                for identificador in base['id'].astype(str):
                    try:
                        detalles[identificador] = _puntos_periodos(cargar_detalle(identificador))
                    except Exception:
                        fallos += 1
            st.session_state[clave] = detalles
            st.session_state[clave + '_fallos'] = fallos
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
    _panel_validacion_historica(partidos, partido)
    with st.expander('⏱️ Cuartos y mitades · datos reales'):
        st.caption('Consulta opcional de hasta 10 partidos finalizados distintos por equipo. Puede tardar y ESPN puede limitar las consultas.')
        clave = f"ri_nba_periodos_{partido['id']}"
        if st.button('📥 Consultar cuartos reales', key='ri_nba_cuartos_btn'):
            juegos = {}
            for e, d in datos.items():
                for fila in d.tail(10).itertuples(index=False):
                    juegos[str(fila.id)] = fila
            muestras = {e: [] for e in (local, visita)}
            errores = 0
            with st.spinner('Consultando desglose de cuartos en ESPN...'):
                for identificador, fila in juegos.items():
                    try:
                        info = _puntos_periodos(cargar_detalle(identificador))
                        for e in muestras:
                            if e in info:
                                muestras[e].append(info[e])
                    except Exception:
                        errores += 1
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
            st.info('Pulsa el botón para recuperar los puntos por cuarto; no se estiman sin marcadores reales por período.')


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


def _mostrar_jugadores(partidos, equipo, limite):
    finales = partidos.loc[partidos['finalizado'].eq(True)].copy()
    if equipo != 'Todos':
        finales = finales.loc[finales['local'].eq(equipo) | finales['visitante'].eq(equipo)]
    if finales.empty:
        st.info('No hay partidos finalizados para consultar jugadores.')
        return
    finales = finales.sort_values('fecha_utc', ascending=False).head(limite)
    ids = tuple((str(r.id), str(r.fecha_utc)[:10]) for r in finales.itertuples(index=False))
    modo = st.radio('Origen de estadísticas individuales',
                    ['Consultar boxscores del período', 'Utilizar historial ya cargado'],
                    key='ri_nba_origen')
    if modo == 'Utilizar historial ya cargado':
        datos, cobertura = obtener_historial_compartido(equipo=equipo)
        if not cobertura.get('disponible'):
            st.warning(cobertura.get('motivo', 'No hay historial disponible.'))
            st.info('Entra en «📚 Historial de jugadores NBA», selecciona el equipo y carga los bloques primero.')
            return
        if datos.empty:
            st.info('El historial cargado no contiene registros individuales.')
            return
        if equipo == 'Todos':
            st.caption(f"Historial cargado del equipo: {cobertura['equipo']}.")
        if not cobertura['completo'] or cobertura['errores']:
            st.warning('Historial parcial o con incidencias; los promedios NO representan necesariamente toda la temporada.')
        else:
            st.caption('Todos los bloques solicitados fueron consultados; la cobertura de ESPN no está garantizada.')
        st.caption(f"Período del historial: {cobertura['desde']} a {cobertura['hasta']} · "
                   f"Bloques consultados: {cobertura['bloques']}")
        errores = []
    else:
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
        if elegidos:
            _panel_equipos(partidos, elegidos)
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

