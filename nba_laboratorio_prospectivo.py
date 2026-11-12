"""Laboratorio prospectivo NBA. Auxiliar: no altera modelos ni registro principal."""
from datetime import datetime, timezone
import json
import hashlib
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import numpy as np
import pandas as pd
import streamlit as st
from nba_lab_motor_offline import (
    _nba_lab_ml_caracteristicas, _nba_lab_ml_entrenar,
    _nba_lab_ml_predecir, _nba_lab_modelo_c,
)

TABLA = 'nba_laboratorio_prospectivo'
MODELOS = ('Base', 'Modelo C', 'Ensemble')


def _credenciales():
    url = str(st.secrets.get('SUPABASE_URL', '')).rstrip('/')
    key = str(st.secrets.get('SUPABASE_SECRET_KEY', ''))
    if not url.startswith('https://') or not key:
        raise RuntimeError('Faltan credenciales de Supabase en Streamlit Secrets.')
    return url, key


def _consulta(method, query='', payload=None, prefer=None):
    url, key = _credenciales()
    headers = {'apikey': key, 'Authorization': 'Bearer ' + key,
               'Content-Type': 'application/json', 'Accept': 'application/json'}
    if prefer:
        headers['Prefer'] = prefer
    request = Request(url + '/rest/v1/' + TABLA + query,
                      data=json.dumps(payload, allow_nan=False).encode() if payload is not None else None,
                      headers=headers, method=method)
    try:
        with urlopen(request, timeout=20) as response:
            raw = response.read()
            return json.loads(raw) if raw else []
    except HTTPError as exc:
        raise RuntimeError(f'Supabase HTTP {exc.code}; verifica que exista la tabla y sus permisos.') from exc
    except (URLError, TimeoutError) as exc:
        raise RuntimeError('No se pudo contactar Supabase.') from exc


def registros():
    salida = []
    offset = 0
    while True:
        q = '?' + urlencode({'select': 'partido_id,modelo,equipo,proyeccion,registrado_utc,inicio_utc,version',
                              'order': 'registrado_utc.asc', 'limit': 500, 'offset': offset})
        lote = _consulta('GET', q)
        salida.extend(lote)
        if len(lote) < 500:
            break
        offset += 500
    return salida


def calcular(historico, juego):
    """Solo historial previo a la hora del encuentro. Sin resultado objetivo futuro."""
    fecha = pd.to_datetime(juego['fecha_utc'], utc=True, errors='coerce')
    if pd.isna(fecha) or fecha <= pd.Timestamp.now(tz='UTC'):
        raise ValueError('Solo se admiten encuentros futuros con fecha verificable.')
    datos = historico.copy()
    datos['_fecha_ml'] = pd.to_datetime(datos['fecha_utc'], utc=True, errors='coerce')
    datos = datos.loc[datos['_fecha_ml'].lt(fecha) & datos['finalizado'].eq(True)].dropna(
        subset=['puntos_local', 'puntos_visitante', '_fecha_ml']).sort_values('_fecha_ml')
    if len(datos) < 20:
        raise ValueError('No hay suficiente historial anterior al encuentro.')
    # Entrenar solo con ejemplos históricos cuyas variables usan juegos anteriores.
    entrenamiento = []
    for anterior in datos.to_dict('records'):
        entrenamiento.extend(_nba_lab_ml_caracteristicas(datos, anterior))
    if len(entrenamiento) < 24:
        raise ValueError('Faltan ejemplos históricos válidos para entrenar Ensemble.')
    motor = _nba_lab_ml_entrenar([r['x'] for r in entrenamiento], [r['real'] for r in entrenamiento])
    if not motor:
        raise ValueError('No se pudo entrenar Ensemble.')
    # La función histórica requiere campos de marcador para formar su estructura;
    # estos valores provisionales nunca entran en las características ni se guardan.
    objetivo = dict(juego)
    objetivo['puntos_local'] = np.nan
    objetivo['puntos_visitante'] = np.nan
    vector = _nba_lab_ml_caracteristicas(datos, objetivo)
    if len(vector) != 2:
        raise ValueError('Faltan antecedentes de uno de los equipos.')
    ajustes = {'forma': True, 'sede': True, 'descanso': True, 'pace': False,
               'fuerza': True, 'regresion': True}
    modelo_c = _nba_lab_modelo_c(datos, objetivo, ajustes)
    if modelo_c is None:
        raise ValueError('Modelo C no dispone de datos suficientes.')
    salida = {}
    for fila in vector:
        predicciones = _nba_lab_ml_predecir(motor, fila['x'], fila['base'], fila['n'], fila['liga'])
        ensemble = predicciones.get('Ensemble')
        if ensemble is None or not np.isfinite(ensemble):
            raise ValueError('Ensemble no generó una predicción válida.')
        salida[fila['equipo']] = {
            'Base': round(float(fila['base']), 3),
            'Modelo C': round(float(modelo_c[fila['equipo']]['pred']), 3),
            'Ensemble': round(float(ensemble), 3),
        }
    return salida


