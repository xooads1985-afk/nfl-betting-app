"""Centro de validación NFL v2: diagnóstico descriptivo, sin modificar modelos."""
import pandas as pd
from datetime import datetime, timezone
import streamlit as st


def _columna(df, candidatos):
    return next((c for c in candidatos if c in df.columns), None)


def _vacio(serie):
    return serie.isna() | serie.astype('string').str.strip().fillna('').eq('')


def _diagnosticar_detallado(df):
    id_col = _columna(df, ('player_id', 'gsis_id', 'ID'))
    week_col = _columna(df, ('week', 'Semana'))
    team_col = _columna(df, ('recent_team', 'team', 'posteam', 'Equipo'))
    name_col = _columna(df, ('player_display_name', 'player_name', 'player', 'Jugador'))
    position_col = _columna(df, ('position', 'position_group', 'Posición'))
    if not all((id_col, week_col, team_col)):
        raise ValueError('Se requieren columnas de jugador, semana y equipo. Disponibles: ' + ', '.join(map(str, df.columns)))

    data = df.copy()
    data['_semana_num'] = pd.to_numeric(data[week_col], errors='coerce')
    faltas_id = _vacio(data[id_col])
    faltas_semana = data['_semana_num'].isna()
    faltas_equipo = _vacio(data[team_col])
    incompletos_mask = faltas_id | faltas_semana | faltas_equipo
    validos = data.loc[~incompletos_mask].copy()

    def detalle_faltantes(row_index):
        partes = []
        if bool(faltas_id.loc[row_index]): partes.append(id_col)
        if bool(faltas_semana.loc[row_index]): partes.append(week_col)
        if bool(faltas_equipo.loc[row_index]): partes.append(team_col)
        return ', '.join(partes)

    incompletos = data.loc[incompletos_mask].copy()
    incompletos.insert(0, 'fila_origen', incompletos.index + 2)
    # enumerate evita errores si el CSV trae índices repetidos
    motivos = []
    for idx in range(len(data)):
        if bool(incompletos_mask.iloc[idx]):
            motivos.append(', '.join(c for c, falta in ((id_col, faltas_id.iloc[idx]), (week_col, faltas_semana.iloc[idx]), (team_col, faltas_equipo.iloc[idx])) if bool(falta)))
    incompletos.insert(1, 'campos_faltantes', motivos)
    incompletos = incompletos.drop(columns=['_semana_num'])

    grupos = validos.groupby([id_col, '_semana_num'], dropna=False)
    equipos_semana = grupos[team_col].nunique(dropna=True)
    duplicados = grupos.size()
    cambios = validos.groupby(id_col)[team_col].nunique(dropna=True)
    ids_cambios = cambios[cambios > 1].index
    cambios_detalle = validos[validos[id_col].isin(ids_cambios)].copy()
    columnas = [id_col]
    if name_col: columnas.append(name_col)
    columnas += [week_col, team_col]
    if position_col: columnas.append(position_col)
    cambios_detalle = cambios_detalle[columnas].drop_duplicates().sort_values([id_col, week_col, team_col])

    ambiguos = equipos_semana[equipos_semana > 1].rename('equipos_distintos').reset_index().rename(columns={'_semana_num': 'semana_numero'})
    resumen = {
        'Registros': len(data),
        'Jugadores únicos': int(validos[id_col].nunique()),
        'Registros incompletos': int(incompletos_mask.sum()),
        'Jugadores con varios equipos': int((cambios > 1).sum()),
        'Jugador-semana con varias filas': int((duplicados > 1).sum()),
        'Jugador-semana con varios equipos': int((equipos_semana > 1).sum()),
    }
    return resumen, ambiguos, cambios_detalle, incompletos


def _diagnosticar(df):
    """Compatibilidad con la interfaz anterior."""
    resumen, ambiguos, _, _ = _diagnosticar_detallado(df)
    return resumen, ambiguos


def _descargar(nombre, tabla, etiqueta):
    st.download_button(etiqueta, tabla.to_csv(index=False).encode('utf-8-sig'), nombre, 'text/csv', use_container_width=True)



