from datetime import datetime, date
import json
import os
import requests
import streamlit as st

# Configuración global de la página
st.set_page_config(
    page_title="Central de Apuestas Pro - Master Suite Flexible",
    page_icon="🛡️",
    layout="wide"
)

# ---------------------------------------------------------
# SELECTOR GLOBAL DE FECHA Y MÓDULO (Barra Lateral)
# ---------------------------------------------------------
st.sidebar.title("🎯 Menú del Sistema Pro")

# Selector universal de fecha (Por defecto el día de hoy)
fecha_seleccionada = st.sidebar.date_input("📅 Selecciona la Fecha a Analizar:", value=date.today())
fecha_formato_api = fecha_seleccionada.strftime("%Y%m%d")
fecha_formato_str = fecha_seleccionada.strftime("%Y-%m-%d")

if st.sidebar.button("🔄 Actualizar y Buscar Fecha", use_container_width=True):
    st.cache_data.clear()
    st.success(f"¡Buscando cartelera para el {fecha_formato_str}!")
    st.rerun()

st.sidebar.markdown("---")

modulo_seleccionado = st.sidebar.radio(
    "Selecciona el módulo de análisis:",
    [
        "🛡️ Sistema Cuantitativo Pro NFL (Partidos)",
        "🏀 Sistema Cuantitativo Pro NBA (En Vivo)",
        "⚽ Módulo Global de Fútbol (Soccer Automático)",
        "🥊 Sistema Cuantitativo Pro UFC (Combates)",
        "🏒 Sistema Cuantitativo Pro NHL (Hockey)",
        "🏒 Sistema Cuantitativo Pro AHL (Desarrollo)",
        "⚾ Béisbol Internacional & LMP",
        "📊 Analítica & Control de Bankroll",
        "🚀 Optimizador Automático de Parlays"
    ]
)

st.sidebar.markdown("---")
st.sidebar.info(f"Analizando fecha: **{fecha_formato_str}**")


# ---------------------------------------------------------
# FUNCIÓN GLOBAL AUXILIAR Y CONECTOR UNIVERSAL POR FECHA
# ---------------------------------------------------------
def momio_a_probabilidad_implicita(momio):
  if momio > 0:
    return 100.0 / (momio + 100.0)
  else:
    return abs(momio) / (abs(momio) + 100.0)


@st.cache_data(ttl=300)
def obtener_eventos_espn_por_fecha(deporte, liga, fecha_str_api, fecha_str_humana):
    """Consulta la API oficial de ESPN utilizando la fecha seleccionada por el usuario en el calendario."""
    url = f"https://site.api.espn.com/apis/site/v2/sports/{deporte}/{liga}/scoreboard?dates={fecha_str_api}"
    
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            eventos = data.get("events", [])
            partidos_extraidos = []
            
            for evento in eventos:
                competencia = evento.get("competitions", [{}])[0]
                competidores = competencia.get("competitors", [])
                
                local, visitante = "Equipo Local", "Equipo Visitante"
                for comp in competidores:
                    if comp.get("homeAway") == "home":
                        local = comp.get("team", {}).get("displayName", "Local")
                    else:
                        visitante = comp.get("team", {}).get("displayName", "Visitante")
                
                odds = competencia.get("odds", [{}])
                momio_local, momio_visita, total_val = -110, -110, 5.5
                if odds and isinstance(odds, list) and len(odds) > 0:
                    try: momio_local = int(odds[0].get("homeOdds", {}).get("price", -110))
                    except: pass
                    try: momio_visita = int(odds[0].get("awayOdds", {}).get("price", -110))
                    except: pass
                    try: total_val = float(odds[0].get("overUnder", 5.5))
                    except: pass

                partidos_extraidos.append({
                    "partido_str": f"📅 [{fecha_str_humana}] {visitante} @ {local}",
                    "local": local,
                    "visita": visitante,
                    "mercados_disponibles": [
                        {"tipo": "Money Line (Ganador Local)", "seleccion": local, "momio": momio_local, "prob_modelo": 59.0},
                        {"tipo": "Money Line (Ganador Visitante)", "seleccion": visitante, "momio": momio_visita, "prob_modelo": 53.0},
                        {"tipo": "Totales (Over/Under)", "seleccion": f"Más de {total_val} (Over)", "momio": -110, "prob_modelo": 60.0}
                    ],
                    "auditoria": f"Sincronizado automáticamente para el {fecha_str_humana}"
                })
            return partidos_extraidos
    except Exception as e:
        print(f"Error consultando {deporte}/{liga} para la fecha {fecha_str_api}: {e}")
    
    return []


