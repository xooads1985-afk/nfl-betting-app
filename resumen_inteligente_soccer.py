"""Resumen Inteligente Soccer - Etapa 11, fuente football-data.org y CSV.
Independiente de NFL, NBA y main.py. Requiere streamlit y requests.
"""
import os
import math
from datetime import datetime, timezone
from io import BytesIO
import csv
import requests
import pandas as pd
import streamlit as st

COMPETICIONES = {
    '🇬🇧 Premier League': 'PL',
    '🇪🇸 LaLiga': 'PD',
    '🇮🇹 Serie A': 'SA',
    '🇩🇪 Bundesliga': 'BL1',
    '🇫🇷 Ligue 1': 'FL1',
    '🏆 UEFA Champions League': 'CL',
}
BASE = 'https://api.football-data.org/v4'


def _token():
    try:
        value = st.secrets.get('FOOTBALL_DATA_KEY', '')
    except Exception:
        value = ''
    return (value if isinstance(value, str) else '').strip() or os.getenv('FOOTBALL_DATA_KEY', '').strip()


@st.cache_data(ttl=3600, show_spinner=False)
def _consulta(ruta, token, temporada=None):
    params = {'season': int(temporada)} if temporada else {}
    try:
        r = requests.get(BASE + ruta, headers={'X-Auth-Token': token}, params=params, timeout=20)
    except requests.RequestException:
        raise ValueError('No se pudo conectar con el servidor. Comprueba la conexión e inténtalo más tarde.') from None
    if r.status_code == 401:
        raise ValueError('Clave no autorizada. Revisa FOOTBALL_DATA_KEY en Streamlit Secrets.')
    if r.status_code == 403:
        raise ValueError('Esta competición, temporada o consulta no está habilitada para tu plan.')
    if r.status_code == 404:
        raise ValueError('La competición o temporada solicitada no está disponible.')
    if r.status_code == 429:
        raise ValueError('Se alcanzó el límite temporal de solicitudes. Espera antes de volver a consultar.')
    if r.status_code >= 400:
        raise ValueError(f'El servidor rechazó la consulta (HTTP {r.status_code}).')
    try:
        payload = r.json()
    except ValueError:
        raise ValueError('El servidor devolvió datos no válidos.') from None
    if not isinstance(payload, dict):
        raise ValueError('La respuesta no tiene el formato esperado.')
    return payload


def _partidos(datos):
    rows = []
    for x in datos:
        home = x.get('homeTeam') or {}
        away = x.get('awayTeam') or {}
        score = x.get('score') or {}
        full = score.get('fullTime') or {}
        half = score.get('halfTime') or {}
        rows.append({
            'Fecha UTC': (x.get('utcDate') or '')[:16].replace('T', ' '),
            'Local': home.get('shortName') or home.get('name') or 'N/D',
            'Visitante': away.get('shortName') or away.get('name') or 'N/D',
            'Estado': x.get('status', 'N/D'),
            'Goles local': full.get('home'),
            'Goles visitante': full.get('away'),
            '1T local': half.get('home'),
            '1T visitante': half.get('away'),
        })
    return rows


def _resumen(rows):
    finalizados = [x for x in rows if x['Estado'] == 'FINISHED'
                   and isinstance(x['Goles local'], int) and isinstance(x['Goles visitante'], int)]
    if not finalizados:
        st.info('Todavía no hay resultados finalizados con marcadores completos en los datos cargados.')
        return
    total = sum(x['Goles local'] + x['Goles visitante'] for x in finalizados)
    a, b = st.columns(2)
    a.metric('Partidos finalizados', len(finalizados))
    b.metric('Goles por partido', f'{total / len(finalizados):.2f}')
    mitades = [x for x in finalizados if isinstance(x['1T local'], int) and isinstance(x['1T visitante'], int)]
    if mitades:
        g1 = sum(x['1T local'] + x['1T visitante'] for x in mitades)
        gfull = sum(x['Goles local'] + x['Goles visitante'] for x in mitades)
        a, b = st.columns(2)
        a.metric('Goles 1.ª mitad / partido', f'{g1 / len(mitades):.2f}')
        b.metric('Goles 2.ª mitad / partido', f'{(gfull-g1) / len(mitades):.2f}')
        st.caption(f'Promedios descriptivos sobre {len(mitades)} partidos con datos de ambas mitades; no son predicciones.')
    else:
        st.info('La fuente no devolvió marcadores por mitades para estos partidos.')



def _terminados(datos):
    """Solo partidos finalizados, con fecha y marcadores válidos."""
    validos = []
    for x in datos:
        if not isinstance(x, dict) or x.get('status') != 'FINISHED':
            continue
        full = (x.get('score') or {}).get('fullTime') or {}
        if not all(type(full.get(lado)) is int for lado in ('home', 'away')):
            continue
        if not (x.get('homeTeam') or {}).get('id') or not (x.get('awayTeam') or {}).get('id'):
            continue
        validos.append(x)
    return sorted(validos, key=lambda x: (x.get('utcDate') or '', x.get('id') or 0))


def _equipos_desde_partidos(datos):
    equipos = {}
    for partido in datos:
        for campo in ('homeTeam', 'awayTeam'):
            equipo = partido.get(campo) or {}
            identificador = equipo.get('id')
            if identificador is not None:
                equipos[identificador] = equipo.get('shortName') or equipo.get('name') or str(identificador)
    return equipos


def _estadisticas_equipo(partidos, equipo_id, cantidad, condicion):
    """Historial por equipo; condicion: Todos, Local o Visitante."""
    filtrados = []
    for partido in _terminados(partidos):
        local = (partido.get('homeTeam') or {}).get('id') == equipo_id
        visita = (partido.get('awayTeam') or {}).get('id') == equipo_id
        if not (local or visita):
            continue
        if condicion == 'Local' and not local:
            continue
        if condicion == 'Visitante' and not visita:
            continue
        filtrados.append(partido)
    muestra = list(reversed(filtrados[-cantidad:]))
    gf, gc, victorias, empates, derrotas = [], [], 0, 0, 0
    mitades = []
    historial = []
    for partido in muestra:
        local = (partido.get('homeTeam') or {}).get('id') == equipo_id
        rival = partido.get('awayTeam') if local else partido.get('homeTeam')
        marcador = (partido.get('score') or {}).get('fullTime') or {}
        propios = marcador['home' if local else 'away']
        ajenos = marcador['away' if local else 'home']
        gf.append(propios)
        gc.append(ajenos)
        resultado = 'Victoria' if propios > ajenos else 'Empate' if propios == ajenos else 'Derrota'
        victorias += resultado == 'Victoria'
        empates += resultado == 'Empate'
        derrotas += resultado == 'Derrota'
        half = (partido.get('score') or {}).get('halfTime') or {}
        if type(half.get('home')) is int and type(half.get('away')) is int:
            propios_1t = half['home' if local else 'away']
            ajenos_1t = half['away' if local else 'home']
            if propios_1t <= propios and ajenos_1t <= ajenos:
                mitades.append((propios_1t, propios - propios_1t))
        historial.append({
            'Fecha UTC': (partido.get('utcDate') or '')[:10],
            'Condición': 'Local' if local else 'Visitante',
            'Rival': (rival or {}).get('shortName') or (rival or {}).get('name') or 'N/D',
            'GF': propios, 'GC': ajenos, 'Resultado': resultado,
            'Temporada': partido.get('_soc_temporada', 'N/D'),
        })
    n = len(muestra)
    return {
        'N': n, 'GF': sum(gf) / n if n else None,
        'GC': sum(gc) / n if n else None,
        'Diferencia': (sum(gf) - sum(gc)) / n if n else None,
        'Victorias': victorias, 'Empates': empates, 'Derrotas': derrotas,
        '1T': sum(x[0] for x in mitades) / len(mitades) if mitades else None,
        '2T': sum(x[1] for x in mitades) / len(mitades) if mitades else None,
        'N mitades': len(mitades), 'Historial': historial,
    }