def _crear_historial_limpio(df):
    """Devuelve historial, catálogo y filas excluidas; no altera el DataFrame original.

    Los duplicados de ID/semana se ponen en cuarentena, sin sumarlos.
    """
    id_col = _columna(df, ('player_id', 'gsis_id', 'ID'))
    week_col = _columna(df, ('week', 'Semana'))
    team_col = _columna(df, ('recent_team', 'team', 'posteam', 'Equipo'))
    name_col = _columna(df, ('player_display_name', 'player_name', 'player', 'Jugador'))
    position_col = _columna(df, ('position', 'position_group', 'Posición'))
    if not all((id_col, week_col, team_col)):
        raise ValueError('Se requieren identificador, semana y equipo.')
    data = df.copy().reset_index(drop=True)
    data['fila_origen'] = data.index + 2
    data['Semana'] = pd.to_numeric(data[week_col], errors='coerce')
    valido = ~(_vacio(data[id_col]) | data['Semana'].isna() | _vacio(data[team_col]))
    base = data.loc[valido].copy()
    base['ID_jugador'] = base[id_col].astype('string').str.strip()
    base['Equipo_semana'] = base[team_col].astype('string').str.strip()
    base['Jugador'] = base[name_col].astype('string') if name_col else base['ID_jugador']
    base['Posicion'] = base[position_col].astype('string') if position_col else 'Sin posición'
    # No se atribuyen estadísticas duplicadas a una semana: se separan para inspección.
    repetido = base.duplicated(['ID_jugador', 'Semana'], keep=False)
    excluidos = pd.concat([
        data.loc[~valido].assign(motivo_exclusion='Identificador, semana o equipo inválido'),
        base.loc[repetido].assign(motivo_exclusion='ID y semana duplicados'),
    ], ignore_index=True)
    historial = base.loc[~repetido].copy()
    if historial.empty:
        historial['Equipo_actual'] = pd.Series(dtype='string')
        catalogo = pd.DataFrame(columns=['ID_jugador','Jugador','Posicion','Equipo_actual','Ultima_semana'])
        return historial, catalogo, excluidos
    # Si la última semana es ambigua, el jugador no debe recibir equipo actual arbitrario.
    ultimas = base.groupby('ID_jugador')['Semana'].transform('max').eq(base['Semana'])
    ultimo_equipo = base.loc[ultimas].groupby('ID_jugador')['Equipo_semana'].nunique()
    ids_ambiguos = set(ultimo_equipo[ultimo_equipo > 1].index)
    historial = historial.sort_values(['ID_jugador', 'Semana', 'fila_origen'])
    catalogo = historial.drop_duplicates('ID_jugador', keep='last')[['ID_jugador','Jugador','Posicion','Equipo_semana','Semana']].copy()
    catalogo = catalogo.rename(columns={'Equipo_semana':'Equipo_actual','Semana':'Ultima_semana'})
    catalogo.loc[catalogo['ID_jugador'].isin(ids_ambiguos), 'Equipo_actual'] = pd.NA
    historial = historial.merge(catalogo[['ID_jugador','Equipo_actual']], on='ID_jugador', how='left', validate='many_to_one')
    return historial, catalogo, excluidos

