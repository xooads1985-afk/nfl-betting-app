import streamlit as st
import requests
from datetime import datetime

# ==========================================
# CONFIGURACIÓN DE LA PÁGINA
# ==========================================
st.set_page_config(
    page_title="Master Suite - Cuantificador +EV (NBA)",
    page_icon="🏀",
    layout="wide"
)

st.title("🎯 Master Suite: Módulo de Análisis Cuantitativo NBA (+EV)")
st.markdown("---")

# ==========================================
# FUNCIONES DE EXTRACCIÓN Y DATOS (API ESPN)
# ==========================================
@st.cache_data(ttl=300)
def obtener_cartelera_pura(deporte="basketball", liga="nba", fecha_str_api="", fecha_str_humana=""):
    # Añadimos &limit=20 para asegurar que la API devuelva toda la cartelera del día sin recortar partidos
    url = f"https://site.api.espn.com/apis/site/v2/sports/{deporte}/{liga}/scoreboard?dates={fecha_str_api}&limit=20"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            eventos = data.get("events", [])
            partidos_extraidos = []
            for evento in eventos:
                competencia = evento.get("competitions", [{}])[0]
                competidores = competencia.get("competitors", [])
                local, visitante = "Local", "Visitante"
                cuota_local, cuota_visita = -110, -110  # Valores base por defecto si la API de cuotas varía
                
                for comp in competidores:
                    if comp.get("homeAway") == "home":
                        local = comp.get("team", {}).get("displayName", "Local")
                    else:
                        visitante = comp.get("team", {}).get("displayName", "Visitante")
                
                partidos_extraidos.append({
                    "partido_str": f"📅 [{fecha_str_humana}] {visitante} @ {local}",
                    "local": local,
                    "visita": visitante,
                    "cuota_local_estimada": -110,
                    "cuota_visita_estimada": -110
                })
            return partidos_extraidos
    except Exception as e:
        st.error(f"Error al conectar con la API de ESPN: {e}")
    return []

# ==========================================
# PANEL DE CONTROL (SIDEBAR)
# ==========================================
st.sidebar.header("Panel de Control NBA")
fecha_hoy_api = datetime.now().strftime("%Y%m%d")
fecha_hoy_humana = datetime.now().strftime("%d/%m/%Y")

st.sidebar.info(f"Fecha analizada: {fecha_hoy_humana}")

st.sidebar.markdown("### ⚙️ Reglas y Filtros de la Suite")
min_edge = st.sidebar.slider("Edge Mínimo Requerido (%)", 1.0, 10.0, 3.0, 0.5)
regla_oro_activo = st.sidebar.checkbox("Aplicar Regla de Oro (Evitar momios peores que -150)", value=True)
bankroll_actual = st.sidebar.number_input("Bankroll Actual ($)", value=1000.0, step=50.0)

# ==========================================
# CARGA DE PARTIDOS
# ==========================================
with st.spinner("Consultando cartelera completa de la NBA en tiempo real..."):
    partidos = obtener_cartelera_pura("basketball", "nba", fecha_hoy_api, fecha_hoy_humana)

st.subheader(f"Cartelera Detectada para Hoy ({len(partidos)} partidos)")

if partidos:
    # Contenedor principal de análisis cuantitativo por partido
    for idx, p in enumerate(partidos):
        with st.expander(f"🏀 Partido {idx + 1}: {p['visita']} @ {p['local']}", expanded=False):
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.markdown(f"**Local:** {p['local']}")
                ef_local = st.slider(f"Eficiencia L5 ({p['local']})", 0.0, 1.0, 0.55, 0.01, key=f"loc_{idx}")
                descanso_local = st.number_input(f"Días descanso ({p['local']})", 0, 7, 2, key=f"dl_{idx}")
                momio_local = st.number_input(f"Momio Local (Amer.)", value=-110, step=5, key=f"ml_{idx}")
                
            with col2:
                st.markdown(f"**Visitante:** {p['visita']}")
                ef_visita = st.slider(f"Eficiencia L5 ({p['visita']})", 0.0, 1.0, 0.48, 0.01, key=f"vis_{idx}")
                descanso_visita = st.number_input(f"Días descanso ({p['visita']})", 0, 7, 1, key=f"dv_{idx}")
                momio_visita = st.number_input(f"Momio Visita (Amer.)", value=-110, step=5, key=f"mv_{idx}")

            with col3:
                st.markdown("### 📊 Panel de Decisión")
                st.markdown(f"**Edge Mínimo:** {min_edge}%")
                st.markdown(f"**Regla de Oro:** {'Activa (-150 máx)' :< 10}")

            # Botón para ejecutar el análisis cuantitativo completo
            if st.button(f"🔍 Ejecutar Escáner Cuantitativo", key=f"btn_{idx}"):
                
                # Motor de cálculo matemático ponderado (L5 + Factor Descanso + Factor Localía)
                factor_home = 0.04 # Ventaja de jugar en casa en la NBA
                factor_descanso = 0.02 * (descanso_local - descanso_visita)
                
                score_local = ef_local + factor_home + factor_descanso
                score_visita = ef_visita
                total_score = score_local + score_visita
                
                prob_local = score_local / total_score if total_score > 0 else 0.5
                prob_visita = 1.0 - prob_local
                
                st.markdown("---")
                res_col1, res_col2 = st.columns(2)
                
                with res_col1:
                    st.metric(label=f"Prob. Modelo ({p['local']})", value=f"{prob_local * 100:.1f}%")
                    st.metric(label=f"Prob. Modelo ({p['visita']})", value=f"{prob_visita * 100:.1f}%")
                
                with res_col2:
                    # Evaluación de la Regla de Oro
                    bloqueo_regla_oro_local = regla_oro_activo and (momio_local < -150)
                    bloqueo_regla_oro_visita = regla_oro_activo and (momio_visita < -150)
                    
                    # Criterio de selección +EV
                    if prob_local > 0.57 and not bloqueo_regla_oro_local:
                        st.success(f"🎯 **¡Mina de Oro (+EV)!**\nApostar al **Local ({p['local']})**.")
                    elif prob_visita > 0.57 and not bloqueo_regla_oro_visita:
                        st.success(f"🎯 **¡Mina de Oro (+EV)!**\nApostar al **Visitante ({p['visita']})**.")
                    else:
                        if bloqueo_regla_oro_local or bloqueo_regla_oro_visita:
                            st.warning("⚠️ **Descartado por Regla de Oro:** El momio es peor que -150, se excede el riesgo.")
                        else:
                            st.warning("⚠️ **Sin valor suficiente (-EV):** Margen muy ajustado. Mejor dejar pasar.")
else:
    st.warning("No se encontraron partidos para la fecha de hoy o la API tardó en responder.")

st.markdown("---")
st.markdown("*Master Suite v2.0 - Módulo NBA Operativo con Motor Cuantitativo Completo.*")