def _grafica_evolucion(stats, nombre):
    """Gráficas descriptivas en orden cronológico, sin extrapolaciones."""
    historial = list(reversed(stats['Historial']))
    if len(historial) < 2:
        st.caption(f'{nombre}: se requieren al menos dos partidos para mostrar evolución.')
        return
    grafica = pd.DataFrame({
        'Goles anotados': [x['GF'] for x in historial],
        'Goles recibidos': [x['GC'] for x in historial],
    }, index=[f"{x['Fecha UTC']} · {i + 1}" for i, x in enumerate(historial)])
    st.line_chart(grafica, use_container_width=True)
    st.caption(f'{nombre}: evolución cronológica de goles en los partidos seleccionados.')




def _historial_cronologico(datos, equipo_id, condicion):
    """Serie histórica válida, ordenada; la condición se aplica antes de evaluar."""
    serie = []
    for partido in _terminados(datos):
        local = (partido.get('homeTeam') or {}).get('id') == equipo_id
        visita = (partido.get('awayTeam') or {}).get('id') == equipo_id
        if not (local or visita):
            continue
        if condicion == 'Local' and not local:
            continue
        if condicion == 'Visitante' and not visita:
            continue
        marcador = (partido.get('score') or {}).get('fullTime') or {}
        gf = marcador['home' if local else 'away']
        gc = marcador['away' if local else 'home']
        serie.append({'Fecha': (partido.get('utcDate') or '')[:10],
                      'GF': gf, 'GC': gc, 'ID': partido.get('id'),
                      'Temporada': partido.get('_soc_temporada', 'N/D')})
    return serie


def _validacion_cronologica(serie, ventana=5, minimo=3):
    """Backtest descriptivo: promedio móvil exclusivamente de partidos previos."""
    registros = []
    for i in range(minimo, len(serie)):
        previos = serie[max(0, i - ventana):i]
        if len(previos) < minimo:
            continue
        estimado_gf = sum(p['GF'] for p in previos) / len(previos)
        estimado_gc = sum(p['GC'] for p in previos) / len(previos)
        actual = serie[i]
        registros.append({
            'Fecha': actual['Fecha'], 'N previos': len(previos),
            'GF estimados': round(estimado_gf, 2), 'GF reales': actual['GF'],
            'GC estimados': round(estimado_gc, 2), 'GC reales': actual['GC'],
            '_error_gf': estimado_gf - actual['GF'],
            '_error_gc': estimado_gc - actual['GC'],
        })
    if not registros:
        return {'N': 0, 'MAE GF': None, 'Sesgo GF': None,
                'MAE GC': None, 'Sesgo GC': None, 'Detalle': []}
    n = len(registros)
    return {'N': n,
            'MAE GF': sum(abs(x['_error_gf']) for x in registros) / n,
            'Sesgo GF': sum(x['_error_gf'] for x in registros) / n,
            'MAE GC': sum(abs(x['_error_gc']) for x in registros) / n,
            'Sesgo GC': sum(x['_error_gc'] for x in registros) / n,
            'Detalle': [{k: v for k, v in r.items() if not k.startswith('_')}
                        for r in registros]}


def _panel_validacion(datos, selecciones, ventana, temporada_actual=None):
    st.subheader('🧪 Validación histórica · Etapa 9')
    st.caption('Promedio móvil evaluado partido a partido. Para cada fecha se usan '
               'exclusivamente resultados anteriores de la misma competición y condición, '
               'incluso si corresponden a otra temporada. No se hacen consultas adicionales.')
    filas = []
    for equipo_id, nombre, condicion in selecciones:
        serie = _historial_cronologico(datos, equipo_id, condicion)
        prueba = _validacion_cronologica(serie, ventana=ventana)
        reciente = serie[-ventana:]
        temporada_serie = [x for x in serie if x.get('Temporada') == temporada_actual]
        n_total = len(serie)
        def promedio(partidos, campo):
            return sum(x[campo] for x in partidos) / len(partidos) if partidos else None
        def formato(valor):
            return f'{valor:.2f}' if valor is not None else 'N/D'
        filas.append({
            'Equipo': nombre, 'Condición': condicion, 'Partidos': n_total,
            'Evaluados': prueba['N'], 'MAE GF': formato(prueba['MAE GF']),
            'Sesgo GF': formato(prueba['Sesgo GF']),
            'MAE GC': formato(prueba['MAE GC']),
            'Sesgo GC': formato(prueba['Sesgo GC']),
        })
        with st.expander(f'🔎 {nombre} · validación y tendencias'):
            por_temporada = {}
            for encuentro in serie:
                clave = str(encuentro.get('Temporada', 'N/D'))
                por_temporada[clave] = por_temporada.get(clave, 0) + 1
            st.caption('Partidos por temporada: ' + ', '.join(f'{k}: {v}' for k, v in sorted(por_temporada.items())))
            st.caption(f'Historial: {n_total} partidos · evaluaciones: {prueba["N"]} · '
                       f'ventana: hasta {ventana} partidos previos · mínimo inicial: 3.')
            if prueba['N'] < 3:
                st.warning('Validación insuficiente: se necesitan más partidos '
                           'para interpretar el error con estabilidad.')
            else:
                st.metric('MAE goles anotados', formato(prueba['MAE GF']))
                st.metric('MAE goles recibidos', formato(prueba['MAE GC']))
                st.caption('Sesgo = estimado − real. Positivo: sobreestima; '
                           'negativo: subestima. MAE más bajo indica menor error histórico.')
            st.markdown('**Rendimiento reciente frente a la temporada seleccionada**')
            if not temporada_serie:
                st.info('No hay partidos finalizados de este equipo en la temporada seleccionada.')
            st.dataframe([
                {'Métrica': 'Goles anotados / partido',
                 f'Últimos {len(reciente)}': formato(promedio(reciente, 'GF')),
                 'Temporada actual': formato(promedio(temporada_serie, 'GF'))},
                {'Métrica': 'Goles recibidos / partido',
                 f'Últimos {len(reciente)}': formato(promedio(reciente, 'GC')),
                 'Temporada actual': formato(promedio(temporada_serie, 'GC'))},
            ], hide_index=True, use_container_width=True)
            if prueba['Detalle']:
                st.dataframe(prueba['Detalle'][-20:], hide_index=True,
                             use_container_width=True)
                st.caption('Se muestran hasta 20 evaluaciones, en orden cronológico.')
    st.dataframe(filas, hide_index=True, use_container_width=True)
    st.info('Validación retrospectiva de un promedio móvil sencillo; no demuestra '
            'capacidad de anticipar partidos futuros. Las muestras pequeñas y '
            'las temporadas incompletas limitan las conclusiones.')



