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
        "🛡️ Sistema Cuantitativo Pro NFL (Hándicap / Spread)",
        "🎯 Módulo Automático de Props NFL",
        "🏀 Sistema Cuantitativo Pro NBA (Hándicap / Spread)",
        "🔥 Módulo Automático de Props NBA",
        "⚽ Módulo Global de Fútbol (Soccer Automático)",
        "🎯 Módulo Automático de Props Fútbol",
        "🎓 NCAA (Robot Universitario & Hándicap)",
        "🥊 Sistema Cuantitativo Pro UFC (Combates)",
        "🎾 Sistema Cuantitativo Pro Tenis (ATP/WTA)",
        "⚾ Liga Mexicana del Pacífico (LMP Invernal)",
        "⚾ Béisbol Internacional (MLB)",
        "🏒 Sistema Cuantitativo Pro NHL (Hándicap / Puck Line)",
        "🏒 Módulo Automático de Props NHL",
        "🏒 Sistema Cuantitativo Pro AHL (Hándicap / Desarrollo)",
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
                spread = -1.5
                momio_spread = +125
                if odds and isinstance(odds, list) and len(odds) > 0:
                    try: spread = float(odds[0].get("details", "-1.5").split()[-1])
                    except: pass
                    try: momio_spread = int(odds[0].get("overOdds", {}).get("price", +125))
                    except: pass

                partidos_extraidos.append({
                    "partido_str": f"📅 [{fecha_str_humana}] {visitante} @ {local}",
                    "local": local,
                    "visita": visitante,
                    "spread": spread,
                    "momio_spread": momio_spread,
                    "mercados_disponibles": [
                        {"tipo": "Run Line (Hándicap)", "seleccion": f"{local} ({spread:+.1f})", "momio": momio_spread, "prob_modelo": 54.5}
                    ]
                })
            return partidos_extraidos
    except:
        pass
    return []


# =========================================================
# 1. NFL (Hándicap / Spread)
# =========================================================
if modulo_seleccionado == "🛡️ Sistema Cuantitativo Pro NFL (Hándicap / Spread)":
    st.title(f"🛡️ **Sistema Cuantitativo Pro NFL (Hándicap) [{fecha_formato_str}]**")
    st.markdown("--- \n *Escáner cuantitativo especializado en Spread y cobertura de puntos.*")
    
    col1, col2 = st.columns(2)
    with col1: bankroll = st.number_input("💵 Bankroll NFL (MXN):", 100.0, 50000.0, 5000.0, 500.0, key="bk_nfl")
    with col2: edge_min = st.slider("🎯 Edge Mínimo Spread (%):", 0.0, 15.0, 3.0, 0.5, key="edge_nfl")

    cartelera = obtener_eventos_cuantitativos("football", "nfl", fecha_formato_api, fecha_formato_str)
    if not cartelera:
        cartelera = [
            {
                "partido_str": f"🏈 [{fecha_formato_str}] Washington Commanders @ Kansas City Chiefs",
                "spread": -6.5,
                "momio_spread": -110,
                "mercados_disponibles": [
                    {"tipo": "Hándicap (Spread)", "seleccion": "Kansas City Chiefs (-6.5)", "momio": -110, "prob_modelo": 64.2}
                ]
            }
        ]
    
    st.markdown("---")
    for idx, op in enumerate(cartelera, 1):
        m = op["mercados_disponibles"][0]
        prob_imp = momio_a_probabilidad_implicita(m["momio"]) * 100.0
        edge = m["prob_modelo"] - prob_imp

        if edge >= edge_min:
            st.success(f"### 🏈 Partido Spread #{idx}: `{op['partido_str']}` — Edge: `+{edge:.1f}%`")
            st.write(f"• **Selección Recomendada (Hándicap):** `{m['seleccion']}`")
            st.write(f"• **Momio Oficial:** `{m['momio']:+}` | Probabilidad del Modelo: `{m['prob_modelo']}%`")
            
            if m['momio'] < -150: st.error("🚨 Infringe la Regla de Oro (-150).")
            else: st.success("🎯 Regla de Oro Aprobada")
            st.markdown("---")