def guardar(juego, pronosticos):
    fecha = pd.to_datetime(juego['fecha_utc'], utc=True, errors='coerce')
    if pd.isna(fecha) or fecha <= pd.Timestamp.now(tz='UTC'):
        raise ValueError('El encuentro ya comenzó o carece de fecha válida.')
    instante = datetime.now(timezone.utc).isoformat()
    filas = []
    for equipo, valores in pronosticos.items():
        for modelo in MODELOS:
            filas.append({'partido_id': str(juego['id']), 'equipo': equipo, 'modelo': modelo,
                          'proyeccion': valores[modelo], 'inicio_utc': fecha.isoformat(),
                          'registrado_utc': instante, 'version': 'laboratorio-prospectivo-1.0'})
    # El índice único impide sobrescribir cualquier predicción original.
    insertados = _consulta('POST', '?on_conflict=partido_id,equipo,modelo', filas,
                           prefer='resolution=ignore-duplicates,return=representation')
    return len(insertados)


def evaluar(historial, guardados):
    """Evaluar únicamente registros anteriores al inicio, con resultado reglamentario."""
    from modulo_nba import cargar_detalle
    from resumen_inteligente_nba import _puntos_periodos
    columnas = ['Partido', 'Equipo', 'Modelo', 'Proyección', 'Real (reglamentario)', 'Error']
    if historial is None or historial.empty:
        return pd.DataFrame(columns=columnas)
    por_id = {str(r['id']): r for r in historial.to_dict('records')}
    cache_periodos = {}
    evaluados = []
    vistos = set()
    for registro in guardados:
        try:
            pid = str(registro['partido_id'])
            equipo = str(registro['equipo'])
            modelo = str(registro['modelo'])
            llave = (pid, equipo, modelo)
            if llave in vistos or modelo not in (*MODELOS, 'Pace + Eficiencia'):
                continue
            partido = por_id.get(pid)
            if partido is None or not bool(partido.get('finalizado')):
                continue
            if equipo not in (str(partido['local']), str(partido['visitante'])):
                continue
            inicio = pd.to_datetime(partido['fecha_utc'], utc=True, errors='coerce')
            inicio_guardado = pd.to_datetime(registro['inicio_utc'], utc=True, errors='coerce')
            registrado = pd.to_datetime(registro['registrado_utc'], utc=True, errors='coerce')
            if pd.isna(inicio) or pd.isna(inicio_guardado) or pd.isna(registrado):
                continue
            if inicio != inicio_guardado or registrado >= inicio:
                continue
            proyeccion = float(registro['proyeccion'])
            if not np.isfinite(proyeccion):
                continue
            if pid not in cache_periodos:
                cache_periodos[pid] = _puntos_periodos(cargar_detalle(pid))
            periodos = cache_periodos[pid].get(equipo)
            if not isinstance(periodos, dict) or not all(k in periodos for k in (1, 2, 3, 4)):
                continue
            real = sum(float(periodos[k]) for k in (1, 2, 3, 4))
            if not np.isfinite(real):
                continue
            vistos.add(llave)
            evaluados.append({'Partido': pid, 'Equipo': equipo, 'Modelo': modelo,
                              'Proyección': proyeccion, 'Real (reglamentario)': real,
                              'Error': proyeccion - real})
        except (ValueError, TypeError, KeyError, RuntimeError, OverflowError):
            continue
    return pd.DataFrame(evaluados, columns=columnas)