# ── Etapa 10: proyecciones descriptivas de goles por períodos ──────────────
def _soc10_goles_periodos(partido):
    """Goles reales por equipo y período; nunca infiere un descanso ausente."""
    if partido.get('status') != 'FINISHED':
        return None
    marcador = (partido.get('score') or {})
    full = marcador.get('fullTime') or {}
    half = marcador.get('halfTime') or {}
    if any(type(full.get(k)) is not int for k in ('home', 'away')):
        return None
    resultado = {'Final': (full['home'], full['away'])}
    if all(type(half.get(k)) is int for k in ('home', 'away')):
        if 0 <= half['home'] <= full['home'] and 0 <= half['away'] <= full['away']:
            resultado['1T'] = (half['home'], half['away'])
            resultado['2T'] = (full['home'] - half['home'], full['away'] - half['away'])
    return resultado


def _soc10_promedio(historial, lado, periodo, minimo=3):
    valores = []
    for partido in historial:
        periodos = _soc10_goles_periodos(partido)
        if periodos and periodo in periodos:
            valores.append(periodos[periodo][lado])
    return sum(valores) / len(valores) if len(valores) >= minimo else None, len(valores)


def _soc10_historial_lado(partidos, equipo_id, es_local, fecha_limite=None, ventana=10):
    campo = 'homeTeam' if es_local else 'awayTeam'
    filtrados = [p for p in _terminados(partidos)
                 if (p.get(campo) or {}).get('id') == equipo_id
                 and (fecha_limite is None or (p.get('utcDate') or '') < fecha_limite)]
    return filtrados[-ventana:]


def _soc10_calcular(partidos, local_id, visitante_id, ventana=10, fecha_limite=None):
    """Ataque/defensa frente a referencia de liga, sin consultar datos futuros."""
    anteriores = [p for p in _terminados(partidos)
                  if fecha_limite is None or (p.get('utcDate') or '') < fecha_limite]
    local = _soc10_historial_lado(anteriores, local_id, True, ventana=ventana)
    visitante = _soc10_historial_lado(anteriores, visitante_id, False, ventana=ventana)
    filas = []
    for periodo in ('1T', '2T', 'Final'):
        ataque_l, n_al = _soc10_promedio(local, 0, periodo)
        defensa_l, n_dl = _soc10_promedio(local, 1, periodo)
        ataque_v, n_av = _soc10_promedio(visitante, 1, periodo)
        defensa_v, n_dv = _soc10_promedio(visitante, 0, periodo)
        ref_l, n_rl = _soc10_promedio(anteriores, 0, periodo, minimo=10)
        ref_v, n_rv = _soc10_promedio(anteriores, 1, periodo, minimo=10)
        if any(v is None for v in (ataque_l, defensa_l, ataque_v, defensa_v, ref_l, ref_v)):
            continue
        est_l = (ataque_l + defensa_v) / 2
        est_v = (ataque_v + defensa_l) / 2
        for tipo, estimado, referencia in (
            ('Local', est_l, ref_l), ('Visitante', est_v, ref_v),
            ('Combinados', est_l + est_v, ref_l + ref_v)):
            filas.append({'Período': periodo, 'Métrica': tipo,
                          'Proyección': estimado, 'Referencia': referencia,
                          'Edge descriptivo': estimado - referencia,
                          'Muestra local': min(n_al, n_dl),
                          'Muestra visitante': min(n_av, n_dv),
                          'Muestra liga': min(n_rl, n_rv)})
    return filas


def _soc10_validacion(partidos, max_partidos=150, ventana=10):
    """Backtest temporal: cada pronóstico utiliza solo encuentros previos."""
    terminados = _terminados(partidos)
    resultados = []
    for partido in terminados:
        fecha = partido.get('utcDate') or ''
        local_id = (partido.get('homeTeam') or {}).get('id')
        visitante_id = (partido.get('awayTeam') or {}).get('id')
        if not fecha or local_id is None or visitante_id is None:
            continue
        reales = _soc10_goles_periodos(partido)
        if not reales:
            continue
        estimaciones = _soc10_calcular(terminados, local_id, visitante_id,
                                       ventana=ventana, fecha_limite=fecha)
        for fila in estimaciones:
            periodo, tipo = fila['Período'], fila['Métrica']
            if periodo not in reales:
                continue
            rl, rv = reales[periodo]
            observado = rl if tipo == 'Local' else rv if tipo == 'Visitante' else rl + rv
            proyeccion = fila['Proyección']
            referencia = fila['Referencia']
            resultados.append({
                'Fecha UTC': fecha, 'Partido':
                    f"{(partido.get('homeTeam') or {}).get('shortName') or 'Local'} vs "
                    f"{(partido.get('awayTeam') or {}).get('shortName') or 'Visitante'}",
                'ID partido': partido.get('id'), 'Período': periodo,
                'Métrica': tipo, 'Proyección': proyeccion,
                'Referencia': referencia, 'Observado': observado,
                'Edge descriptivo': proyeccion - referencia,
                'Error firmado': proyeccion - observado,
                'Error absoluto': abs(proyeccion - observado),
                'Error referencia': abs(referencia - observado),
            })
    ids = list(dict.fromkeys(r['ID partido'] for r in resultados))[-max_partidos:]
    permitidos = set(ids)
    return [r for r in resultados if r['ID partido'] in permitidos]