def mostrar_centro_validacion_nfl():
    st.title('🛡️ Centro de Validación NFL')
    st.caption('Diagnóstico independiente: no modifica las proyecciones ni los archivos estables.')
    st.info('Analiza la calidad de estadísticas semanales. No mide todavía MAE ni precisión de las proyecciones.')
    temporada = st.selectbox('Temporada', [2026, 2025, 2024], index=0)
    fuente = st.radio('Fuente de datos', ['Subir CSV semanal', 'Consultar NFLverse (nflreadpy)'])
    df = None
    if fuente == 'Subir CSV semanal':
        archivo = st.file_uploader('Selecciona CSV de estadísticas semanales', type=['csv'])
        if archivo is not None:
            try:
                df = pd.read_csv(archivo)
            except Exception as exc:
                st.error(f'No se pudo leer el CSV: {exc}')
    elif st.button('Consultar estadísticas reales', use_container_width=True):
        try:
            import nflreadpy
            resultado = nflreadpy.load_player_stats([temporada])
            df = resultado.to_pandas() if hasattr(resultado, 'to_pandas') else pd.DataFrame(resultado)
        except Exception as exc:
            st.error(f'No fue posible consultar NFLverse: {exc}')
    _panel_registro_manual()
    _panel_validacion_proyecciones()
    if df is None:
        st.caption('El diagnóstico se ejecutará al cargar un CSV o consultar NFLverse.')
        return
    try:
        resumen, ambiguos, cambios, incompletos = _diagnosticar_detallado(df)
    except Exception as exc:
        st.error(str(exc))
        return
    st.subheader('Calidad de datos')
    for clave, valor in resumen.items():
        st.metric(clave, valor)
    st.subheader('Jugadores registrados en varios equipos')
    st.caption('Muestra semanas y equipos observados; no confirma por sí solo un traspaso.')
    if cambios.empty:
        st.success('No se detectaron jugadores con varios equipos.')
    else:
        st.dataframe(cambios, use_container_width=True, hide_index=True)
    _descargar('validacion_nfl_cambios_equipo.csv', cambios, 'Descargar jugadores y equipos CSV')
    st.subheader('Registros incompletos')
    st.caption('Campos obligatorios revisados: identificador, semana y equipo.')
    if incompletos.empty:
        st.success('No hay registros incompletos en esos campos.')
    else:
        st.dataframe(incompletos, use_container_width=True, hide_index=True)
    _descargar('validacion_nfl_incompletos.csv', incompletos, 'Descargar registros incompletos CSV')
    st.subheader('Semanas con varios equipos para un jugador')
    if ambiguos.empty:
        st.success('No se encontraron casos ambiguos en los registros disponibles.')
    else:
        st.dataframe(ambiguos, use_container_width=True, hide_index=True)
    _descargar('validacion_nfl_resumen.csv', pd.DataFrame([resumen]), 'Descargar resumen CSV')
    _descargar('validacion_nfl_ambiguos.csv', ambiguos, 'Descargar casos ambiguos CSV')
    st.subheader('Historial semanal limpio (experimental)')
    st.caption('No modifica el motor NFL. Los duplicados se excluyen para revisión, sin sumar sus métricas.')
    try:
        historial, catalogo, excluidos = _crear_historial_limpio(df)
        st.metric('Filas del historial limpio', len(historial))
        st.metric('Jugadores en catálogo', len(catalogo))
        st.metric('Filas excluidas', len(excluidos))
        _descargar('validacion_nfl_historial_limpio.csv', historial, 'Descargar historial limpio CSV')
        _descargar('validacion_nfl_catalogo.csv', catalogo, 'Descargar catálogo CSV')
        _descargar('validacion_nfl_excluidos.csv', excluidos, 'Descargar excluidos CSV')
    except Exception as exc:
        st.error(f'No se pudo generar el historial experimental: {exc}')

