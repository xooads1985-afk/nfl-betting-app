import html
"""Resumen Inteligente NFL 1.9.4: vista compacta y descriptiva para móvil."""
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
    # Unificar iniciales escritas con puntos: D.K. y DK -> dk.
    unidas = []
    i = 0
    while i < len(partes):
        if i + 1 < len(partes) and len(partes[i]) == len(partes[i + 1]) == 1:
            unidas.append(partes[i] + partes[i + 1])
            i += 2
        else:
            unidas.append(partes[i])
            i += 1
    return ' '.join(unidas)


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


# --- Extensión NFL: análisis descriptivo, sin alterar estimadores originales ---
def _ri_edge(proyeccion, referencia):
    if proyeccion is None or referencia is None or pd.isna(proyeccion) or pd.isna(referencia):
        return None
    return round(float(proyeccion) - float(referencia), 1)


def _ri_valor_visible(valor):
    """Normaliza cero negativo solamente al mostrarlo; no cambia cálculos."""
    if valor is None or pd.isna(valor):
        return 'N/D'
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        if float(valor) == 0 or (isinstance(valor, float) and abs(valor) < 0.05):
            return '0.0' if isinstance(valor, float) else '0'
    return str(valor)


def _ri_tarjetas(filas):
    """Presentación adaptable a móvil sin desplazamiento horizontal de tablas."""
    if not filas:
        st.info('N/D: faltan registros históricos suficientes.')
        return
    for fila in filas:
        etiqueta = fila.get('Estadística', fila.get('Jugador', 'Resultado'))
        detalles = [(clave, valor) for clave, valor in fila.items()
                    if clave not in ('Estadística', 'Jugador')]
        celdas = ''.join(
            '<div style="min-width:0;flex:1 1 76px;padding:3px 3px;">'
            '<div style="font-size:.72rem;color:#9ca3af;">{}</div>'
            '<div style="font-size:.94rem;font-weight:600;overflow-wrap:anywhere;">{}</div>'
            '</div>'.format(html.escape(str(clave)),
                            html.escape(_ri_valor_visible(valor)))
            for clave, valor in detalles
        )
        st.markdown(
            '<div style="border:1px solid #374151;border-radius:10px;'
            'padding:8px 10px;margin:5px 0;background:#161b24;">'
            '<div style="font-weight:700;font-size:1rem;margin-bottom:3px;'
            'overflow-wrap:anywhere;">{}</div>'
            '<div style="display:flex;flex-wrap:wrap;gap:0px 7px;">{}</div>'
            '</div>'.format(html.escape(str(etiqueta)), celdas),
            unsafe_allow_html=True
        )


def _ri_tabla(filas, nota=None):
    _ri_tarjetas(filas)
    st.caption(nota or 'Edge descriptivo = proyección − referencia histórica; no indica probabilidad ni precisión.')


def _ri_error(errores):
    if not errores:
        return None
    serie = pd.Series(errores, dtype='float64')
    return {'Partidos': len(serie), 'MAE': round(float(serie.abs().mean()), 1),
            'Sesgo': round(float(serie.mean()), 1)}


def _ri_validacion(resumen, titulo='📐 Validación histórica'):
    with st.expander(titulo, expanded=False):
        if resumen is None:
            st.info('No hay suficientes partidos previos para validar.')
        else:
            _ri_tarjetas([resumen])
            st.caption('MAE = error absoluto promedio. Sesgo = proyección − resultado. '
                       'Cada evaluación utiliza únicamente datos anteriores al partido evaluado.')


def _ri_validar_equipo(cal, equipo, temporada):
    d = _partidos(cal, equipo, temporada)
    errores = []
    fechas = pd.to_datetime(cal['gameday'], errors='coerce')
    for fila in d.itertuples(index=False):
        fecha = pd.to_datetime(fila.gameday, errors='coerce')
        if pd.isna(fecha):
            continue
        previo = cal.loc[fechas < fecha]
        estimado = _estimacion_puntos(previo, equipo, temporada, fila.Rival)
        if estimado is not None and pd.notna(fila.PF):
            errores.append(float(estimado) - float(fila.PF))
    return _ri_error(errores)


def _ri_estimar_metrica(d, columna):
    serie = pd.to_numeric(d.sort_values('Semana')[columna], errors='coerce').dropna()
    if len(serie) < 3:
        return None, None, len(serie)
    proyeccion = max(0.0, 0.70 * float(serie.tail(5).mean()) + 0.30 * float(serie.mean()))
    referencia = float(serie.tail(5).mean())
    return proyeccion, referencia, len(serie)


