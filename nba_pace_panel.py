"""Panel opcional de auditoría de pace; no modifica predicciones ni escribe resultados."""
import pandas as pd
import streamlit as st
from nba_pace_auditoria_fase2 import auditar_partidos, resumen_cobertura


def mostrar_auditoria_pace(partidos: pd.DataFrame):
    """Se inserta en el laboratorio existente; requiere historial con IDs ESPN."""
    with st.expander('🧪 Auditoría de posesiones ESPN (experimental)', expanded=False):
        st.caption('Solo lectura. Consulta partidos finalizados; no modifica modelos, Supabase ni proyecciones.')
        n = st.select_slider('Partidos recientes a revisar', options=[5, 10, 20, 30, 50], value=5, key='pace_audit_n')
        if st.button('🔍 Verificar cobertura ESPN', key='pace_audit_run', use_container_width=True):
            try:
                from modulo_nba import cargar_detalle
                with st.spinner('Consultando estadísticas de equipos...'):
                    resultado = auditar_partidos(partidos, cargar_detalle, max_partidos=n)
                st.session_state['pace_audit_result'] = resultado
            except Exception as exc:
                st.error(f'No se pudo ejecutar la auditoría: {type(exc).__name__}: {exc}')
        resultado = st.session_state.get('pace_audit_result')
        if isinstance(resultado, pd.DataFrame):
            if resultado.empty:
                st.info('No se encontraron partidos finalizados con identificador ESPN válido.')
                return
            resumen = resumen_cobertura(resultado)
            a, b, c = st.columns(3)
            a.metric('Revisados', resumen['partidos_revisados'])
            b.metric('Completos', resumen['partidos_completos'])
            pct = resumen['cobertura_pct']
            c.metric('Cobertura', f'{pct:.1f}%' if pct is not None else 'N/D')
            st.dataframe(resultado, hide_index=True, use_container_width=True)
            st.download_button('📥 Descargar auditoría CSV', resultado.to_csv(index=False).encode('utf-8-sig'),
                               file_name='auditoria_pace_espn.csv', mime='text/csv', key='pace_audit_csv')
            st.caption('Posesiones estimadas ≠ pace normalizado por 48 minutos. No se usan para predicciones.')
