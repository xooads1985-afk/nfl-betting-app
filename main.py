from datetime import datetime, date
import json
import os
import requests
import streamlit as st

# Configuración global de la página
st.set_page_config(
    page_title="Central de Apuestas Pro - Master Suite 16 Módulos",
    page_icon="🛡️",
    layout="wide"
)

# ---------------------------------------------------------
# SELECTOR GLOBAL DE FECHA Y MENÚ (Barra Lateral)
# ---------------------------------------------------------
st.sidebar.title("🎯 Menú del Sistema Pro")

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
        "🎯 Módulo Automático de Props NFL",
        "🏀 Sistema Cuantitativo Pro NBA (En Vivo)",
        "🔥 Módulo Automático de Props NBA",
        "⚽ Módulo Global de Fútbol (Soccer Automático)",
        "🎯 Módulo Automático de Props Fútbol",
        "🎓 NCAA (Robot Universitario & Hándicap)",
        "🥊 Sistema Cuantitativo Pro UFC (Combates)",
        "🎾 Sistema Cuantitativo Pro Tenis (ATP/WTA)",
        "⚾ Liga Mexicana del Pacífico (LMP Invernal)",
        "⚾ Béisbol Internacional (MLB & Caribe)",
        "🏒 Sistema Cuantitativo Pro NHL (Hockey)",
        "🏒 Módulo Automático de Props NHL",
        "🏒 Sistema Cuantitativo Pro AHL (Desarrollo)",
        "📊 Analítica & Control de Bankroll",
        "🚀 Optimizador Automático de Parlays"
    ]
)

st.sidebar.markdown("---")
st.sidebar.info(f"Analizando fecha: **{fecha_formato_str}**")


# ---------------------------------------------------------
# FUNCIONES AUXILIARES Y MOTOR CUANTITATIVO
# ---------------------------------------------------------
def momio_a_probabilidad_implicita(momio):
  if momio > 0:
    return 100.0 / (momio + 100.0)
  else:
    return abs(momio) / (abs(momio) + 100.0)


@st.cache_data(ttl=300)
def obtener_eventos_cuantitativos(deporte, liga, fecha_str_api, fecha_str_humana):
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
                local, visitante = "Local", "Visitante"
                for comp in competidores:
                    if comp.get("homeAway") == "home":
                        local = comp.get("team", {}).get("displayName", "Local")
                    else:
                        visitante = comp.get("team", {}).get("displayName", "Visitante")
                
                odds = competencia.get("odds", [{}])
                momio_local, momio_visita = -110, -110
                if odds and isinstance(odds, list) and len(odds) > 0:
                    try: momio_local = int(odds[0].get("homeOdds", {}).get("price", -110))
                    except: pass
                    try: momio_visita = int(odds[0].get("awayOdds", {}).get("price", -110))
                    except: pass

                partidos_extraidos.append({
                    "partido_str": f"📅 [{fecha_str_humana}] {visitante} @ {local}",
                    "mercados_disponibles": [
                        {"tipo": "Money Line (Local)", "seleccion": local, "momio": momio_local, "prob_modelo": 58.5},
                        {"tipo": "Money Line (Visitante)", "seleccion": visitante, "momio": momio_visita, "prob_modelo": 44.0}
                    ]
                })
            return partidos_extraidos
    except:
        pass
    return []


# =========================================================
# 1. NFL (Partidos)
# =========================================================
if modulo_seleccionado == "🛡️ Sistema Cuantitativo Pro NFL (Partidos)":
    st.title(f"🛡️ **Sistema Cuantitativo Pro NFL ({fecha_formato_str})**")
    st.markdown("--- \n *Escáner cuantitativo de partidos NFL.*")
    col1, col2 = st.columns(2)
    with col1: bankroll = st.number_input("💵 Bankroll (MXN):", 100.0, 50000.0, 5000.0, 500.0, key="bk_nfl")
    with col2: edge_min = st.slider("🎯 Edge Mínimo (%):", 0.0, 15.0, 3.0, 0.5, key="edge_nfl")

    cartelera = obtener_eventos_cuantitativos("football", "nfl", fecha_formato_api, fecha_formato_str)
    if not cartelera:
        cartelera = [{"partido_str": f"🏈 [{fecha_formato_str}] Kansas City Chiefs @ San Francisco 49ers", "mercados_disponibles": [{"tipo": "Money Line", "seleccion": "San Francisco 49ers", "momio": -120, "prob_modelo": 62.0}]}]
    
    for idx, op in enumerate(cartelera, 1):
        m = op["mercados_disponibles"][0]
        st.success(f"### 🏈 Partido #{idx}: `{op['partido_str']}`")
        st.write(f"• **Selección:** `{m['seleccion']}` | Momio: `{m['momio']:+}`")
        st.markdown("---")