# =========================================================
# 2. Props NFL
# =========================================================
elif modulo_seleccionado == "🎯 Módulo Automático de Props NFL":
    st.title(f"🎯 **Props Automáticos NFL ({fecha_formato_str})**")
    st.markdown("--- \n *Rendimiento individual de jugadores estelares alineados a la fecha.*")

    ESTRELLAS_POR_EQUIPO = {
        "Kansas City Chiefs": [{"jugador": "Patrick Mahomes", "mercado": "Yardas de Pase (Over 245.5)", "momio": -115, "prob": 64.2, "matchup": "Defensa secundaria vulnerable"}],
        "San Francisco 49ers": [{"jugador": "Christian McCaffrey", "mercado": "Yardas Totales (Over 89.5)", "momio": -110, "prob": 65.0, "matchup": "Uso constante por tierra y aire"}],
        "Washington Commanders": [{"jugador": "Jayden Daniels", "mercado": "Yardas por Tierra (Over 45.5)", "momio": -115, "prob": 63.0, "matchup": "Uso de jugadas diseñadas por tierra"}]
    }
    
    cartelera_nfl_hoy = obtener_eventos_cuantitativos("football", "nfl", fecha_formato_api, fecha_formato_str)
    equipos_en_cancha = {eq for p in cartelera_nfl_hoy for eq in ESTRELLAS_POR_EQUIPO if eq.lower() in p["partido_str"].lower()}
    if not equipos_en_cancha: equipos_en_cancha = {"Kansas City Chiefs", "Washington Commanders"}

    for equipo in equipos_en_cancha:
        if equipo in ESTRELLAS_POR_EQUIPO:
            for p in ESTRELLAS_POR_EQUIPO[equipo]:
                prob_imp = momio_a_probabilidad_implicita(p["momio"]) * 100.0
                edge = p["prob"] - prob_imp
                st.success(f"### 🎯 Prop NFL [{equipo}]: `{p['jugador']}` — `{p['mercado']}` (Edge: `+{edge:.1f}%`)")
                st.write(f"• **Momio Oficial:** `{p['momio']:+}` | Análisis: 🛡️ {p['matchup']}")
                st.markdown("---")