def comparar_cuatro_modelos(tabla):
    """Misma muestra (partido, equipo) para los cuatro modelos; sin duplicados."""
    columnas = ['Modelo', 'N', 'MAE', 'RMSE', 'Sesgo']
    if tabla is None or tabla.empty:
        return pd.DataFrame(columns=columnas), pd.DataFrame()
    modelos = [*MODELOS, 'Pace + Eficiencia']
    t = tabla.loc[tabla['Modelo'].isin(modelos)].copy()
    # No incluir errores ni resultados no finitos en la muestra comparable.
    for campo in ('Error', 'Real (reglamentario)', 'Proyección'):
        t[campo] = pd.to_numeric(t[campo], errors='coerce')
    t = t.loc[np.isfinite(t[['Error', 'Real (reglamentario)', 'Proyección']]).all(axis=1)]
    # El error debe corresponder a la proyección y al resultado registrado.
    t = t.loc[np.isclose(t['Error'], t['Proyección'] - t['Real (reglamentario)'], atol=1e-6)]
    if t.duplicated(['Partido', 'Equipo', 'Modelo']).any():
        t = t.drop_duplicates(['Partido', 'Equipo', 'Modelo'], keep=False)
    completos = t.groupby(['Partido', 'Equipo'])['Modelo'].nunique()
    completos = completos[completos.eq(len(modelos))].index
    if len(completos) == 0:
        return pd.DataFrame(columns=columnas), pd.DataFrame(columns=t.columns)
    t = t.set_index(['Partido', 'Equipo']).loc[completos].reset_index()
    # Rechazar resultados reales discrepantes para el mismo partido/equipo.
    consistentes = t.groupby(['Partido', 'Equipo'])['Real (reglamentario)'].nunique()
    t = t.set_index(['Partido', 'Equipo']).loc[consistentes[consistentes.eq(1)].index].reset_index()
    if t.empty:
        return pd.DataFrame(columns=columnas), pd.DataFrame(columns=tabla.columns)
    resumen = t.groupby('Modelo').agg(
        N=('Error', 'size'), MAE=('Error', lambda x: x.abs().mean()),
        RMSE=('Error', lambda x: np.sqrt(np.mean(x ** 2))),
        Sesgo=('Error', 'mean')).reindex(modelos).reset_index()
    return resumen, t