# Validación histórica independiente. No calcula ni altera predicciones.
def _evaluar_proyecciones(pronosticos, resultados):
    """Une registros por claves explícitas y evalúa MAE/sesgo sin inventar datos."""
    claves = ['partido_id', 'entidad_tipo', 'entidad_id', 'periodo', 'metrica']
    obligatorias_pred = claves + ['proyeccion', 'fecha_prediccion', 'inicio_partido']
    obligatorias_real = claves + ['real']
    for etiqueta, tabla, requeridas in [('Proyecciones', pronosticos, obligatorias_pred), ('Resultados', resultados, obligatorias_real)]:
        faltan = [c for c in requeridas if c not in tabla.columns]
        if faltan:
            raise ValueError(f'{etiqueta}: faltan columnas: {", ".join(faltan)}')
    p, r = pronosticos.copy(), resultados.copy()
    for tabla in (p, r):
        for c in claves:
            tabla[c] = tabla[c].astype('string').str.strip()
            if _vacio(tabla[c]).any():
                raise ValueError(f'Hay claves vacías en {c}.')
        if tabla.duplicated(claves).any():
            raise ValueError('Hay claves duplicadas. Corrige los registros antes de comparar.')
    p['proyeccion'] = pd.to_numeric(p['proyeccion'], errors='coerce')
    r['real'] = pd.to_numeric(r['real'], errors='coerce')
    if p['proyeccion'].isna().any() or r['real'].isna().any():
        raise ValueError('Hay proyecciones o resultados no numéricos.')
    for c in ['fecha_prediccion', 'inicio_partido']:
        p[c] = pd.to_datetime(p[c], utc=True, errors='coerce')
        if p[c].isna().any():
            raise ValueError(f'{c} debe contener fechas válidas con zona horaria.')
    if (p['fecha_prediccion'] >= p['inicio_partido']).any():
        raise ValueError('Se detectaron predicciones registradas durante o después del inicio del partido.')
    comparacion = p.merge(r, on=claves, how='inner', validate='one_to_one')
    comparacion['error'] = comparacion['proyeccion'] - comparacion['real']
    comparacion['error_absoluto'] = comparacion['error'].abs()
    resumen = (comparacion.groupby(['entidad_tipo','periodo','metrica'], dropna=False)
               .agg(casos=('error','size'), MAE=('error_absoluto','mean'), sesgo=('error','mean'))
               .reset_index())
    return comparacion, resumen, {'proyecciones': len(p), 'resultados': len(r), 'comparaciones': len(comparacion),
                                  'proyecciones_sin_resultado': len(p) - len(comparacion),
                                  'resultados_sin_proyeccion': len(r) - len(comparacion)}


def _panel_validacion_proyecciones():
    with st.expander('📏 Validación histórica de proyecciones (experimental)', expanded=False):
        st.caption('Carga predicciones guardadas antes del partido y resultados reales. No modifica el motor NFL.')
        st.info('El MAE mide el error absoluto medio. El sesgo es proyección menos resultado; positivo indica sobreestimación.')
        plantilla_p = pd.DataFrame(columns=['partido_id','entidad_tipo','entidad_id','periodo','metrica','proyeccion','fecha_prediccion','inicio_partido'])
        plantilla_r = pd.DataFrame(columns=['partido_id','entidad_tipo','entidad_id','periodo','metrica','real'])
        _descargar('plantilla_proyecciones_nfl.csv', plantilla_p, 'Descargar plantilla de proyecciones')
        _descargar('plantilla_resultados_nfl.csv', plantilla_r, 'Descargar plantilla de resultados')
        st.caption('Usa fechas ISO 8601 con zona horaria, por ejemplo 2026-11-01T15:00:00-06:00. Periodos: Q1, Q2, Q3, Q4, H1, H2 o FINAL. Identifica cada jugador con su ID estable.')
        archivo_p = st.file_uploader('CSV de proyecciones registradas', type=['csv'], key='nfl_v4_pred')
        archivo_r = st.file_uploader('CSV de resultados reales', type=['csv'], key='nfl_v4_real')
        if archivo_p is None or archivo_r is None:
            st.caption('Necesitamos ambos CSV para calcular errores. El historial de jugadores por sí solo no contiene las predicciones originales.')
            return
        try:
            p = pd.read_csv(archivo_p, dtype={c:'string' for c in ['partido_id','entidad_tipo','entidad_id','periodo','metrica']})
            r = pd.read_csv(archivo_r, dtype={c:'string' for c in ['partido_id','entidad_tipo','entidad_id','periodo','metrica']})
            comparacion, resumen, cobertura = _evaluar_proyecciones(p, r)
        except Exception as exc:
            st.error(f'No se pudieron validar los CSV: {exc}')
            return
        st.metric('Comparaciones válidas', cobertura['comparaciones'])
        st.metric('Proyecciones sin resultado', cobertura['proyecciones_sin_resultado'])
        st.metric('Resultados sin proyección', cobertura['resultados_sin_proyeccion'])
        if comparacion.empty:
            st.warning('No hay coincidencias exactas entre las claves de ambos archivos.')
            return
        st.caption('Compara el MAE por métrica: no mezcles puntos, yardas y recepciones para evaluar precisión.')
        st.dataframe(resumen, use_container_width=True, hide_index=True)
        _descargar('validacion_nfl_errores_detalle.csv', comparacion, 'Descargar errores por registro CSV')
        _descargar('validacion_nfl_mae_sesgo.csv', resumen, 'Descargar MAE y sesgo CSV')