def _soc10_panel(datos, local_id, visitante_id, nombre_local, nombre_visitante, ventana):
    st.subheader('⚽ Proyecciones de goles y Edge · Etapa 10')
    st.caption('Escenario estadístico ilustrativo: equipo A como local y equipo B como '
               'visitante. No corresponde necesariamente a un encuentro programado. '
               'Edge descriptivo = proyección − referencia histórica de liga.')
    proyecciones = _soc10_calcular(datos, local_id, visitante_id, ventana=ventana)
    if not proyecciones:
        st.warning('No hay cobertura suficiente para proyectar goles. Se necesitan '
                   'al menos 3 partidos de cada equipo en su condición y 10 de liga '
                   'por período. No se inventan marcadores al descanso.')
    else:
        for periodo in ('1T', '2T', 'Final'):
            filas = [f for f in proyecciones if f['Período'] == periodo]
            if not filas:
                st.info(f'{periodo}: datos por mitades insuficientes o no disponibles.')
                continue
            with st.expander(f'📊 {periodo} · goles y Edge', expanded=(periodo == 'Final')):
                tabla = []
                for f in filas:
                    etiqueta = nombre_local if f['Métrica'] == 'Local' else (
                        nombre_visitante if f['Métrica'] == 'Visitante' else 'Ambos equipos')
                    tabla.append({'Equipo': etiqueta,
                                  'Proyección': round(f['Proyección'], 2),
                                  'Referencia': round(f['Referencia'], 2),
                                  'Edge': round(f['Edge descriptivo'], 2)})
                st.dataframe(tabla, hide_index=True, use_container_width=True)
                st.caption(f"Cobertura: {filas[0]['Muestra local']} partidos local, "
                           f"{filas[0]['Muestra visitante']} visitante y "
                           f"{filas[0]['Muestra liga']} de liga.")
        df = pd.DataFrame(proyecciones)
        st.download_button('📥 Descargar proyecciones de goles CSV',
                           data=df.to_csv(index=False).encode('utf-8-sig'),
                           file_name='soccer_proyecciones_goles.csv',
                           mime='text/csv', key='soc10_export_proy')

    with st.expander('🧪 Validación histórica de goles · sin datos futuros'):
        st.caption('Cada partido se evalúa exclusivamente con resultados anteriores '
                   'a su fecha UTC. Los partidos simultáneos no se utilizan como historial. '
                   'MAE y sesgo se calculan sin redondear las proyecciones.')
        maximo = st.selectbox('Máximo de partidos históricos', [35, 70, 150],
                              index=1, key='soc10_n_backtest')
        if st.button('🔍 Calcular validación histórica', key='soc10_run_backtest'):
            with st.spinner('Evaluando encuentros cronológicamente...'):
                st.session_state['soc10_resultado'] = (
                    len(datos), maximo, ventana, _soc10_validacion(datos, maximo, ventana))
        guardado = st.session_state.get('soc10_resultado')
        if not guardado or guardado[:3] != (len(datos), maximo, ventana):
            st.info('Pulsa Calcular validación histórica para generar la tabla.')
            return
        resultados = guardado[3]
        if not resultados:
            st.warning('No hay suficientes partidos anteriores para una validación.')
            return
        resumen = []
        for periodo in ('1T', '2T', 'Final'):
            for tipo in ('Local', 'Visitante', 'Combinados'):
                muestra = [x for x in resultados if x['Período'] == periodo and x['Métrica'] == tipo]
                if not muestra:
                    continue
                n = len(muestra)
                resumen.append({'Período': periodo, 'Métrica': tipo, 'Partidos': n,
                                'MAE': round(sum(x['Error absoluto'] for x in muestra) / n, 3),
                                'Sesgo': round(sum(x['Error firmado'] for x in muestra) / n, 3),
                                'MAE referencia': round(sum(x['Error referencia'] for x in muestra) / n, 3)})
        st.dataframe(resumen, hide_index=True, use_container_width=True)
        st.markdown('**📊 Comparación inteligente · modelo frente a referencia**')
        st.caption('Ambos MAE se calculan sobre los mismos partidos y período. '
                   'Diferencia = MAE referencia − MAE modelo; positiva favorece al modelo.')
        for periodo in ('1T', '2T', 'Final'):
            periodo_filas = [f for f in resumen if f['Período'] == periodo]
            if not periodo_filas:
                continue
            titulo_periodo = {'1T': 'Primera mitad', '2T': 'Segunda mitad',
                              'Final': 'Partido completo'}[periodo]
            with st.container(border=True):
                st.markdown(f'**{titulo_periodo}**')
                for fila in periodo_filas:
                    muestra = [x for x in resultados if x['Período'] == periodo
                               and x['Métrica'] == fila['Métrica']]
                    n = len(muestra)
                    if not n:
                        continue
                    mae_m = sum(x['Error absoluto'] for x in muestra) / n
                    mae_r = sum(x['Error referencia'] for x in muestra) / n
                    diferencia = mae_r - mae_m
                    st.markdown(f"**{fila['Métrica']} · {n} partidos**")
                    a, b = st.columns(2)
                    a.metric('MAE modelo', f'{mae_m:.3f}')
                    b.metric('MAE referencia', f'{mae_r:.3f}')
                    if abs(diferencia) < 0.0005:
                        mensaje = 'Errores prácticamente iguales.'
                    elif diferencia > 0:
                        mensaje = f'Menor error del modelo por {diferencia:.3f} goles.'
                    else:
                        mensaje = f'Menor error de la referencia por {-diferencia:.3f} goles.'
                    st.caption(mensaje)
        st.info('La comparación es retrospectiva. Diferencias pequeñas no demuestran '
                'superioridad futura; conviene acumular más encuentros y repetir la evaluación.')
        st.caption('Sesgo positivo = sobreestimación. La referencia corresponde al '
                   'promedio de liga disponible antes de cada partido evaluado.')
        tabla = pd.DataFrame(resultados)
        st.download_button('📥 Descargar validación completa CSV',
                           data=tabla.to_csv(index=False).encode('utf-8-sig'),
                           file_name='soccer_validacion_goles.csv',
                           mime='text/csv', key='soc10_export_val')
        with st.expander('📋 Partidos evaluados'):
            st.dataframe(tabla.round(3), hide_index=True, use_container_width=True)



# ── Etapa 12: interpretación de Edge y contexto de precisión ───────────────
def _soc12_interpretacion_edge(proyeccion, referencia, mae=None, sesgo=None):
    """Interpretación descriptiva; no altera las estimaciones de Etapa 11."""
    edge = proyeccion - referencia
    direccion = ('superior' if edge > 0 else 'inferior' if edge < 0 else 'igual')
    texto = f'Proyección {direccion} a la referencia histórica por {abs(edge):.2f} goles.'
    if mae is not None:
        texto += f' Error absoluto medio histórico: {mae:.2f} goles.'
    if sesgo is not None:
        texto += (f' Sesgo histórico: {sesgo:+.2f} goles '
                  '(estimado menos real).')
    return {'Edge': edge, 'Interpretación': texto}


def _soc12_resumen_validacion(datos, ventana):
    """Agrupa el backtest temporal original por período y tipo."""
    registros = _soc10_validacion(datos, max_partidos=150, ventana=ventana)
    resumen = {}
    for periodo in ('1T', '2T', 'Final'):
        for tipo in ('Local', 'Visitante', 'Combinados'):
            grupo = [r for r in registros if r['Período'] == periodo and r['Métrica'] == tipo]
            if grupo:
                n = len(grupo)
                resumen[(periodo, tipo)] = {
                    'N': n,
                    'MAE': sum(r['Error absoluto'] for r in grupo) / n,
                    'Sesgo': sum(r['Error firmado'] for r in grupo) / n,
                    'MAE referencia': sum(r['Error referencia'] for r in grupo) / n,
                }
    return resumen


def _soc12_comparar_precision(mae_modelo, mae_referencia, n, tolerancia=0.02, minimo=30):
    """Clasificación descriptiva conservadora usando MAE sin redondear."""
    if n < minimo:
        return ('Muestra limitada',
                f'Solo {n} encuentros evaluados; conviene ampliar la muestra antes de interpretar diferencias.')
    diferencia = mae_referencia - mae_modelo
    if abs(diferencia) <= tolerancia + 1e-12:
        return ('Rendimiento similar',
                f'Diferencia de MAE de {abs(diferencia):.3f} goles, dentro del margen descriptivo de ±{tolerancia:.2f}.')
    if diferencia > 0:
        return ('Modelo con menor MAE',
                f'En esta muestra, el modelo reduce el MAE en {diferencia:.3f} goles respecto a la referencia.')
    return ('Referencia con menor MAE',
            f'En esta muestra, la referencia reduce el MAE en {abs(diferencia):.3f} goles respecto al modelo.')