def _ri_validar_jugador(d, columna):
    ordenado = d.sort_values('Semana')
    errores = []
    for i in range(1, len(ordenado)):
        pred, _, _ = _ri_estimar_metrica(ordenado.iloc[:i], columna)
        real = pd.to_numeric(ordenado.iloc[i][columna], errors='coerce')
        if pred is not None and pd.notna(real):
            errores.append(float(pred) - float(real))
    return _ri_error(errores)


def _ri_panel_jugador(d, metricas):
    filas = []
    for nombre in _metricas_posicion(d, metricas):
        proy, ref, n = _ri_estimar_metrica(d, metricas[nombre])
        if proy is None:
            continue
        filas.append({'Estadística': nombre, 'Proy.': round(proy, 1),
                      'Ref.': round(ref, 1), 'Edge': _ri_edge(proy, ref), 'N': n})
    st.markdown('**📊 Proyecciones y Edge descriptivo por estadística**')
    _ri_tabla(filas, 'Ref. = promedio de hasta 5 partidos recientes; N = registros válidos. '
              'Las métricas adicionales usan ponderación histórica 70/30. '
              'La proyección principal de yardas conserva su función original.')
    with st.expander('📐 Validación histórica por estadística', expanded=False):
        validaciones = []
        for nombre in _metricas_posicion(d, metricas):
            resumen = _ri_validar_jugador(d, metricas[nombre])
            if resumen:
                validaciones.append({'Estadística': nombre, **resumen})
        _ri_tabla(validaciones, 'Evaluación cronológica de las nuevas proyecciones; '
                  'no constituye validación independiente fuera de muestra.')


@st.cache_data(ttl=21600, show_spinner=False)
def _ri_cargar_puntos_por_cuarto(temporada):
    """Extrae marcadores parciales reales del play-by-play NFLverse."""
    import nflreadpy as nfl
    bruto = nfl.load_pbp([int(temporada)])
    pbp = bruto.to_pandas() if hasattr(bruto, "to_pandas") else pd.DataFrame(bruto)
    pbp.columns = [str(c).lower().strip() for c in pbp.columns]
    requeridas = {"game_id", "qtr", "total_home_score", "total_away_score"}
    faltan = requeridas - set(pbp.columns)
    if faltan:
        raise ValueError("Faltan columnas de play-by-play: " + ", ".join(sorted(faltan)))

    pbp = pbp.loc[pd.to_numeric(pbp["qtr"], errors="coerce").between(1, 4),
                  ["game_id", "qtr", "total_home_score", "total_away_score"]].copy()
    for columna in ("qtr", "total_home_score", "total_away_score"):
        pbp[columna] = pd.to_numeric(pbp[columna], errors="coerce")
    pbp = pbp.dropna(subset=["game_id", "qtr", "total_home_score", "total_away_score"])
    if pbp.empty:
        return pd.DataFrame(columns=["game_id"] +
                            [f"{lado}_q{i}" for lado in ("home", "away") for i in range(1, 5)])

    # Los marcadores de NFLverse son acumulados. El máximo de cada cuarto
    # representa su marcador al cierre, no los puntos anotados en ese cuarto.
    finales = (pbp.groupby(["game_id", "qtr"], as_index=False)
               [["total_home_score", "total_away_score"]].max())
    partidos = []
    for game_id, grupo in finales.groupby("game_id", sort=False):
        por_cuarto = grupo.set_index("qtr")
        if not all(i in por_cuarto.index for i in (1, 2, 3, 4)):
            continue
        fila = {"game_id": game_id}
        valido = True
        for lado, campo in (("home", "total_home_score"),
                            ("away", "total_away_score")):
            prev = 0.0
            for i in range(1, 5):
                acumulado = float(por_cuarto.loc[i, campo])
                parcial = acumulado - prev
                if parcial < 0:
                    valido = False
                    break
                fila[f"{lado}_q{i}"] = parcial
                prev = acumulado
        if valido:
            partidos.append(fila)
    return pd.DataFrame(partidos, columns=["game_id"] +
                        [f"{lado}_q{i}" for lado in ("home", "away") for i in range(1, 5)])