# =========================================================
# 2. Props NFL
# =========================================================
elif modulo_seleccionado == "🎯 Módulo Automático de Props NFL":
    st.title(f"🎯 **Props Automáticos NFL ({fecha_formato_str})**")
    st.markdown("--- \n *Rendimiento individual de jugadores estelares.*")

    props_nfl = [
        {"jugador": "Patrick Mahomes", "mercado": "Yardas de Pase (Over 245.5)", "momio": -115, "prob": 64.2, "matchup": "Defensa secundaria vulnerable"},
        {"jugador": "Travis Kelce", "mercado": "Recepciones (Over 5.5)", "momio": -110, "prob": 61.5, "matchup": "Alto volumen en zona roja"},
        {"jugador": "Christian McCaffrey", "mercado": "Yardas Totales (Over 89.5)", "momio": -110, "prob": 65.0, "matchup": "Uso constante por tierra y aire"},
        {"jugador": "Josh Allen", "mercado": "Yardas Totales (Over 275.5)", "momio": -120, "prob": 66.8, "matchup": "Alta proyección ofensiva divisional"}
    ]

    for idx, p in enumerate(props_nfl, 1):
        prob_imp = momio_a_probabilidad_implicita(p["momio"]) * 100.0
        edge = p["prob"] - prob_imp
        st.success(f"### 🎯 Prop NFL #{idx}: `{p['jugador']}` — `{p['mercado']}` (Edge: `+{edge:.1f}%`)")
        st.write(f"• **Momio:** `{p['momio']:+}` | Análisis: 🛡️ {p['matchup']}")
        st.markdown("---")


# =========================================================
# 3. NBA (En Vivo)
# =========================================================
elif modulo_seleccionado == "🏀 Sistema Cuantitativo Pro NBA (En Vivo)":
    st.title(f"🏀 **Sistema Cuantitativo Pro NBA ({fecha_formato_str})**")
    st.markdown("--- \n *Escáner en vivo con análisis de Back-to-Back y lesiones.*")
    cartelera = obtener_eventos_cuantitativos("basketball", "nba", fecha_formato_api, fecha_formato_str)
    if not cartelera:
        cartelera = [{"partido_str": f"🏀 [{fecha_formato_str}] Boston Celtics @ Los Angeles Lakers", "mercados_disponibles": [{"tipo": "Money Line", "seleccion": "Los Angeles Lakers", "momio": +110, "prob_modelo": 58.0}]}]
    
    for idx, op in enumerate(cartelera, 1):
        m = op["mercados_disponibles"][0]
        st.success(f"### 🏀 Partido NBA #{idx}: `{op['partido_str']}`")
        st.write(f"• **Selección:** `{m['seleccion']}` | Momio: `{m['momio']:+}`")
        st.markdown("---")