# ── Etapa 12.2: diagnóstico transversal de precisión ──────────────────────
def _soc122_diagnostico(resumen, tolerancia=0.02, minimo=30):
    """Solo interpreta los resultados existentes; no modifica el backtest."""
    filas = []
    for periodo, etiqueta in (('1T', 'Primera mitad'), ('2T', 'Segunda mitad'), ('Final', 'Partido completo')):
        for tipo in ('Local', 'Visitante', 'Combinados'):
            r = resumen.get((periodo, tipo))
            if not r:
                continue
            n = r['N']
            mae = r['MAE']
            base = r['MAE referencia']
            sesgo = r['Sesgo']
            estado, _ = _soc12_comparar_precision(mae, base, n, tolerancia, minimo)
            filas.append({'Período': etiqueta, 'Métrica': tipo, 'N': n,
                          'MAE modelo': mae, 'MAE referencia': base,
                          'Diferencia MAE': mae - base, 'Sesgo': sesgo,
                          'Estado': estado})
    return filas


def _soc122_panel_diagnostico(resumen):
    """Panel móvil compacto: tres períodos y las nueve métricas existentes."""
    if not resumen:
        return
    filas = _soc122_diagnostico(resumen)
    if not filas:
        return
    st.markdown('#### 🔎 Diagnóstico histórico · Etapa 12.2')
    st.caption('Diferencia MAE = MAE modelo − MAE referencia. Negativa: menor error del modelo. '
               'El sesgo es proyección − resultado real; positivo indica sobreestimación.')
    for periodo in ('Primera mitad', 'Segunda mitad', 'Partido completo'):
        bloque = [r for r in filas if r['Período'] == periodo]
        if not bloque:
            continue
        with st.expander(f'📋 {periodo} · diagnóstico', expanded=(periodo == 'Partido completo')):
            for r in bloque:
                st.markdown(f'**{r["Métrica"]}** · {r["Estado"]}')
                st.caption(f'MAE modelo {r["MAE modelo"]:.3f} · referencia {r["MAE referencia"]:.3f} '
                           f'· diferencia {r["Diferencia MAE"]:+.3f} goles')
                st.caption(f'Sesgo {r["Sesgo"]:+.3f} goles · muestra {r["N"]} encuentros')
                if r['N'] < 30:
                    st.caption('⚠️ Muestra limitada: interpretación provisional.')
    menores = sum(r['Estado'] == 'Modelo con menor MAE' for r in filas)
    similares = sum(r['Estado'] == 'Rendimiento similar' for r in filas)
    referencias = sum(r['Estado'] == 'Referencia con menor MAE' for r in filas)
    limitadas = sum(r['Estado'] == 'Muestra limitada' for r in filas)
    st.caption(f'Resumen de {len(filas)} métricas: modelo menor MAE {menores} · '
               f'similares {similares} · referencia menor MAE {referencias} · '
               f'muestra limitada {limitadas}.')
    st.caption('Diagnóstico retrospectivo descriptivo; no equivale a una predicción '
               'de rendimiento futuro. Los valores no se recalculan ni ajustan aquí.')


def _soc12_panel(datos, local_id, visitante_id, nombre_local, nombre_visitante, ventana):
    st.subheader('🧠 Interpretación inteligente · Etapa 12.2')
    st.caption('Edge = proyección menos referencia histórica. MAE y sesgo proceden '
               'de validación cronológica retrospectiva, no son garantías futuras.')
    proyecciones = _soc10_calcular(datos, local_id, visitante_id, ventana=ventana)
    if not proyecciones:
        st.info('Muestra insuficiente para mostrar la interpretación del Edge.')
        return
    # El backtest puede resultar costoso: se ejecuta solo a petición del usuario.
    clave = ('soc12_validacion', len(datos), ventana,
             tuple((p.get('id'), p.get('status'), (p.get('score') or {}).get('fullTime', {} ).get('home'),
                    (p.get('score') or {}).get('fullTime', {}).get('away'))
                   for p in datos if isinstance(p, dict)))
    if st.button('🧪 Calcular precisión histórica para interpretar Edge', key='soc12_validar'):
        with st.spinner('Calculando validación cronológica...'):
            st.session_state['soc12_resultado'] = (clave, _soc12_resumen_validacion(datos, ventana))
    guardado = st.session_state.get('soc12_resultado')
    validacion = guardado[1] if guardado and guardado[0] == clave else {}
    if not validacion:
        st.caption('La precisión histórica se mostrará al pulsar el botón de validación.')
    else:
        _soc122_panel_diagnostico(validacion)
    for periodo, etiqueta in [('Final', 'Partido completo'), ('1T', 'Primera mitad'), ('2T', 'Segunda mitad')]:
        filas = [p for p in proyecciones if p['Período'] == periodo]
        if not filas:
            continue
        with st.expander(f'📊 {etiqueta} · proyección y Edge', expanded=(periodo == 'Final')):
            for fila in filas:
                tipo = fila['Métrica']
                nombre = nombre_local if tipo == 'Local' else nombre_visitante if tipo == 'Visitante' else 'Ambos equipos'
                referencia = fila['Referencia']
                estimacion = fila['Proyección']
                historial = validacion.get((periodo, tipo), {})
                interpretacion = _soc12_interpretacion_edge(estimacion, referencia,
                                  historial.get('MAE'), historial.get('Sesgo'))
                st.markdown(f'**{nombre}**')
                a, b, c = st.columns(3)
                a.metric('Proyección', f'{estimacion:.2f}')
                b.metric('Referencia', f'{referencia:.2f}')
                c.metric('Edge', f'{interpretacion["Edge"]:+.2f}')
                st.caption(interpretacion['Interpretación'])
                if historial:
                    st.caption(f'Muestra histórica: {historial["N"]} encuentros · '
                               f'MAE referencia: {historial["MAE referencia"]:.2f}')
                    estado, detalle = _soc12_comparar_precision(
                        historial['MAE'], historial['MAE referencia'], historial['N'])
                    st.markdown(f'**Precisión histórica: {estado}**')
                    st.caption(detalle)
                    st.caption('Comparación retrospectiva descriptiva; una diferencia de MAE '
                               'no demuestra por sí sola superioridad futura.')
                else:
                    st.caption('MAE y sesgo pendientes de calcular.')
    st.caption('Escenario ilustrativo de local y visitante; no implica que exista '
               'un partido programado entre los equipos seleccionados.')

