"""Panel de predicciones remotas dentro del Laboratorio NBA existente.
No importa ni modifica módulos NBA/NFL estables.
"""
import streamlit as st
from nba_lab_fuente_remota import BASE_URL, _descargar_json, obtener_tarjeta_segura


def mostrar_predicciones_remotas():
    st.subheader('📅 Próximos partidos · Predicciones experimentales')
    st.caption('Datos publicados automáticamente. Solo lectura; no son resultados garantizados.')
    try:
        indice = _descargar_json(BASE_URL.rstrip('/') + '/indice_tarjetas.json')
        if not isinstance(indice, dict) or not isinstance(indice.get('tarjetas'), list):
            raise ValueError('Formato de índice inválido')
        opciones = {}
        for item in indice['tarjetas']:
            if not isinstance(item, dict):
                continue
            pid = str(item.get('id', ''))
            if pid.isdigit() and item.get('local') and item.get('visitante'):
                opciones[f"{item['local']} vs {item['visitante']} · {pid}"] = pid
    except Exception as exc:
        st.warning(f'No se pudo consultar la publicación: {exc}')
        return
    if not opciones:
        st.info('No hay partidos publicados por el laboratorio.')
        return
    st.caption(f"Publicación UTC: {indice.get('generado_utc', 'sin fecha')} · {len(opciones)} encuentros")
    etiqueta = st.selectbox('Selecciona un encuentro', list(opciones), key='nba_lab_remoto_partido')
    tarjeta, error = obtener_tarjeta_segura(opciones[etiqueta])
    if tarjeta is None:
        st.info(f'No hay una proyección vigente para este partido: {error}')
        return
    with st.container(border=True):
        st.markdown(f"**{tarjeta['local']} vs {tarjeta['visitante']}**")
        a, b = st.columns(2)
        a.metric('Local', f"{tarjeta['proyeccion_local']:.2f}")
        b.metric('Visitante', f"{tarjeta['proyeccion_visitante']:.2f}")
        a, b = st.columns(2)
        a.metric('Total Ensemble', f"{tarjeta['total_ensemble']:.2f}")
        b.metric('Total Modelo C', f"{tarjeta['total_modelo_c']:.2f}")
        st.caption(f"Referencia histórica: {tarjeta['referencia_total']:.2f} · Edge Ensemble: {tarjeta['edge_ensemble']:+.2f} · Edge Modelo C: {tarjeta['edge_modelo_c']:+.2f}")
        st.caption('Pace: ' + (f"{tarjeta['pace_prepartido']:.2f}" if tarjeta['pace_prepartido'] is not None else 'no disponible'))
        st.caption(f"Generada UTC: {tarjeta['generado_utc']}")
