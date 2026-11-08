"""Resumen Inteligente NBA v3.12.6 · diseño mixto móvil.

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
                pred[equipo] = (propio['media'] + recibido['media']) / 2
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
            # Comparación pareada: misma fecha, partido y resultado observado.
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
                st.caption('Positivo = el modelo tuvo menor error medio; negativo = la referencia fue mejor. '
                           'El Edge descriptivo es proyección menos referencia; no es una probabilidad.')
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
        st.caption(f"Victorias: **{int(d['Resultado'].eq('V').sum())}** · "
                   f"PF/PJ: **{d['PF'].mean():.1f}** · "
                   f"PC/PJ: **{d['PC'].mean():.1f}**")
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
        st.caption(f"🏠 Local: **{estim[local]['media']:.1f}** · "
                   f"✈️ Visitante: **{estim[visita]['media']:.1f}** · "
                   f"Total: **{sum(x['media'] for x in estim.values()):.1f}**")
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
    """Backtest pareado: media hasta 10 vs media 5, solo partidos previos.

    Requiere minutos positivos para acreditar participación; los datos ausentes
    permanecen ausentes. No evalúa dos partidos de una misma fecha entre sí.
    """
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
            # Fecha estrictamente anterior: sin filtraciones entre partidos del mismo día.
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
    """Panel móvil: reutiliza cálculos existentes y validación cronológica."""
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
        if abs(margen) < 0.05:
            st.info('📏 Diferencia estimada: prácticamente igualada.')
        else:
            superior = local if margen > 0 else visita
            magnitud = abs(margen)
            etiqueta = ('pequeña' if magnitud <= 3 else 'moderada' if magnitud <= 7 else 'amplia')
            st.info(f'📏 {_abreviatura_equipo(superior)} +{magnitud:.1f} pts · diferencia {etiqueta}')
            st.caption('Escala visual provisional; no expresa probabilidad ni certeza del resultado.')
        st.caption('Los cuartos excluyen prórrogas. Puede haber diferencias de 0.1 por redondeo.')
    elif len(proy) == 2:
        st.metric('🏀 Total descriptivo · marcadores completos', f'{sum(proy.values()):.1f} pts')
        st.caption('No hay datos suficientes para una proyección integrada de tiempo reglamentario.')
    else:
        st.warning('No hay suficientes datos para construir el resumen numérico.')

    with st.expander('📊 Comparación de equipos', expanded=False):
        modo = st.radio('Estadísticas', ['General', 'Según sede'], horizontal=True,
                        key='ri_nba_interpretacion_modo_sede',
                        help='Según sede: se consideran solo los partidos del visitante fuera de casa y del local en casa.')
        for nombre, sede in ((visita, 'Visitante'), (local, 'Local')):
            d = historiales[nombre]
            filtrado = d if modo == 'General' else d.loc[d['Sede'].eq(sede)]
            st.markdown(f'**{"✈️" if sede == "Visitante" else "🏠"} {nombre} · {sede}**')
            if filtrado.empty:
                st.caption('Sin partidos verificables para este filtro; no se sustituyen valores ausentes.')
                continue
            pf = float(filtrado['PF'].mean())
            pc = float(filtrado['PC'].mean())
            st.caption(f'PJ: **{len(filtrado)}** · PF/PJ: **{pf:.1f}** · PC/PJ: **{pc:.1f}** · Diferencia: **{pf-pc:+.1f}**')
            if modo == 'Según sede' and len(filtrado) < 5:
                st.warning(f'Muestra pequeña: {nombre} tiene solo {len(filtrado)} partido(s) como {sede.lower()}. Los promedios por sede son preliminares.')
        st.caption('El filtro según sede solo cambia la comparación descriptiva; no modifica la proyección existente.')
        st.caption('La estimación de ataque/defensa con marcadores completos puede incluir prórrogas históricas.')

    with st.expander('⏱️ Evolución de puntos por cuartos', expanded=False):
        orden = ['Q1', 'Q2', 'Q3', 'Q4']
        datos = tabla_periodos.set_index('Período').reindex(orden)[['Visitante', 'Local']]
        if datos.notna().all().all():
            acum = datos.astype(float).cumsum()
            ab_vis, ab_loc = _abreviatura_equipo(visita), _abreviatura_equipo(local)
            # SVG estático integrado en Streamlit: sin matplotlib ni tooltips.
            import streamlit.components.v1 as components
            import html
            def _svg_lineas(acumulado):
                w, h = 580, 270
                izq, der, arriba, abajo = 52, 20, 28, 43
                ancho, alto = w-izq-der, h-arriba-abajo
                maximo = max(float(acumulado.max().max()), 1.) * 1.20
                xx = [izq + i*ancho/3 for i in range(4)]
                yy = lambda v: arriba + alto*(1-float(v)/maximo)
                partes = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" role="img" aria-label="Puntos acumulados por cuarto" style="width:100%;height:auto;background:#0e1117">']
                for j in range(5):
                    valor = maximo*j/4
                    y = yy(valor)
                    partes.append(f'<line x1="{izq}" y1="{y:.1f}" x2="{w-der}" y2="{y:.1f}" stroke="#364152" stroke-width="1"/>')
                    partes.append(f'<text x="{izq-9}" y="{y+4:.1f}" fill="#cbd5e1" font-size="12" text-anchor="end">{valor:.0f}</text>')
                for i, q in enumerate(orden):
                    partes.append(f'<text x="{xx[i]:.1f}" y="{h-12}" fill="#cbd5e1" font-size="13" text-anchor="middle">{q}</text>')
                for col, color, nombre, dy in [('Visitante','#2879d0',ab_vis,17),('Local','#84c9ff',ab_loc,-10)]:
                    vals = acumulado[col].astype(float).tolist()
                    puntos = ' '.join(f'{xx[i]:.1f},{yy(v):.1f}' for i,v in enumerate(vals))
                    partes.append(f'<polyline points="{puntos}" fill="none" stroke="{color}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>')
                    for i,v in enumerate(vals):
                        partes.append(f'<circle cx="{xx[i]:.1f}" cy="{yy(v):.1f}" r="4" fill="{color}"/>')
                        partes.append(f'<text x="{xx[i]:.1f}" y="{yy(v)+dy:.1f}" fill="{color}" font-size="12" text-anchor="middle">{v:.1f}</text>')
                partes.append(f'<text x="{izq}" y="16" fill="#84c9ff" font-size="12">{html.escape(ab_loc)} (local)</text>')
                partes.append(f'<text x="{izq+120}" y="16" fill="#2879d0" font-size="12">{html.escape(ab_vis)} (visitante)</text>')
                return ''.join(partes)+'</svg>'
            components.html(_svg_lineas(acum), height=285, scrolling=False)
            st.caption('Puntos acumulados estimados; no representa una simulación de jugadas.')
            diferencia = acum['Local'] - acum['Visitante']
            st.markdown('**📋 Marcador acumulado por cuarto**')
            for q in orden:
                v, l = float(acum.loc[q, 'Visitante']), float(acum.loc[q, 'Local'])
                dif = l-v
                lider = ab_loc if dif > 0 else ab_vis if dif < 0 else 'Igualados'
                st.caption(f'**{q}** · {ab_vis} {v:.1f} · {ab_loc} {l:.1f} · '
                           f'{lider} {abs(dif):.1f} pts' if dif else
                           f'**{q}** · {ab_vis} {v:.1f} · {ab_loc} {l:.1f} · Igualados')
            st.markdown('**📈 Diferencia acumulada (local − visitante)**')
            def _svg_diferencias(diferencias):
                w,h = 580,245
                izq,der,arriba,abajo = 52,20,24,40
                ancho,alto = w-izq-der,h-arriba-abajo
                valores = diferencias.astype(float).tolist()
                minimo = min(0., min(valores))
                maximo = max(0., max(valores))
                margen = max(1., (maximo-minimo)*.22)
                inferior, superior = minimo-margen, maximo+margen
                yy = lambda v: arriba+alto*(superior-float(v))/(superior-inferior)
                base = yy(0)
                partes = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" role="img" aria-label="Diferencia acumulada local menos visitante" style="width:100%;height:auto;background:#0e1117">']
                partes.append(f'<line x1="{izq}" y1="{base:.1f}" x2="{w-der}" y2="{base:.1f}" stroke="#cbd5e1" stroke-width="1"/>')
                for i,(q,v) in enumerate(zip(orden,valores)):
                    cx = izq+(i+.5)*ancho/4
                    y = yy(v)
                    partes.append(f'<rect x="{cx-29:.1f}" y="{min(y,base):.1f}" width="58" height="{max(abs(y-base),1):.1f}" fill="{ "#84c9ff" if v>=0 else "#2879d0" }"/>')
                    etiqueta_y = max(15,y-7) if v>=0 else min(h-abajo+15,y+17)
                    partes.append(f'<text x="{cx:.1f}" y="{etiqueta_y:.1f}" fill="#f1f5f9" font-size="14" text-anchor="middle">{v:+.1f}</text>')
                    partes.append(f'<text x="{cx:.1f}" y="{h-10}" fill="#cbd5e1" font-size="13" text-anchor="middle">{q}</text>')
                return ''.join(partes)+'</svg>'
            components.html(_svg_diferencias(diferencia), height=255, scrolling=False)
            st.caption('Positivo: mayor puntuación acumulada del local; negativo: del visitante.')
            idx = diferencia.abs().idxmax()
            max_dif = float(diferencia.loc[idx])
            lider_max = local if max_dif > 0 else visita if max_dif < 0 else None
            if lider_max:
                st.info(f'🧠 La mayor separación acumulada estimada ocurre al terminar {idx}: '
                        f'{lider_max} +{abs(max_dif):.1f} puntos. '
                        'Los cambios entre cuartos son descriptivos, no resultados observados.')
        else:
            st.info('Faltan datos completos por cuartos para mostrar la evolución.')

    with st.expander('📐 Proyección frente a referencia', expanded=False):
        if valido and pd.notna(fila['Referencia total']):
            ref = float(fila['Referencia total'])
            c1, c2 = st.columns(2)
            c1.metric('Referencia · reglamentario', f'{ref:.1f} pts')
            c2.metric('Diferencia del total', f'{total-ref:+.1f} pts')
            st.caption('Referencia por períodos: anotación reciente. No es una validación independiente.')
        else:
            st.info('No hay referencia completa por períodos.')
        diferencias = []
        for nombre, sede in ((visita, 'Visitante'), (local, 'Local')):
            d = historiales[nombre]
            pf = pd.to_numeric(d['PF'], errors='coerce').dropna().tail(5) if 'PF' in d else pd.Series(dtype=float)
            if nombre in proy and len(pf) == 5:
                proyeccion, referencia = float(proy[nombre]), float(pf.mean())
                delta = proyeccion - referencia
                diferencias.append((nombre, delta))
                st.markdown(f'**{"✈️" if sede == "Visitante" else "🏠"} {nombre}**')
                st.caption(f'Proyección completa: **{proyeccion:.1f}** · Referencia: **{referencia:.1f}** · '
                           f'Diferencia: **{delta:+.1f} pts**')
            else:
                st.caption(f'{nombre}: sin cinco marcadores válidos para referencia individual.')
        if len(diferencias) == 2:
            (n1, d1), (n2, d2) = diferencias
            if d1*d2 < 0:
                st.info(f'🧠 Las diferencias individuales se compensan parcialmente: '
                        f'{_abreviatura_equipo(n1)} {d1:+.1f} pts y '
                        f'{_abreviatura_equipo(n2)} {d2:+.1f} pts. '
                        'Una diferencia pequeña en el total no implica coincidencia por equipo.')
        st.caption('Las referencias individuales usan marcadores completos y pueden incluir prórrogas; '
                   'no deben confundirse con la referencia total por cuartos.')

    with st.expander('🧪 Calidad de datos y validación', expanded=False):
        st.caption(f'Partidos históricos · {visita}: **{len(historiales[visita])}** · '
                   f'{local}: **{len(historiales[local])}**')
        st.caption(f'Cuatro cuartos observados · {visita}: **{len(muestras[visita])}** · '
                   f'{local}: **{len(muestras[local])}**')
        if min(len(muestras[visita]), len(muestras[local])) < 10:
            st.warning('Muestra por períodos limitada: las estimaciones pueden variar con nuevos partidos.')
        st.markdown('**🧪 Validación general NBA · ataque/defensa**')
        if pd.isna(fecha):
            st.info('No hay fecha válida para realizar la evaluación histórica.')
        else:
            try:
                evaluaciones = _validacion_historica_equipos(partidos, fecha)
                validos = evaluaciones.dropna(subset=['ataque', 'real_completo'])
                if validos.empty:
                    st.info('Aún no hay suficientes partidos históricos para evaluar el método.')
                else:
                    error = validos['ataque'] - validos['real_completo']
                    st.caption(f'**{len(validos)} evaluaciones cronológicas** · '
                               f'MAE: **{error.abs().mean():.1f} pts** · '
                               f'Sesgo: **{error.mean():+.1f} pts**')
                    if len(validos) < 20:
                        st.warning('Validación provisional: menos de 20 evaluaciones.')
                    st.caption('MAE = error absoluto medio; sesgo positivo = sobreestimación. '
                               'No representan probabilidades de acierto.')
            except (KeyError, ValueError, TypeError, IndexError) as exc:
                st.warning(f'Validación general no disponible ({type(exc).__name__}).')
        st.caption('La validación es general para los partidos anteriores del calendario consultado, '
                   'no mide la precisión específica de este encuentro. '
                   'La validación por cuartos se consulta por separado en el panel histórico.')


# Registro de proyecciones: funcionalidad independiente de los cálculos.
def _nba_archivo_registros():
    import os
    return os.environ.get('NBA_REGISTRO_RUTA', 'nba_proyecciones_registradas.json')

def _nba_leer_registros():
    from proyecciones_supabase import leer
    return leer('NBA')


def _nba_guardar_registros(registros):
    from proyecciones_supabase import insertar_nuevos
    return insertar_nuevos('NBA', registros, origen='respaldo_json')


def _nba_registrar_proyeccion(partido, tabla_periodos):
    """Guarda solo encuentros futuros; nunca sobrescribe la primera proyección."""
    from datetime import datetime, timezone
    fecha = pd.to_datetime(partido.get('fecha_utc'), utc=True, errors='coerce')
    if pd.isna(fecha) or fecha <= pd.Timestamp.now(tz='UTC'):
        return False, 'Partido iniciado o sin fecha válida: no se crea una proyección retrospectiva.'
    clave = str(partido.get('id', ''))
    if not clave:
        return False, 'Falta el identificador del encuentro.'
    try:
        registros = _nba_leer_registros()
    except Exception as exc:
        return False, f'No se pudo consultar Supabase: {exc}'
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
        from proyecciones_supabase import insertar_nuevos
        creados = insertar_nuevos('NBA', {clave: registros[clave]})
    except Exception as exc:
        return False, f'No se pudo confirmar el guardado en Supabase: {exc}'
    if not creados:
        return False, 'El encuentro ya tiene una proyección original; no se sobrescribe.'
    return True, 'Proyección original guardada en Supabase.'

def _nba_fecha_mazatlan(valor, formato='%d/%m/%Y %H:%M'):
    """Solo presentación: conserva intacta la fecha UTC de origen."""
    fecha = pd.to_datetime(valor, utc=True, errors='coerce')
    if pd.isna(fecha):
        return 'Fecha no disponible'
    return fecha.tz_convert(ZoneInfo('America/Mazatlan')).strftime(formato)

def _nba_panel_seguimiento(partidos):
    """Compara proyecciones previas con resultados; no inventa períodos ausentes."""
    import json
    with st.expander('🧪 Seguimiento de proyecciones registradas', expanded=False):
        st.caption('Las proyecciones deben haberse guardado antes del inicio. Los resultados se verifican al volver a abrir o actualizar la aplicación; no existe ejecución en segundo plano.')
        try:
            registros = _nba_leer_registros()
        except Exception as exc:
            st.error(f'No se pudo consultar Supabase: {exc}')
            return
        st.download_button('📥 Respaldar registros JSON',
                           json.dumps(registros, ensure_ascii=False, indent=2).encode('utf-8'),
                           file_name='nba_proyecciones_respaldo.json', mime='application/json',
                           key='ri_nba_respaldo_registros')
        archivo = st.file_uploader('Restaurar respaldo JSON (sin sobrescribir registros existentes)',
                                   type=['json'], key='ri_nba_importar_registros')
        if archivo is not None and st.button('Restaurar registros', key='ri_nba_restaurar'):
            try:
                nuevos = json.load(archivo)
                if not isinstance(nuevos, dict):
                    raise ValueError('El archivo no contiene un diccionario de registros.')
                agregados = 0
                for clave, registro in nuevos.items():
                    if (isinstance(registro, dict) and isinstance(registro.get('periodos'), dict)
                            and str(clave) == str(registro.get('id')) and clave not in registros):
                        registros[clave] = registro
                        agregados += 1
                insertados = _nba_guardar_registros(registros)
                st.success(f'Registros nuevos restaurados en Supabase: {insertados}. Actualiza la vista para comprobar resultados.')
            except Exception as exc:
                st.error(f'Respaldo no válido o no guardado: {type(exc).__name__}.')
        registros = _nba_leer_registros()
        if not registros:
            st.info('Aún no hay proyecciones en Supabase. Puedes restaurar un respaldo JSON desde el control anterior.')
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
                # Marcadores finales incluyen prórroga. No se comparan con tiempo reglamentario.
                puntos_local = pd.to_numeric(fila.get('puntos_local'), errors='coerce')
                puntos_visita = pd.to_numeric(fila.get('puntos_visitante'), errors='coerce')
                if pd.notna(puntos_local) and pd.notna(puntos_visita):
                    estado = 'Finalizado · pendientes cuartos verificables'
                    # Recuperar únicamente detalles de partidos registrados y finalizados.
                    try:
                        cuartos = _puntos_periodos(cargar_detalle(str(clave)))
                        if registro.get('local') in cuartos and registro.get('visitante') in cuartos:
                            observado = sum(cuartos[registro['local']].values()) + sum(cuartos[registro['visitante']].values())
                            if proy is not None:
                                error = float(proy) - float(observado)
                            estado = 'Evaluado · reglamentario'
                    except Exception:
                        pass
            filas.append({'Partido': f"{registro.get('visitante','?')} @ {registro.get('local','?')}",
                          'Fecha Mazatlán': _nba_fecha_mazatlan(registro.get('fecha_utc')),
                          'Proyección': proy, 'Observado': observado,
                          'Error firmado': round(error, 2) if error is not None else None,
                          'Estado': estado})
        tabla = pd.DataFrame(filas)
        # Tarjetas verticales: legibles en teléfonos sin desplazamiento lateral.
        st.markdown('**📱 Historial de proyecciones**')
        for _, item in tabla.iterrows():
            with st.container(border=True):
                st.markdown(f"**{item['Partido']}**")
                st.caption(f"📅 {item['Fecha Mazatlán']} · Mazatlán")
                st.write(f"**Proyección reglamentaria:** {float(item['Proyección']):.1f} pts" if pd.notna(item['Proyección']) else '**Proyección reglamentaria:** —')
                if pd.notna(item['Observado']):
                    st.write(f"**Observado:** {float(item['Observado']):.1f} pts · **Error firmado:** {float(item['Error firmado']):+.1f} pts")
                else:
                    st.caption('Observado: pendiente · Error firmado: —')
                st.caption(f"Estado: {item['Estado']}")
        with st.expander('📋 Tabla detallada', expanded=False):
            st.dataframe(tabla.fillna('—'), hide_index=True, use_container_width=True)
        validos = pd.to_numeric(tabla['Error firmado'], errors='coerce').dropna()
        if len(validos):
            a, b, c = st.columns(3)
            a.metric('Evaluados', len(validos))
            b.metric('MAE total', f'{validos.abs().mean():.2f}')
            c.metric('Sesgo total', f'{validos.mean():+.2f}')
            if len(validos) < 20:
                st.warning('Muestra pequeña: métricas provisionales.')
        st.caption('Historial almacenado en Supabase. Conserva también un respaldo JSON independiente.')



# ---------------------------------------------------------------------------
# Laboratorio NBA 3.12.17: cálculos adicionales aislados; no altera el modelo
# original ni el registro de proyecciones en Supabase.
# ---------------------------------------------------------------------------
def _nba_lab_numero(valor):
    """Acepta números y cadenas simples; no convierte ausencias en cero."""
    try:
        if valor is None or isinstance(valor, bool):
            return None
        v = float(str(valor).replace(',', '').replace('%', '').strip())
        import math
        return v if math.isfinite(v) else None
    except (ValueError, TypeError):
        return None


def _nba_lab_estadisticas_equipo(detalle, auditoria=False):
    """Extrae cuatro componentes reales de boxscore ESPN y explica ausencias.

    No rellena ceros. Admite estadísticas separadas y tiros en formato M-A.
    """
    import re
    salida, diagnostico = {}, {}
    equipos = (detalle.get('boxscore') or {}).get('teams') or []
    aliases = {
        'fieldgoalsattempted':'fga', 'fieldgoalattempts':'fga', 'fga':'fga',
        'freethrowsattempted':'fta', 'freethrowattempts':'fta', 'fta':'fta',
        'offensiverebounds':'oreb', 'offensiverebound':'oreb', 'offreb':'oreb',
        'oreb':'oreb', 'offrebounds':'oreb', 'rebounds-offensive':'oreb',
        'turnovers':'tov', 'turnover':'tov', 'to':'tov', 'tov':'tov',
        'totalturnovers':'tov',
    }
    tiros = {
        'fieldgoals':'fga', 'fg':'fga', 'fieldgoalsmade-fieldgoalsattempted':'fga',
        'fieldgoalsmadeattempted':'fga',
        'freethrows':'fta', 'ft':'fta', 'freethrowsmade-freethrowsattempted':'fta',
        'freethrowsmadeattempted':'fta',
    }
    for entrada in equipos:
        nombre = (entrada.get('team') or {}).get('displayName')
        if not nombre:
            continue
        valores, vistos = {}, []
        for stat in entrada.get('statistics') or []:
            if not isinstance(stat, dict):
                continue
            claves = [str(stat.get(k) or '') for k in ('name','abbreviation','label','displayName')]
            valor = stat.get('displayValue')
            if valor is None or str(valor).strip() in ('', '--'):
                valor = stat.get('value')
            vistos.append({'nombre':claves[0], 'abreviatura':claves[1], 'valor':str(valor)[:32]})
            for clave in claves:
                normal = re.sub(r'[^a-z0-9-]', '', clave.lower())
                if normal in aliases:
                    numero = _nba_lab_numero(valor)
                    if numero is not None:
                        valores[aliases[normal]] = numero
                if normal in tiros:
                    match = re.fullmatch(r'\s*(\d+)\s*[-/]\s*(\d+)\s*', str(valor))
                    if match:
                        valores[tiros[normal]] = float(match.group(2))
        faltan = [k for k in ('fga','fta','oreb','tov') if k not in valores]
        razon = 'OK' if not faltan else 'Faltan: ' + ', '.join(faltan)
        if not faltan:
            fga, fta, oreb, tov = (valores[k] for k in ('fga','fta','oreb','tov'))
            posesiones = fga - oreb + tov + .44 * fta
            if 40 <= posesiones <= 160:
                salida[nombre] = {'posesiones': posesiones, **valores}
            else:
                razon = f'Posesiones fuera de rango: {posesiones:.1f}'
        diagnostico[nombre] = {'Estado':razon, 'Campos':valores, 'Muestra ESPN':vistos[:15]}
    if not equipos:
        diagnostico['_general'] = {'Estado':'Sin boxscore.teams', 'Campos':{}, 'Muestra ESPN':[]}
    return (salida, diagnostico) if auditoria else salida


def _nba_lab_posesiones_previas(partidos, fecha, equipos, cache_detalles, max_por_equipo=10,
                               permitir_consultas=False, max_consultas=100):
    """Recolecta boxscores de partidos estrictamente anteriores al corte UTC.

    Caché de la sesión reutilizada; limita solicitudes y devuelve auditoría.
    """
    posesiones = {equipo: [] for equipo in equipos}
    auditoria, consultas = [], 0
    anteriores = partidos.copy()
    anteriores['_fecha_pace'] = pd.to_datetime(anteriores['fecha_utc'], utc=True, errors='coerce')
    anteriores = anteriores.loc[anteriores['_fecha_pace'].lt(fecha) & anteriores['finalizado'].eq(True)]
    anteriores = anteriores.dropna(subset=['puntos_local','puntos_visitante'])
    for equipo in equipos:
        juegos = anteriores.loc[(anteriores['local'].eq(equipo)) | (anteriores['visitante'].eq(equipo))]
        juegos = juegos.sort_values('_fecha_pace', ascending=False).head(max_por_equipo)
        for fila in juegos.to_dict('records'):
            ident = str(fila['id'])
            detalle = cache_detalles.get(ident)
            origen = 'Caché'
            if not isinstance(detalle, dict) and permitir_consultas and consultas < max_consultas:
                consultas += 1
                try:
                    detalle = cargar_detalle(ident)
                    if isinstance(detalle, dict):
                        cache_detalles[ident] = detalle
                        origen = 'ESPN'
                except Exception as exc:
                    auditoria.append({'Equipo':equipo,'Partido':ident,'Fecha':str(fila['fecha_utc']),
                                      'Estado':f'Error ESPN: {type(exc).__name__}', 'Origen':'ESPN',
                                      'Campos detectados':''})
                    continue
            if not isinstance(detalle, dict):
                auditoria.append({'Equipo':equipo,'Partido':ident,'Fecha':str(fila['fecha_utc']),
                                  'Estado':'Detalle no consultado', 'Origen':'Sin caché',
                                  'Campos detectados':''})
                continue
            datos, diag = _nba_lab_estadisticas_equipo(detalle, auditoria=True)
            estad = datos.get(equipo)
            if estad:
                es_local = fila['local'] == equipo
                pf = float(fila['puntos_local'] if es_local else fila['puntos_visitante'])
                pc = float(fila['puntos_visitante'] if es_local else fila['puntos_local'])
                posesiones[equipo].append({**estad,'pf':pf,'pc':pc})
            d = diag.get(equipo, {'Estado':'Equipo no encontrado en boxscore.teams','Campos':{}})
            auditoria.append({'Equipo':equipo,'Partido':ident,'Fecha':str(fila['fecha_utc']),
                              'Estado':d['Estado'],'Origen':origen,
                              'Campos detectados':str(d.get('Campos',{})),
                              'Ejemplo ESPN':str(d.get('Muestra ESPN',[])[:5])})
    return posesiones, pd.DataFrame(auditoria), consultas



def _nba_lab_dias_descanso(historial, fecha):
    if historial.empty or pd.isna(fecha):
        return None
    ult = pd.to_datetime(historial['fecha_utc'], utc=True, errors='coerce').dropna()
    if ult.empty:
        return None
    # Día de calendario local: partidos consecutivos pueden empezar en días UTC diferentes.
    anterior = ult.max().tz_convert('America/Mazatlan').date()
    actual = fecha.tz_convert('America/Mazatlan').date()
    return max(0, (actual-anterior).days-1)


def _nba_lab_calcular(partidos, partido, ajustes, posesiones=None):
    """Predicción experimental de ambos equipos; no modifica proyecciones originales."""
    fecha = pd.to_datetime(partido['fecha_utc'], utc=True, errors='coerce')
    local, visita = str(partido['local']), str(partido['visitante'])
    h = {e: _historial_equipo(partidos, e, fecha) for e in (local, visita)}
    resultado = {}
    for equipo, rival, sede in ((local, visita, 'Local'), (visita, local, 'Visitante')):
        propio, contrario = h[equipo], h[rival]
        if propio.empty or contrario.empty:
            return None
        pf = pd.to_numeric(propio['PF'], errors='coerce').dropna().tail(10)
        pc = pd.to_numeric(contrario['PC'], errors='coerce').dropna().tail(10)
        if min(len(pf), len(pc)) < 3:
            return None
        base = (pf.mean() + pc.mean()) / 2
        pred = float(base)
        componentes = {'Base': round(pred, 2)}
        if ajustes.get('forma') and len(pf) >= 5 and len(pc) >= 5:
            reciente = (pf.tail(5).mean() + pc.tail(5).mean()) / 2
            pred = .7 * pred + .3 * reciente
            componentes['Forma 5'] = round(pred-base, 2)
        if ajustes.get('sede'):
            propia_sede = propio.loc[propio['Sede'].eq(sede), 'PF'].tail(10)
            rival_sede = contrario.loc[contrario['Sede'].eq('Visitante' if sede == 'Local' else 'Local'), 'PC'].tail(10)
            if len(propia_sede) >= 5 and len(rival_sede) >= 5:
                especifica = (propia_sede.mean() + rival_sede.mean()) / 2
                antes = pred
                pred = .8 * pred + .2 * especifica
                componentes['Sede'] = round(pred-antes, 2)
        if ajustes.get('descanso'):
            dias = _nba_lab_dias_descanso(propio, fecha)
            rival_dias = _nba_lab_dias_descanso(contrario, fecha)
            if dias is not None and rival_dias is not None:
                # Hipótesis exploratoria, no coeficiente calibrado.
                diferencia = max(-2, min(2, dias-rival_dias))
                antes = pred
                pred += .5 * diferencia
                componentes['Descanso (experimental)'] = round(pred-antes, 2)
        resultado[equipo] = {'base': float(base), 'pred': pred, 'componentes': componentes,
                             'descanso': _nba_lab_dias_descanso(propio, fecha)}
    if ajustes.get('pace') and posesiones:
        # Solo con >=3 boxscores por equipo; ratings = puntos/posesiones * 100.
        if all(e in posesiones and len(posesiones[e]) >= 3 for e in (local, visita)):
            import statistics
            pace = statistics.mean([statistics.mean([x['posesiones'] for x in posesiones[e]]) for e in (local, visita)])
            if 60 <= pace <= 140:
                for equipo, rival in ((local, visita), (visita, local)):
                    own = posesiones[equipo]
                    opp = posesiones[rival]
                    off = statistics.mean([x['pf']/x['posesiones']*100 for x in own])
                    defense = statistics.mean([x['pc']/x['posesiones']*100 for x in opp])
                    estimado = pace * (off+defense)/200
                    if 60 <= estimado <= 180:
                        antes = resultado[equipo]['pred']
                        # Mezcla conservadora; peso a calibrar con backtesting.
                        resultado[equipo]['pred'] = (1 - float(ajustes.get('peso_pace', .5))) * antes + float(ajustes.get('peso_pace', .5)) * estimado
                        resultado[equipo]['componentes']['Pace + ORtg/DRtg'] = round(resultado[equipo]['pred']-antes, 2)
                        resultado[equipo]['pace'] = round(pace, 2)
                        resultado[equipo]['ortg'] = round(off, 2)
                        resultado[equipo]['drtg_rival'] = round(defense, 2)
    return resultado



# Motor C: mejoras aisladas, reversibles y sujetas a validación.
def _nba_lab_modelo_c(partidos, partido, ajustes, posesiones=None):
    """Modelo C: nunca utiliza marcadores de la fecha evaluada o posteriores."""
    import math
    fecha = pd.to_datetime(partido.get('fecha_utc'), utc=True, errors='coerce')
    if pd.isna(fecha):
        return None
    anteriores = partidos.copy()
    anteriores['_fecha_lab'] = pd.to_datetime(anteriores['fecha_utc'], utc=True, errors='coerce')
    anteriores = anteriores.loc[anteriores['_fecha_lab'].lt(fecha) & anteriores['finalizado'].eq(True)].copy()
    anteriores = anteriores.dropna(subset=['puntos_local', 'puntos_visitante'])
    if anteriores.empty:
        return None
    # Solo partidos anteriores: no filtrar por el resultado del juego a predecir.
    base = _nba_lab_calcular(anteriores, partido, ajustes, posesiones)
    if base is None:
        return None
    totales = pd.concat([pd.to_numeric(anteriores['puntos_local'], errors='coerce'),
                         pd.to_numeric(anteriores['puntos_visitante'], errors='coerce')]).dropna()
    media_liga = float(totales.mean()) if len(totales) >= 20 else None
    for equipo, rival in ((str(partido['local']), str(partido['visitante'])),
                          (str(partido['visitante']), str(partido['local']))):
        dato = base[equipo]
        pred = float(dato['pred'])
        hist = _historial_equipo(anteriores, equipo, fecha)
        rival_hist = _historial_equipo(anteriores, rival, fecha)
        if ajustes.get('fuerza') and media_liga is not None and len(hist) >= 5:
            # Fuerza del calendario: ajustar puntos logrados según la defensa media
            # de los oponentes, calculada solo con partidos anteriores al corte.
            ajustes_rival = []
            for fila in hist.tail(10).itertuples(index=False):
                oponente = str(fila.Rival)
                o_hist = _historial_equipo(anteriores, oponente, pd.to_datetime(fila.fecha_utc, utc=True))
                if len(o_hist) >= 3:
                    ajustes_rival.append(float(o_hist['PC'].tail(10).mean()) - media_liga)
            if len(ajustes_rival) >= 3:
                delta = -0.15 * float(sum(ajustes_rival) / len(ajustes_rival))
                pred += delta
                dato['componentes']['Fuerza calendario (exploratorio)'] = round(delta, 2)
        if ajustes.get('regresion') and media_liga is not None:
            # Encogimiento prudente con muestra pequeña, no coeficiente validado.
            n = min(len(hist), len(rival_hist))
            peso = max(0.05, min(0.25, 5.0 / (n + 5.0)))
            anterior = pred
            pred = (1-peso)*pred + peso*media_liga
            dato['componentes']['Regresión media liga'] = round(pred-anterior, 2)
        dato['pred'] = round(max(60.0, min(180.0, pred)), 3)
        # Rango descriptivo, NO intervalo de confianza calibrado.
        residuos = pd.to_numeric(hist['PF'], errors='coerce').dropna().tail(15)
        dato['desviacion_historica'] = round(float(residuos.std()), 2) if len(residuos) >= 5 else None
        dato['muestra'] = len(hist)
    return base


def _nba_lab_validacion_pareada(partidos, ajustes, limite=100, incluir_pace=False,
                                  cache_detalles=None, max_consultas=120):
    """Backtest cronológico pareado, con opción Pace de datos prepartido reales.

    Compara sobre los mismos juegos base, C sin Pace y C con Pace. No utiliza
    boxscores del encuentro evaluado ni partidos posteriores al corte.
    """
    datos = partidos.copy()
    datos['_fecha_lab'] = pd.to_datetime(datos['fecha_utc'], utc=True, errors='coerce')
    datos = datos.loc[datos['finalizado'].eq(True)].dropna(
        subset=['_fecha_lab','puntos_local','puntos_visitante']).sort_values('_fecha_lab')
    filas = []
    cache_detalles = cache_detalles if cache_detalles is not None else {}
    consultas = 0
    for fila in datos.tail(limite).to_dict('records'):
        previo = datos.loc[datos['_fecha_lab'].lt(fila['_fecha_lab'])]
        original = _nba_lab_calcular(previo, fila, {'forma':False,'sede':False,'descanso':False,'pace':False})
        sin_pace = _nba_lab_modelo_c(previo, fila, {**ajustes,'pace':False})
        if original is None or sin_pace is None:
            continue
        estim_pace, conteos = None, {fila['local']:0, fila['visitante']:0}
        if incluir_pace:
            faltantes = max(0, max_consultas - consultas)
            posesiones, _, nuevas = _nba_lab_posesiones_previas(
                previo, fila['_fecha_lab'], (fila['local'], fila['visitante']),
                cache_detalles, max_por_equipo=10, permitir_consultas=faltantes>0,
                max_consultas=faltantes)
            consultas += nuevas
            conteos = {e:len(posesiones[e]) for e in conteos}
            if min(conteos.values()) >= 3:
                estim_pace = _nba_lab_modelo_c(previo, fila, {**ajustes,'pace':True, 'peso_pace':.5}, posesiones)
                estim_pace_25 = _nba_lab_modelo_c(previo, fila, {**ajustes,'pace':True, 'peso_pace':.25}, posesiones)
            else:
                estim_pace_25 = None
        else:
            estim_pace_25 = None
        for equipo, real in ((fila['local'],fila['puntos_local']),
                             (fila['visitante'],fila['puntos_visitante'])):
            filas.append({'fecha':str(fila['fecha_utc']),'partido':str(fila['id']),
                          'equipo':equipo,'real':float(real),
                          'base':float(original[equipo]['pred']),
                          'modelo_c':float(sin_pace[equipo]['pred']),
                          'modelo_c_pace':(float(estim_pace[equipo]['pred'])
                                          if estim_pace and 'pace' in estim_pace[equipo] else None),
                          'modelo_c_pace_25':(float(estim_pace_25[equipo]['pred'])
                                          if estim_pace_25 and 'pace' in estim_pace_25[equipo] else None),
                          'boxscores_previos':conteos[equipo]})
    return pd.DataFrame(filas)



def _nba_lab_resumen_errores(df):
    import math
    resumen=[]
    for nombre in ('base','modelo_c'):
        e = df[nombre] - df['real']
        resumen.append({'Modelo':nombre, 'Predicciones':len(e),
                        'MAE':round(float(e.abs().mean()),2),
                        'RMSE':round(math.sqrt(float((e*e).mean())),2),
                        'Sesgo (+ sobreestima)':round(float(e.mean()),2)})
    return pd.DataFrame(resumen)


def _nba_lab_panel(partidos, partido, historiales, cache_detalles):
    """Herramientas de prueba dentro de la tarjeta original; sin escrituras."""
    local, visita = str(partido['local']), str(partido['visitante'])
    with st.expander('🧪 Laboratorio NBA 3.12.17 · ajustes y pruebas', expanded=False):
        st.caption('Independiente de las proyecciones originales y del guardado Supabase. '
                   'Los ajustes son hipótesis que deben validarse antes de adoptarse.')
        c1, c2 = st.columns(2)
        with c1:
            forma = st.checkbox('Forma reciente (5)', value=True, key='nba_lab_forma')
            sede = st.checkbox('Localía / visita', value=True, key='nba_lab_sede')
        with c2:
            descanso = st.checkbox('Días de descanso', value=True, key='nba_lab_descanso')
            pace = st.checkbox('Pace + ORtg/DRtg', value=True, key='nba_lab_pace')
        c3, c4 = st.columns(2)
        with c3:
            fuerza = st.checkbox('Fuerza de rivales', value=True, key='nba_lab_fuerza')
        with c4:
            regresion = st.checkbox('Regresión a media', value=True, key='nba_lab_regresion')
        st.caption('La disponibilidad de jugadores no se aplica automáticamente: no hay una '
                   'fuente prepartido confirmada en estos archivos. No se inventan lesiones.')
        fechas = pd.to_datetime(partido['fecha_utc'], utc=True, errors='coerce')
        posesiones = {local: [], visita: []}
        if pace:
            st.caption('Auditoría Pace: consulta únicamente boxscores anteriores al partido. '
                       'Los campos ausentes nunca se sustituyen por cero.')
            consultar = st.button('🔍 Recuperar y auditar boxscores Pace',
                                  key=f'nba_lab_auditar_pace_{partido["id"]}')
            with st.spinner('Verificando campos de ESPN...') if consultar else st.container():
                posesiones, auditoria, consultas = _nba_lab_posesiones_previas(
                    partidos, fechas, (local, visita), cache_detalles,
                    max_por_equipo=10, permitir_consultas=consultar, max_consultas=20)
            st.caption(f'Posesiones verificables: {visita} {len(posesiones[visita])}/10 · '
                       f'{local} {len(posesiones[local])}/10 · Nuevas consultas ESPN: {consultas}.')
            if not auditoria.empty:
                with st.expander('🔎 Diagnóstico por boxscore ESPN'):
                    st.dataframe(auditoria, hide_index=True, use_container_width=True)
                    st.download_button('Descargar auditoría Pace CSV',
                                       auditoria.to_csv(index=False).encode('utf-8-sig'),
                                       file_name='nba_pace_auditoria.csv', mime='text/csv',
                                       key=f'nba_lab_pace_auditoria_{partido["id"]}')
            if min(len(posesiones[local]),len(posesiones[visita])) < 3:
                st.warning('Pace no aplicado: se necesitan al menos 3 boxscores completos '
                           'por equipo, anteriores al encuentro.')
        ajustes = {'forma':forma, 'sede':sede, 'descanso':descanso, 'pace':pace,
                   'fuerza':fuerza, 'regresion':regresion}
        estim = _nba_lab_modelo_c(partidos, partido, ajustes, posesiones)
        if estim is None:
            st.info('Faltan marcadores históricos para ejecutar el laboratorio.')
            return
        filas = []
        for equipo in (visita, local):
            dato = estim[equipo]
            filas.append({'Equipo':_abreviatura_equipo(equipo), 'Base':round(dato['base'],1),
                          'Experimental':round(dato['pred'],1),
                          'Cambio':round(dato['pred']-dato['base'],1),
                          'Descanso':dato['descanso']})
        filas.append({'Equipo':'TOTAL', 'Base':round(sum(v['base'] for v in estim.values()),1),
                      'Experimental':round(sum(v['pred'] for v in estim.values()),1),
                      'Cambio':round(sum(v['pred']-v['base'] for v in estim.values()),1),
                      'Descanso':None})
        st.dataframe(pd.DataFrame(filas), hide_index=True, use_container_width=True)
        for equipo in (visita, local):
            dato = estim[equipo]
            with st.expander(f'🔎 Componentes · {_abreviatura_equipo(equipo)}'):
                st.json(dato['componentes'])
                if 'pace' in dato:
                    st.write({'Pace aproximado':dato['pace'], 'ORtg':dato['ortg'],
                              'DRtg rival (puntos permitidos)':dato['drtg_rival']})
        st.caption('Pace = FGA − rebotes ofensivos + pérdidas + 0.44×FTA (aproximación). '
                   'ORtg y DRtg son estimaciones por 100 posesiones. '
                   'El descanso usa 0.5 puntos por día relativo como hipótesis provisional. '
                   'No existe calibración demostrada de estos pesos.')
        st.download_button('📥 Descargar comparación experimental CSV',
                           pd.DataFrame(filas).to_csv(index=False).encode('utf-8-sig'),
                           file_name=f'nba_lab_{partido["id"]}.csv', mime='text/csv',
                           key=f'nba_lab_export_{partido["id"]}')
        st.markdown('**🧪 Laboratorio de comparación pareada: Base estadística vs Modelo C**')
        st.caption('Prueba cronológica: los tres modelos usan los mismos partidos. '
                   'Pace solo utiliza boxscores previos al juego evaluado. '
                   'La muestra con Pace puede ser menor y se informa por separado.')
        activar_pace_prueba = st.checkbox('Incluir prueba histórica Pace + ORtg/DRtg',
                                         value=False, key=f'nba_lab_pace_backtest_{partido["id"]}')
        limite_prueba = st.slider('Últimos partidos para evaluar', 10, 100, 30, step=10,
                                 key=f'nba_lab_pace_limite_{partido["id"]}')
        if st.button('Ejecutar prueba cronológica pareada', key=f'nba_lab_pareado_{partido["id"]}'):
            with st.spinner('Validando sin información futura; Pace puede requerir consultas ESPN...'):
                comparacion = _nba_lab_validacion_pareada(
                    partidos, ajustes, limite=limite_prueba,
                    incluir_pace=activar_pace_prueba, cache_detalles=cache_detalles,
                    max_consultas=120)
            if len(comparacion) < 20:
                st.warning(f'Solo {len(comparacion)} predicciones comparables; muestra pequeña.')
            if not comparacion.empty:
                st.dataframe(_nba_lab_resumen_errores(comparacion),
                             hide_index=True, use_container_width=True)
                if activar_pace_prueba:
                    pareados_pace = comparacion.dropna(subset=['modelo_c_pace']).copy()
                    st.caption(f'Cobertura Pace: {len(pareados_pace)} de {len(comparacion)} '
                               'predicciones comparables con Pace realmente aplicado.')
                    if not pareados_pace.empty:
                        import math
                        filas_pace = []
                        for nombre, etiqueta in (('base','Base'),('modelo_c','Modelo C · 0%'),
                                                ('modelo_c_pace_25','Modelo C · 25%'),
                                                ('modelo_c_pace','Modelo C · 50%')):
                            error = pareados_pace[nombre] - pareados_pace['real']
                            filas_pace.append({'Modelo':etiqueta,'Predicciones':len(error),
                                               'MAE':round(float(error.abs().mean()),2),
                                               'RMSE':round(math.sqrt(float((error*error).mean())),2),
                                               'Sesgo':round(float(error.mean()),2)})
                        st.markdown('**Comparación estrictamente pareada: solo juegos con Pace**')
                        st.dataframe(pd.DataFrame(filas_pace), hide_index=True,
                                     use_container_width=True)
                        st.caption('Pesos 0%, 25% y 50% recalculados por separado con '
                                   'los mismos boxscores anteriores a cada partido. '
                                   'La muestra es exploratoria, no una validación independiente.')
                    else:
                        st.warning('No hay suficientes boxscores anteriores para validar Pace. '
                                   'Consulta la auditoría y evita interpretar Pace como evaluado.')
                st.download_button('Descargar evaluación pareada CSV',
                                   comparacion.to_csv(index=False).encode('utf-8-sig'),
                                   file_name='nba_modelo_c_validacion_pace.csv', mime='text/csv',
                                   key=f'nba_lab_pareado_csv_{partido["id"]}')
                st.caption('Evaluación exploratoria; no es prueba fuera de muestra independiente '
                           'si se ajustan parámetros tras revisar resultados.')
        st.markdown('**🧪 Validación histórica cronológica del modelo base**')
        if st.button('Evaluar modelo base con partidos anteriores', key=f'nba_lab_backtest_{partido["id"]}'):
            if pd.isna(fechas):
                st.warning('Fecha no válida.')
            else:
                evaluacion = _validacion_historica_equipos(partidos, fechas)
                validos = evaluacion.dropna(subset=['ataque','real_completo'])
                if validos.empty:
                    st.info('Muestra histórica insuficiente.')
                else:
                    err = validos['ataque'] - validos['real_completo']
                    st.write({'Partidos':len(err), 'MAE':round(float(err.abs().mean()),2),
                              'RMSE':round(float((err.pow(2).mean())**.5),2),
                              'Sesgo estimado menos real':round(float(err.mean()),2)})
                    st.caption('El resultado corresponde al modelo base, no demuestra precisión '
                               'del experimental. El experimento necesita una validación pareada '
                               'con estadísticas disponibles antes de cada partido.')


def _nba_consultar_disponibilidad_espn():
    """Datos informativos de lesiones ESPN; no modifican proyecciones."""
    import requests
    from datetime import datetime, timezone
    url = 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries'
    respuesta = requests.get(url, timeout=12, headers={'User-Agent': 'NBA-Stats-Viewer/1.0'})
    respuesta.raise_for_status()
    datos = respuesta.json()
    if not isinstance(datos, dict):
        raise ValueError('Respuesta de disponibilidad inesperada')
    return datos, datetime.now(timezone.utc).isoformat(timespec='minutes')


def _nba_extraer_disponibilidad(datos):
    """Lectura defensiva de formatos ESPN; conserva estados sin inferir aptitud."""
    filas = []
    grupos = datos.get('injuries') or datos.get('items') or []
    if not isinstance(grupos, list):
        return pd.DataFrame(columns=['Equipo', 'Jugador', 'Estado', 'Detalle'])
    for grupo in grupos:
        if not isinstance(grupo, dict):
            continue
        team = grupo.get('team') or {}
        if not isinstance(team, dict):
            team = {}
        equipo = team.get('displayName') or team.get('name') or grupo.get('displayName') or ''
        elementos = grupo.get('injuries') or grupo.get('items') or []
        if not elementos and (grupo.get('athlete') or grupo.get('player')):
            elementos = [grupo]
        for item in elementos if isinstance(elementos, list) else []:
            if not isinstance(item, dict):
                continue
            atleta = item.get('athlete') or item.get('player') or {}
            if not isinstance(atleta, dict):
                atleta = {}
            nombre = atleta.get('displayName') or atleta.get('fullName') or item.get('displayName')
            estado = item.get('status') or item.get('type') or 'Sin clasificación'
            if isinstance(estado, dict):
                estado = estado.get('displayName') or estado.get('name') or 'Sin clasificación'
            detalle = item.get('details') or item.get('description') or ''
            if isinstance(detalle, dict):
                detalle = detalle.get('detail') or detalle.get('description') or ''
            if nombre:
                filas.append({'Equipo':str(equipo), 'Jugador':str(nombre),
                              'Estado':str(estado), 'Detalle':str(detalle)[:180]})
    return pd.DataFrame(filas, columns=['Equipo', 'Jugador', 'Estado', 'Detalle']).drop_duplicates()


def _nba_panel_disponibilidad_jugadores(equipos=None):
    """Consulta explícita y aislada; ninguna ausencia altera los pronósticos."""
    with st.expander('🏥 Disponibilidad reportada de jugadores · ESPN', expanded=False):
        st.caption('Información orientativa. No aparecer en esta lista NO confirma que un jugador pueda participar. '
                   'Los estados pueden cambiar antes del inicio del partido.')
        st.markdown('[📋 Reporte oficial de lesiones NBA](https://official.nba.com/nba-injury-report-2026-27-season/)')
        clave = 'ri_nba_disponibilidad_consulta_v1'
        if st.button('🔄 Consultar estados de jugadores', key='ri_nba_disponibilidad_btn'):
            try:
                st.session_state[clave] = _nba_consultar_disponibilidad_espn()
            except Exception as exc:
                st.warning(f'No se pudo recuperar el reporte ESPN: {type(exc).__name__}. '
                           'Consulta el reporte oficial desde el enlace anterior.')
        guardado = st.session_state.get(clave)
        if not guardado:
            st.info('Pulsa consultar para recuperar el reporte. No se utilizan datos de lesiones guardados de otra fecha.')
            return
        datos, consultado = guardado
        st.caption(f'Consulta ESPN: {consultado} UTC. Fuente no oficial; puede estar incompleta.')
        tabla = _nba_extraer_disponibilidad(datos)
        if equipos and not tabla.empty:
            # Mostrar sólo coincidencias exactas de nombres de equipo; si no hay,
            # evitar afirmar que no existen lesiones para ese enfrentamiento.
            filtrada = tabla.loc[tabla['Equipo'].isin(equipos)]
            if filtrada.empty:
                st.info('La fuente no proporcionó coincidencias verificables para estos equipos. '
                        'Consulta el reporte oficial; esto no significa plantilla completa.')
                return
            tabla = filtrada
        if tabla.empty:
            st.info('Sin registros interpretables en la respuesta. No equivale a ausencia de lesiones.')
            return
        st.dataframe(tabla, hide_index=True, use_container_width=True)
        st.caption('Este panel es informativo: no modifica las proyecciones ni el historial guardado.')


def _tarjeta_unica_partido(partidos, partido):
    """Vista móvil: equipos, totales, comparación estadística y hasta 3 jugadores."""
    import math
    local, visita = str(partido['local']), str(partido['visitante'])
    fecha = pd.to_datetime(partido['fecha_utc'], utc=True, errors='coerce')
    st.markdown(f'### 🏀 {visita} vs. {local}')
    st.caption(f"Próximo partido · {str(partido['fecha_utc'])[:16]} UTC · estimaciones exploratorias")
    _nba_panel_disponibilidad_jugadores([local, visita])
    historiales = {e: _historial_equipo(partidos, e, fecha) for e in (local, visita)}
    # Los marcadores completos pueden incluir prórrogas.
    proy = {}
    for equipo, rival in ((local, visita), (visita, local)):
        a, b = historiales[equipo], historiales[rival]
        if not a.empty and not b.empty:
            pf, pc = _media_rango(a['PF']), _media_rango(b['PC'])
            if pf and pc:
                proy[equipo] = (pf['media'] + pc['media']) / 2
    st.markdown('**🏆 Partido completo · puntos esperados**')
    if len(proy) == 2:
        st.metric('Media ataque/defensa (marcadores finales históricos)', f"{sum(proy.values()):.1f} pts")
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
    # Modelo de períodos: ataque reciente del equipo y defensa reciente del rival.
    # Referencia independiente: media de puntos anotados en los últimos 5 juegos.
    # Se usan exclusivamente partidos anteriores al encuentro, sin prórrogas.
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
        st.caption('Registro manual antes del inicio: conserva la primera proyección y no altera los cálculos.')
        if st.button('Guardar proyección original', key=f"ri_nba_guardar_{partido['id']}"):
            correcto, mensaje = _nba_registrar_proyeccion(partido, tabla_periodos)
            (st.success if correcto else st.info)(mensaje)
    _interpretacion_inteligente_nba(local, visita, historiales, proy, tabla_periodos, muestras, partidos, fecha)
    _nba_lab_panel(partidos, partido, historiales, cache_detalles)
    st.dataframe(tabla_periodos[['Período', 'Visitante', 'Local', 'Total']],
                 hide_index=True, use_container_width=True)
    st.markdown('**📐 Proyección, referencia y Edge · cada período**')
    tabla_edge_periodos = tabla_periodos[['Período', 'Total', 'Referencia total', 'Edge descriptivo']].copy()
    tabla_edge_periodos.columns = ['Período', 'Proy.', 'Ref.', 'Edge']
    st.dataframe(tabla_edge_periodos, hide_index=True, use_container_width=True)
    with st.expander('🔎 Muestra histórica por período'):
        st.dataframe(tabla_periodos[['Período', 'Muestra mínima']],
                     hide_index=True, use_container_width=True)
    with st.expander('ℹ️ Cómo interpretar las proyecciones'):
        st.caption('Proyección por período = media de puntos anotados por el equipo y '
               'puntos permitidos por el rival (hasta 10 partidos previos). '
               'Referencia = promedio anotado en los últimos 5 partidos disponibles. '
               'Edge descriptivo = proyección − referencia; no mide probabilidades. '
               'Mínimo 3 partidos por cada componente; N/D si faltan datos. '
               'Cuartos 1–4 excluyen prórrogas.')
    if len(proy) == 2:
        resumen_equipos = []
        for e in (visita, local):
            pf = pd.to_numeric(historiales[e]['PF'], errors='coerce').dropna().tail(5)
            if len(pf) >= 5:
                ref = float(pf.mean())
                resumen_equipos.append({'Equipo': e, 'Proyección': round(proy[e],1),
                                       'Referencia': round(ref,1),
                                       'Edge descriptivo': round(proy[e]-ref,1), 'Muestra': len(pf)})
        if len(resumen_equipos) == 2:
            resumen_equipos.append({'Equipo': 'TOTAL PARTIDO',
                                    'Proyección': round(sum(proy.values()),1),
                                    'Referencia': round(sum(x['Referencia'] for x in resumen_equipos),1),
                                    'Edge descriptivo': round(sum(x['Edge descriptivo'] for x in resumen_equipos),1),
                                    'Muestra': min(x['Muestra'] for x in resumen_equipos)})
            st.markdown('**📐 Edge descriptivo · puntos por equipo y partido completo**')
            tabla_equipos_movil = pd.DataFrame(resumen_equipos)[
                ['Equipo', 'Proyección', 'Referencia', 'Edge descriptivo']
            ].rename(columns={'Proyección': 'Proy.', 'Referencia': 'Ref.',
                              'Edge descriptivo': 'Edge'})
            tabla_equipos_movil['Equipo'] = tabla_equipos_movil['Equipo'].map(
                lambda nombre: 'TOTAL' if nombre == 'TOTAL PARTIDO'
                else _abreviatura_equipo(nombre))
            st.dataframe(tabla_equipos_movil, hide_index=True, use_container_width=True)
            st.caption(f"Equipos: {_abreviatura_equipo(visita)} = {visita} · "
                       f"{_abreviatura_equipo(local)} = {local}.")
            with st.expander('📋 Nombres completos y tamaño de muestra'):
                st.dataframe(pd.DataFrame(resumen_equipos), hide_index=True,
                             use_container_width=True)
            st.caption('Referencia: promedio de puntos a favor de los últimos 5 partidos de cada equipo. '
                       'Proyección: ataque propio y defensa rival. Los marcadores históricos pueden incluir prórrogas.')
        else:
            st.info('Edge por equipos no disponible: faltan cinco marcadores históricos por equipo.')
    st.caption(f'Cobertura por períodos: {visita} {len(muestras[visita])} · '
               f'{local} {len(muestras[local])} partidos con cuatro cuartos.')
    st.markdown('**👤 Jugadores · puntos, rebotes, asistencias y triples**')
    # Primero reutilizar historial compartido. Si no existe, consultar automáticamente
    # boxscores de partidos previos de AMBOS equipos sin exigir abrir otra vista.
    try:
        historial, cobertura = obtener_historial_compartido(equipo='Todos')
    except Exception as exc:
        historial = pd.DataFrame()
        st.caption(f'Historial compartido no disponible: {type(exc).__name__}')
    if not {'equipo', 'jugador'}.issubset(historial.columns):
        historial = pd.DataFrame()
    disponibles = (historial.loc[historial['equipo'].isin([local, visita])].copy()
                   if not historial.empty else pd.DataFrame())
    if disponibles.empty:
        ids = {}
        for equipo in (local, visita):
            for fila in historiales[equipo].tail(12).itertuples(index=False):
                ids[str(fila.id)] = str(fila.fecha_utc)[:10]
        if ids:
            with st.spinner(f'Cargando jugadores de {len(ids)} partidos anteriores...'):
                try:
                    historial_auto, errores_jugadores = _historial(tuple(sorted(ids.items(), key=lambda x: x[1])))
                except Exception as exc:
                    historial_auto, errores_jugadores = pd.DataFrame(), [f'{type(exc).__name__}: {exc}']
            if not historial_auto.empty and {'equipo','jugador'}.issubset(historial_auto.columns):
                disponibles = historial_auto.loc[historial_auto['equipo'].isin([local, visita])].copy()
            st.caption(f'Boxscores solicitados: {len(ids)} · incidencias: {len(errores_jugadores)}. '
                       'Cobertura limitada al calendario histórico seleccionado.')
        else:
            st.info('No hay partidos anteriores disponibles para cargar jugadores.')
    if disponibles.empty:
        st.warning('ESPN no devolvió registros individuales de estos equipos. '
                   'Amplía el rango histórico de fechas y vuelve a consultar.')
    else:
        if 'fecha' in disponibles.columns and pd.notna(fecha):
            disponibles = disponibles.loc[pd.to_datetime(disponibles['fecha'], utc=True, errors='coerce').lt(fecha)].copy()
        if 'partido_id' in disponibles.columns:
            disponibles = disponibles.drop_duplicates(subset=['partido_id','equipo','jugador'])
        if 'Minutos' in disponibles.columns:
            minutos_validos = pd.to_numeric(disponibles['Minutos'], errors='coerce').gt(0)
            excluidos = int((~minutos_validos).sum())
            disponibles = disponibles.loc[minutos_validos].copy()
            if excluidos:
                st.caption(f'{excluidos} registros sin participación confirmada excluidos de la tarjeta.')
        else:
            disponibles = disponibles.iloc[0:0].copy()
            st.warning('No hay minutos verificables para calcular promedios de jugadores.')
        opciones = sorted(disponibles['jugador'].dropna().astype(str).unique())
        elegidos = st.multiselect('Selecciona hasta tres jugadores', opciones, max_selections=3,
                                 key='ri_nba_tarjeta_jugadores')
        triples = pd.DataFrame()
        if elegidos:
            ids_fechas = list(juegos.items())
            triples = _historial_triples({(e, n) for e in (local, visita) for n in elegidos},
                                        ids_fechas, cache_detalles)
        for nombre in elegidos:
            d = disponibles.loc[disponibles['jugador'].eq(nombre)].copy()
            if 'fecha' in d.columns:
                d = d.sort_values('fecha')
            st.markdown(f'### 👤 {nombre}')
            tabla_jugador = []
            calidad_jugador = []
            for metrica in ('Puntos', 'Rebotes', 'Asistencias', 'Triples'):
                fuente = (triples.loc[triples['jugador'].eq(nombre)].sort_values('fecha')['Triples']
                          if metrica == 'Triples' and not triples.empty else
                          d[metrica] if metrica in d else pd.Series(dtype=float))
                pred = _pronostico_estadistico(fuente) if not fuente.empty else None
                edge = _edge_descriptivo(fuente) if not fuente.empty else None
                tabla_jugador.append({
                    'Estadística': metrica,
                    'Proyección': pred['media'] if pred else None,
                    'Referencia': round(edge['referencia'],1) if edge else None,
                    'Edge descriptivo': round(edge['diferencia'],1) if edge else None,
                    'Rango': f"{pred['bajo']:.1f}–{pred['alto']:.1f}" if pred else 'N/D'})
                calidad_jugador.append({
                    'Estadística': metrica, 'Partidos': pred['n'] if pred else 0,
                    'MAE histórico': pred['mae'] if pred else None,
                    'Pruebas': pred['pruebas'] if pred else 0})
            tabla_jugador_df = pd.DataFrame(tabla_jugador)
            tabla_visible = tabla_jugador_df[['Estadística', 'Proyección', 'Referencia', 'Edge descriptivo']].copy()
            tabla_visible.columns = ['Estadística', 'Proy.', 'Ref.', 'Edge']
            st.dataframe(tabla_visible, hide_index=True, use_container_width=True)
            with st.expander(f'📊 Rangos orientativos · {nombre}'):
                st.dataframe(tabla_jugador_df[['Estadística', 'Rango']],
                             hide_index=True, use_container_width=True)
            with st.expander(f'📐 Validación histórica del Edge · {nombre}'):
                # Se evalúan exclusivamente encuentros previos al partido seleccionado.
                # El historial compartido ya fue filtrado por fecha y participación.
                datos_validacion = d.copy()
                if {'fecha', 'partido_id', 'Minutos'}.issubset(datos_validacion.columns):
                    if not triples.empty and {'partido_id', 'Triples'}.issubset(triples.columns):
                        triples_j = triples.loc[triples['jugador'].eq(nombre), ['partido_id', 'Triples']].copy()
                        triples_j['partido_id'] = triples_j['partido_id'].astype(str)
                        triples_j = triples_j.drop_duplicates('partido_id', keep='last')
                        datos_validacion['partido_id'] = datos_validacion['partido_id'].astype(str)
                        datos_validacion = datos_validacion.drop(columns=['Triples'], errors='ignore').merge(
                            triples_j, on='partido_id', how='left')
                    resumen_val, detalle_val = _validar_edge_jugador_v312(datos_validacion)
                    if resumen_val.empty:
                        st.info('Aún no hay al menos cinco partidos anteriores válidos por estadística para evaluar el Edge.')
                    else:
                        st.dataframe(resumen_val, hide_index=True, use_container_width=True)
                        st.caption('Mejora positiva: menor MAE que la referencia de 5 partidos. '
                                   'Negativa: la referencia tuvo menor error. '
                                   'Proyección = promedio de hasta 10 partidos anteriores. '
                                   'No equivale a una probabilidad.')
                        st.download_button('📥 Descargar validación de jugador CSV',
                            detalle_val.round(3).to_csv(index=False).encode('utf-8-sig'),
                            file_name=f'nba_validacion_jugador_{str(nombre).replace(" ", "_")}.csv',
                            mime='text/csv', key=f'ri_nba_val312_{nombre}_{partido["id"]}')
                    if 'Triples' not in datos_validacion or datos_validacion['Triples'].notna().sum() < 6:
                        st.caption('Triples: cobertura insuficiente para validación cronológica; '
                                   'solo se utilizan boxscores con triples observados, sin completar ausencias con cero.')
                else:
                    st.info('Faltan fechas, identificadores o minutos confirmados para validar jugadores.')

            with st.expander(f'ℹ️ Interpretación de estadísticas · {nombre}'):
                st.caption('Edge descriptivo = proyección − promedio de los últimos 5 registros válidos. '
                           'Positivo: proyección mayor; negativo: menor. No mide probabilidad de acierto.')
            with st.expander(f'🔎 Precisión y calidad de datos · {nombre}'):
                st.dataframe(pd.DataFrame(calidad_jugador), hide_index=True, use_container_width=True)
                st.caption('MAE: error absoluto medio en pruebas cronológicas. '
                           'N/D: información insuficiente. El rango es orientativo, no una garantía.')
        if not elegidos:
            st.caption('Elige hasta tres jugadores para ver sus promedios y rangos orientativos.')
    st.download_button('📥 Exportar tarjeta de equipos CSV',
                       pd.DataFrame(filas).to_csv(index=False).encode('utf-8-sig'),
                       'nba_v3_9_tarjeta_equipos.csv', 'text/csv',
                       key=f"ri_nba_v34_export_{partido['id']}", use_container_width=True)
    st.caption('Estimaciones estadísticas sujetas a cobertura de ESPN. No son resultados garantizados.')

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




def _auditar_participacion(datos):
    """Audita sin inventar ceros; solo minutos positivos acreditan participación."""
    d = datos.copy()
    d['partido_id'] = d['partido_id'].astype(str)
    d = d.drop_duplicates(['jugador', 'equipo', 'partido_id'], keep='last')
    metricas = [m for m in ('Puntos', 'Rebotes', 'Asistencias', 'Minutos', 'Robos', 'Tapones', 'Pérdidas') if m in d]
    for m in metricas:
        d[m] = pd.to_numeric(d[m], errors='coerce')
    mins = d['Minutos'] if 'Minutos' in d else pd.Series(float('nan'), index=d.index)
    otras = [m for m in metricas if m != 'Minutos']
    con_estadisticas = d[otras].notna().any(axis=1) if otras else pd.Series(False, index=d.index)
    d['Motivo'] = 'Participación confirmada'
    d.loc[mins.eq(0), 'Motivo'] = '0 minutos registrados'
    d.loc[mins.isna() & ~con_estadisticas, 'Motivo'] = 'Minutos y estadísticas ausentes'
    d.loc[mins.isna() & con_estadisticas, 'Motivo'] = 'Minutos ausentes; estadísticas observadas'
    d['Incluido'] = mins.gt(0).fillna(False)
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


def _validacion_cronologica_v37(datos, metricas=('Puntos', 'Rebotes', 'Asistencias', 'Minutos'), minimo=5, ventana=10):
    """Backtest sin fuga temporal: predicción del juego i con juegos anteriores.

    No incluye DNP, minutos no confirmados, valores ausentes ni partidos futuros.
    Los resultados describen errores históricos, no probabilidades futuras.
    """
    if datos is None or datos.empty or not {'fecha', 'partido_id'}.issubset(datos.columns):
        return pd.DataFrame(), pd.DataFrame()
    d = datos.copy()
    d['_fecha_orden'] = pd.to_datetime(d['fecha'], utc=True, errors='coerce')
    d = d.dropna(subset=['_fecha_orden']).sort_values(['_fecha_orden', 'partido_id'])
    d = d.drop_duplicates('partido_id', keep='last')
    resultados = []
    for metrica in metricas:
        if metrica not in d.columns:
            continue
        serie = pd.to_numeric(d[metrica], errors='coerce')
        # Cada evaluación usa SOLO juegos anteriores, incluso si el juego actual no tiene dato.
        for i in range(minimo, len(d)):
            actual = serie.iloc[i]
            if pd.isna(actual):
                continue
            anteriores = serie.iloc[max(0, i-ventana):i].dropna()
            if len(anteriores) < minimo:
                continue
            estimado = float(anteriores.mean())
            real = float(actual)
            resultados.append({'Métrica': metrica,
                               'Fecha': str(d.iloc[i]['fecha'])[:10],
                               'Partido ID': str(d.iloc[i]['partido_id']),
                               'N previo': int(len(anteriores)),
                               'Estimación': round(estimado, 3),
                               'Real': real,
                               'Error': round(estimado-real, 3),
                               'Error absoluto': round(abs(estimado-real), 3)})
    detalle = pd.DataFrame(resultados)
    if detalle.empty:
        return pd.DataFrame(), detalle
    resumen = []
    for metrica, g in detalle.groupby('Métrica', sort=False):
        e = g['Error'].astype(float)
        resumen.append({'Métrica': metrica, 'Evaluaciones': len(g),
                        'MAE': round(float(e.abs().mean()), 2),
                        'RMSE': round(float((e.pow(2).mean()) ** 0.5), 2),
                        'Sesgo estimado-real': round(float(e.mean()), 2),
                        'Estado': 'Muestra inicial' if len(g) < 10 else 'Histórico evaluable'})
    return pd.DataFrame(resumen), detalle


def _comparacion_cronologica_v38(datos, minimo=5, ventana=10):
    """Compara dos medias móviles en los MISMOS partidos, sin información futura.

    Referencia: últimos 5 registros válidos anteriores. Modelo histórico:
    últimos 10 registros válidos anteriores (o los disponibles, mínimo 5).
    Ambos son promedios descriptivos, no modelos predictivos calibrados.
    """
    if datos is None or datos.empty or not {'fecha', 'partido_id'}.issubset(datos.columns):
        return pd.DataFrame(), pd.DataFrame()
    d = datos.copy()
    d['_fecha_orden'] = pd.to_datetime(d['fecha'], utc=True, errors='coerce')
    d = (d.dropna(subset=['_fecha_orden'])
           .sort_values(['_fecha_orden', 'partido_id'])
           .drop_duplicates('partido_id', keep='last'))
    filas = []
    for metrica in ('Puntos', 'Rebotes', 'Asistencias', 'Minutos'):
        if metrica not in d:
            continue
        serie = pd.to_numeric(d[metrica], errors='coerce')
        minutos = pd.to_numeric(d['Minutos'], errors='coerce') if 'Minutos' in d else None
        for i in range(minimo, len(d)):
            real = serie.iloc[i]
            if pd.isna(real):
                continue
            previos = serie.iloc[max(0, i-ventana):i].dropna()
            if len(previos) < minimo:
                continue
            base = float(previos.tail(5).mean())
            historico = float(previos.mean())
            min_previos = (minutos.iloc[max(0, i-5):i].dropna()
                           if minutos is not None else pd.Series(dtype=float))
            min_actual = minutos.iloc[i] if minutos is not None else float('nan')
            cambio_min = (float(min_actual - min_previos.mean())
                          if pd.notna(min_actual) and len(min_previos) >= 3 else float('nan'))
            filas.append({'Métrica': metrica, 'Fecha': str(d.iloc[i]['fecha'])[:10],
                          'Partido ID': str(d.iloc[i]['partido_id']), 'N previo': len(previos),
                          'Real': float(real), 'Referencia 5': round(base, 3),
                          'Histórico hasta 10': round(historico, 3),
                          'Error absoluto referencia': round(abs(base-real), 3),
                          'Error absoluto histórico': round(abs(historico-real), 3),
                          'Cambio minutos vs 5 previos': round(cambio_min, 3)
                          if pd.notna(cambio_min) else float('nan')})
    detalle = pd.DataFrame(filas)
    if detalle.empty:
        return pd.DataFrame(), detalle
    resumen = []
    for metrica, g in detalle.groupby('Métrica', sort=False):
        mae_base = float(g['Error absoluto referencia'].mean())
        mae_hist = float(g['Error absoluto histórico'].mean())
        delta = mae_hist - mae_base
        resumen.append({'Métrica': metrica, 'Evaluaciones pareadas': len(g),
                        'MAE referencia 5': round(mae_base, 2),
                        'MAE histórico 10': round(mae_hist, 2),
                        'Diferencia MAE': round(delta, 2),
                        'Lectura': ('Muestra pequeña' if len(g) < 20 else
                                    'Histórico menor error' if delta < -0.01 else
                                    'Referencia menor error' if delta > 0.01 else 'Error similar'),
                        'Cambio minutos abs. medio': round(float(g['Cambio minutos vs 5 previos'].abs().mean()), 2)
                        if g['Cambio minutos vs 5 previos'].notna().any() else float('nan')})
    return pd.DataFrame(resumen), detalle


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
        with st.expander('🧪 NBA 3.7 · Validación histórica sin datos futuros'):
            resumen_v37, detalle_v37 = _validacion_cronologica_v37(d)
            if resumen_v37.empty:
                st.info('Aún no hay suficientes partidos anteriores con datos válidos para evaluar errores históricos.')
            else:
                st.dataframe(resumen_v37, hide_index=True, use_container_width=True)
                st.caption('Cada estimación se calcula con hasta 10 partidos anteriores y mínimo 5 datos válidos. '
                           'MAE = error absoluto medio; RMSE penaliza errores grandes; '
                           'sesgo positivo = estimación por encima del resultado. '
                           'Son pruebas retrospectivas, no predicciones certificadas.')
                st.download_button('⬇️ Exportar validación histórica CSV',
                                   detalle_v37.to_csv(index=False).encode('utf-8-sig'),
                                   f"validacion_nba_v37_{str(nombre).replace(' ', '_')}.csv",
                                   'text/csv', key=f'ri_nba_v37_{str(nombre)}')

        with st.expander('📊 NBA 3.8 · Comparación histórica y cambios de minutos'):
            resumen_v38, detalle_v38 = _comparacion_cronologica_v38(d)
            if resumen_v38.empty:
                st.info('No hay suficientes partidos previos para comparar ambos métodos.')
            else:
                st.dataframe(resumen_v38, hide_index=True, use_container_width=True)
                st.caption('Diferencia MAE = error histórico de hasta 10 partidos menos error '
                           'de la referencia de 5 partidos. Negativo favorece al histórico; '
                           'positivo favorece a la referencia. Ambos usan los mismos partidos '
                           'evaluados y solo datos anteriores. Con menos de 20 evaluaciones, '
                           'la comparación es exploratoria.')
                st.caption('Cambio de minutos = minutos reales menos promedio de los 5 partidos '
                           'previos; es descriptivo y no demuestra causalidad. '
                           'No se convierten ausencias en ceros.')
                st.download_button('⬇️ Exportar comparación NBA 3.8 CSV',
                                   detalle_v38.to_csv(index=False).encode('utf-8-sig'),
                                   f"comparacion_nba_v38_{str(nombre).replace(' ', '_')}.csv",
                                   'text/csv', key=f'ri_nba_v38_{str(nombre)}')

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
    puntos_explicitos = {q: 0 for q in range(1, 5)}
    puntos_provisionales = {q: 0 for q in range(1, 5)}
    prorroga_explicita = prorroga_provisional = 0
    ids_vistos, autores = set(), set()
    diag = {'Jugadas recibidas': len(jugadas), 'Jugadas únicas': 0,
            'Anotaciones': 0, 'Sin participantes': 0, 'Sin rol anotador': 0,
            'Sin ID anotador': 0, 'Anotaciones verificadas': 0,
            'Anotaciones del jugador': 0, 'Anotaciones del jugador con rol explícito': 0, 'Anotaciones del jugador inferidas': 0, 'Fuera de Q1–Q4': 0,
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
        origen_autor = None
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
                    origen_autor = 'rol explícito'
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
                origen_autor = 'participante único'
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
                    origen_autor = 'orden ESPN'
        if len(set(candidatos)) != 1:
            diag['Sin rol anotador'] += 1
            continue
        diag['Anotaciones verificadas'] += 1
        if candidatos[0] == str(jugador_id):
            diag['Anotaciones del jugador'] += 1
            if origen_autor == 'rol explícito':
                diag['Anotaciones del jugador con rol explícito'] += 1
            else:
                diag['Anotaciones del jugador inferidas'] += 1
            if periodo in puntos and valor in (1, 2, 3):
                puntos[periodo] += valor
                if origen_autor == 'rol explícito':
                    puntos_explicitos[periodo] += valor
                else:
                    puntos_provisionales[periodo] += valor
            elif periodo > 4 and valor in (1, 2, 3):
                diag['Puntos de prórroga'] += valor
                if origen_autor == 'rol explícito':
                    prorroga_explicita += valor
                else:
                    prorroga_provisional += valor
            else:
                diag['Fuera de Q1–Q4'] += 1
    diag['IDs observados'] = ', '.join(sorted(diag['IDs observados'])[:8]) or 'N/D'
    diag['Roles observados'] = ', '.join(sorted(diag['Roles observados'])[:8]) or 'N/D'
    diag['Esquemas participantes'] = ', '.join(sorted(diag['Esquemas participantes'])[:12]) or 'N/D'
    return {'puntos': puntos, 'puntos_explicitos': puntos_explicitos,
            'puntos_provisionales': puntos_provisionales,
            'prorroga_explicita': prorroga_explicita,
            'prorroga_provisional': prorroga_provisional,
            'anotaciones': diag['Anotaciones'],
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
                   'La coincidencia de puntos no prueba la autoría. Se distingue entre roles explícitos y atribuciones inferidas; las cifras provisionales se identifican como tales.')
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
                # El boxscore suma reglamentario y posibles prórrogas.
                # Conservar Q1–Q4 separados: la igualdad de totales valida
                # consistencia numérica, NO la identidad de cada anotador.
                puntos_prorroga = evento['diagnostico']['Puntos de prórroga']
                total_pbp = total + puntos_prorroga
                conciliado = (evento['sin_autor_verificado'] == 0 and
                              pd.notna(puntos_oficiales) and
                              total_pbp == puntos_oficiales)
                if conciliado:
                    # La igualdad de totales no valida por sí sola al autor.
                    # Solo marcar como verificado cuando cada punto atribuido
                    # al jugador tiene un rol de anotador explícito en ESPN.
                    autor_verificado = (
                        evento['diagnostico']['Anotaciones del jugador inferidas'] == 0
                        and (puntos_oficiales == 0 or
                             evento['diagnostico']['Anotaciones del jugador con rol explícito'] > 0)
                    )
                    if autor_verificado:
                        estado = ('Verificado con prórroga (rol explícito)' if puntos_prorroga
                                  else 'Verificado (rol explícito)')
                    else:
                        estado = ('Conciliado con prórroga (atribución provisional)'
                                  if puntos_prorroga else
                                  'Conciliado (atribución provisional)')
                else:
                    estado = 'Sin conciliar'
                resultado = {'Fecha': fila.get('fecha'), 'Partido': pid,
                             'Estado': estado,
                             'Nivel de atribución': ('Rol explícito' if conciliado and evento['diagnostico']['Anotaciones del jugador inferidas'] == 0 else
                                                     'Inferida; requiere verificación' if conciliado else 'No conciliado'),
                             'Jugadas sin autor': evento['sin_autor_verificado'],
                             'Puntos boxscore': puntos_oficiales,
                             'Puntos PBP Q1–Q4': total,
                             'Puntos PBP prórroga': puntos_prorroga,
                             'Puntos PBP total': total_pbp,
                             'Puntos con rol explícito': sum(evento['puntos_explicitos'].values()) + evento['prorroga_explicita'],
                             'Puntos atribuidos provisionalmente': sum(evento['puntos_provisionales'].values()) + evento['prorroga_provisional'],
                             'Prórroga con rol explícito': evento['prorroga_explicita'],
                             'Prórroga provisional': evento['prorroga_provisional'],
                             'Diferencia PBP - boxscore':
                                 total_pbp - puntos_oficiales if pd.notna(puntos_oficiales) else None,
                              **evento['diagnostico']}
                for q in range(1, 5):
                    resultado[f'Q{q}'] = evento['puntos'][q] if conciliado else None
                    resultado[f'Q{q} rol explícito'] = evento['puntos_explicitos'][q]
                    resultado[f'Q{q} provisional'] = evento['puntos_provisionales'][q]
                resultados.append(resultado)
            except Exception as exc:
                resultados.append({'Fecha': fila.get('fecha'), 'Partido': pid,
                                   'Estado': f'Consulta fallida ({type(exc).__name__})'})
        tabla = pd.DataFrame(resultados)
        st.dataframe(tabla.fillna('N/D'), hide_index=True, use_container_width=True)
        st.download_button('📥 Exportar diagnóstico detallado CSV',
                           tabla.to_csv(index=False).encode('utf-8-sig'),
                           'nba_v3_6_auditoria_eventos.csv', 'text/csv',
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
        st.subheader('🔎 Diagnóstico de rebotes del cuarto período · v3.4.0')
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
        estados = tabla['Estado'].astype(str) if 'Estado' in tabla else pd.Series(dtype=str)
        mascara_conciliados = estados.str.startswith(('Conciliado', 'Verificado'))
        n = int(mascara_conciliados.sum())
        verificados = int(estados.str.startswith('Verificado').sum())
        st.caption(f'Partidos con totales conciliados: {n}/{len(tabla)}; con rol explícito: {verificados}. '
                   'La coincidencia del total no garantiza la atribución de cada anotación.')
        if n:
            aceptados = tabla.loc[mascara_conciliados]
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
    # El archivo puede contener otros períodos. Limitar estrictamente a los
    # partidos finalizados solicitados; completar los IDs faltantes con ESPN.
    ids_solicitados = {ident for ident, _ in ids}
    try:
        datos_compartidos, cobertura = obtener_historial_compartido(equipo=equipo)
    except Exception as exc:
        datos_compartidos, cobertura = pd.DataFrame(), {'disponible': False}
        st.warning(f'No se pudo consultar el archivo compartido: {type(exc).__name__}. Se intentará ESPN.')
    if not datos_compartidos.empty and 'partido_id' in datos_compartidos:
        datos_compartidos = datos_compartidos.loc[
            datos_compartidos['partido_id'].astype(str).isin(ids_solicitados)].copy()
    else:
        datos_compartidos = pd.DataFrame()
    cubiertos = set(datos_compartidos['partido_id'].astype(str)) if not datos_compartidos.empty else set()
    pendientes = tuple((ident, fecha) for ident, fecha in ids if ident not in cubiertos)
    errores = []
    datos = datos_compartidos.copy()
    if pendientes:
        with st.spinner(f'Recuperando {len(pendientes)} partidos no archivados...'):
            try:
                adicionales, errores = _historial(pendientes)
            except Exception as exc:
                adicionales, errores = pd.DataFrame(), [f'{type(exc).__name__}: {exc}']
        if not adicionales.empty:
            datos = pd.concat([datos, adicionales], ignore_index=True) if not datos.empty else adicionales
    if not datos.empty and {'partido_id', 'equipo', 'jugador'}.issubset(datos.columns):
        datos = datos.drop_duplicates(['partido_id', 'equipo', 'jugador'], keep='last')
    st.caption(f'Cobertura de partidos solicitados: {len(cubiertos)}/{len(ids)} en Supabase; '
               f'{len(pendientes)} consultados a ESPN. Los datos pueden ser parciales.')
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


def _cargar_historial_temporada_nba(desde, hasta):
    """Carga todo el intervalo en bloques compatibles con modulo_nba (máx. 32 días).

    Conserva las incidencias por bloque y deduplica por ID; nunca convierte
    errores de descarga en partidos inventados.
    """
    if hasta < desde:
        raise ValueError('La fecha final debe ser posterior o igual a la inicial.')
    fragmentos, incidencias = [], []
    inicio = desde
    while inicio <= hasta:
        fin = min(inicio + timedelta(days=31), hasta)
        try:
            bloque, errores = cargar_partidos(inicio.isoformat(), fin.isoformat())
            if bloque is not None and not bloque.empty:
                fragmentos.append(bloque)
            incidencias.extend(f'{inicio} a {fin}: {e}' for e in (errores or []))
        except Exception as exc:
            incidencias.append(f'{inicio} a {fin}: {type(exc).__name__}: {exc}')
        inicio = fin + timedelta(days=1)
    if not fragmentos:
        return pd.DataFrame(), incidencias
    resultado = pd.concat(fragmentos, ignore_index=True)
    if 'id' in resultado.columns:
        resultado['id'] = resultado['id'].astype(str)
        resultado = resultado.drop_duplicates(subset=['id'], keep='last')
    if 'fecha_utc' in resultado.columns:
        resultado = resultado.sort_values('fecha_utc').reset_index(drop=True)
    return resultado, incidencias


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




def _aplicar_diseno_mixto_nba():
    """Estilos visuales aislados: no modifican datos, cálculos ni consultas."""
    st.markdown("""
    <style>
    /* NBA: estilo mixto responsivo; respetar tema claro u oscuro de Streamlit. */
    .block-container {max-width: 1100px; padding-top: 1.1rem; padding-bottom: 2.2rem;}
    [data-testid="stAppViewContainer"] h1 {font-size: clamp(1.55rem, 5vw, 2.1rem); letter-spacing: -.035em; font-weight: 780;}
    [data-testid="stAppViewContainer"] h2 {font-size: clamp(1.3rem, 4.2vw, 1.7rem); font-weight: 750; margin-top: .8rem;}
    [data-testid="stAppViewContainer"] h3 {font-size: clamp(1.05rem, 3.8vw, 1.3rem); font-weight: 720; margin-top: .65rem;}
    [data-testid="stMetric"] {
        border: 1px solid rgba(110, 143, 190, .25);
        background: rgba(70, 120, 185, .065);
        border-radius: 13px; padding: .8rem .85rem; min-height: 94px;
        box-shadow: 0 2px 8px rgba(20, 35, 65, .035);
    }
    [data-testid="stMetricLabel"] {font-size: .83rem; line-height: 1.2;}
    [data-testid="stMetricValue"] {font-size: clamp(1.18rem, 4.4vw, 1.85rem); font-weight: 760;}
    [data-testid="stMetricDelta"] {font-size: .78rem;}
    [data-testid="stDataFrame"] {border: 1px solid rgba(110, 143, 190, .20); border-radius: 12px; overflow: hidden;}
    [data-testid="stExpander"] {border: 1px solid rgba(110, 143, 190, .23); border-radius: 12px; margin: .4rem 0;}
    [data-testid="stExpander"] summary {font-weight: 680;}
    [data-testid="stAlert"] {border-radius: 12px;}
    div.stButton > button, div.stDownloadButton > button {border-radius: 10px; font-weight: 650; min-height: 2.55rem;}
    [data-testid="stCaptionContainer"] {line-height: 1.42;}
    [data-testid="stVerticalBlock"] {gap: .58rem;}
    @media (max-width: 640px) {
        .block-container {padding-left: .7rem; padding-right: .7rem; padding-top: .6rem;}
        [data-testid="stMetric"] {padding: .55rem .65rem; min-height: 78px;}
        [data-testid="stMetricValue"] {font-size: 1.3rem;}
        [data-testid="stMetricLabel"] {font-size: .76rem;}
        [data-testid="stHorizontalBlock"] {gap: .42rem;}
        [data-testid="stDataFrame"] {font-size: .82rem;}
        [data-testid="stExpander"] summary {font-size: .91rem;}
    }
    </style>
    """, unsafe_allow_html=True)

def mostrar_resumen_inteligente_nba():
    """Punto de entrada del Resumen Inteligente NBA."""
    _aplicar_diseno_mixto_nba()
    st.title('🏠 Resumen Inteligente NBA')
    st.caption('Motor estadístico automático: elige equipos o jugadores; los detalles disponibles se consultan y reutilizan sin botones adicionales.')
    st.caption(f'v{VERSION} · Consulta automática · Fuente ESPN no oficial · Sin datos simulados')
    hoy = date.today()
    inicio_temporada = date(2026, 10, 20)
    c1, c2 = st.columns(2)
    with c1:
        desde = st.date_input('Desde', min(inicio_temporada, hoy), key='ri_nba_desde')
    with c2:
        hasta = st.date_input('Hasta', hoy, key='ri_nba_hasta')
    if hasta < desde:
        st.warning('Elige un intervalo válido: Hasta debe ser igual o posterior a Desde.')
        return
    # El historial solo consulta días hasta hoy; el calendario futuro se
    # recupera por separado, como en la versión anterior.
    fin_historial = min(hasta, hoy)
    periodo = (desde.isoformat(), fin_historial.isoformat())
    if st.button('🔄 Actualizar datos NBA', key='ri_nba_consultar', use_container_width=True):
        st.session_state['ri_nba_periodo'] = periodo
    if st.session_state.get('ri_nba_periodo') != periodo:
        st.session_state['ri_nba_periodo'] = periodo
    try:
        with st.spinner('Consultando calendario NBA...'):
            partidos, errores = _cargar_historial_temporada_nba(desde, fin_historial)
    except Exception as exc:
        st.error(f'No fue posible cargar el calendario: {type(exc).__name__}: {exc}')
        return
    if errores:
        st.warning(f'Cobertura parcial: {len(errores)} días con incidencias.')
        with st.expander('Ver incidencias'):
            st.text('\n'.join(map(str, errores)))
    if partidos.empty:
        st.info('No hay partidos históricos en las fechas seleccionadas; se buscarán próximos encuentros.')
    else:
        finalizados = partidos.loc[partidos['finalizado'].eq(True)] if 'finalizado' in partidos else pd.DataFrame()
        st.caption(f'📚 Cobertura histórica: {len(partidos)} encuentros recuperados, '
                   f'{len(finalizados)} finalizados · {desde.isoformat()} a {fin_historial.isoformat()}. '
                   'Las incidencias de ESPN pueden reducir la cobertura.')
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
    st.caption('Historial de temporada en bloques de hasta 32 días · Próximos partidos: '
               'consulta automática de los siguientes 14 días (si ESPN los publica).')
    equipos = sorted(set(partidos_completos['local'].dropna()) | set(partidos_completos['visitante'].dropna()))
    _nba_panel_seguimiento(partidos_completos)
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
                opciones = {f"{r.visitante} @ {r.local} · {str(r.fecha_utc)[:10]}": r._asdict()
                            for r in futuros_disponibles.head(40).itertuples(index=False)}
                elegido = st.selectbox('🏀 Selecciona un partido para la tarjeta única',
                                       list(opciones), key='ri_nba_tarjeta_partido')
                _tarjeta_unica_partido(partidos_completos, opciones[elegido])
    elif vista == '👥 Jugadores':
        _nba_panel_disponibilidad_jugadores()
        equipo = st.selectbox('Filtrar jugadores por equipo', ['Todos'] + equipos, key='ri_nba_equipo_jugadores')
        finales = partidos.loc[partidos['finalizado'].eq(True)]
        maximo = min(35, len(finales))
        if maximo == 0:
            st.info('No hay partidos finalizados con estadísticas individuales.')
        else:
            limite = st.slider('Máximo de boxscores a consultar', 1, maximo,
                               min(12, maximo), key='ri_nba_limite')
            _mostrar_jugadores(partidos_completos, equipo, limite, historico=partidos)
    else:
        equipo = st.selectbox('Filtrar calendario por equipo', ['Todos'] + equipos, key='ri_nba_equipo_calendario')
        vista_cal = partidos.copy()
        if equipo != 'Todos':
            vista_cal = vista_cal.loc[vista_cal['local'].eq(equipo) |
                                          vista_cal['visitante'].eq(equipo)]
        columnas = ['fecha_utc', 'visitante', 'local', 'estado',
                    'puntos_visitante', 'puntos_local']
        st.dataframe(vista_cal[columnas], hide_index=True, use_container_width=True)
    st.caption('Las estadísticas se limitan a las fechas y partidos consultados. '
               'La disponibilidad depende del proveedor externo.')