def _comparador_equipos(datos, temporada_actual=None):
    st.subheader('⚽ Comparador de equipos · Etapa 9')
    st.caption('Datos reales de la competición seleccionada. Si activas el historial ampliado, se incluyen temporadas anteriores identificadas; el comparador no realiza consultas adicionales.')
    equipos = _equipos_desde_partidos(datos)
    if len(equipos) < 2:
        st.info('No hay suficientes equipos identificados en los partidos cargados.')
        return
    opciones = sorted(equipos, key=lambda identificador: (equipos[identificador].casefold(), identificador))
    izquierda = st.selectbox('Equipo A', opciones, format_func=lambda i: equipos[i], key='soc_eq_a_v4')
    alternativas = [i for i in opciones if i != izquierda]
    derecha = st.selectbox('Equipo B', alternativas, format_func=lambda i: equipos[i], key='soc_eq_b_v4')
    cantidad = st.selectbox('Últimos partidos', [5, 10, 20], key='soc_n_v4')
    st.markdown('**Condición independiente por equipo**')
    condicion_a = st.selectbox(f'Condición · {equipos[izquierda]}', ['Local', 'Visitante', 'Todos'], key='soc_cond_a_v5')
    condicion_b = st.selectbox(f'Condición · {equipos[derecha]}', ['Visitante', 'Local', 'Todos'], key='soc_cond_b_v5')
    a = _estadisticas_equipo(datos, izquierda, cantidad, condicion_a)
    b = _estadisticas_equipo(datos, derecha, cantidad, condicion_b)
    st.caption(f"Muestra: {equipos[izquierda]} ({condicion_a}) {a['N']}/{cantidad} · {equipos[derecha]} ({condicion_b}) {b['N']}/{cantidad}.")
    if not a['N'] or not b['N']:
        st.warning('Uno o ambos equipos no tienen partidos finalizados para la condición elegida.')
    elif min(a['N'], b['N']) < 5:
        st.warning('Muestra pequeña: al menos uno de los equipos tiene menos de cinco partidos disponibles.')
    elif a['N'] < cantidad or b['N'] < cantidad:
        st.info('La muestra es menor a la solicitada; se utilizan únicamente los partidos disponibles.')

    def mostrar(valor):
        return f'{valor:.2f}' if valor is not None else 'N/D'

    tabla = []
    for nombre, campo in [
        ('Partidos analizados', 'N'), ('Victorias', 'Victorias'), ('Empates', 'Empates'),
        ('Derrotas', 'Derrotas'), ('Goles a favor / partido', 'GF'),
        ('Goles en contra / partido', 'GC'), ('Diferencia / partido', 'Diferencia'),
        ('Goles a favor 1.ª mitad / partido', '1T'),
        ('Goles a favor 2.ª mitad / partido', '2T'),
        ('Partidos con datos por mitades', 'N mitades'),
    ]:
        fmt = str if campo in ('N', 'Victorias', 'Empates', 'Derrotas', 'N mitades') else mostrar
        tabla.append({'Métrica': nombre, equipos[izquierda]: fmt(a[campo]), equipos[derecha]: fmt(b[campo])})
    st.dataframe(tabla, hide_index=True, use_container_width=True)
    st.caption('Los promedios por mitades solo utilizan encuentros con marcadores válidos al descanso.')

    st.subheader('📈 Evolución de goles')
    for identificador, stats in ((izquierda, a), (derecha, b)):
        with st.expander(f"📈 {equipos[identificador]} · gráfica ({stats['N']} partidos)"):
            _grafica_evolucion(stats, equipos[identificador])
    for identificador, stats in ((izquierda, a), (derecha, b)):
        with st.expander(f"📋 Historial: {equipos[identificador]} ({stats['N']} partidos)"):
            if stats['Historial']:
                st.dataframe(stats['Historial'], hide_index=True, use_container_width=True)
            else:
                st.info('No hay partidos finalizados para el filtro seleccionado.')
    _panel_validacion(datos, [(izquierda, equipos[izquierda], condicion_a),
                              (derecha, equipos[derecha], condicion_b)], cantidad, temporada_actual)
    _soc10_panel(datos, izquierda, derecha, equipos[izquierda],
                 equipos[derecha], cantidad)
    _soc12_panel(datos, izquierda, derecha, equipos[izquierda],
                 equipos[derecha], cantidad)
    _panel_probabilidades(datos, izquierda, derecha, equipos[izquierda],
                           equipos[derecha], condicion_a, condicion_b, cantidad)
    _panel_validacion_probabilidades(datos)
    st.info('Comparación histórica descriptiva; no predice resultados futuros. Córners y jugadores requieren fuentes adicionales verificadas.')



def _probabilidades_poisson(media_local, media_visitante, max_goles=10):
    """Probabilidades descriptivas de marcador, truncadas y normalizadas."""
    def pmf(media, k):
        return math.exp(-media) * media ** k / math.factorial(k)
    p_local = [pmf(media_local, i) for i in range(max_goles + 1)]
    p_visita = [pmf(media_visitante, i) for i in range(max_goles + 1)]
    total = sum(p_local) * sum(p_visita)
    if total <= 0:
        return None
    return {
        'Local': sum(p_local[i] * p_visita[j] for i in range(max_goles + 1)
                     for j in range(max_goles + 1) if i > j) / total,
        'Empate': sum(p_local[i] * p_visita[i] for i in range(max_goles + 1)) / total,
        'Visitante': sum(p_local[i] * p_visita[j] for i in range(max_goles + 1)
                         for j in range(max_goles + 1) if i < j) / total,
    }


def _panel_probabilidades(datos, equipo_a, equipo_b, nombre_a, nombre_b,
                          condicion_a, condicion_b, ventana):
    """Comparación educativa entre modelo de equipos y referencia de liga."""
    st.subheader('📐 Probabilidades estadísticas · Etapa 9')
    st.caption('Distribución de Poisson ilustrativa. No utiliza cuotas, '
               'mercados ni recomendaciones de apuestas.')
    finalizados = _terminados(datos)
    serie_a = _historial_cronologico(datos, equipo_a, condicion_a)
    serie_b = _historial_cronologico(datos, equipo_b, condicion_b)
    # La ventana del comparador puede ser 5; la muestra minima de este
    # panel es independiente para evitar un bloqueo artificial.
    ventana_modelo = max(10, ventana)
    recientes_a = serie_a[-ventana_modelo:]
    recientes_b = serie_b[-ventana_modelo:]
    if len(serie_a) < 10 or len(serie_b) < 10:
        st.warning('Muestra insuficiente para comparar probabilidades: '
                   'se requieren al menos 10 partidos por equipo con los filtros elegidos.')
        return
    st.caption(f'Muestra del modelo: {len(recientes_a)} partidos de {nombre_a} y '
               f'{len(recientes_b)} de {nombre_b}; mínimo 10 por equipo.')
    # Se interpreta A como local y B como visitante. No es un fixture real.
    if condicion_a != 'Local' or condicion_b != 'Visitante':
        st.info('Para este ejercicio selecciona Local para el equipo A '
                'y Visitante para el equipo B.')
        return
    if len(finalizados) < 30:
        st.warning('La competición cargada tiene menos de 30 partidos '
                   'finalizados; no se calcula referencia de liga.')
        return

    media_a_gf = sum(x['GF'] for x in recientes_a) / len(recientes_a)
    media_a_gc = sum(x['GC'] for x in recientes_a) / len(recientes_a)
    media_b_gf = sum(x['GF'] for x in recientes_b) / len(recientes_b)
    media_b_gc = sum(x['GC'] for x in recientes_b) / len(recientes_b)
    lambda_a = (media_a_gf + media_b_gc) / 2
    lambda_b = (media_b_gf + media_a_gc) / 2

    media_liga_local = sum(x['score']['fullTime']['home'] for x in finalizados) / len(finalizados)
    media_liga_visita = sum(x['score']['fullTime']['away'] for x in finalizados) / len(finalizados)
    modelo = _probabilidades_poisson(lambda_a, lambda_b)
    referencia = _probabilidades_poisson(media_liga_local, media_liga_visita)
    if not modelo or not referencia:
        st.info('No fue posible calcular las probabilidades con estos datos.')
        return

    st.caption(f'Escenario ilustrativo: {nombre_a} (local) frente a '
               f'{nombre_b} (visitante). No representa un partido confirmado.')
    st.write(f'Goles medios estimados: {nombre_a} **{lambda_a:.2f}** · '
             f'{nombre_b} **{lambda_b:.2f}**')
    filas = []
    for evento in ('Local', 'Empate', 'Visitante'):
        filas.append({
            'Resultado': evento,
            'Modelo equipos': f'{modelo[evento] * 100:.1f}%',
            'Referencia liga': f'{referencia[evento] * 100:.1f}%',
            'Diferencia (pp)': f'{(modelo[evento] - referencia[evento]) * 100:+.1f}',
        })
    st.dataframe(filas, hide_index=True, use_container_width=True)
    st.caption('Diferencia (pp), también denominada aquí Edge estadístico: '
               'probabilidad del modelo menos probabilidad de referencia. '
               'No es una ventaja económica ni mide rentabilidad.')
    st.info('Estas probabilidades son estimaciones no calibradas. '
            'El MAE de goles no valida por sí solo las probabilidades de '
            'victoria o empate. Las temporadas, cambios de plantilla y '
            'la independencia supuesta por Poisson limitan el modelo.')


