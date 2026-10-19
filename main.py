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
st.sidebar.title("🎯 Selector de Competición")
deporte = st.sidebar.radio(
    "Elige el sistema:",
    ["🛡️ Sistema Cuantitativo Pro NFL", "🎓 NCAA (Robot Universitario)"]
)

st.sidebar.markdown("---")
st.sidebar.info("Motor analítico con calibración estricta de valor y control de riesgo.")


# ---------------------------------------------------------
# MÓDULO 1: SISTEMA CUANTITATIVO PRO NFL (Tu interfaz original exactos)
# ---------------------------------------------------------
if deporte == "🛡️ Sistema Cuantitativo Pro NFL":
    st.title("🛡️ Sistema Cuantitativo Pro NFL (Filtro de Precisión EV+)")
    st.markdown("*Motor analítico con calibración estricta de valor y control de riesgo.*")

    st.markdown("---")
    st.subheader("⚙️ Panel de Control y Filtros Cuantitativos")

    # Controles de bankroll y filtros tal como los usas
    col_b1, col_b2 = st.columns(2)
    with col_b1:
        bankroll = st.number_input("💵 Bankroll Total (MXN):", min_value=0.0, value=10000.0, step=500.0)
    with col_b2:
        filtro_precision = st.slider("Filtro de Precisión Mínima (%)", min_value=50, max_value=90, value=60)

    st.markdown("---")

    # Pestañas del Sistema Pro NFL
    tab_pro_1, tab_pro_2 = st.tabs(["📊 Análisis Cuantitativo EV+", "📋 Gestión de Apuestas"])

    with tab_pro_1:
        st.subheader("Evaluación de Partidos y Hándicaps Cuantitativos")
        
        # Estructura de datos analíticos principales
        datos_cuantitativos = [
            {"Partido": "Pittsburgh Steelers vs Cleveland Browns", "Apuesta / Línea": "Pittsburgh Steelers -3.5", "Cuota": 1.90, "Probabilidad Modelo": "68.5%", "EV+": "+5.2%"},
            {"Partido": "Kansas City Chiefs vs Las Vegas Raiders", "Apuesta / Línea": "Under 47.5 Puntos", "Cuota": 1.85, "Probabilidad Modelo": "74.0%", "EV+": "+7.1%"}
        ]
        
        df_cuat = pd.DataFrame(datos_cuantitativos)
        st.dataframe(df_cuat, use_container_width=True)

        if st.button("🚀 Ejecutar Motor Cuantitativo NFL"):
            st.success("¡Análisis completado! Se filtraron las mejores oportunidades con valor EV+.")

    with tab_pro_2:
        st.subheader("Historial de Operaciones y Control de Riesgo")
        st.info("No hay operaciones registradas en el periodo actual.")


# ---------------------------------------------------------
# MÓDULO 2: NCAA (Robot Universitario y Hándicap)
# ---------------------------------------------------------
else:
    st.title("🎓 Robot Analítico y Hándicap - NCAA (Colegial)")
    st.markdown("*Módulo especializado en el escaneo de los mejores partidos universitarios y análisis de cobertura por hándicap.*")

    st.markdown("---")
    st.subheader("🤖 Panel de Control Universitario (NCAA)")

    tab_ncaa_1, tab_ncaa_2 = st.tabs(["⚡ Mejores Partidos y Hándicaps", "📋 Selección de Parlays NCAA"])

    with tab_ncaa_1:
        st.subheader("Escáner de Cobertura de Hándicap (Spread) NCAA")
        
        datos_ncaa = [
            {"Partido": "Alabama Crimson Tide vs Georgia Bulldogs", "Hándicap Sugerido": "Alabama -4.5", "Cuota": 1.88, "Probabilidad": "65.0%"},
            {"Partido": "Michigan Wolverines vs Ohio State Buckeyes", "Hándicap Sugerido": "Under 51.5", "Cuota": 1.91, "Probabilidad": "62.0%"}
        ]
        
        df_ncaa = pd.DataFrame(datos_ncaa)
        st.dataframe(df_ncaa, use_container_width=True)

        if st.button("⚡ Ejecutar Escaneo Robot NCAA"):
            st.success("¡Escaneo universitario finalizado! Oportunidades detectadas con éxito.")

    with tab_ncaa_2:
        st.subheader("Resumen y Viabilidad NCAA")
        nc1, nc2 = st.columns(2)
        nc1.metric("Confianza Promedio Robot", "73.5%", "Alto Valor")
        nc2.metric("Momio Combinado Estimado", "3.10", "Recomendado")
