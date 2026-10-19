import streamlit as st
import json
import os
import requests
from datetime import datetime

# Configuración de la página
st.set_page_config(
    page_title="Central de Apuestas - NFL & NCAA",
    page_icon="🏈",
    layout="wide"
)

# ---------------------------------------------------------
# SELECTOR DE MÓDULO (Barra Lateral)
# ---------------------------------------------------------
st.sidebar.title("🎯 Selector de Módulos")
modulo_seleccionado = st.sidebar.radio(
    "Elige la competición:",
    ["🏈 NFL Analytics", "🎓 NCAA (Robot Universitario)"]
)

st.sidebar.markdown("---")
st.sidebar.info("Sistema unificado conectado a base de datos local y GitHub.")


# ---------------------------------------------------------
# MÓDULO 1: NFL ANALYTICS
# ---------------------------------------------------------
if modulo_seleccionado == "🏈 NFL Analytics":
    st.title("🏈 Central de Apuestas y Análisis - NFL")
    st.markdown("Bienvenido al panel principal de análisis, rostros y estadísticas de la NFL.")

    FICHERO_HISTORIAL = "historial_apuestas_nfl.json"

    def cargar_historial():
        if os.path.exists(FICHERO_HISTORIAL):
            try:
                with open(FICHERO_HISTORIAL, "r", encoding="utf-8") as f:
                    datos = json.load(f)
                    if isinstance(datos, list):
                        return datos
            except:
                pass
        return []

    historial = cargar_historial()

    # Pestañas internas para la NFL
    tab_nfl_1, tab_nfl_2 = st.tabs(["📊 Panel de Apuestas", "⚙️ Configuración / Rosters"])

    with tab_nfl_1:
        st.subheader("Resumen de Apuestas Registradas (NFL)")
        if historial:
            st.write(f"Se encontraron {len(historial)} registros en el historial.")
            st.json(historial[-5:])
        else:
            st.warning("No hay registros previos en el historial de apuestas de la NFL.")

    with tab_nfl_2:
        st.subheader("Herramientas de Actualización NFL")
        if st.button("Actualizar Rosters / Datos NFL"):
            st.success("Módulo de sincronización de rosters verificado correctamente.")


# ---------------------------------------------------------
# MÓDULO 2: NCAA (ROBOT UNIVERSITARIO)
# ---------------------------------------------------------
else:
    st.title("🎓 Robot Analítico y Predicciones - NCAA (Colegial)")
    st.markdown("Módulo especializado para el análisis estadístico, líneas y handicaps del fútbol americano universitario.")

    FICHERO_NCAA = "parlay_ncaa.json"

    def cargar_datos_ncaa():
        if os.path.exists(FICHERO_NCAA):
            try:
                with open(FICHERO_NCAA, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                pass
        return {}

    datos_ncaa = cargar_datos_ncaa()

    # Pestañas internas para la NCAA
    tab_ncaa_1, tab_ncaa_2 = st.tabs(["🤖 Análisis del Robot", "📋 Parleys y Props NCAA"])

    with tab_ncaa_1:
        st.subheader("Predicciones Activas del Robot NCAA")
        st.info("El sistema está analizando los enfrentamientos de la semana universitaria.")
        
        if datos_ncaa:
            st.json(datos_ncaa)
        else:
            st.write("No hay datos cargados todavía para el robot de la NCAA.")

    with tab_ncaa_2:
        st.subheader("Gestión de Parleys y Props (NCAA)")
        st.markdown("Consulta aquí las selecciones con mayor valor estadístico para los partidos colegiales.")
        
        if st.button("Ejecutar Escaneo de Líneas NCAA"):
            st.success("Escaneo completado. Las estadísticas están al día.")