def _evaluar_probabilidades_historicas(datos, max_evaluaciones=100, ventana=10):
    """Evaluación temporal 1X2 sin datos del partido evaluado ni posteriores."""
    partidos = _terminados(datos)
    resultados = []
    for partido in partidos:
        fecha = partido.get('utcDate') or ''
        anteriores = [p for p in partidos if (p.get('utcDate') or '') < fecha]
        if len(anteriores) < 30:
            continue
        local_id = (partido.get('homeTeam') or {}).get('id')
        visita_id = (partido.get('awayTeam') or {}).get('id')
        local = _historial_cronologico(anteriores, local_id, 'Local')[-ventana:]
        visita = _historial_cronologico(anteriores, visita_id, 'Visitante')[-ventana:]
        if len(local) < 5 or len(visita) < 5:
            continue
        gf_local = sum(x['GF'] for x in local) / len(local)
        gc_local = sum(x['GC'] for x in local) / len(local)
        gf_visita = sum(x['GF'] for x in visita) / len(visita)
        gc_visita = sum(x['GC'] for x in visita) / len(visita)
        estimacion = _probabilidades_poisson((gf_local + gc_visita) / 2,
                                            (gf_visita + gc_local) / 2)
        media_l = sum(p['score']['fullTime']['home'] for p in anteriores) / len(anteriores)
        media_v = sum(p['score']['fullTime']['away'] for p in anteriores) / len(anteriores)
        base = _probabilidades_poisson(media_l, media_v)
        if not estimacion or not base:
            continue
        marcador = partido['score']['fullTime']
        real = ('Local' if marcador['home'] > marcador['away']
                else 'Visitante' if marcador['home'] < marcador['away'] else 'Empate')
        def brier(probabilidades):
            return sum((probabilidades[k] - int(k == real)) ** 2
                       for k in ('Local', 'Empate', 'Visitante'))
        resultados.append({
            'Fecha': fecha[:10], 'Resultado real': real,
            'Brier modelo': brier(estimacion),
            'Brier referencia': brier(base),
            'Confianza máxima': max(estimacion.values()),
            'Acierto favorito': max(estimacion, key=estimacion.get) == real,
        })
    return resultados[-max_evaluaciones:]


def _panel_validacion_probabilidades(datos):
    st.subheader('🧪 Validación de probabilidades · Etapa 9')
    st.caption('Prueba retrospectiva cronológica de resultados local/empate/visitante. '
               'Se utilizan solo partidos anteriores a cada encuentro, con '
               'un mínimo de 30 partidos de liga y 5 de cada equipo según su condición. '
               'Sin consultas adicionales.')
    registros = _evaluar_probabilidades_historicas(datos)
    if len(registros) < 10:
        st.warning(f'Solo hay {len(registros)} evaluaciones elegibles. '
                   'Se requieren al menos 10 para mostrar un resumen; '
                   'es preferible contar con muchas más.')
        return
    n = len(registros)
    mae_modelo = sum(x['Brier modelo'] for x in registros) / n
    mae_base = sum(x['Brier referencia'] for x in registros) / n
    a, b = st.columns(2)
    a.metric('Brier modelo', f'{mae_modelo:.3f}')
    b.metric('Brier referencia', f'{mae_base:.3f}')
    st.caption(f'{n} partidos evaluados (máximo 100 recientes). '
               'Brier multiclase: suma de errores cuadráticos de tres resultados; '
               'menor es mejor. No equivale al MAE de goles.')
    if mae_modelo < mae_base:
        st.info('En esta muestra, el modelo tiene menor error probabilístico '
                'que la referencia histórica de liga.')
    elif mae_modelo > mae_base:
        st.info('En esta muestra, la referencia de liga tiene menor error '
                'probabilístico que el modelo de equipos.')
    else:
        st.info('Ambos modelos muestran el mismo error medio redondeado.')
    st.markdown('**Comprobación de confianza (descriptiva)**')
    intervalos = [(0, .5, 'Hasta 50 %'), (.5, .65, '50–65 %'),
                  (.65, 1.01, 'Más de 65 %')]
    filas = []
    for inferior, superior, nombre in intervalos:
        sub = [x for x in registros if inferior <= x['Confianza máxima'] < superior]
        if sub:
            filas.append({'Confianza máxima': nombre, 'Partidos': len(sub),
                          'Acierto del resultado más probable':
                          f"{sum(x['Acierto favorito'] for x in sub) / len(sub) * 100:.1f}%"})
    st.dataframe(filas, hide_index=True, use_container_width=True)
    with st.expander('📋 Evaluaciones cronológicas'):
        st.dataframe([{'Fecha': x['Fecha'], 'Resultado': x['Resultado real'],
                       'Brier modelo': round(x['Brier modelo'], 3),
                       'Brier referencia': round(x['Brier referencia'], 3)}
                      for x in registros], hide_index=True, use_container_width=True)
    st.caption('La tabla de confianza no demuestra calibración estadística; '
               'para evaluarla formalmente se requieren más observaciones. '
               'Los partidos simultáneos quedan excluidos del historial previo.')