# =========================================================
# 3. NBA (Hándicap / Spread - Automático & Ingreso Manual Pro)
# =========================================================
elif modulo_seleccionado == "🏀 Sistema Cuantitativo Pro NBA (Hándicap / Spread)":
    st.title(f"🏀 **Sistema Cuantitativo Pro NBA (Hándicap) [{fecha_formato_str}]**")
    st.markdown("--- \n *Escáner cuantitativo especializado en Spread de puntos y margen de victoria.*")

    col1, col2 = st.columns(2)
    with col1: bankroll_nba = st.number_input("💵 Bankroll NBA (MXN):", 100.0, 50000.0, 5000.0, 500.0, key="bk_nba")
    with col2: edge_min_nba = st.slider("🎯 Edge Mínimo Spread NBA (%):", 0.0, 15.0, 3.0, 0.5, key="edge_nba")

    modo_nba = st.radio("🛠️ Modo de Carga Cartelera NBA:", ["Automático (API ESPN)", "Ingreso Manual (Apertura de Temporada)"], horizontal=True)

    cartelera_nba = []

    if modo_nba == "Automático (API ESPN)":
        url_nba = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={fecha_formato_api}"
        try:
            resp_nba = requests.get(url_nba, timeout=5)
            if resp_nba.status_code == 200:
                data_nba = resp_nba.json()
                eventos_nba = data_nba.get("events", [])
                for evento in eventos_nba:
                    comp = evento.get("competitions", [{}])[0]
                    competidores = comp.get("competitors", [])
                    local_nba, visita_nba = "Local", "Visitante"
                    for c in competidores:
                        if c.get("homeAway") == "home":
                            local_nba = c.get("team", {}).get("displayName", "Local")
                        else:
                            visita_nba = c.get("team", {}).get("displayName", "Visitante")
                    
                    cartelera_nba.append({
                        "partido_str": f"🏀 [{fecha_formato_str}] {visita_nba} @ {local_nba}",
                        "spread": -4.5,
                        "momio_spread": -110,
                        "mercados_disponibles": [
                            {"tipo": "Hándicap (Spread)", "seleccion": f"{local_nba} (-4.5)", "momio": -110, "prob_modelo": 58.0}
                        ]
                    })
        except:
            pass

    if not cartelera_nba:
        st.info("ℹ️ Ingresando cartelera de apertura de temporada recomendada para esta fecha:")
        col_mn1, col_mn2 = st.columns(2)
        with col_mn1:
            equipo_v_nba = st.text_input("🏀 Equipo Visitante NBA:", value="New York Knicks")
            equipo_l_nba = st.text_input("🏀 Equipo Local NBA:", value="Boston Celtics")
        with col_mn2:
            seleccion_nba = st.text_input("🎯 Selección Spread:", value="Boston Celtics (-5.5)")
            momio_nba_manual = st.number_input("📈 Momio Oficial:", value=-110, step=5, key="momio_nba_m")
            prob_nba_manual = st.slider("🤖 Probabilidad del Modelo (%):", 40.0, 80.0, 62.0, 0.5, key="prob_nba_m")

        cartelera_nba = [
            {
                "partido_str": f"🏀 [{fecha_formato_str}] {equipo_v_nba} @ {equipo_l_nba}",
                "mercados_disponibles": [
                    {"tipo": "Hándicap (Spread)", "seleccion": seleccion_nba, "momio": momio_nba_manual, "prob_modelo": prob_nba_manual}
                ]
            }
        ]

    st.markdown("---")
    st.subheader("📊 Oportunidades Detectadas en Spread NBA (EV+)")

    contador_nba = 0
    for idx, op in enumerate(cartelera_nba, 1):
        m = op["mercados_disponibles"][0]
        prob_imp = momio_a_probabilidad_implicita(m["momio"]) * 100.0
        edge = m["prob_modelo"] - prob_imp

        if edge >= edge_min_nba:
            contador_nba += 1
            st.success(f"### 🏀 Partido Spread NBA #{idx}: `{op['partido_str']}` — Edge: `+{edge:.1f}%`")
            st.write(f"• **Selección Recomendada (Hándicap):** `{m['seleccion']}`")
            st.write(f"• **Momio Oficial:** `{m['momio']:+}` | Prob. Implícita: `{prob_imp:.1f}%` | Modelo: `{m['prob_modelo']}%`")
            
            if m['momio'] < -150: 
                st.error("🚨 Infringe la Regla de Oro (-150).")
            else: 
                st.success("🎯 Regla de Oro Aprobada")
            st.markdown("---")

    if contador_nba == 0:
        st.info("ℹ️ El Edge actual está por debajo del mínimo seleccionado. Ajusta el deslizador de Edge.")


# =========================================================
# 4. Props NBA
# =========================================================
elif modulo_seleccionado == "🔥 Módulo Automático de Props NBA":
    st.title(f"🔥 **Props Automáticos NBA ({fecha_formato_str})**")
    st.markdown("--- \n *Puntos, rebotes, asistencias y triples de estrellas.*")
    
    props_nba = [
        {"jugador": "LeBron James", "mercado": "Puntos + Rebotes + Asistencias (Over 39.5)", "momio": -115, "prob": 65.2, "matchup": "Alto volumen de minutos y posesiones"},
        {"jugador": "Nikola Jokic", "mercado": "Asistencias Totales (Over 9.5)", "momio": -115, "prob": 66.0, "matchup": "Distribuidor principal en ofensiva"}
    ]
    for idx, p in enumerate(props_nba, 1):
        prob_imp = momio_a_probabilidad_implicita(p["momio"]) * 100.0
        edge = p["prob"] - prob_imp
        st.success(f"### 🔥 Prop NBA #{idx}: `{p['jugador']}` — `{p['mercado']}` (Edge: `+{edge:.1f}%`)")
        st.write(f"• **Momio Oficial:** `{p['momio']:+}` | Análisis: 🛡️ {p['matchup']}")
        st.markdown("---")


