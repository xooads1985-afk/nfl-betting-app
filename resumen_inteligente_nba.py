"""Resumen Inteligente NBA v3.12.17 · diseño mixto móvil.

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

VERSION = '3.12.17'


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
                'real_completo', 'real_reglamentario',
                'ref_ataque', 'ref_cuartos']
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
    
    # Baseline global aproximado para validación histórica
    baseline_liga_val = 112.0
    
    for _, juego in d.iterrows():
        local, visita = str(juego['local']), str(juego['visitante'])
        fecha = juego['fecha_dt']
        anteriores = d.loc[d['fecha_dt'].lt(fecha)]
        historicos = {e: _historial_equipo(anteriores, e, fecha)
                      for e in (local, visita)}
        pred = {}
        ref_ataque = {}
        for equipo, rival in ((local, visita), (visita, local)):
            propio_hist = historicos[equipo]
            rival_hist = historicos[rival]
            propio = (_media_rango(propio_hist['PF'])
                      if not propio_hist.empty and 'PF' in propio_hist else None)
            recibido = (_media_rango(rival_hist['PC'])
                        if not rival_hist.empty and 'PC' in rival_hist else None)
            if propio_hist is not None and not propio_hist.empty and 'PF' in propio_hist:
                ultimos_pf = pd.to_numeric(propio_hist['PF'], errors='coerce').dropna().tail(5)
                if len(ultimos_pf) == 5:
                    ref_ataque[equipo] = float(ultimos_pf.mean())
            if propio and recibido:
                eficiencia_relativa = recibido['media'] / max(baseline_liga_val, 1.0)
                media_ponderada = propio['media'] * eficiencia_relativa
                pred[equipo] = media_ponderada * 0.95
                
        ident = str(juego['id'])
        fila = {'Fecha': fecha.strftime('%Y-%m-%d'),
                'Partido': f'{visita} @ {local}', 'id': ident,
                'ataque': None, 'cuartos': None,
                'ref_ataque': None, 'ref_cuartos': None,
                'real_completo': float(juego['puntos_local'] + juego['puntos_visitante']),
                'real_reglamentario': None}
        if len(pred) == 2:
            fila['ataque'] = pred[local] + pred[visita]
        if len(ref_ataque) == 2:
            fila['ref_ataque'] = ref_ataque[local] + ref_ataque[visita]
        if detalles and ident in detalles:
            actual = detalles[ident]
            if isinstance(actual, dict) and local in actual and visita in actual:
                fila['real_reglamentario'] = (sum(actual[local].values()) +
                                             sum(actual[visita].values()))
                pron = {}
                ref_cuartos = {}
                for equipo in (local, visita):
                    observados = []
                    for _, ant in historicos[equipo].tail(10).iterrows():
                        par = detalles.get(str(ant['id']), {})
                        if isinstance(par, dict) and equipo in par:
                            observados.append(sum(par[equipo].values()))
                    media = _media_rango(observados)
                    if media:
                        pron[equipo] = media['media']
                    if len(observados) >= 5:
                        ref_cuartos[equipo] = float(sum(observados[-5:]) / 5)
                if len(pron) == 2:
                    fila['cuartos'] = pron[local] + pron[visita]
                if len(ref_cuartos) == 2:
                    fila['ref_cuartos'] = ref_cuartos[local] + ref_cuartos[visita]
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
                                       'para ambos equipos de un mismo encuentro evaluable.')
                        elif diag['sin_consulta']:
                            st.warning('Hay partidos anteriores sin consultar.')
                        else:
                            st.info('No hay objetivos elegibles con los datos disponibles.')
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
            ref_col = 'ref_ataque' if pred == 'ataque' else 'ref_cuartos'
            pareados = validos.dropna(subset=[ref_col]).copy()
            st.markdown('**📐 Evaluación de la referencia histórica (Edge descriptivo)**')
            if pareados.empty:
                st.info('Sin partidos con cinco antecedentes válidos por equipo para comparar modelo y referencia.')
            else:
                pareados['Error modelo'] = (pareados[pred] - pareados[real]).abs()
                pareados['Error referencia'] = (pareados[ref_col] - pareados[real]).abs()
                mae_modelo = float(pareados['Error modelo'].mean())
                mae_ref = float(pareados['Error referencia'].mean())
                mejora = mae_ref - mae_modelo
                st.write(f'**{len(pareados)} partidos comparables** · MAE modelo: **{mae_modelo:.2f}** pts · '
                         f'MAE referencia: **{mae_ref:.2f}** pts')
                st.metric('Mejora de error frente a referencia', f'{mejora:+.2f} pts')
                st.caption('Positivo = el modelo tuvo menor error medio; negativo = la referencia fue mejor.')
                if len(pareados) < 20:
                    st.warning('Comparación provisional: menos de 20 partidos con referencias completas.')
                with st.expander(f'📋 Modelo frente a referencia · {titulo}'):
                    tabla_ref = pareados[['Fecha', 'Partido', pred, ref_col, real,
                                         'Error modelo', 'Error referencia']].copy()
                    tabla_ref.columns = ['Fecha', 'Partido', 'Proyección', 'Referencia',
                                         'Observado', 'Error modelo', 'Error referencia']
                    tabla_ref['Edge descriptivo'] = tabla_ref['Proyección'] - tabla_ref['Referencia']
                    st.dataframe(tabla_ref.round(2), hide_index=True, use_container_width=True)
                    st.download_button('📥 Descargar comparación CSV',
                                       tabla_ref.to_csv(index=False).encode('utf-8-sig'),
                                       file_name=f'nba_edge_validacion_{pred}.csv',
                                       mime='text/csv', key=f'ri_nba_edge_csv_{pred}_{partido["id"]}')
            with st.expander(f'📋 Partidos evaluados · {titulo}'):
                tabla = validos[['Fecha', 'Partido', pred, real, 'Error']].copy()
                tabla.columns = ['Fecha', 'Partido', 'Estimado', 'Observado', 'Error absoluto']
                tabla['Error firmado'] = tabla['Estimado'] - tabla['Observado']
                st.dataframe(tabla.round(1), hide_index=True, use_container_width=True)
                st.download_button(
                    '📥 Descargar todos los partidos evaluados (CSV)',
                    data=tabla.to_csv(index=False).encode('utf-8-sig'),
                    file_name=f'nba_validacion_completa_{pred}.csv',
                    mime='text/csv',
                    key=f'ri_nba_validacion_completa_csv_{pred}_{partido["id"]}',
                )


def _mostrar_proyeccion_equipos(partidos, partido):
    """Estimaciones descriptivas por equipo, total y períodos con datos reales."""
    local, visita = str(partido['local']), str(partido['visitante'])
    fecha = pd.to_datetime(partido['fecha_utc'], utc=True, errors='coerce')
    st.markdown(f'### 🏀 Próximo encuentro: {visita} @ {local}')
    st.caption(f"Calendario consultado: {str(partido['fecha_utc'])[:16]} UTC. Solo se consideran resultados anteriores al encuentro.")
    datos = {e: _historial_equipo(partidos, e, fecha) for e in (local, visita)}
    
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
            st.write(f'**{nombre}** · registros finalizados: {len(base)} · IDs repetidos: {duplicados_id} · sin marcador: {sin_marcador}')
        st.caption('Esta revisión solo cubre el intervalo consultado.')

    for e in (local, visita):
        d = datos[e]
        st.markdown(f'**{e} · {len(d)} partidos disponibles**')
        if d.empty:
            st.info('Sin resultados anteriores en el período consultado.')
            continue
        st.caption(f"Victorias: **{int(d['Resultado'].eq('V').sum())}** · "
                   f"PF/PJ: **{d['PF'].mean():.1f}** · "
                   f"PC/PJ: **{d['PC'].mean():.1f}**")

    # ==========================================
    # INTEGRACIÓN CLAVE: EFICIENCIA PONDERADA Y REGRESIÓN ANTI-SESGO (OVER/UNDER)
    # ==========================================
    estim = {}
    media_liga_local = datos[local]['PF'].mean() if not datos[local].empty else 112.0
    media_liga_visita = datos[visita]['PF'].mean() if not datos[visita].empty else 112.0
    baseline_liga = (media_liga_local + media_liga_visita) / 2.0

    for e, rival in ((local, visita), (visita, local)):
        propios = _media_rango(datos[e]['PF']) if not datos[e].empty else None
        recibidos = _media_rango(datos[rival]['PC']) if not datos[rival].empty else None
        if propios and recibidos:
            eficiencia_relativa = recibidos['media'] / max(baseline_liga, 1.0)
            media_ponderada = propios['media'] * eficiencia_relativa
            media_final = media_ponderada * 0.95  # Factor de regresión conservador del 95%
            estim[e] = {'media': media_final, 'n': min(propios['n'], recibidos['n'])}

    st.markdown('#### 📊 Puntos descriptivos · partido completo (Ajustado por Eficiencia)')
    if len(estim) == 2:
        st.caption(f"🏠 Local: **{estim[local]['media']:.1f}** · "
                   f"✈️ Visitante: **{estim[visita]['media']:.1f}** · "
                   f"Total: **{sum(x['media'] for x in estim.values()):.1f}**")
        st.caption('Modelo ponderado por eficiencia relativa de ritmo y regresión anti-sesgo.')
    else:
        st.info('Se requieren al menos 3 partidos con marcadores completos de cada equipo para estimar puntos del partido.')

    try:
        _panel_validacion_historica(partidos, partido)
    except (KeyError, ValueError, TypeError, IndexError) as exc:
        with st.expander('🧪 Validación histórica de equipos · diagnóstico'):
            st.warning('No fue posible completar la validación histórica.')
            st.code(f'{type(exc).__name__}: {exc}', language='text')

    with st.expander('⏱️ Cuartos y mitades · datos reales'):
        st.caption('Consulta automática de hasta 10 partidos finalizados por equipo.')
        clave = f"ri_nba_periodos_{partido['id']}"
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
            muestras = guardado['muestras']
            periodos = [('1.er cuarto', [1]), ('2.º cuarto', [2]), ('Primera mitad', [1,2]),
                        ('3.er cuarto', [3]), ('4.º cuarto', [4]), ('Segunda mitad', [3,4]),
                        ('Final reglamentario', [1,2,3,4])]
            col_local = _abreviatura_equipo(local)
            col_visita = _abreviatura_equipo(visita)
            if col_local == col_visita:
                col_local, col_visita = 'Local', 'Visita'
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


def _edge_descriptivo(serie, ventana=10):
    """Diferencia de medias históricas, NO ventaja de apuestas ni probabilidad."""
    x = pd.to_numeric(pd.Series(serie), errors='coerce').dropna()
    if len(x) < 5:
        return None
    reciente = x.tail(ventana)
    referencia = x.tail(5)
    proy = _pronostico_estadistico(x)
    if proy is None:
        return None
    return {'proyeccion': proy['media'], 'referencia': float(referencia.mean()),
            'diferencia': float(proy['media'] - referencia.mean()),
            'n': len(reciente), 'bajo': proy['bajo'], 'alto': proy['alto'],
            'mae': proy['mae'], 'pruebas': proy['pruebas']}


def _triples_desde_detalle(detalle):
    """Recupera triples anotados de boxscore ESPN (3PT, formato aciertos-intentos)."""
    resultado = {}
    for equipo in (detalle.get('boxscore', {}).get('players') or []):
        nombre_equipo = (equipo.get('team') or {}).get('displayName', '')
        for bloque in equipo.get('statistics') or []:
            etiquetas = bloque.get('labels') or bloque.get('names') or []
            indice = next((i for i, v in enumerate(etiquetas)
                           if str(v).upper().replace(' ', '') in ('3PT', '3FG', '3PM-A', '3PTM-A', '3PM')), None)
            if indice is None:
                continue
            for jugador in bloque.get('athletes') or []:
                atleta = jugador.get('athlete') or {}
                nombre = atleta.get('displayName') or atleta.get('fullName')
                estadisticas = jugador.get('stats') or []
                if not nombre or indice >= len(estadisticas):
                    continue
                dato = str(estadisticas[indice]).strip()
                primer = dato.split('-', 1)[0].strip()
                try:
                    valor = float(primer)
                except (TypeError, ValueError):
                    continue
                if valor >= 0:
                    resultado[(str(nombre_equipo), str(nombre))] = valor
    return resultado


def _historial_triples(jugadores, ids_fechas, cache_detalles):
    """Solo partidas observadas; nunca convierte ausencia de estadística en cero."""
    filas = []
    for identificador, fecha in ids_fechas:
        detalle = cache_detalles.get(str(identificador))
        if detalle is None:
            try:
                detalle = cargar_detalle(str(identificador))
            except Exception:
                detalle = {}
            cache_detalles[str(identificador)] = detalle
        if not isinstance(detalle, dict):
            continue
        triples = _triples_desde_detalle(detalle)
        for (equipo, nombre), valor in triples.items():
            if (equipo, nombre) in jugadores:
                filas.append({'equipo': equipo, 'jugador': nombre,
                              'fecha': fecha, 'partido_id': str(identificador), 'Triples': valor})
    return pd.DataFrame(filas)


def _validar_edge_jugador_v312(datos, metricas=('Puntos', 'Rebotes', 'Asistencias', 'Triples'), minimo=5, ventana=10):
    columnas = ['Estadística', 'Fecha', 'Partido ID', 'Previos', 'Proyección',
                'Referencia', 'Edge descriptivo', 'Observado', 'Error modelo', 'Error referencia']
    if datos is None or datos.empty or not {'fecha', 'partido_id', 'Minutos'}.issubset(datos.columns):
        return pd.DataFrame(), pd.DataFrame(columns=columnas)
    d = datos.copy()
    d['_fecha'] = pd.to_datetime(d['fecha'], utc=True, errors='coerce').dt.normalize()
    d['Minutos'] = pd.to_numeric(d['Minutos'], errors='coerce')
    d = d.loc[d['_fecha'].notna() & d['Minutos'].gt(0)].copy()
    d = d.sort_values(['_fecha', 'partido_id']).drop_duplicates('partido_id', keep='last')
    resultados = []
    for metrica in metricas:
        if metrica not in d.columns:
            continue
        valores = pd.to_numeric(d[metrica], errors='coerce')
        for i in range(len(d)):
            actual = valores.iloc[i]
            if pd.isna(actual):
                continue
            previos = valores.loc[d['_fecha'].lt(d['_fecha'].iloc[i])].dropna().tail(ventana)
            if len(previos) < minimo:
                continue
            proy = float(previos.mean())
            ref = float(previos.tail(5).mean())
            real = float(actual)
            resultados.append({'Estadística': metrica,
                'Fecha': d['_fecha'].iloc[i].strftime('%Y-%m-%d'),
                'Partido ID': str(d['partido_id'].iloc[i]), 'Previos': len(previos),
                'Proyección': proy, 'Referencia': ref,
                'Edge descriptivo': proy-ref, 'Observado': real,
                'Error modelo': abs(proy-real), 'Error referencia': abs(ref-real)})
    detalle = pd.DataFrame(resultados, columns=columnas)
    if detalle.empty:
        return pd.DataFrame(), detalle
    resumen = []
    for metrica, grupo in detalle.groupby('Estadística', sort=False):
        mae_modelo = float(grupo['Error modelo'].mean())
        mae_ref = float(grupo['Error referencia'].mean())
        resumen.append({'Estadística': metrica, 'Evaluaciones': len(grupo),
            'MAE modelo': round(mae_modelo, 2), 'MAE referencia': round(mae_ref, 2),
            'Mejora vs referencia': round(mae_ref-mae_modelo, 2),
            'Sesgo modelo': round(float((grupo['Proyección']-grupo['Observado']).mean()), 2),
            'Estado': 'Muestra pequeña' if len(grupo) < 20 else 'Evaluación histórica'})
    return pd.DataFrame(resumen), detalle


def _interpretacion_inteligente_nba(local, visita, historiales, proy, tabla_periodos, muestras, partidos, fecha):
    st.markdown('### 🧠 Interpretación Inteligente NBA · 1.2')
    st.caption(f'✈️ {visita} · 🏠 {local} · Estimaciones estadísticas, no resultados garantizados.')
    final = tabla_periodos.loc[tabla_periodos['Período'].eq('Final reglamentario')]
    fila = final.iloc[0] if not final.empty else None
    valido = fila is not None and pd.notna(fila['Visitante']) and pd.notna(fila['Local'])
    if valido:
        pv, pl = float(fila['Visitante']), float(fila['Local'])
        total, margen = pv + pl, pl - pv
        st.metric('🏀 Total estimado · tiempo reglamentario', f'{total:.1f} pts')
        c1, c2 = st.columns(2)
        c1.metric(f'✈️ {_abreviatura_equipo(visita)}', f'{pv:.1f} pts')
        c2.metric(f'🏠 {_abreviatura_equipo(local)}', f'{pl:.1f} pts')


def _nba_archivo_registros():
    import os
    return os.environ.get('NBA_REGISTRO_RUTA', 'nba_proyecciones_registradas.json')


def _nba_leer_registros():
    import json
    try:
        with open(_nba_archivo_registros(), 'r', encoding='utf-8') as archivo:
            datos = json.load(archivo)
        return datos if isinstance(datos, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _nba_guardar_registros(registros):
    import json
    import os
    destino = _nba_archivo_registros()
    temporal = destino + '.tmp'
    with open(temporal, 'w', encoding='utf-8') as archivo:
        json.dump(registros, archivo, ensure_ascii=False, indent=2)
    os.replace(temporal, destino)


def _nba_registrar_proyeccion(partido, tabla_periodos):
    from datetime import datetime, timezone
    fecha = pd.to_datetime(partido.get('fecha_utc'), utc=True, errors='coerce')
    if pd.isna(fecha) or fecha <= pd.Timestamp.now(tz='UTC'):
        return False, 'Partido iniciado o sin fecha válida: no se crea una proyección retrospectiva.'
    clave = str(partido.get('id', ''))
    if not clave:
        return False, 'Falta el identificador del encuentro.'
    registros = _nba_leer_registros()
    if clave in registros:
        return False, 'La primera proyección de este encuentro ya está registrada.'
    datos = {}
    for _, fila in tabla_periodos.iterrows():
        nombre = str(fila['Período'])
        valores = {}
        for columna in ('Visitante', 'Local', 'Total', 'Referencia total', 'Edge descriptivo'):
            valor = pd.to_numeric(fila.get(columna), errors='coerce')
            valores[columna] = round(float(valor), 3) if pd.notna(valor) else None
        datos[nombre] = valores
    if datos.get('Final reglamentario', {}).get('Total') is None:
        return False, 'No hay una proyección reglamentaria completa que registrar.'
    registros[clave] = {
        'id': clave, 'fecha_utc': fecha.isoformat(),
        'registrado_utc': datetime.now(timezone.utc).isoformat(),
        'visitante': str(partido['visitante']), 'local': str(partido['local']),
        'version': VERSION, 'periodos': datos,
    }
    try:
        _nba_guardar_registros(registros)
    except OSError as exc:
        return False, f'No se pudo guardar el registro local: {type(exc).__name__}.'
    return True, 'Proyección original guardada sin modificar las fórmulas.'


def _nba_fecha_mazatlan(valor, formato='%d/%m/%Y %H:%M'):
    fecha = pd.to_datetime(valor, utc=True, errors='coerce')
    if pd.isna(fecha):
        return 'Fecha no disponible'
    return fecha.tz_convert(ZoneInfo('America/Mazatlan')).strftime(formato)


def _nba_validar_registro_respaldo(clave, registro):
    from datetime import datetime
    import math
    if not isinstance(registro, dict) or not isinstance(clave, str):
        return False
    if not clave or clave != str(registro.get('id', '')):
        return False
    periodos = registro.get('periodos')
    if not isinstance(periodos, dict):
        return False
    final = periodos.get('Final reglamentario')
    if not isinstance(final, dict):
        return False
    return isinstance(final.get('Total'), (int, float)) and not isinstance(final.get('Total'), bool) and math.isfinite(final['Total']) and final['Total'] >= 0


def _nba_panel_seguimiento(partidos):
    import json
    with st.expander('🧪 Seguimiento de proyecciones registradas', expanded=False):
        registros = _nba_leer_registros()
        if not registros:
            st.info('Aún no hay proyecciones registradas en este despliegue.')
            return
        filas = []
        mapa = {}
        if not partidos.empty and 'id' in partidos:
            mapa = {str(fila['id']): fila for _, fila in partidos.iterrows()}
        for clave, registro in registros.items():
            fila = mapa.get(str(clave))
            estado = 'Pendiente o fuera del calendario consultado'
            observado = None
            error = None
            proy = registro.get('periodos', {}).get('Final reglamentario', {}).get('Total')
            if fila is not None and fila.get('finalizado') == True:
                estado = 'Finalizado · verificando desglose reglamentario'
                try:
                    detalle = cargar_detalle(str(clave))
                    cuartos = _puntos_periodos(detalle)
                    local = registro.get('local')
                    visita = registro.get('visitante')
                    if local in cuartos and visita in cuartos:
                        totales = {q: cuartos[local][q] + cuartos[visita][q] for q in (1, 2, 3, 4)}
                        observado = sum(totales.values())
                        if proy is not None:
                            error = float(proy) - observado
                        estado = 'Evaluado · cuatro cuartos verificados'
                except Exception:
                    estado = 'Finalizado · detalle ESPN no disponible'
            filas.append({'Partido': f"{registro.get('visitante','?')} @ {registro.get('local','?')}",
                          'Fecha Mazatlán': _nba_fecha_mazatlan(registro.get('fecha_utc')),
                          'Proyección': proy, 'Observado': observado,
                          'Error firmado': round(error, 2) if error is not None else None,
                          'Estado': estado})
        tabla = pd.DataFrame(filas)
        st.dataframe(tabla.fillna('—'), hide_index=True, use_container_width=True)


def _tarjeta_unica_partido(partidos, partido):
    local, visita = str(partido['local']), str(partido['visitante'])
    fecha = pd.to_datetime(partido['fecha_utc'], utc=True, errors='coerce')
    st.markdown(f'### 🏀 {visita} vs. {local}')
    fecha_mx = fecha.tz_convert(ZoneInfo('America/Mazatlan')) if pd.notna(fecha) else None
    st.caption(f"Próximo partido · {fecha_mx.strftime('%d/%m/%Y %H:%M') if fecha_mx is not None else 'fecha no disponible'} (Mazatlán) · estimaciones exploratorias")
    
    historiales = {e: _historial_equipo(partidos, e, fecha) for e in (local, visita)}
    
    # Cálculo integrado con eficiencia ponderada y factor de regresión anti-sesgo
    proy = {}
    media_liga_local = historiales[local]['PF'].mean() if not historiales[local].empty else 112.0
    media_liga_visita = historiales[visita]['PF'].mean() if not historiales[visita].empty else 112.0
    baseline_liga_tarjeta = (media_liga_local + media_liga_visita) / 2.0

    for equipo, rival in ((local, visita), (visita, local)):
        a, b = historiales[equipo], historiales[rival]
        if not a.empty and not b.empty:
            pf, pc = _media_rango(a['PF']), _media_rango(b['PC'])
            if pf and pc:
                eficiencia_relativa = pc['media'] / max(baseline_liga_tarjeta, 1.0)
                media_ponderada = pf['media'] * eficiencia_relativa
                proy[equipo] = media_ponderada * 0.95

    st.markdown('**🏆 Partido completo · puntos esperados (Ajustado por Eficiencia)**')
    if len(proy) == 2:
        st.metric('Media ponderada por eficiencia', f"{sum(proy.values()):.1f} pts")
        st.caption(f"{visita}: {proy[visita]:.1f} · {local}: {proy[local]:.1f} · diferencia: {proy[local]-proy[visita]:+.1f} local")
    else:
        st.info('Faltan al menos 3 partidos anteriores por equipo para estimar el marcador completo.')

    st.markdown('**⏱️ Proyección integrada · equipos y períodos**')
    juegos = {}
    for e, hist in historiales.items():
        for fila in hist.tail(10).itertuples(index=False):
            juegos[str(fila.id)] = str(fila.fecha_utc)[:10]
    cache = st.session_state.setdefault('ri_nba_cache_cuartos_v17', {})
    cache_detalles = st.session_state.setdefault('ri_nba_detalles_triples_v39', {})
    for ident in juegos:
        if ident not in cache:
            try:
                detalle = cargar_detalle(ident)
                cache[ident] = _puntos_periodos(detalle)
                cache_detalles[ident] = detalle
            except Exception:
                cache[ident] = None
    muestras = {e: [] for e in (local, visita)}
    for e, hist in historiales.items():
        for fila in hist.tail(10).itertuples(index=False):
            datos = cache.get(str(fila.id))
            if isinstance(datos, dict) and e in datos:
                muestras[e].append(datos[e])
    periodos = [('Q1',(1,)),('Q2',(2,)),('Primera mitad',(1,2)),
                ('Q3',(3,)),('Q4',(4,)),('Segunda mitad',(3,4)),
                ('Final reglamentario',(1,2,3,4))]

    def _serie_periodos(equipo, qs, recibidos=False):
        valores = []
        hist = historiales[equipo].tail(10)
        for juego in hist.itertuples(index=False):
            info = cache.get(str(juego.id))
            if not isinstance(info, dict):
                continue
            nombre = str(juego.Rival) if recibidos else equipo
            dato = info.get(nombre)
            if isinstance(dato, dict) and all(q in dato for q in qs):
                valores.append(sum(float(dato[q]) for q in qs))
        return valores

    filas = []
    for titulo, qs in periodos:
        resultados = {}
        for equipo, rival in ((visita, local), (local, visita)):
            ataque = _serie_periodos(equipo, qs)
            defensa = _serie_periodos(rival, qs, recibidos=True)
            if len(ataque) < 3 or len(defensa) < 3:
                resultados[equipo] = None
                continue
            proyeccion = (sum(ataque) / len(ataque) + sum(defensa) / len(defensa)) / 2
            referencia = sum(ataque[-5:]) / len(ataque[-5:])
            resultados[equipo] = {'proyeccion': proyeccion,
                                  'referencia': referencia,
                                  'n': min(len(ataque), len(defensa))}
        a, b = resultados[visita], resultados[local]
        filas.append({'Período': titulo,
                      'Visitante': round(a['proyeccion'], 1) if a else None,
                      'Local': round(b['proyeccion'], 1) if b else None,
                      'Total': round(a['proyeccion'] + b['proyeccion'], 1) if a and b else None,
                      'Referencia total': round(a['referencia'] + b['referencia'], 1) if a and b else None,
                      'Edge descriptivo': round((a['proyeccion'] + b['proyeccion']) -
                                                (a['referencia'] + b['referencia']), 1) if a and b else None,
                      'Muestra mínima': min(a['n'], b['n']) if a and b else None})
    tabla_periodos = pd.DataFrame(filas)
    with st.expander('💾 Guardar proyección previa al partido'):
        if st.button('Guardar proyección original', key=f"ri_nba_guardar_{partido['id']}"):
            correcto, mensaje = _nba_registrar_proyeccion(partido, tabla_periodos)
            (st.success if correcto else st.info)(mensaje)
    _interpretacion_inteligente_nba(local, visita, historiales, proy, tabla_periodos, muestras, partidos, fecha)
    st.dataframe(tabla_periodos[['Período', 'Visitante', 'Local', 'Total']],
                 hide_index=True, use_container_width=True)


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
        opciones = {f"{p['visitante']} @ {p['local']} · {_nba_fecha_mazatlan(p['fecha_utc'])} (Mazatlán)": p for p in proximos.values()}
        elegido = st.selectbox('Partido para análisis de puntos', list(opciones), key='ri_nba_partido_equipos')
        _tarjeta_unica_partido(partidos, opciones[elegido])
        with st.expander('🔬 Análisis detallado y validación histórica (vista anterior)'):
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


def _pronostico_estadistico(serie, ventana=10):
    v = pd.to_numeric(serie, errors='coerce').dropna().tail(ventana)
    if len(v) < 3:
        return None
    promedio = float(v.mean())
    desviacion = float(v.std(ddof=1)) if len(v) > 1 else 0.0
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


@st.cache_data(ttl=1800, show_spinner=False)
def _calendario_proximos_nba(desde_iso, hasta_iso):
    return cargar_partidos(desde_iso, hasta_iso)


def _combinar_calendarios_nba(historico, futuro):
    if futuro is None or futuro.empty:
        return historico.copy()
    if historico is None or historico.empty:
        return futuro.copy()
    combinado = pd.concat([historico, futuro], ignore_index=True)
    if 'id' in combinado.columns:
        combinado['id'] = combinado['id'].astype(str)
        combinado = combinado.drop_duplicates(subset=['id'], keep='first')
    return combinado


def _aplicar_diseno_mixto_nba():
    st.markdown("""
    <style>
    .block-container {max-width: 1100px; padding-top: 1.1rem; padding-bottom: 2.2rem;}
    [data-testid="stAppViewContainer"] h1 {font-size: clamp(1.55rem, 5vw, 2.1rem); letter-spacing: -.035em; font-weight: 780;}
    [data-testid="stMetric"] {
        border: 1px solid rgba(110, 143, 190, .25);
        background: rgba(70, 120, 185, .065);
        border-radius: 13px; padding: .8rem .85rem; min-height: 94px;
        box-shadow: 0 2px 8px rgba(20, 35, 65, .035);
    }
    [data-testid="stDataFrame"] {border: 1px solid rgba(110, 143, 190, .20); border-radius: 12px; overflow: hidden;}
    [data-testid="stExpander"] {border: 1px solid rgba(110, 143, 190, .23); border-radius: 12px; margin: .4rem 0;}
    div.stButton > button, div.stDownloadButton > button {border-radius: 10px; font-weight: 650; min-height: 2.55rem;}
    </style>
    """, unsafe_allow_html=True)


def mostrar_resumen_inteligente_nba():
    _aplicar_diseno_mixto_nba()
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
        st.caption(f'Calendario futuro con incidencias ({len(errores_futuro)}).')
    _nba_panel_seguimiento(partidos_completos)
    
    equipos = sorted(set(partidos_completos['local'].dropna()) | set(partidos_completos['visitante'].dropna()))
    vista = st.radio('Vista', ['🏟️ Equipos', '👥 Jugadores', '📅 Calendario'],
                    key='ri_nba_vista', horizontal=False)
    if vista == '🏟️ Equipos':
        elegidos = st.multiselect('Comparar hasta dos equipos (opcional)', equipos,
                                 max_selections=2, key='ri_nba_equipos')
        if elegidos:
            _panel_equipos(partidos_completos, elegidos)
        else:
            futuros_disponibles = partidos_completos.loc[partidos_completos['finalizado'].eq(False)].copy()
            futuros_disponibles['fecha_dt'] = pd.to_datetime(futuros_disponibles['fecha_utc'], utc=True, errors='coerce')
            futuros_disponibles = futuros_disponibles.loc[futuros_disponibles['fecha_dt'].ge(pd.Timestamp.now(tz='UTC'))]
            futuros_disponibles = futuros_disponibles.sort_values('fecha_dt').drop_duplicates('id')
            if futuros_disponibles.empty:
                st.info('No hay próximos encuentros en el calendario consultado.')
            else:
                opciones = {f"{r.visitante} @ {r.local} · {_nba_fecha_mazatlan(r.fecha_utc)} (Mazatlán)": r._asdict()
                            for r in futuros_disponibles.head(40).itertuples(index=False)}
                elegido = st.selectbox('🏀 Selecciona un partido para la tarjeta única',
                                       list(opciones), key='ri_nba_tarjeta_partido')
                _tarjeta_unica_partido(partidos_completos, opciones[elegido])
    elif vista == '👥 Jugadores':
        st.info('Vista de jugadores activa a través del módulo de resumen.')
    else:
        equipo = st.selectbox('Filtrar calendario por equipo', ['Todos'] + equipos, key='ri_nba_equipo_calendario')
        vista_cal = partidos.copy()
        if equipo != 'Todos':
            vista_cal = vista_cal.loc[vista_cal['local'].eq(equipo) |
                                          vista_cal['visitante'].eq(equipo)]
        columnas = ['fecha_utc', 'visitante', 'local', 'estado',
                    'puntos_visitante', 'puntos_local']
        st.dataframe(vista_cal[columnas], hide_index=True, use_container_width=True)
    st.caption('Las estadísticas se limitan a las fechas y partidos consultados.')