def _archivo_csv():
    st.subheader('📂 Archivo histórico CSV (opcional)')
    st.caption('Puedes consultar un CSV propio sin utilizar ninguna API. Se muestran las columnas originales, sin inventar datos.')
    archivo = st.file_uploader('Selecciona un archivo CSV', type=['csv'], key='soc_csv')
    if archivo is None:
        return
    if archivo.size > 5 * 1024 * 1024:
        st.error('El archivo supera 5 MB. Selecciona uno más pequeño.')
        return
    try:
        raw = archivo.getvalue().decode('utf-8-sig')
    except UnicodeDecodeError:
        try:
            raw = archivo.getvalue().decode('latin-1')
        except UnicodeError:
            st.error('No se pudo leer la codificación del archivo.')
            return
    try:
        dialect = csv.Sniffer().sniff(raw[:4096], delimiters=',;\t')
        reader = csv.DictReader(raw.splitlines(), dialect=dialect)
        rows = list(reader)
    except (csv.Error, ValueError):
        st.error('El CSV no tiene un formato válido.')
        return
    if not rows:
        st.warning('El archivo no contiene registros.')
        return
    st.success(f'Registros cargados: {len(rows)}')
    st.dataframe(rows[:200], hide_index=True, use_container_width=True)
    st.caption('Vista limitada a 200 registros. Las estadísticas automáticas se habilitarán tras validar las columnas disponibles.')


def mostrar_resumen_inteligente_soccer():
    st.title('⚽ Resumen Inteligente Soccer')
    st.caption('Etapa 12.2 · Goles y Edge · Diagnóstico histórico · Diseño móvil')
    fuente = st.radio('Fuente de datos', ['football-data.org', 'CSV local'], horizontal=True, key='soc_fuente_v3')
    if fuente == 'CSV local':
        _archivo_csv()
        return
    token = _token()
    if not token:
        st.warning('Falta configurar FOOTBALL_DATA_KEY en los Secrets de esta aplicación.')
        st.info('Obtén una clave gratuita en football-data.org y guárdala en Streamlit Cloud → Settings → Secrets como FOOTBALL_DATA_KEY = "tu_clave". No compartas tu clave.')
        st.caption('Puedes usar «CSV local» mientras configuras la nueva fuente.')
        return
    st.success('Nueva fuente configurada. Clave detectada sin mostrar su valor.')
    st.caption('Consultas únicamente al pulsar botones; caché de una hora. La cobertura depende del plan y la temporada.')
    nombre = st.selectbox('Competición', list(COMPETICIONES), key='soc_comp_v3')
    codigo = COMPETICIONES[nombre]
    temporada = st.selectbox('Temporada (año de inicio)', [2026, 2025, 2024, 2023], key='soc_season_v3')
    st.caption('La Champions League utiliza el código CL. Algunas temporadas o competiciones pueden estar restringidas.')
    if st.button('📅 Cargar partidos', key='soc_matches_v3'):
        try:
            data = _consulta(f'/competitions/{codigo}/matches', token, temporada)
            st.session_state['soc_partidos_v3'] = (codigo, temporada, data.get('matches', []))
            st.success(f"Partidos recibidos: {len(data.get('matches', []))}")
        except ValueError as exc:
            st.error(str(exc))
    saved = st.session_state.get('soc_partidos_v3')
    if saved and saved[:2] == (codigo, temporada):
        rows = _partidos(saved[2])
        if rows:
            estados = ['Todos', 'Finalizados', 'Programados']
            vista = st.selectbox('Mostrar partidos', estados, key='soc_vista_v3')
            if vista == 'Finalizados':
                rows_view = [x for x in rows if x['Estado'] == 'FINISHED']
            elif vista == 'Programados':
                rows_view = [x for x in rows if x['Estado'] in ('SCHEDULED', 'TIMED')]
            else:
                rows_view = rows
            st.dataframe(rows_view[:100], hide_index=True, use_container_width=True)
            st.caption(f'Se muestran {min(100, len(rows_view))} de {len(rows_view)} partidos. Horario UTC.')
            st.subheader('📊 Estadísticas históricas')
            _resumen(rows)
            st.subheader('📚 Historial ampliado · Etapa 9')
            st.caption('Opcional: consulta una temporada anterior de la misma competición. '
                       'Solo se añaden partidos finalizados; las temporadas se mantienen identificadas.')
            ampliar = st.checkbox('Incluir temporada anterior en el comparador', key='soc_ampliar_v7')
            datos_comparador = [dict(x, _soc_temporada=temporada) for x in saved[2]]
            if ampliar:
                anterior = temporada - 1
                st.caption(f'Temporada adicional solicitada: {anterior}. Puede estar restringida por el plan gratuito.')
                if st.button(f'📚 Cargar temporada {anterior}', key='soc_prev_v7'):
                    try:
                        respuesta = _consulta(f'/competitions/{codigo}/matches', token, anterior)
                        anteriores = respuesta.get('matches', [])
                        if not isinstance(anteriores, list):
                            raise ValueError('La respuesta no contiene una lista de partidos.')
                        st.session_state['soc_historico_v7'] = (codigo, anterior, anteriores)
                        st.success(f'Temporada {anterior}: {len(anteriores)} partidos recibidos.')
                    except ValueError as exc:
                        st.warning(f'No se pudo cargar la temporada {anterior}: {exc}')
                previos = st.session_state.get('soc_historico_v7')
                if previos and previos[:2] == (codigo, anterior):
                    finalizados_previos = _terminados(previos[2])
                    st.caption(f'Temporada {anterior}: {len(finalizados_previos)} partidos finalizados válidos.')
                    ids = {x.get('id') for x in datos_comparador if x.get('id') is not None}
                    for partido in finalizados_previos:
                        if partido.get('id') not in ids:
                            datos_comparador.append(dict(partido, _soc_temporada=anterior))
                            ids.add(partido.get('id'))
                else:
                    st.info('Aún no se ha cargado la temporada anterior. Puedes seguir con los datos actuales.')
            cuenta = {}
            for partido in _terminados(datos_comparador):
                t = partido.get('_soc_temporada', 'N/D')
                cuenta[t] = cuenta.get(t, 0) + 1
            st.caption('Partidos finalizados válidos por temporada: ' +
                       ', '.join(f'{t}: {n}' for t, n in sorted(cuenta.items())) if cuenta
                       else 'Todavía no hay partidos finalizados válidos.')
            _comparador_equipos(datos_comparador, temporada)
        else:
            st.info('La API no devolvió partidos para la competición y temporada elegidas.')
    if st.button('👥 Cargar equipos', key='soc_teams_v3'):
        try:
            data = _consulta(f'/competitions/{codigo}/teams', token, temporada)
            st.session_state['soc_equipos_v3'] = (codigo, temporada, data.get('teams', []))
            st.success(f"Equipos recibidos: {len(data.get('teams', []))}")
        except ValueError as exc:
            st.error(str(exc))
    teams = st.session_state.get('soc_equipos_v3')
    if teams and teams[:2] == (codigo, temporada):
        st.dataframe([{'Equipo': x.get('name', 'N/D'), 'País': x.get('area', {}).get('name', 'N/D')}
                      for x in teams[2]], hide_index=True, use_container_width=True)
    st.divider()
    st.caption('Córners y estadísticas individuales: pendientes de fuente verificada. No se muestran cifras inventadas.')


if __name__ == '__main__':
    mostrar_resumen_inteligente_soccer()