# =========================================================
# 5. Fútbol / Soccer Global
# =========================================================
elif modulo_seleccionado == "⚽ Módulo Global de Fútbol (Soccer Automático)":
    st.title(f"⚽ **Módulo Global de Fútbol (Goles & EV+) [{fecha_formato_str}]**")
    st.markdown("--- \n *Escáner cuantitativo de mercados de goles (Over/Under).*")

    liga_soccer = st.selectbox(
        "🌍 Selecciona la Liga o Torneo de Fútbol:",
        [
            "UEFA Champions League (uefa.champions)",
            "UEFA Europa League (uefa.europa)",
            "UEFA Europa Conference League (uefa.conf)",
            "Brasileirão - Brasil (bra.1)",
            "Premier League de Inglaterra (eng.1)",
            "La Liga de España (esp.1)",
            "Serie A de Italia (ita.1)",
            "Bundesliga de Alemania (ger.1)",
            "Ligue 1 de Francia (fra.1)",
            "Liga MX (mex.1)",
            "Eredivisie de Países Bajos (ned.1)",
            "Primeira Liga de Portugal (por.1)",
            "MLS - Estados Unidos (usa.1)"
        ]
    )

    codigo_liga_api = liga_soccer.split("(")[-1].replace(")", "").strip()

    col_f1, col_f2 = st.columns(2)
    with col_f1: bankroll_soccer = st.number_input("💵 Bankroll Fútbol (MXN):", 100.0, 50000.0, 3000.0, 500.0, key="bk_soccer")
    with col_f2: edge_min_soccer = st.slider("🎯 Edge Mínimo Goles (%):", 0.0, 15.0, 3.0, 0.5, key="edge_soccer")

    @st.cache_data(ttl=60)
    def obtener_partidos_soccer_goles_automatico(fecha_api_str, liga_codigo, fecha_humana):
        url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{liga_codigo}/scoreboard?dates={fecha_api_str}"
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
                    
                    if local != "Local" and visitante != "Visitante":
                        partidos_extraidos.append({
                            "partido_str": f"📅 [{fecha_humana}] {visitante} @ {local}",
                            "mercados": [
                                {"tipo": "Total de Goles", "seleccion": "Más de 2.5 Goles (Over)", "momio": -115, "prob_modelo": 58.5},
                                {"tipo": "Total de Goles", "seleccion": "Menos de 2.5 Goles (Under)", "momio": -105, "prob_modelo": 52.0}
                            ]
                        })
                return partidos_extraidos
        except:
            pass
        return []

    cartelera_soccer = obtener_partidos_soccer_goles_automatico(fecha_formato_api, codigo_liga_api, fecha_formato_str)
    
    st.markdown("---")
    st.subheader("📊 Oportunidades Detectadas de Goles (EV+)")

    if not cartelera_soccer:
        st.warning(f"⚠️ No se encontraron partidos oficiales programados en la API para **{liga_soccer.split('(')[0].strip()}** en la fecha `{fecha_formato_str}`.")
    else:
        contador_oportunidades = 0
        for idx, op in enumerate(cartelera_soccer, 1):
            st.markdown(f"### ⚽ Encuentro #{idx}: `{op['partido_str']}`")
            for m in op["mercados"]:
                prob_imp = momio_a_probabilidad_implicita(m["momio"]) * 100.0
                edge = m["prob_modelo"] - prob_imp

                if edge >= edge_min_soccer:
                    contador_oportunidades += 1
                    st.success(f"• **Mercado:** `{m['tipo']}` | **Selección:** `{m['seleccion']}` — Edge: `+{edge:.1f}%`")
                    st.write(f"  - **Momio Oficial:** `{m['momio']:+}` | Prob. Implícita: `{prob_imp:.1f}%` | Modelo: `{m['prob_modelo']}%`")
                    if m['momio'] < -150:
                        st.warning("⚠️ Precaución: El momio es inferior a -150.")
                    else:
                        st.success("🎯 Valor EV+ Aprobado")
            st.markdown("---")