def _ri_periodos(cal, equipo, temporada, rival, total_proyectado):
    """Distribuye la proyección total según los puntos históricos por cuarto."""
    propios = _partidos(cal, equipo, temporada)
    contrarios = _partidos(cal, rival, temporada)
    if len(propios) < 3 or len(contrarios) < 3:
        return []
    nombres = [("Q1", 1), ("Q2", 2), ("Q3", 3), ("Q4", 4)]
    parciales = []
    for nombre, i in nombres:
        hc, ac = f"home_q{i}", f"away_q{i}"
        if hc not in cal or ac not in cal:
            return []
        es_casa = propios.home_team.eq(equipo)
        rival_casa = contrarios.home_team.eq(rival)
        anotados = pd.to_numeric(propios[hc].where(es_casa, propios[ac]), errors="coerce")
        permitidos = pd.to_numeric(contrarios[ac].where(rival_casa, contrarios[hc]), errors="coerce")
        a, b = anotados.dropna(), permitidos.dropna()
        if len(a) < 3 or len(b) < 3:
            return []
        base = max(0.0, float(.50 * a.tail(5).mean() +
                              .25 * a.mean() + .25 * b.tail(5).mean()))
        referencia = float(a.tail(5).mean())
        parciales.append((nombre, base, referencia))

    suma = sum(x[1] for x in parciales)
    if suma <= 0:
        return []
    # La suma de Q1-Q4 coincide con la proyección general ya existente.
    escala = float(total_proyectado) / suma
    valores = [(nombre, base * escala, ref) for nombre, base, ref in parciales]
    for nombre, indices in (("1.ª mitad", (0, 1)), ("2.ª mitad", (2, 3)),
                            ("Partido completo", (0, 1, 2, 3))):
        valores.append((nombre, sum(valores[i][1] for i in indices),
                        sum(valores[i][2] for i in indices)))
    return [{"Período": nombre, "Proy.": round(proy, 1),
             "Ref.": round(ref, 1), "Edge": _ri_edge(proy, ref)}
            for nombre, proy, ref in valores]



# Registro auxiliar NFL: no modifica las funciones de proyección existentes.
def _ri194_registros_ruta():
    from pathlib import Path
    return Path('nfl_proyecciones_registradas.json')


def _ri194_leer_registros():
    import json
    try:
        datos = json.loads(_ri194_registros_ruta().read_text(encoding='utf-8'))
        return datos if isinstance(datos, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _ri194_escribir_registros(datos):
    import json, os, tempfile
    ruta = _ri194_registros_ruta()
    temporal = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=str(ruta.parent),
                                         prefix='.nfl_reg_', suffix='.tmp', delete=False) as archivo:
            temporal = archivo.name
            json.dump(datos, archivo, ensure_ascii=False, indent=2, allow_nan=False)
        os.replace(temporal, ruta)
        return True
    except (OSError, TypeError, ValueError):
        return False
    finally:
        if temporal and os.path.exists(temporal):
            try:
                os.unlink(temporal)
            except OSError:
                pass


def _ri194_registro_partido(cal, temporada, a, b, fa, fb, combinados, pa, pb, ra, rb):
    import datetime as dt
    import json
    # Se exige que los equipos tengan el mismo encuentro pendiente.
    pendientes = cal.loc[(cal.home_team.eq(a) & cal.away_team.eq(b)) |
                         (cal.home_team.eq(b) & cal.away_team.eq(a))].copy()
    pendientes = pendientes.loc[pendientes.home_score.isna() & pendientes.away_score.isna()]
    pendientes = pendientes.sort_values('gameday')
    if pendientes.empty:
        return None
    juego = pendientes.iloc[0]
    fecha = pd.to_datetime(juego['gameday'], errors='coerce')
    if pd.isna(fecha):
        return None
    local, visita = str(juego.home_team), str(juego.away_team)
    filas = {a: fa, b: fb}
    pred = {a: pa, b: pb}
    refs = {a: ra, b: rb}
    # La fecha del calendario NFL puede carecer de hora; no se certifica el inicio.
    return {'id': str(juego.game_id), 'temporada': int(temporada),
            'fecha_calendario': str(juego.gameday), 'local': local, 'visitante': visita,
            'registrado_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
            'verificacion_preinicio': 'No verificable con fecha de calendario sin hora confirmada',
            'version': '1.9.4 + registro',
            'proyeccion': {'local': round(pred[local], 1), 'visitante': round(pred[visita], 1),
                           'total': round(pa+pb, 1)},
            'referencia': {'local': round(refs[local], 1), 'visitante': round(refs[visita], 1),
                           'total': round(ra+rb, 1)},
            'periodos': {equipo: {f['Período']: {'proyeccion': f['Proy.'], 'referencia': f['Ref.'],
                         'edge': f['Edge']} for f in filas[equipo]} for equipo in (local, visita)},
            'combinados': {f['Período']: {'proyeccion': f['Proy.'], 'referencia': f['Ref.'],
                          'edge': f['Edge']} for f in combinados}}