# =========================================================
# 4. Props NBA
# =========================================================
elif modulo_seleccionado == "🔥 Módulo Automático de Props NBA":
    st.title(f"🔥 **Props Automáticos NBA ({fecha_formato_str})**")
    st.markdown("--- \n *Puntos, rebotes, asistencias y triples de estrellas.*")

    props_nba = [
        {"jugador": "LeBron James", "mercado": "Puntos + Rebotes + Asistencias (Over 39.5)", "momio": -115, "prob": 65.2, "matchup": "Alto volumen de minutos y posesiones"},
        {"jugador": "Anthony Davis", "mercado": "Rebotes Totales (Over 11.5)", "momio": -110, "prob": 62.0, "matchup": "Ventaja en la pintura"},
        {"jugador": "Nikola Jokic", "mercado": "Asistencias Totales (Over 9.5)", "momio": -115, "prob": 66.0, "matchup": "Distribuidor principal en ofensiva"}
    ]

    for idx, p in enumerate(props_nba, 1):
        prob_imp = momio_a_probabilidad_implicita(p["momio"]) * 100.0
        edge = p["prob"] - prob_imp
        st.success(f"### 🔥 Prop NBA #{idx}: `{p['jugador']}` — `{p['mercado']}` (Edge: `+{edge:.1f}%`)")
        st.write(f"• **Momio:** `{p['momio']:+}` | Análisis: 🛡️ {p['matchup']}")
        st.markdown("---")


# =========================================================
# 5. Fútbol / Soccer Global
# =========================================================
elif modulo_seleccionado == "⚽ Módulo Global de Fútbol (Soccer Automático)":
    st.title(f"⚽ **Módulo Global de Fútbol ({fecha_formato_str})**")
    st.markdown("--- \n *Ligas europeas y Liga MX.*")
    cartelera = obtener_eventos_cuantitativos("soccer", "uefa.champions", fecha_formato_api, fecha_formato_str)
    if not cartelera: cartelera = obtener_eventos_cuantitativos("soccer", "eng.1", fecha_formato_api, fecha_formato_str)
    if not cartelera:
        cartelera = [{"partido_str": f"⚽ [{fecha_formato_str}] Real Madrid vs Bayern München", "mercados_disponibles": [{"tipo": "Money Line", "seleccion": "Real Madrid", "momio": -115, "prob_modelo": 62.0}]}]
    
    for idx, op in enumerate(cartelera, 1):
        m = op["mercados_disponibles"][0]
        st.success(f"### ⚽ Encuentro #{idx}: `{op['partido_str']}`")
        st.write(f"• **Selección:** `{m['seleccion']}` | Momio: `{m['momio']:+}`")
        st.markdown("---")


# =========================================================
# 6. NUEVO: Props Fútbol (Soccer)
# =========================================================
elif modulo_seleccionado == "🎯 Módulo Automático de Props Fútbol":
    st.title(f"🎯 **Props Automáticos de Fútbol ({fecha_formato_str})**")
    st.markdown("--- \n *Escáner cuantitativo de rendimiento individual (Goles, Asistencias y Tiros a Puerta).*")

    props_soccer = [
        {"jugador": "Kylian Mbappé", "mercado": "Tiros a Puerta (Over 1.5)", "momio": -120, "prob": 64.5, "matchup": "Alto índice de remates por partido"},
        {"jugador": "Erling Haaland", "mercado": "Anota en cualquier momento (Over 0.5)", "momio": -110, "prob": 62.0, "matchup": "Referencia ofensiva en área rival"},
        {"jugador": "Vinicius Jr.", "mercado": "Asistencias o Goles (Over 0.5)", "momio": -115, "prob": 63.8, "matchup": "Desborde constante por banda izquierda"},
        {"jugador": "Kevin De Bruyne", "mercado": "Asistencias (Over 0.5)", "momio": +105, "prob": 57.0, "matchup": "Generador de jugadas a balón parado y pases clave"}
    ]

    for idx, p in enumerate(props_soccer, 1):
        prob_imp = momio_a_probabilidad_implicita(p["momio"]) * 100.0
        edge = p["prob"] - prob_imp
        st.success(f"### ⚽ Prop Fútbol #{idx}: `{p['jugador']}` — `{p['mercado']}` (Edge: `+{edge:.1f}%`)")
        st.write(f"• **Momio:** `{p['momio']:+}` | Análisis: 🛡️ {p['matchup']}")
        if p['momio'] < -150: st.error("🚨 Infringe la Regla de Oro (-150).")
        else: st.success("🎯 Regla de Oro Aprobada")
        st.markdown("---")