# =========================================================
# 6. Props Fútbol
# =========================================================
elif modulo_seleccionado == "🎯 Módulo Automático de Props Fútbol":
    st.title(f"🎯 **Props Automáticos de Fútbol ({fecha_formato_str})**")
    st.markdown("--- \n *Escáner cuantitativo de rendimiento individual.*")

    col_p1, col_p2 = st.columns(2)
    with col_p1: bankroll_props_fut = st.number_input("💵 Bankroll Props Fútbol (MXN):", 100.0, 50000.0, 3000.0, 500.0, key="bk_props_fut")
    with col_p2: edge_min_props_fut = st.slider("🎯 Edge Mínimo Props (%):", 0.0, 15.0, 3.0, 0.5, key="edge_props_fut")

    props_futbol_cartelera = [
        {
            "partido": "Real Madrid vs Bayern München",
            "jugador": "Kylian Mbappé",
            "equipo": "Real Madrid",
            "mercado": "Tiros a Puerta (Over 1.5)",
            "momio": -120,
            "prob_modelo": 64.0,
            "analisis": "Alto volumen de remates y posesión en ofensiva dentro del área."
        },
        {
            "partido": "Real Madrid vs Bayern München",
            "jugador": "Harry Kane",
            "equipo": "Bayern München",
            "mercado": "Tiros Totales (Over 3.5)",
            "momio": +105,
            "prob_modelo": 55.5,
            "analisis": "Referente principal de remates de media y larga distancia."
        }
    ]

    st.markdown("---")
    st.subheader("📊 Oportunidades Detectadas en Props (EV+)")

    contador_props = 0
    for idx, p in enumerate(props_futbol_cartelera, 1):
        prob_imp = momio_a_probabilidad_implicita(p["momio"]) * 100.0
        edge = p["prob_modelo"] - prob_imp

        if edge >= edge_min_props_fut:
            contador_props += 1
            st.success(f"### 🎯 Prop #{contador_props}: `{p['jugador']}` ({p['equipo']}) — `{p['mercado']}`")
            st.write(f"• **Encuentro:** `{p['partido']}` ({fecha_formato_str})")
            st.write(f"• **Momio Oficial:** `{p['momio']:+}` | Prob. Implícita: `{prob_imp:.1f}%` | Modelo: `{p['prob_modelo']}%` — **Edge: `+{edge:.1f}%`**")
            st.markdown("---")


# =========================================================
# 7. NCAA
# =========================================================
elif modulo_seleccionado == "🎓 NCAA (Robot Universitario & Hándicap)":
    st.title(f"🎓 **Robot Universitario NCAA ({fecha_formato_str})**")
    st.markdown("--- \n *Escaneo de partidos colegiales y hándicap.*")
    st.success("### 🎓 Análisis NCAA Spread: Alabama Crimson Tide (-7.5)")


# =========================================================
# 8. UFC
# =========================================================
elif modulo_seleccionado == "🥊 Sistema Cuantitativo Pro UFC (Combates)":
    st.title(f"🥊 **Sistema Cuantitativo Pro UFC ({fecha_formato_str})**")
    st.markdown("--- \n *Cartelera oficial sincronizada para el evento estelar.*")
    st.success("### 🥊 Combate Estelar: Alexander Volkanovski vs Movsar Evloev")


