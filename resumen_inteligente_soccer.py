"""Resumen Inteligente Soccer - Etapa 8, fuente football-data.org y CSV.
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
    st.subheader('🧪 Validación histórica · Etapa 8')
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

def _comparador_equipos(datos, temporada_actual=None):
    st.subheader('⚽ Comparador de equipos · Etapa 8')
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
    _panel_probabilidades(datos, izquierda, derecha, equipos[izquierda],
                           equipos[derecha], condicion_a, condicion_b, cantidad)
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
    st.subheader('📐 Probabilidades estadísticas · Etapa 8')
    st.caption('Distribución de Poisson ilustrativa. No utiliza cuotas, '
               'mercados ni recomendaciones de apuestas.')
    finalizados = _terminados(datos)
    serie_a = _historial_cronologico(datos, equipo_a, condicion_a)
    serie_b = _historial_cronologico(datos, equipo_b, condicion_b)
    recientes_a = serie_a[-ventana:]
    recientes_b = serie_b[-ventana:]
    if len(recientes_a) < 10 or len(recientes_b) < 10:
        st.warning('Muestra insuficiente para comparar probabilidades: '
                   'se requieren al menos 10 partidos por equipo con los filtros elegidos.')
        return
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
    st.caption('Etapa 8 · Probabilidades estadísticas · Historial y validación · Diseño móvil')
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
            st.subheader('📚 Historial ampliado · Etapa 8')
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