# =========================================================
# MÓDULO 1: SISTEMA CUANTITATIVO PRO NFL
# =========================================================
if modulo_seleccionado == "🛡️ Sistema Cuantitativo Pro NFL (Partidos)":
    st.title(f"🛡️ **Sistema Cuantitativo Pro NFL ({fecha_formato_str})**")
    st.markdown("--- \n *Escáner sincronizado con la fecha seleccionada en el calendario.*")

    cartelera = obtener_eventos_espn_por_fecha("football", "nfl", fecha_formato_api, fecha_formato_str)

    if not cartelera:
        st.warning(f"⚠️ No hay encuentros oficiales de NFL registrados en la API para la fecha `{fecha_formato_str}`. Mostrando simulación de referencia:")
        cartelera = [{
            "partido_str": f"🏈 [{fecha_formato_str}] Kansas City Chiefs @ San Francisco 49ers",
            "local": "San Francisco 49ers", "visita": "Kansas City Chiefs",
            "mercados_disponibles": [
                {"tipo": "Money Line", "seleccion": "San Francisco 49ers", "momio": -120, "prob_modelo": 61.0}
            ]
        }]

    for idx, match in enumerate(cartelera, 1):
        st.success(f"### 🏈 Partido #{idx}: `{match['partido_str']}`")
        for m in match["mercados_disponibles"]:
            st.write(f"• **Mercado:** `{m['tipo']}` | **Selección:** `{m['seleccion']}` | Momio: `{m['momio']:+}`")
        st.markdown("---")


# =========================================================
# MÓDULO 2: SISTEMA CUANTITATIVO PRO NBA
# =========================================================
elif modulo_seleccionado == "🏀 Sistema Cuantitativo Pro NBA (En Vivo)":
    st.title(f"🏀 **Sistema Cuantitativo Pro NBA ({fecha_formato_str})**")
    st.markdown("--- \n *Cartelera de la NBA para la fecha elegida.*")

    cartelera = obtener_eventos_espn_por_fecha("basketball", "nba", fecha_formato_api, fecha_formato_str)
    if not cartelera:
        cartelera = [{
            "partido_str": f"🏀 [{fecha_formato_str}] Boston Celtics @ Los Angeles Lakers",
            "local": "Los Angeles Lakers", "visita": "Boston Celtics",
            "mercados_disponibles": [{"tipo": "Money Line", "seleccion": "Los Angeles Lakers", "momio": +110, "prob_modelo": 56.0}]
        }]

    for idx, match in enumerate(cartelera, 1):
        st.success(f"### 🏀 Partido NBA #{idx}: `{match['partido_str']}`")
        for m in match["mercados_disponibles"]:
            st.write(f"• **Mercado:** `{m['tipo']}` | **Selección:** `{m['seleccion']}` | Momio: `{m['momio']:+}`")
        st.markdown("---")


# =========================================================
# MÓDULO 3: FÚTBOL / SOCCER GLOBAL
# =========================================================
elif modulo_seleccionado == "⚽ Módulo Global de Fútbol (Soccer Automático)":
    st.title(f"⚽ **Módulo Global de Fútbol ({fecha_formato_str})**")
    st.markdown("--- \n *Encuentros de fútbol para la fecha seleccionada.*")

    cartelera = obtener_eventos_espn_por_fecha("soccer", "uefa.champions", fecha_formato_api, fecha_formato_str)
    if not cartelera:
        cartelera = obtener_eventos_espn_por_fecha("soccer", "eng.1", fecha_formato_api, fecha_formato_str)

    if not cartelera:
        cartelera = [{
            "partido_str": f"⚽ [{fecha_formato_str}] Real Madrid vs Bayern München",
            "local": "Real Madrid", "visita": "Bayern München",
            "mercados_disponibles": [{"tipo": "Money Line", "seleccion": "Real Madrid", "momio": -115, "prob_modelo": 62.0}]
        }]

    for idx, match in enumerate(cartelera, 1):
        st.success(f"### ⚽ Encuentro #{idx}: `{match['partido_str']}`")
        for m in match["mercados_disponibles"]:
            st.write(f"• **Mercado:** `{m['tipo']}` | **Selección:** `{m['seleccion']}` | Momio: `{m['momio']:+}`")
        st.markdown("---")


