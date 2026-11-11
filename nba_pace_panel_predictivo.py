"""Panel experimental de predicción pace: solo lectura y caché de sesión."""
import pandas as pd
import streamlit as st
from nba_pace_historial import construir_historial
from nba_pace_predictivo import predecir_pace

CLAVE = 'nba_pace_historial_predictivo_v1'

def mostrar_panel_predictivo(historico, juego=None):
    with st.expander('🧠 Pace + Eficiencia — predicción experimental', expanded=False):
        st.caption('Solo historial anterior al partido. No modifica Base, Modelo C, Ensemble ni Supabase.')
        if not isinstance(historico, pd.DataFrame) or historico.empty:
            st.info('Carga primero el historial NBA.'); return
        if not {'id', 'fecha_utc', 'finalizado'}.issubset(historico.columns):
            st.warning('Faltan columnas de historial.'); return
        ids = set(historico.loc[historico['finalizado'].eq(True), 'id'].astype(str))
        estado = st.session_state.get(CLAVE)
        if not isinstance(estado, dict):
            estado = {'filas': [], 'consultados': [], 'fallidos': []}
            st.session_state[CLAVE] = estado
        # Recuperación opcional desde CSV para no perder avance al reiniciar Streamlit.
        archivo = st.file_uploader('Restaurar historial pace CSV (opcional)', type=['csv'], key='pace_restaurar_csv')
        if archivo is not None and st.button('Restaurar CSV sin duplicados', key='pace_restaurar_btn'):
            try:
                previo = pd.read_csv(archivo, dtype={'partido_id': str})
                obligatorias = {'partido_id', 'fecha_utc', 'pace_48', 'posesiones_local', 'posesiones_visitante'}
                if not obligatorias.issubset(previo.columns):
                    st.error('El CSV no tiene las columnas esperadas.')
                else:
                    actual = pd.DataFrame(estado['filas'])
                    unido = pd.concat([actual, previo], ignore_index=True)
                    unido['partido_id'] = unido['partido_id'].astype(str)
                    unido = unido.drop_duplicates('partido_id', keep='first')
                    estado['filas'] = unido.to_dict('records')
                    estado['consultados'] = list(dict.fromkeys(
                        [str(x) for x in estado['consultados']] + unido['partido_id'].tolist()))
                    st.success(f'Restaurados {len(unido)} partidos únicos.')
            except Exception as exc:
                st.error(f'CSV inválido: {type(exc).__name__}: {exc}')
        # Los bloques más antiguos primero
        # para dar antecedentes al modelo, nunca se consulta el partido objetivo.
        # Reconciliar estado antiguo que pudo contener múltiples copias del mismo juego.
        if estado['filas']:
            unico = pd.DataFrame(estado['filas'])
            if 'partido_id' in unico:
                unico['partido_id'] = unico['partido_id'].astype(str)
                unico = unico.drop_duplicates('partido_id', keep='first')
                estado['filas'] = unico.to_dict('records')
                estado['consultados'] = list(dict.fromkeys(
                    [str(x) for x in estado['consultados']] + unico['partido_id'].tolist()))
        pendientes = historico.loc[historico['finalizado'].eq(True)].copy()
        pendientes['id'] = pendientes['id'].astype(str)
        pendientes = pendientes.drop_duplicates('id').sort_values('fecha_utc')
        pendientes = pendientes.loc[~pendientes['id'].isin(set(estado['consultados']))]
        n = st.select_slider('Partidos a recuperar en este bloque', options=[5, 10, 20, 30, 50], value=20, key='pace_pred_bloque')
        if st.button('📥 Recuperar siguiente bloque de estadísticas', key='pace_pred_recuperar', disabled=pendientes.empty, use_container_width=True):
            try:
                from modulo_nba import cargar_detalle
                with st.spinner('Recuperando boxscores finalizados...'):
                    nuevos, errores = construir_historial(pendientes, cargar_detalle, max_partidos=n)
                seleccionados = pendientes.head(n)['id'].tolist()
                estado['consultados'] = list(dict.fromkeys(estado['consultados'] + seleccionados))
                if not nuevos.empty:
                    existente = {str(x['partido_id']) for x in estado['filas']}
                    estado['filas'].extend(r for r in nuevos.to_dict('records')
                                         if str(r['partido_id']) not in existente)
                if not errores.empty:
                    estado['fallidos'].extend(errores.to_dict('records'))
                st.success(f'Bloque procesado: {len(nuevos)} completos de {len(seleccionados)}.')
            except Exception as exc:
                st.error(f'Error al recuperar estadísticas: {type(exc).__name__}: {exc}')
        tabla = pd.DataFrame(estado['filas'])
        st.caption(f"Historial de pace en esta sesión: {len(tabla)} partidos completos; "
                   f"{len(estado['fallidos'])} incompletos; {len(pendientes)} pendientes antes de esta ejecución.")
        if not tabla.empty:
            st.download_button('📥 Exportar historial de pace CSV', tabla.to_csv(index=False).encode('utf-8-sig'),
                               file_name='nba_historial_pace.csv', mime='text/csv', key='pace_pred_exportar')
        if juego is None:
            st.info('Selecciona un próximo partido para calcular su predicción con pace.'); return
        if tabla.empty:
            st.info('Recupera primero partidos históricos.'); return
        if st.button('🧠 Calcular predicción Pace + Eficiencia', key='pace_pred_calcular', use_container_width=True):
            try:
                pred = predecir_pace(tabla, juego, ventana=10, minimo=3)
                if pred is None:
                    st.warning('No hay suficientes antecedentes completos para ambos equipos (mínimo 3 cada uno).')
                else:
                    local, visitante = str(juego['local']), str(juego['visitante'])
                    filas = [{'Equipo': equipo, 'Puntos proyectados': pred['equipos'][equipo]['prediccion'],
                              'Pace reciente': round(pred['equipos'][equipo]['pace'], 2),
                              'Eficiencia ofensiva': round(pred['equipos'][equipo]['ortg'], 2),
                              'Eficiencia defensiva': round(pred['equipos'][equipo]['drtg'], 2),
                              'Partidos previos': pred['equipos'][equipo]['muestra']}
                             for equipo in (local, visitante)]
                    st.dataframe(pd.DataFrame(filas), hide_index=True, use_container_width=True)
                    st.metric('Total proyectado Pace + Eficiencia', f"{pred['total']:.1f}")
                    st.caption(f"Ritmo previsto: {pred['pace_48']:.1f} posesiones estimadas por 48 min. "
                               'Modelo experimental sin validación de precisión todavía.')
            except Exception as exc:
                st.error(f'No se pudo predecir: {type(exc).__name__}: {exc}')
