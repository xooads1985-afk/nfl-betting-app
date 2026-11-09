"""Laboratorio prospectivo NBA. Auxiliar: no altera modelos ni registro principal."""
from datetime import datetime, timezone
import json
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
    """Evaluación de puntos por equipo: no usa marcador final de prórroga."""
    from modulo_nba import cargar_detalle
    from resumen_inteligente_nba import _puntos_periodos
    por_id = {str(r['id']): r for r in historial.to_dict('records')}
    evaluados = []
    for registro in guardados:
        partido = por_id.get(str(registro['partido_id']))
        if not partido or not bool(partido.get('finalizado')):
            continue
        try:
            detalle = _puntos_periodos(cargar_detalle(str(registro['partido_id'])))
            periodos = detalle.get(registro['equipo'])
            if not isinstance(periodos, dict) or not all(k in periodos for k in (1, 2, 3, 4)):
                continue
            real = sum(float(periodos[k]) for k in (1, 2, 3, 4))
            error = float(registro['proyeccion']) - real
            evaluados.append({'Partido': registro['partido_id'], 'Equipo': registro['equipo'],
                              'Modelo': registro['modelo'], 'Proyección': float(registro['proyeccion']),
                              'Real (reglamentario)': real, 'Error': error})
        except (ValueError, TypeError, KeyError, RuntimeError):
            continue
    return pd.DataFrame(evaluados)


def mostrar():
    from resumen_inteligente_nba import _cargar_historial_temporada_nba, _calendario_proximos_nba
    from datetime import date, timedelta
    st.title('🧪 Laboratorio prospectivo NBA')
    st.caption('Página auxiliar dentro de la misma app. No modifica el resumen ni sus registros originales.')
    hoy = date.today()
    incluir_pasada = st.checkbox('Incluir temporada anterior para entrenar', value=True)
    inicio = date(2025, 10, 21) if incluir_pasada else date(2026, 10, 20)
    with st.spinner('Cargando historial y calendario...'):
        historico, incidencias = _cargar_historial_temporada_nba(inicio, hoy)
        futuros, _ = _calendario_proximos_nba(hoy.isoformat(), (hoy + timedelta(days=14)).isoformat())
    if incidencias:
        st.warning(f'Cobertura histórica parcial: {len(incidencias)} incidencias.')
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
        if st.button('Calcular tres modelos', use_container_width=True):
            try:
                st.session_state['nba_lab_prospectivo'] = {'id': str(juego['id']), 'valores': calcular(historico, juego)}
            except Exception as exc:
                st.error(str(exc))
        calculado = st.session_state.get('nba_lab_prospectivo', {})
        if calculado.get('id') == str(juego['id']):
            st.dataframe(pd.DataFrame(calculado['valores']).T, use_container_width=True)
            if st.button('💾 Guardar los tres modelos en Supabase', use_container_width=True):
                try:
                    n = guardar(juego, calculado['valores'])
                    st.success(f'{n} registros nuevos confirmados; los existentes no se modificaron.')
                except Exception as exc:
                    st.error(str(exc))
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
        except Exception as exc:
            st.error(str(exc))


if __name__ == '__main__':
    mostrar()