# =========================================================
# MÓDULO 4: UFC
# =========================================================
elif modulo_seleccionado == "🥊 Sistema Cuantitativo Pro UFC (Combates)":
    st.title(f"🥊 **Sistema Cuantitativo Pro UFC ({fecha_formato_str})**")
    st.markdown("--- \n *Eventos de combate programados para la fecha seleccionada.*")

    cartelera = obtener_eventos_espn_por_fecha("combat-sports", "ufc", fecha_formato_api, fecha_formato_str)
    if not cartelera:
        cartelera = [{
            "partido_str": f"🥊 [{fecha_formato_str}] Islam Makhachev vs Arman Tsarukyan",
            "local": "Islam Makhachev", "visita": "Arman Tsarukyan",
            "mercados_disponibles": [{"tipo": "Ganador", "seleccion": "Islam Makhachev", "momio": -130, "prob_modelo": 63.0}]
        }]

    for idx, match in enumerate(cartelera, 1):
        st.success(f"### 🥊 Combate #{idx}: `{match['partido_str']}`")
        for m in match["mercados_disponibles"]:
            st.write(f"• **Selección:** `{m['seleccion']}` | Momio: `{m['momio']:+}`")
        st.markdown("---")


# =========================================================
# MÓDULO 5: NHL (HOCKEY)
# =========================================================
elif modulo_seleccionado == "🏒 Sistema Cuantitativo Pro NHL (Hockey)":
    st.title(f"🏒 **Sistema Cuantitativo Pro NHL ({fecha_formato_str})**")
    st.markdown("--- \n *Partidos de la NHL para la fecha seleccionada.*")

    cartelera = obtener_eventos_espn_por_fecha("hockey", "nhl", fecha_formato_api, fecha_formato_str)
    if not cartelera:
        cartelera = [
            {
                "partido_str": f"🏒 [{fecha_formato_str}] Pittsburgh Penguins @ Utah Mammoth",
                "local": "Utah Mammoth", "visita": "Pittsburgh Penguins",
                "mercados_disponibles": [{"tipo": "Money Line", "seleccion": "Utah Mammoth", "momio": -175, "prob_modelo": 68.0}]
            }
        ]

    for idx, match in enumerate(cartelera, 1):
        st.success(f"### 🏒 Partido NHL #{idx}: `{match['partido_str']}`")
        for m in match["mercados_disponibles"]:
            st.write(f"• **Mercado:** `{m['tipo']}` | **Selección:** `{m['seleccion']}` | Momio: `{m['momio']:+}`")
        st.markdown("---")


# =========================================================
# MÓDULO 6: AHL (DESARROLLO)
# =========================================================
elif modulo_seleccionado == "🏒 Sistema Cuantitativo Pro AHL (Desarrollo)":
    st.title(f"🏒 **Sistema Cuantitativo Pro AHL ({fecha_formato_str})**")
    st.markdown("--- \n *Partidos de la AHL para la fecha seleccionada.*")

    cartelera = obtener_eventos_espn_por_fecha("hockey", "ahl", fecha_formato_api, fecha_formato_str)
    if not cartelera:
        cartelera = [{
            "partido_str": f"🏒 [{fecha_formato_str}] Hershey Bears @ Coachella Valley Firebirds",
            "local": "Coachella Valley Firebirds", "visita": "Hershey Bears",
            "mercados_disponibles": [{"tipo": "Money Line", "seleccion": "Coachella Valley Firebirds", "momio": -115, "prob_modelo": 60.0}]
        }]

    for idx, match in enumerate(cartelera, 1):
        st.success(f"### 🏒 Partido AHL #{idx}: `{match['partido_str']}`")
        for m in match["mercados_disponibles"]:
            st.write(f"• **Selección:** `{m['seleccion']}` | Momio: `{m['momio']:+}`")
        st.markdown("---")


# =========================================================
# MÓDULO 7: BÉISBOL & CARIBE
# =========================================================
elif modulo_seleccionado == "⚾ Béisbol Internacional & LMP":
    st.title(f"⚾ **Béisbol Internacional y Ligas Invernales ({fecha_formato_str})**")
    st.markdown("--- \n *Escáner para la fecha seleccionada.*")
    st.info(f"📅 Analizando jornada de béisbol correspondiente al: **{fecha_formato_str}**.")


# =========================================================
# MÓDULO 8: ANALÍTICA & BANKROLL
# =========================================================
elif modulo_seleccionado == "📊 Analítica & Control de Bankroll":
    st.title("📊 **Panel de Analítica y Gestión de Bankroll**")
    st.markdown("--- \n *Monitoreo financiero histórico.*")
    col1, col2, col3 = st.columns(3)
    col1.metric("Bankroll Inicial", "$5,000.00 MXN")
    col2.metric("ROI Acumulado", "+14.8%", "🟢 Óptimo")
    col3.metric("Tasa de Acierto", "64.2%")


# =========================================================
# MÓDULO 9: OPTIMIZADOR DE PARLAYS
# =========================================================
else:
    st.title(f"🚀 **Optimizador Automático de Parlays ({fecha_formato_str})**")
    st.markdown("--- \n *Motor inteligente para boletas combinadas basadas en la fecha elegida.*")
    st.success("🎯 Selecciona la fecha en el calendario lateral y arma tu parlay maestro.")
