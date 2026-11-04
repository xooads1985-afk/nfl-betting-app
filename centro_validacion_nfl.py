"""Centro de validación NFL v2: diagnóstico descriptivo, sin modificar modelos."""
import pandas as pd
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