_COLUMNAS_REGISTRO = ['partido_id','entidad_tipo','entidad_id','periodo','metrica','proyeccion','fecha_prediccion','inicio_partido']


def _registrar_proyeccion_manual(registros, partido_id, entidad_tipo, entidad_id, periodo,
                                 metrica, proyeccion, inicio_partido, ahora=None):
    """Registro de sesión: la marca de tiempo la crea el servidor, nunca el usuario."""
    ahora = ahora or datetime.now(timezone.utc)
    ahora = pd.Timestamp(ahora)
    if ahora.tzinfo is None:
        raise ValueError('La hora del servidor debe incluir zona horaria.')
    inicio = pd.to_datetime(inicio_partido, utc=True, errors='coerce')
    if pd.isna(inicio):
        raise ValueError('Introduce una fecha ISO 8601 válida con zona horaria.')
    if ahora >= inicio:
        raise ValueError('No se pueden registrar proyecciones cuando el partido ya comenzó.')
    campos = [partido_id, entidad_tipo, entidad_id, periodo, metrica]
    if any(not str(x).strip() for x in campos):
        raise ValueError('Completa todos los campos de identificación.')
    if not pd.notna(proyeccion):
        raise ValueError('La proyección debe ser un número válido.')
    clave = tuple(str(x).strip() for x in campos)
    for r in registros:
        if tuple(str(r[k]).strip() for k in _COLUMNAS_REGISTRO[:5]) == clave:
            raise ValueError('Ya existe una proyección para esta combinación. No se sobrescribe el registro original.')
    fila = dict(zip(_COLUMNAS_REGISTRO, [*clave, float(proyeccion), ahora.isoformat(), inicio.isoformat()]))
    return [*registros, fila]


def _panel_registro_manual():
    with st.expander('📝 Registro manual de proyecciones NFL', expanded=False):
        st.caption('Registra una estimación antes del partido. La hora de captura la asigna el servidor (UTC).')
        st.warning('Los registros se conservan solo durante esta sesión. Descarga el CSV después de cada captura: un reinicio puede borrar el historial. Un CSV descargado no constituye por sí solo una prueba inalterable de la fecha de creación.')
        key = 'nfl_registro_manual_v41'
        if key not in st.session_state:
            st.session_state[key] = []
        with st.form('nfl_form_registro_v41', clear_on_submit=False):
            partido = st.text_input('ID del partido (identificador estable)', placeholder='2026_09_PIT_CLE')
            tipo = st.selectbox('Tipo de entidad', ['equipo', 'jugador', 'partido'])
            entidad = st.text_input('ID de equipo o jugador', placeholder='PIT o ID de jugador')
            periodo = st.selectbox('Período', ['FINAL', 'Q1', 'Q2', 'Q3', 'Q4', 'H1', 'H2'])
            metrica = st.text_input('Métrica y unidad', placeholder='puntos o yardas_recepcion')
            valor = st.number_input('Valor proyectado', value=0.0, step=0.1, format='%.2f')
            inicio = st.text_input('Inicio del partido (ISO 8601 con zona horaria)', placeholder='2026-11-08T13:00:00-06:00')
            guardar = st.form_submit_button('Guardar proyección en esta sesión', use_container_width=True)
        if guardar:
            try:
                st.session_state[key] = _registrar_proyeccion_manual(
                    st.session_state[key], partido, tipo, entidad, periodo, metrica, valor, inicio)
                st.success('Proyección registrada. Descarga ahora el CSV de respaldo.')
            except Exception as exc:
                st.error(str(exc))
        registros = st.session_state[key]
        st.metric('Proyecciones en esta sesión', len(registros))
        if registros:
            tabla = pd.DataFrame(registros, columns=_COLUMNAS_REGISTRO)
            st.dataframe(tabla, use_container_width=True, hide_index=True)
            _descargar('nfl_proyecciones_registradas.csv', tabla, 'Descargar respaldo CSV de proyecciones')
            st.caption('El archivo descargado puede cargarse en la sección de validación histórica junto con los resultados reales.')
