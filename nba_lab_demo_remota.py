"""Pantalla experimental aislada; no modifica main.py ni NBA estable."""
import streamlit as st
from nba_lab_fuente_remota import BASE_URL, _descargar_json, obtener_tarjeta_segura

st.set_page_config(page_title='NBA Laboratorio · conexión remota', layout='centered')
st.title('🏀 NBA · conexión experimental')
st.caption('Solo lectura. Datos experimentales; no reemplazan las proyecciones estables.')

try:
    indice = _descargar_json(BASE_URL.rstrip('/') + '/indice_tarjetas.json')
    items = indice.get('tarjetas', [])
    if not isinstance(items, list):
        raise ValueError('Índice inválido')
    opciones = {f"{x['local']} vs {x['visitante']} · {x['id']}": str(x['id'])
                for x in items if isinstance(x, dict) and all(x.get(k) for k in ('local', 'visitante', 'id'))}
    if not opciones:
        st.warning('No hay partidos publicados.')
        st.stop()
except Exception as exc:
    st.error(f'No fue posible consultar el índice: {exc}')
    st.stop()

st.caption(f"Tarjetas publicadas: {len(opciones)} · Última publicación: {indice.get('generado_utc', 'desconocida')}")
elegido = st.selectbox('Selecciona un encuentro', list(opciones))
partido_id = opciones[elegido]
d, error = obtener_tarjeta_segura(partido_id)
if d is None:
    st.info(f'No hay predicción vigente para este encuentro: {error}')
    st.stop()

with st.container(border=True):
    st.subheader(f"{d['local']} vs {d['visitante']}")
    a, b = st.columns(2)
    a.metric(d['local'], f"{d['proyeccion_local']:.2f}")
    b.metric(d['visitante'], f"{d['proyeccion_visitante']:.2f}")
    a, b = st.columns(2)
    a.metric('Total Ensemble', f"{d['total_ensemble']:.2f}")
    b.metric('Total Modelo C', f"{d['total_modelo_c']:.2f}")
    st.caption(f"Referencia: {d['referencia_total']:.2f} · Edge Ensemble: {d['edge_ensemble']:+.2f} · Edge Modelo C: {d['edge_modelo_c']:+.2f}")
    st.caption(f"Pace: {d['pace_prepartido'] if d['pace_prepartido'] is not None else 'sin datos'} · Generada UTC: {d['generado_utc']}")
    st.caption('Proyección experimental. No garantiza resultados.')