def mostrar():
    # Las dependencias del resumen estable se importan solo al evaluar resultados.
    from datetime import date, timedelta

    st.title('🧪 Laboratorio prospectivo NBA')
    st.info("VERSIÓN DE PRUEBA: CARGA POR BLOQUES")
    st.caption('Página auxiliar dentro de la misma app. No modifica el resumen ni sus registros originales.')
    hoy = date.today()

    incluir_pasada = st.checkbox('Incluir temporada anterior para entrenar', value=False)
    inicio = date(2025, 10, 21) if incluir_pasada else date(2026, 10, 20)
    clave_periodo = (inicio.isoformat(), hoy.isoformat())
    clave = 'nba_prospectivo_carga_bloques_v2'
    estado = st.session_state.get(clave)
    if not isinstance(estado, dict) or estado.get('periodo') != clave_periodo:
        estado = {'periodo': clave_periodo, 'siguiente': inicio,
                  'fragmentos': [], 'incidencias': [], 'futuros': pd.DataFrame(),
                  'completo': False}
        st.session_state[clave] = estado

    if st.button('📥 Cargar siguiente bloque (14 días)',
                 disabled=estado['completo'], use_container_width=True):
        desde = estado['siguiente']
        hasta = min(desde + timedelta(days=13), hoy)
        try:
            # Una sola petición de rango por pulsación; no recorrer la temporada
            # completa en un único ciclo de Streamlit.
            from modulo_nba import cargar_partidos
            with st.spinner(f'Consultando del {desde} al {hasta}...'):
                bloque, errores = cargar_partidos(desde.isoformat(), hasta.isoformat())
            if bloque is not None and not bloque.empty:
                estado['fragmentos'].append(bloque)
            estado['incidencias'].extend(
                f'{desde} a {hasta}: {e}' for e in (errores or []))
            estado['siguiente'] = hasta + timedelta(days=1)
            estado['completo'] = estado['siguiente'] > hoy
        except Exception as exc:
            # No avanzar el cursor: se puede reintentar sin perder los bloques previos.
            st.error(f'Bloque {desde} a {hasta}: {type(exc).__name__}: {exc}')

    total_dias = (hoy - inicio).days + 1
    dias_cargados = min(total_dias, max(0, (estado['siguiente'] - inicio).days))
    st.progress(dias_cargados / max(1, total_dias))
    st.caption(f'Cobertura consultada: {dias_cargados}/{total_dias} días. '
               'Cada pulsación recupera como máximo 14 días; se conserva el avance en esta sesión.')
    if estado['incidencias']:
        st.warning(f'Consultas con incidencias: {len(estado["incidencias"])}. '
                   'No se inventan partidos faltantes.')
        with st.expander('Ver incidencias'):
            st.write(estado['incidencias'][-30:])
    if not estado['completo']:
        st.info('El historial de los tres modelos aún está incompleto; Pace y la validación siguen accesibles.')

    if not estado.get('calendario_consultado'):
        if st.button('📅 Consultar próximos partidos', use_container_width=True):
            try:
                from modulo_nba import cargar_partidos
                with st.spinner('Consultando próximos 14 días...'):
                    futuros, errores = cargar_partidos(
                        hoy.isoformat(), (hoy + timedelta(days=14)).isoformat())
                estado['futuros'] = futuros if futuros is not None else pd.DataFrame()
                estado['calendario_consultado'] = True
                estado['incidencias'].extend(f'Calendario: {e}' for e in (errores or []))
            except Exception as exc:
                st.error(f'Calendario: {type(exc).__name__}: {exc}')
        if not estado.get('calendario_consultado'):
            st.info('Consulta el calendario cuando quieras calcular proyecciones futuras.')

    historico = pd.concat(estado['fragmentos'], ignore_index=True) if estado['fragmentos'] else pd.DataFrame()
    if 'id' in historico:
        historico['id'] = historico['id'].astype(str)
        historico = historico.drop_duplicates('id', keep='last')
    # Auditoría experimental de posesiones: aislada de las proyecciones guardadas.
    from nba_pace_panel import mostrar_auditoria_pace
    mostrar_auditoria_pace(historico)

    # Cuarto modelo experimental: historial cargado por CSV, sin alterar el histórico ESPN.
    st.subheader('Pace + Eficiencia · registro prospectivo')
    archivo_pace = st.file_uploader('Cargar historial pace CSV (160 partidos)', type=['csv'], key='nba_lab_pace_csv_v1')
    historial_pace = pd.DataFrame()
    huella_pace = None
    if archivo_pace is not None:
        try:
            contenido_csv = archivo_pace.getvalue()
            huella_pace = hashlib.sha256(contenido_csv).hexdigest()
            historial_pace = pd.read_csv(archivo_pace)
            columnas = {'partido_id', 'fecha_utc', 'local', 'visitante', 'finalizado',
                        'puntos_local', 'puntos_visitante', 'posesiones_local',
                        'posesiones_visitante', 'minutos_partido'}
            faltantes = columnas.difference(historial_pace.columns)
            if faltantes:
                raise ValueError('Faltan columnas: ' + ', '.join(sorted(faltantes)))
            historial_pace['partido_id'] = historial_pace['partido_id'].astype(str)
            historial_pace['finalizado'] = historial_pace['finalizado'].astype(str).str.lower().eq('true')
            fechas_pace = pd.to_datetime(historial_pace['fecha_utc'], utc=True, errors='coerce')
            if fechas_pace.isna().any() or not historial_pace['finalizado'].all():
                raise ValueError('Hay fechas inválidas o partidos sin finalizar en el CSV.')
            for columna in ('puntos_local', 'puntos_visitante', 'posesiones_local', 'posesiones_visitante', 'minutos_partido'):
                valores = pd.to_numeric(historial_pace[columna], errors='coerce')
                if valores.isna().any() or (valores <= 0).any():
                    raise ValueError(f'Valores faltantes o no positivos en {columna}.')
                historial_pace[columna] = valores
            if historial_pace['partido_id'].duplicated().any():
                st.warning('Se encontraron IDs duplicados; se conserva la primera aparición.')
            historial_pace = historial_pace.drop_duplicates('partido_id', keep='first')
            st.success(f'Historial Pace: {len(historial_pace)} partidos únicos cargados.')
        except (ValueError, pd.errors.ParserError, UnicodeError) as exc:
            st.error(f'CSV Pace inválido: {exc}')
            historial_pace = pd.DataFrame()
            huella_pace = None
    # Nunca mostrar ni guardar una predicción calculada con otro CSV.
    if st.session_state.get('nba_lab_pace_huella') != huella_pace:
        st.session_state.pop('nba_lab_pace_prospectivo', None)
        st.session_state['nba_lab_pace_huella'] = huella_pace

    futuros = estado['futuros']
    st.caption(f'Historial recuperado: {len(historico)} partidos. '
               'El avance se conserva mientras dure esta sesión de Streamlit.')
    if not futuros.empty:
        futuros = futuros.copy()
        fechas = pd.to_datetime(futuros['fecha_utc'], utc=True, errors='coerce')
        futuros = futuros.loc[fechas.gt(pd.Timestamp.now(tz='UTC')) & futuros['finalizado'].eq(False)].drop_duplicates('id')
    if futuros.empty:
        st.info('No se encontraron próximos partidos.')
    else:
        opciones = {f"{r['visitante']} @ {r['local']} · {r['fecha_utc']}": r for r in futuros.to_dict('records')}
        elegido = st.selectbox('Partido', list(opciones))
        juego = opciones[elegido]
        if not historial_pace.empty:
            if st.button('🧠 Calcular Pace + Eficiencia', use_container_width=True):
                try:
                    from nba_pace_prospectivo import preparar_prediccion
                    calculo_pace = preparar_prediccion(historial_pace, juego)
                    calculo_pace['huella_csv'] = huella_pace
                    st.session_state['nba_lab_pace_prospectivo'] = calculo_pace
                except (ValueError, KeyError, TypeError) as exc:
                    st.error(f'Pace: {exc}')
            calculo_pace = st.session_state.get('nba_lab_pace_prospectivo', {})
            if (calculo_pace.get('partido_id') == str(juego['id'])
                    and calculo_pace.get('huella_csv') == huella_pace
                    and pd.to_datetime(calculo_pace.get('inicio_utc'), utc=True, errors='coerce')
                        == pd.to_datetime(juego['fecha_utc'], utc=True, errors='coerce')):
                st.dataframe(pd.DataFrame([
                    {'Equipo': equipo, 'Puntos proyectados': puntos,
                     'Antecedentes': calculo_pace['antecedentes'][equipo]}
                    for equipo, puntos in calculo_pace['equipos'].items()
                ]), hide_index=True, use_container_width=True)
                st.caption(f"Pace proyectado: {calculo_pace['pace_48']:.2f} posesiones/48 min")
                if st.button('💾 Guardar Pace en Supabase', use_container_width=True):
                    try:
                        from nba_pace_prospectivo import guardar_pace
                        n = guardar_pace(calculo_pace)
                        st.success(f'{n} registros nuevos confirmados; duplicados conservados.')
                    except (RuntimeError, ValueError, KeyError) as exc:
                        st.error(f'No se pudo guardar Pace: {exc}')
        # Asociar las predicciones de los tres motores al historial exacto y al inicio.
        firma_historial = hashlib.sha256(
            pd.util.hash_pandas_object(
                historico.sort_values('id').reset_index(drop=True), index=False
            ).values.tobytes()
        ).hexdigest() if not historico.empty else None
        inicio_juego = pd.to_datetime(juego['fecha_utc'], utc=True, errors='coerce')
        if st.button('Calcular tres modelos', use_container_width=True, disabled=not estado['completo']):
            try:
                valores = calcular(historico, juego)
                st.session_state['nba_lab_prospectivo'] = {
                    'id': str(juego['id']), 'inicio_utc': inicio_juego.isoformat(),
                    'firma_historial': firma_historial, 'valores': valores,
                }
            except Exception as exc:
                st.session_state.pop('nba_lab_prospectivo', None)
                st.error(str(exc))
        calculado = st.session_state.get('nba_lab_prospectivo', {})
        vigente = (estado['completo'] and calculado.get('id') == str(juego['id'])
                   and calculado.get('firma_historial') == firma_historial
                   and calculado.get('inicio_utc') == inicio_juego.isoformat())
        if vigente:
            st.dataframe(pd.DataFrame(calculado['valores']).T, use_container_width=True)
            if st.button('💾 Guardar los tres modelos en Supabase', use_container_width=True):
                try:
                    n = guardar(juego, calculado['valores'])
                    st.success(f'{n} registros nuevos confirmados; los existentes no se modificaron.')
                except Exception as exc:
                    st.error(str(exc))
    from nba_pace_panel_predictivo import mostrar_panel_predictivo
    mostrar_panel_predictivo(historico, juego if not futuros.empty else None)
    # Diagnóstico sin escrituras ni exposición de secretos.
    from nba_supabase_diagnostico import mostrar_diagnostico
    mostrar_diagnostico()
    st.subheader('Validación prospectiva')
    if st.button('Consultar registros y evaluar', use_container_width=True):
        try:
            guardados = registros()
            st.write(f'Registros de modelo: {len(guardados)}')
            tabla = evaluar(historico, guardados)
            if tabla.empty:
                st.info('Todavía no hay resultados reglamentarios verificables en el historial consultado.')
            else:
                st.dataframe(tabla, hide_index=True, use_container_width=True)
                resumen = tabla.groupby('Modelo').agg(
                    N=('Error', 'size'), MAE=('Error', lambda s: s.abs().mean()),
                    RMSE=('Error', lambda s: np.sqrt(np.mean(s ** 2))),
                    Sesgo=('Error', 'mean')).reset_index()
                st.dataframe(resumen.round(3), hide_index=True, use_container_width=True)
                st.caption('Métricas individuales: las muestras pueden ser diferentes.')
                comparacion, comunes = comparar_cuatro_modelos(tabla)
                st.subheader('Comparación justa · cuatro modelos')
                if comparacion.empty:
                    st.info('Aún no hay partidos/equipos con predicciones válidas de los cuatro modelos.')
                else:
                    st.caption(f'Misma muestra: {len(comunes) // 4} partido-equipo, {len(comunes)} registros.')
                    st.dataframe(comparacion.round(3), hide_index=True, use_container_width=True)
                    st.download_button('Descargar comparación CSV',
                        comparacion.to_csv(index=False).encode('utf-8'),
                        file_name='nba_cuatro_modelos_prospectivo.csv', mime='text/csv')
        except Exception as exc:
            st.error(str(exc))


if __name__ == '__main__':
    mostrar()