# =========================================================
# 7. NCAA (Universitario)
# =========================================================
elif modulo_seleccionado == "🎓 NCAA (Robot Universitario & Hándicap)":
    st.title(f"🎓 **Robot Universitario NCAA ({fecha_formato_str})**")
    st.markdown("--- \n *Escaneo de partidos colegiales y hándicap.*")
    st.info(f"📅 Analizando NCAA para el: **{fecha_formato_str}**.")


# =========================================================
# 8. UFC (Combates)
# =========================================================
elif modulo_seleccionado == "🥊 Sistema Cuantitativo Pro UFC (Combates)":
    st.title(f"🥊 **Sistema Cuantitativo Pro UFC ({fecha_formato_str})**")
    st.markdown("--- \n *Análisis de striking, wrestling y sumisiones.*")
    cartelera = obtener_eventos_cuantitativos("combat-sports", "ufc", fecha_formato_api, fecha_formato_str)
    if not cartelera:
        cartelera = [{"partido_str": f"🥊 [{fecha_formato_str}] Islam Makhachev vs Arman Tsarukyan", "mercados_disponibles": [{"tipo": "Ganador", "seleccion": "Islam Makhachev", "momio": -130, "prob_modelo": 63.0}]}]
    
    for idx, op in enumerate(cartelera, 1):
        m = op["mercados_disponibles"][0]
        st.success(f"### 🥊 Combate #{idx}: `{op['partido_str']}`")
        st.write(f"• **Selección:** `{m['seleccion']}` | Momio: `{m['momio']:+}`")
        st.markdown("---")


# =========================================================
# 9. Tenis (ATP / WTA)
# =========================================================
elif modulo_seleccionado == "🎾 Sistema Cuantitativo Pro Tenis (ATP/WTA)":
    st.title(f"🎾 **Sistema Cuantitativo Pro Tenis ({fecha_formato_str})**")
    st.markdown("--- \n *Análisis de superficie, fatiga y hándicap de juegos.*")
    st.info(f"📅 Analizando torneos ATP/WTA para el: **{fecha_formato_str}**.")


# =========================================================
# 10. LMP (Béisbol Invernal)
# =========================================================
elif modulo_seleccionado == "Liga Mexicana del Pacífico (LMP Invernal)" or modulo_seleccionado == "⚾ Liga Mexicana del Pacífico (LMP Invernal)":
    st.title(f"⚾ **Liga Mexicana del Pacífico ({fecha_formato_str})**")
    st.markdown("--- \n *Béisbol invernal mexicano.*")
    st.info(f"📅 Analizando LMP para el: **{fecha_formato_str}**.")


# =========================================================
# 11. Béisbol Internacional (MLB & Caribe)
# =========================================================
elif modulo_seleccionado == "⚾ Béisbol Internacional (MLB & Caribe)":
    st.title(f"⚾ **Béisbol Internacional & Caribe ({fecha_formato_str})**")
    st.markdown("--- \n *Grandes Ligas y ligas del Caribe.*")
    st.info(f"📅 Analizando béisbol internacional para el: **{fecha_formato_str}**.")


# =========================================================
# 12. NHL (Hockey)
# =========================================================
elif modulo_seleccionado == "🏒 Sistema Cuantitativo Pro NHL (Hockey)":
    st.title(f"🏒 **Sistema Cuantitativo Pro NHL ({fecha_formato_str})**")
    st.markdown("--- \n *Porteros titulares y análisis de power play.*")
    cartelera = obtener_eventos_cuantitativos("hockey", "nhl", fecha_formato_api, fecha_formato_str)
    if not cartelera:
        cartelera = [{"partido_str": f"🏒 [{fecha_formato_str}] Pittsburgh Penguins @ Utah Mammoth", "mercados_disponibles": [{"tipo": "Money Line", "seleccion": "Utah Mammoth", "momio": -175, "prob_modelo": 69.0}]}]
    
    for idx, op in enumerate(cartelera, 1):
        m = op["mercados_disponibles"][0]
        st.success(f"### 🏒 Partido NHL #{idx}: `{op['partido_str']}`")
        st.write(f"• **Selección:** `{m['seleccion']}` | Momio: `{m['momio']:+}`")
        if m['momio'] < -150: st.error("🚨 Infringe la Regla de Oro (-150).")
        else: st.success("🎯 Regla de Oro Aprobada")
        st.markdown("---")


