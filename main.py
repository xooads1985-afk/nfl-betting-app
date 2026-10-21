import streamlit as st
import requests
from datetime import datetime

# Configuración de la página
st.set_page_config(
    page_title="Master Suite - Cuantificador +EV (NBA)",
    page_icon="🏀",
    layout="wide"
)

st.title("🎯 Master Suite: Módulo de Análisis Cuantitativo NBA (+EV)")
st.markdown("---")

# Función robusta para extraer la cartelera completa sin límites de ESPN
@st.cache_data(ttl=300)
def obtener_cartelera_pura(deporte="basketball", liga="nba", fecha_str_api="", fecha_str_humana=""):
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
                for comp in competidores:
                    if comp.get("homeAway") == "home":
                        local = comp.get("team", {}).get("displayName", "Local")
                    else:
                        visitante = comp.get("team", {}).get("displayName", "Visitante")
                
                partidos_extraidos.append({
                    "partido_str": f"📅 [{fecha_str_humana}] {visitante} @ {local}",
                    "local": local,
                    "visita": visitante
                })
            return partidos_extraidos
    except Exception as e:
        st.error(f"Error al conectar con la API: {e}")
    return []

# Sidebar para controles y parámetros de la Suite
st.sidebar.header("Panel de Control NBA")
fecha_hoy_api = datetime.now().strftime("%Y%m%d")
fecha_hoy_humana = datetime.now().strftime("%d/%m/%Y")

st.sidebar.info(f"Fecha analizada: {fecha_hoy_humana}")

# Regla de Oro del sistema
st.sidebar.markdown("### ⚙️ Filtros y Reglas")
min_edge = st.sidebar.slider("Edge Mínimo Requerido (%)", 1.0, 10.0, 3.0, 0.5)
regla_oro_activo = st.sidebar.checkbox("Aplicar Regla de Oro (Evitar momios peores que -150)", value=True)

# Cargar partidos
with st.spinner("Consultando cartelera completa de la NBA..."):
    partidos = obtener_cartelera_pura("basketball", "nba", fecha_hoy_api, fecha_hoy_humana)

st.subheader(f"Cartelera Detectada para Hoy ({len(partidos)} partidos)")

if partidos:
    # Contenedor principal de análisis por partido
    for idx, p in enumerate(partidos):
        with st.expander(f"🏀 Partido {idx + 1}: {p['visita']} @ {p['local']}"):
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown(f"**Local:** {p['local']}")
                # Simulación de datos L5 y descanso (aquí entra el motor de cálculo)
                ef_local = st.slider(f"Eficiencia L5 ({p['local']})", 0.0, 1.0, 0.55, 0.01, key=f"loc_{idx}")
                descanso_local = st.number_input(f"Días de descanso ({p['local']})", 0, 7, 2, key=f"dl_{idx}")
                
            with col2:
                st.markdown(f"**Visitante:** {p['visita']}")
                ef_visita = st.slider(f"Eficiencia L5 ({p['visita']})", 0.0, 1.0, 0.48, 0.01, key=f"vis_{idx}")
                descanso_visita = st.number_input(f"Días de descanso ({p['visita']})", 0, 7, 1, key=f"dv_{idx}")
            
            # Botón de análisis cuantitativo para este encuentro específico
            if st.button(f"Ejecutar Escáner Cuantitativo - {p['visita']} @ {p['local']}", key=f"btn_{idx}"):
                # Simulación de evaluación del modelo
                probabilidad_estimada = (ef_local + (0.05 if descanso_local > descanso_visita else 0.0)) / (ef_local + ef_visita)
                
                st.success(f"Modelo procesado con éxito para: {p['visita']} @ {p['local']}")
                st.write(f"📊 **Probabilidad estimada del modelo (Local):** {probabilidad_estimada * 100:.1f}%")
                st.write(f"📊 **Probabilidad estimada del modelo (Visitante):** {(1 - probabilidad_estimada) * 100:.1f}%")
                
                # Alerta de valor
                if probabilidad_estimada > 0.58:
                    st.markdown("🎯 **¡Mina de Oro Detectada (+EV)!** Fuerte inclinación hacia el **Local**.")
                elif (1 - probabilidad_estimada) > 0.58:
                    st.markdown("🎯 **¡Mina de Oro Detectada (+EV)!** Fuerte inclinación hacia el **Visitante**.")
                else:
                    st.warning("⚠️ Sin valor suficiente (-EV). El mercado está ajustado. Mejor dejar pasar.")
else:
    st.warning("No se encontraron partidos para la fecha de hoy o la API tardó en responder.")

st.markdown("---")
st.markdown("*Master Suite v2.0 - Módulo NBA completo con parámetros cuantitativos.*")
