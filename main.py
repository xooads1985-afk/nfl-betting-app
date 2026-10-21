import streamlit as st
import requests
from datetime import datetime

# Configuración de la página
st.set_page_config(
    page_title="Master Suite - Cuantificador +EV",
    page_icon="🏀",
    layout="wide"
)

st.title("🎯 Master Suite: Módulo de Análisis NBA (+EV)")
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

# Sidebar para controles
st.sidebar.header("Panel de Control")
fecha_hoy_api = datetime.now().strftime("%Y%m%d")
fecha_hoy_humana = datetime.now().strftime("%d/%m/%Y")

st.sidebar.info(f"Fecha analizada: {fecha_hoy_humana}")

# Cargar partidos
with st.spinner("Consultando cartelera completa de la NBA..."):
    partidos = obtener_cartelera_pura("basketball", "nba", fecha_hoy_api, fecha_hoy_humana)

st.subheader(f"Partidos Detectados para Hoy ({len(partidos)} en total)")

if partidos:
    for idx, p in enumerate(partidos):
        st.write(f"{idx + 1}. **{p['visita']}** visitando a **{p['local']}**")
else:
    st.warning("No se encontraron partidos para la fecha de hoy o la API tardó en responder.")

st.markdown("---")
st.markdown("*Master Suite v2.0 - Módulo NBA activo con Creador / Filtros cuantitativos.*")