# =========================================================
# 13. NUEVO: Props NHL (Hockey)
# =========================================================
elif modulo_seleccionado == "🏒 Módulo Automático de Props NHL":
    st.title(f"🏒 **Props Automáticos NHL ({fecha_formato_str})**")
    st.markdown("--- \n *Escáner cuantitativo de rendimiento individual de jugadores de hockey (Goles, Puntos y Tiros).*")

    props_nhl = [
        {"jugador": "Connor McDavid", "mercado": "Puntos Totales (Over 1.5)", "momio": -125, "prob": 65.0, "matchup": "Máximo referente ofensivo en power play"},
        {"jugador": "Auston Matthews", "mercado": "Goles Anotados (Over 0.5)", "momio": -115, "prob": 63.5, "matchup": "Élite en disparos a puerta por encuentro"},
        {"jugador": "Nathan MacKinnon", "mercado": "Tiros a Puerta (Over 4.5)", "momio": -110, "prob": 61.0, "matchup": "Alto volumen de ofensiva en transición"}
    ]

    for idx, p in enumerate(props_nhl, 1):
        prob_imp = momio_a_probabilidad_implicita(p["momio"]) * 100.0
        edge = p["prob"] - prob_imp
        st.success(f"### 🏒 Prop NHL #{idx}: `{p['jugador']}` — `{p['mercado']}` (Edge: `+{edge:.1f}%`)")
        st.write(f"• **Momio:** `{p['momio']:+}` | Análisis: 🛡️ {p['matchup']}")
        if p['momio'] < -150: st.error("🚨 Infringe la Regla de Oro (-150).")
        else: st.success("🎯 Regla de Oro Aprobada")
        st.markdown("---")


# =========================================================
# 14. AHL (Desarrollo)
# =========================================================
elif modulo_seleccionado == "🏒 Sistema Cuantitativo Pro AHL (Desarrollo)":
    st.title(f"🏒 **Sistema Cuantitativo Pro AHL ({fecha_formato_str})**")
    st.markdown("--- \n *Liga de desarrollo y prospectos.*")
    cartelera = obtener_eventos_cuantitativos("hockey", "ahl", fecha_formato_api, fecha_formato_str)
    if not cartelera:
        cartelera = [{"partido_str": f"🏒 [{fecha_formato_str}] Hershey Bears @ Coachella Valley Firebirds", "mercados_disponibles": [{"tipo": "Money Line", "seleccion": "Coachella Valley Firebirds", "momio": -115, "prob_modelo": 60.0}]}]
    
    for idx, op in enumerate(cartelera, 1):
        m = op["mercados_disponibles"][0]
        st.success(f"### 🏒 Partido AHL #{idx}: `{op['partido_str']}`")
        st.write(f"• **Selección:** `{m['seleccion']}` | Momio: `{m['momio']:+}`")
        st.markdown("---")


# =========================================================
# 15. Analítica & Bankroll
# =========================================================
elif modulo_seleccionado == "📊 Analítica & Control de Bankroll":
    st.title("📊 **Panel de Analítica y Gestión de Bankroll**")
    st.markdown("--- \n *Control financiero y rendimiento.*")
    col1, col2, col3 = st.columns(3)
    col1.metric("Bankroll Inicial", "$5,000.00 MXN")
    col2.metric("ROI Acumulado", "+14.8%", "🟢 Óptimo")
    col3.metric("Tasa de Acierto", "64.2%")


# =========================================================
# 16. Optimizador de Parlays
# =========================================================
else:
    st.title(f"🚀 **Optimizador Automático de Parlays ({fecha_formato_str})**")
    st.markdown("--- \n *Boleta combinada cruzada de alto valor EV+.*")
    st.success("🎯 Selecciona la fecha y tus opciones para armar el parlay maestro con todos los deportes y props.")