def _ri194_guardar_proyeccion(registro):
    import datetime as dt
    if not registro:
        st.info('No se encontró un partido pendiente con datos completos para registrar.')
        return
    fecha = pd.to_datetime(registro['fecha_calendario'], errors='coerce', utc=True)
    if pd.isna(fecha):
        st.warning('No hay fecha verificable; no se guardó el registro.')
        return
    # Fecha sola: impedir el guardado a partir del día posterior; sin hora, no afirmar preinicio.
    if fecha.date() < dt.datetime.now(dt.timezone.utc).date():
        st.warning('La fecha del encuentro ya pasó; no se permite registrar una nueva proyección original.')
        return
    registros = _ri194_leer_registros()
    clave = registro['id']
    if clave in registros:
        st.info('Este encuentro ya tiene una primera proyección guardada. No se sobrescribe.')
        return
    registros[clave] = registro
    if _ri194_escribir_registros(registros):
        st.success('Proyección guardada sin modificar las fórmulas.')
        st.caption('La hora exacta de inicio no se verifica con este calendario. Descarga el respaldo JSON.')
    else:
        st.error('No se pudo escribir el registro; no se confirma el guardado.')


def _ri194_panel_seguimiento(cal):
    import json
    with st.expander('📚 Seguimiento y respaldo de proyecciones NFL', expanded=False):
        registros = _ri194_leer_registros()
        respaldo = json.dumps(registros, ensure_ascii=False, indent=2).encode('utf-8')
        st.download_button('📥 Descargar respaldo JSON', respaldo,
                           file_name='nfl_proyecciones_respaldo.json', mime='application/json',
                           key='ri194_descargar_respaldo')
        archivo = st.file_uploader('Restaurar respaldo JSON (sin sobrescribir registros existentes)',
                                   type=['json'], key='ri194_restaurar_json')
        if archivo is not None and st.button('Restaurar registros válidos', key='ri194_restaurar_btn'):
            try:
                entrada = json.loads(archivo.getvalue().decode('utf-8'))
                if not isinstance(entrada, dict):
                    raise ValueError('Formato JSON inválido')
                nuevos = {str(k): v for k, v in entrada.items()
                          if isinstance(v, dict) and str(v.get('id')) == str(k)
                          and all(x in v for x in ('local', 'visitante', 'proyeccion', 'fecha_calendario'))}
                if len(nuevos) != len(entrada):
                    st.warning('Algunos registros no tienen el formato requerido y se omitieron.')
                fusion = {**nuevos, **registros}  # los existentes tienen prioridad
                if _ri194_escribir_registros(fusion):
                    st.success(f'Se incorporaron {len(fusion)-len(registros)} registros nuevos.')
                    registros = fusion
                else:
                    st.error('No se pudo restaurar el respaldo.')
            except (UnicodeDecodeError, ValueError, TypeError) as exc:
                st.error(f'No se pudo leer el respaldo: {exc}')
        st.caption('Streamlit Cloud puede borrar el almacenamiento local al reiniciar o redesplegar. '
                   'Descarga el respaldo después de guardar cada encuentro.')
        if not registros:
            st.info('Todavía no hay proyecciones registradas.')
            return
        filas = []
        for ident, r in registros.items():
            actual = cal.loc[cal.game_id.astype(str).eq(str(ident))]
            estado, real, error = 'Pendiente o fuera del calendario', None, None
            if not actual.empty:
                juego = actual.iloc[0]
                if pd.notna(juego.home_score) and pd.notna(juego.away_score):
                    real = float(juego.home_score) + float(juego.away_score)
                    esperado = r.get('proyeccion', {}).get('total')
                    if isinstance(esperado, (int, float)):
                        error = round(float(esperado)-real, 1)
                    estado = 'Finalizado (marcador completo, posible tiempo extra)'
            filas.append({'Fecha': str(r.get('fecha_calendario',''))[:10],
                          'Partido': f"{r.get('visitante','?')} @ {r.get('local','?')}",
                          'Proyección total': r.get('proyeccion',{}).get('total'),
                          'Observado completo': real, 'Error firmado': error,
                          'Estado': estado, 'Registrado UTC': r.get('registrado_utc','')})
        tabla = pd.DataFrame(filas)
        st.dataframe(tabla, hide_index=True, use_container_width=True)
        evaluados = pd.to_numeric(tabla['Error firmado'], errors='coerce').dropna()
        if not evaluados.empty:
            c1, c2 = st.columns(2)
            c1.metric('MAE · total completo', f'{evaluados.abs().mean():.1f} pts')
            c2.metric('Sesgo · total completo', f'{evaluados.mean():+.1f} pts')
            st.caption('Comparación de total completo: los resultados reales pueden incluir tiempo extra; '
                       'no se equiparan automáticamente con proyecciones de cuartos reglamentarios.')

