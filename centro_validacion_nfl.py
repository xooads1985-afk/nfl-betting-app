"""Centro de validación estadística NFL. Independiente del motor estable."""
import io
import pandas as pd
import streamlit as st


def _diagnosticar(df):
    cols = set(df.columns)
    id_col = next((x for x in ('player_id', 'gsis_id', 'ID') if x in cols), None)
    week_col = next((x for x in ('week', 'Semana') if x in cols), None)
    team_col = next((x for x in ('recent_team', 'team', 'posteam', 'Equipo') if x in cols), None)
    if not id_col or not week_col or not team_col:
        raise ValueError('Se requieren columnas de jugador, semana y equipo. Columnas disponibles: ' + ', '.join(map(str, df.columns)))
    data = df.copy()
    data[week_col] = pd.to_numeric(data[week_col], errors='coerce')
    faltantes = data[[id_col, week_col, team_col]].isna().any(axis=1)
    validos = data.loc[~faltantes].copy()
    grupos = validos.groupby([id_col, week_col], dropna=False)
    equipos_semana = grupos[team_col].nunique(dropna=True)
    duplicados = grupos.size()
    cambios = validos.groupby(id_col)[team_col].nunique(dropna=True)
    resumen = {
        'Registros': len(data),
        'Jugadores únicos': int(validos[id_col].nunique()),
        'Registros incompletos': int(faltantes.sum()),
        'Jugadores con varios equipos': int((cambios > 1).sum()),
        'Jugador-semana con varias filas': int((duplicados > 1).sum()),
        'Jugador-semana con varios equipos': int((equipos_semana > 1).sum()),
    }
    ambiguos = equipos_semana[equipos_semana > 1].rename('equipos_distintos').reset_index()
    return resumen, ambiguos


def mostrar_centro_validacion_nfl():
    st.title('🛡️ Centro de Validación NFL')
    st.caption('Apartado experimental independiente. No modifica las proyecciones ni los archivos estables.')
    st.info('Este panel revisa calidad de estadísticas semanales; todavía no calcula MAE de proyecciones ni valida precisión predictiva.')
    temporada = st.selectbox('Temporada', [2026, 2025, 2024], index=0)
    fuente = st.radio('Fuente de datos', ['Subir CSV semanal', 'Consultar NFLverse (nflreadpy)'], horizontal=False)
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
        resumen, ambiguos = _diagnosticar(df)
    except Exception as exc:
        st.error(str(exc))
        return
    st.subheader('Calidad de datos')
    for clave, valor in resumen.items():
        st.metric(clave, valor)
    st.subheader('Semanas con varios equipos para un jugador')
    if ambiguos.empty:
        st.success('No se encontraron casos en los registros disponibles.')
    else:
        st.dataframe(ambiguos, use_container_width=True)
    st.download_button('Descargar resumen CSV', pd.DataFrame([resumen]).to_csv(index=False).encode('utf-8'), 'validacion_nfl_resumen.csv', 'text/csv')
    st.download_button('Descargar casos ambiguos CSV', ambiguos.to_csv(index=False).encode('utf-8'), 'validacion_nfl_ambiguos.csv', 'text/csv')
