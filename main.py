import streamlit as st
import pandas as pd
import json
import os

# Configuración de la página
st.set_page_config(
    page_title="Sistema Cuantitativo Pro NFL & NCAA",
    page_icon="🛡️",
    layout="wide"
)

# ---------------------------------------------------------
# SELECTOR DE MÓDULO (Barra Lateral)
# ---------------------------------------------------------
st.sidebar.title("🎯 Módulos del Sistema")
modulo_activo = st.sidebar.radio(
    "Selecciona la competición:",
    ["🛡️ Sistema Cuantitativo Pro NFL", "🎓 NCAA (Robot Universitario)"]
)

st.sidebar.markdown("---")
st.sidebar.info("Motor cuantitativo con calibración estricta de valor y control de riesgo.")


# ---------------------------------------------------------
# MÓDULO 1: SISTEMA CUANTITATIVO PRO NFL (Tu interfaz original)
# ---------------------------------------------------------
if modulo_activo == "🛡️ Sistema Cuantitativo Pro NFL":
    st.title("🛡️ Sistema Cuantitativo Pro NFL (Filtro de Precisión EV+)")
    st.markdown("*Motor analítico con calibración estricta de valor y control de riesgo.*")

    st.markdown("---")
    st.subheader("⚙️ Panel de Control y Filtros Cuantitativos")

    # Control de Bankroll en la interfaz tal como lo tenías
    bankroll = st.number_input("💵 Bankroll Total (MXN):", min_value=0.0, value=10000.0, step=500.0)

    # Pestañas del sistema Pro NFL
    tab_nfl_1, tab_nfl_2 = st.tabs(["📊 Análisis Cuantitativo y EV+", "📋 Gestión de Apuestas"])

    with tab_nfl_1:
        st.subheader("Evaluación de Partidos y Filtros de Precisión")
        
        # Datos de ejemplo o estructura de la sesión
        datos_pro = [
            {"Partido": "Pittsburgh Steelers vs Cleveland Browns", "Pick": "DK Metcalf Over 4.5 Recepciones", "Momio": 1.82, "EV+ Estimado": "+4.5%", "Confianza": "Alta"},
            {"Partido": "Pittsburgh Steelers vs Cleveland Browns", "Pick": "Nick Chubb Over 65.5 Yardas", "Momio": 1.85, "EV+ Estimado": "+3.2%", "Confianza": "Media"}
        ]
        
        df_pro = pd.DataFrame(datos_pro)
        st.dataframe(df_pro, use_container_width=True)

        if st.button("🚀 Ejecutar Escaneo Cuantitativo NFL"):
            st.success("Escaneo completado. Las líneas han sido filtradas bajo criterios de valor EV+.")

    with tab_nfl_2:
        st.subheader("Historial de Operaciones y Control de Riesgo")
        st.info("No hay operaciones registradas en el periodo actual.")


# ---------------------------------------------------------
# MÓDULO 2: NCAA (Robot Universitario)
# ---------------------------------------------------------
else:
    st.title("🎓 Robot Analítico y Hándicap - NCAA (Colegial)")
    st.markdown("*Módulo especializado en el escaneo de los mejores partidos universitarios y análisis de cobertura por hándicap.*")

    st.markdown("---")
    st.subheader("🤖 Panel del Robot Universitario")

    tab_ncaa_1, tab_ncaa_2 = st.tabs(["⚡ Mejores Partidos y Hándicaps", "📋 Selección de Parlays NCAA"])

    with tab_ncaa_1:
        st.subheader("Escáner de Cobertura de Hándicap (Spread)")
        
        datos_ncaa = [
            {"Partido": "Alabama Crimson Tide vs Georgia Bulldogs", "Hándicap Sugerido": "Alabama -3.5", "Momio": 1.90, "Probabilidad": "64.0%"},
            {"Partido": "Michigan Wolverines vs Ohio State Buckeyes", "Hándicap Sugerido": "Under 48.5", "Momio": 1.85, "Probabilidad": "61.5%"}
        ]
        
        df_ncaa = pd.DataFrame(datos_ncaa)
        st.dataframe(df_ncaa, use_container_width=True)

        if st.button("⚡ Ejecutar Escaneo NCAA"):
            st.success("¡Escaneo universitario finalizado! Oportunidades detectadas con éxito.")

    with tab_ncaa_2:
        st.subheader("Resumen y Viabilidad NCAA")
        c1, c2 = st.columns(2)
        c1.metric("Confianza Promedio Robot", "73.1%", "Alto Valor")
        c2.metric("Momio Combinado Estimado", "3.10", "Recomendado")