def _ri_total_enfrentamiento(cal, temporada, elegidos):
    if len(elegidos) != 2:
        return
    a, b = elegidos
    prox_a = _proximo_partido(cal, a, temporada)
    prox_b = _proximo_partido(cal, b, temporada)
    if not prox_a or not prox_b or prox_a['rival'] != b or prox_b['rival'] != a:
        return
    pa = _estimacion_puntos(cal, a, temporada, b)
    pb = _estimacion_puntos(cal, b, temporada, a)
    if pa is None or pb is None:
        return
    da, db = _partidos(cal, a, temporada), _partidos(cal, b, temporada)
    ra, rb = float(da.PF.tail(5).mean()), float(db.PF.tail(5).mean())
    st.markdown('**🏈 Proyección del enfrentamiento**')
    _ri_tabla([{'Equipo': a, 'Proy.': round(pa, 1), 'Ref.': round(ra, 1), 'Edge': _ri_edge(pa, ra)},
               {'Equipo': b, 'Proy.': round(pb, 1), 'Ref.': round(rb, 1), 'Edge': _ri_edge(pb, rb)},
               {'Equipo': 'TOTAL', 'Proy.': round(pa + pb, 1),
                'Ref.': round(ra + rb, 1), 'Edge': _ri_edge(pa + pb, ra + rb)}])
    st.markdown('**⏱️ Cuartos y mitades**')
    try:
        historicos = _ri_cargar_puntos_por_cuarto(temporada)
        datos = cal.merge(historicos, on="game_id", how="left", validate="one_to_one")
        # Solo se usan encuentros con marcador final publicado. Los partidos
        # con tiempo extra no se mezclan con los cuatro cuartos reglamentarios.
        for lado, marcador in (("home", "home_score"), ("away", "away_score")):
            cols = [f"{lado}_q{i}" for i in range(1, 5)]
            diferencia = (datos[cols].sum(axis=1, min_count=4) -
                          pd.to_numeric(datos[marcador], errors="coerce")).abs()
            datos.loc[diferencia.gt(.01), cols] = float("nan")
        fa = _ri_periodos(datos, a, temporada, b, pa)
        fb = _ri_periodos(datos, b, temporada, a, pb)
    except Exception as exc:
        st.info("N/D: no se pudieron consultar los marcadores históricos por cuarto.")
        st.caption(f"Detalle técnico: {type(exc).__name__}: {exc}")
        return
    if not fa or not fb:
        st.info("N/D: no hay suficientes partidos completos con datos "
                "verificables por cuarto para ambos equipos.")
        return
    for nombre, filas in ((a, fa), (b, fb)):
        st.markdown(f"**{nombre} · puntos por período**")
        _ri_tabla(filas)
    combinados = []
    for x, y in zip(fa, fb):
        p = x["Proy."] + y["Proy."]
        r = x["Ref."] + y["Ref."]
        combinados.append({"Período": x["Período"], "Proy.": round(p, 1),
                           "Ref.": round(r, 1), "Edge": _ri_edge(p, r)})
    st.markdown("**Ambos equipos · puntos combinados**")
    _ri_tabla(combinados)
    with st.expander('💾 Guardar proyección previa al partido', expanded=False):
        st.caption('Conserva la primera proyección; el calendario puede no incluir la hora exacta de inicio.')
        registro = _ri194_registro_partido(cal, temporada, a, b, fa, fb, combinados, pa, pb, ra, rb)
        if st.button('Guardar proyección original', key='ri194_guardar_proyeccion'):
            _ri194_guardar_proyeccion(registro)
    st.caption("Distribución orientativa basada en anotación y puntos permitidos "
               "por cuarto; ajustada a las proyecciones generales ya existentes. "
               "No equivale a resultados garantizados.")

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
                ref = float(d.PF.tail(5).mean())
                _ri_tabla([{'Estadística': 'Puntos', 'Proy.': round(estimado, 1),
                            'Ref.': round(ref, 1), 'Edge': _ri_edge(estimado, ref)}])
                _ri_validacion(_ri_validar_equipo(cal, equipo, temporada))
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
    candidatos = completo[~completo.ID.isin(guardados)]
    if pos != 'Todas':
        candidatos = candidatos[candidatos['Posición'].str.upper().eq(pos)]
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
        st.caption('No hay jugadores disponibles para esta posición.')

    seleccionados = st.session_state[clave]
    if seleccionados:
        st.caption(f'Seleccionados: {len(seleccionados)} de 3')
        for ident in seleccionados:
            d = semanal[semanal.ID.eq(ident)].sort_values('Semana')
            if d.empty:
                continue
            # Encabezado compacto: nombre a la izquierda y botón a la derecha.
            # El CSS mantiene ambas columnas en una fila también en móvil.
            with st.container(key=f'ri194_fila_{seleccionados.index(ident)}'):
                nombre_col, quitar_col = st.columns([5, 1], gap='small', vertical_alignment='center')
                with nombre_col:
                    st.markdown(f'**{_etiqueta(completo, ident)}**')
                with quitar_col:
                    if st.button('✕', key=f'ri194_quitar_{ident}',
                                 help='Quitar jugador', use_container_width=False):
                        st.session_state[clave] = [x for x in seleccionados if x != ident]
                        st.rerun()
            _ficha(d, metricas, cal, temporada, snaps)
            _ri_panel_jugador(d, metricas)
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
    nivel, detalle = _participacion(d, snaps)
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
        # Una sola tabla de texto compacta evita grandes espacios verticales
        # entre llamadas consecutivas a st.markdown en pantallas pequeñas.
        import html
        renglones = []
        for fila in filas:
            promedio = fila['Promedio últimos 5']
            valor = f'{promedio:g}' if promedio is not None else 'N/D'
            etiqueta = html.escape(str(fila['Estadística']))
            renglones.append(
                f'<div style="margin:0;padding:2px 0;line-height:1.35;">'
                f'<strong>{etiqueta}</strong>: {fila["Total temporada"]:g} · {valor}</div>'
            )
        st.markdown(''.join(renglones), unsafe_allow_html=True)

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
    _ri_tarjetas(filas)
    st.caption('Promedios de hasta cinco partidos registrados. Sin gráficas.')