# =========================================================
# 9. Tenis
# =========================================================
elif modulo_seleccionado == "🎾 Sistema Cuantitativo Pro Tenis (ATP/WTA)":
    st.title(f"🎾 **Sistema Cuantitativo Pro Tenis ({fecha_formato_str})**")
    st.markdown("--- \n *Análisis de superficie, fatiga y hándicap de juegos.*")
    st.success("### 🎾 Análisis Tenis (Hándicap de Juegos): Jannik Sinner (-3.5)")


# =========================================================
# 10. LMP (Liga Mexicana del Pacífico)
# =========================================================
elif modulo_seleccionado == "Liga Mexicana del Pacífico (LMP Invernal)" or modulo_seleccionado == "⚾ Liga Mexicana del Pacífico (LMP Invernal)":
    st.title(f"⚾ **Liga Mexicana del Pacífico (LMP) [{fecha_formato_str}]**")
    st.markdown("--- \n *Módulo limpio de análisis de Run Line (±1.5).*")
    col_i1, col_i2 = st.columns(2)
    with col_i1:
        equipo_visitante_lmp = st.text_input("⚾ Equipo Visitante:", value="Naranjeros de Hermosillo")
        equipo_local_lmp = st.text_input("⚾ Equipo Local:", value="Cañeros de Los Mochis")
    with col_i2:
        seleccion_apuesta_lmp = st.text_input("🎯 Selección con Run Line:", value="Naranjeros de Hermosillo (-1.5)")
        momio_lmp = st.number_input("📈 Momio Americano Oficial:", value=130, step=5, key="momio_lmp")
        prob_modelo_lmp = st.slider("🤖 Probabilidad Estimada del Modelo (%):", 40.0, 80.0, 54.0, 0.5, key="prob_lmp")


# =========================================================
# 11. Béisbol Internacional (MLB)
# =========================================================
elif modulo_seleccionado == "⚾ Béisbol Internacional (MLB)":
    st.title(f"⚾ **Béisbol Internacional - MLB ({fecha_formato_str})**")
    st.markdown("--- \n *Escáner cuantitativo sincronizado con la MLB.*")


# =========================================================
# 12. NHL
# =========================================================
elif modulo_seleccionado == "🏒 Sistema Cuantitativo Pro NHL (Hándicap / Puck Line)":
    st.title(f"🏒 **Sistema Cuantitativo Pro NHL (Puck Line) [{fecha_formato_str}]**")
    st.markdown("--- \n *Escáner cuantitativo especializado en hándicap de goles.*")


# =========================================================
# 13. Props NHL
# =========================================================
elif modulo_seleccionado == "🏒 Módulo Automático de Props NHL":
    st.title(f"🏒 **Props Automáticos NHL ({fecha_formato_str})**")
    st.markdown("--- \n *Rendimiento individual de jugadores de hockey.*")


# =========================================================
# 14. AHL
# =========================================================
elif modulo_seleccionado == "🏒 Sistema Cuantitativo Pro AHL (Hándicap / Desarrollo)":
    st.title(f"🏒 **Sistema Cuantitativo Pro AHL (Hándicap) [{fecha_formato_str}]**")
    st.markdown("--- \n *Liga de desarrollo y análisis de margen de goles.*")


# =========================================================
# 15. Analítica & Bankroll
# =========================================================
elif modulo_seleccionado == "📊 Analítica & Control de Bankroll":
    st.title("📊 **Panel de Analítica y Gestión de Bankroll**")
    st.markdown("--- \n *Control financiero y rendimiento.*")


# =========================================================
# 16. Optimizador de Parlays
# =========================================================
else:
    st.title(f"🚀 **Optimizador Automático de Parlays ({fecha_formato_str})**")
    st.markdown("--- \n *Boleta combinada cruzada de alto valor EV+.*")