def mostrar_resumen_inteligente_nfl():
    st.header('🏈 Resumen Inteligente NFL 1.9.4 · Edge ampliado')
    st.markdown("""
    <style>
    /* Solo los encabezados de jugadores: conservar la fila en pantallas estrechas. */
    [class*="st-key-ri194_fila_"] [data-testid="stHorizontalBlock"] {
        flex-wrap: nowrap !important;
        align-items: center !important;
        gap: 0.35rem !important;
    }
    [class*="st-key-ri194_fila_"] [data-testid="stColumn"]:first-child {
        flex: 1 1 auto !important;
        min-width: 0 !important;
        width: auto !important;
    }
    [class*="st-key-ri194_fila_"] [data-testid="stColumn"]:last-child {
        flex: 0 0 auto !important;
        min-width: 2.5rem !important;
        width: auto !important;
    }
    [class*="st-key-ri194_fila_"] [data-testid="stColumn"]:last-child button {
        min-height: 2.25rem;
        padding: 0.2rem 0.65rem;
    }
    </style>
    """, unsafe_allow_html=True)
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
    _ri_total_enfrentamiento(juegos, temporada, elegidos)
    _ri194_panel_seguimiento(juegos)
    with st.expander('⭐ 2. Jugadores', expanded=False):
        semanal, metricas, seleccionados = _jugadores(temporada, elegidos, juegos)
    with st.expander('🔎 3. Comparación de jugadores', expanded=False):
        _comparar(semanal, metricas, seleccionados)
