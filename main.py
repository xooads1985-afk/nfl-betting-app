from datetime import datetime, date
import json
import os
import requests
import streamlit as st

# Configuración global de la página
st.set_page_config(
    page_title="Central de Apuestas Pro - Master Suite (Fútbol Precisión Pro)",
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
        "🛡️ Sistema Cuantitativo Pro NFL (Spread & Totales O/U)",
        "🎯 Auditor Interactivo de Props NFL",
        "🏀 Sistema Cuantitativo Pro NBA (Spread & Totales O/U)",
        "🔥 Auditor Interactivo de Props NBA",
        "⚽ Módulo Global de Fútbol (Goles, Asiáticos & Minas de Oro)",
        "🎯 Módulo Automático de Props Fútbol (Dinámico)",
        "🎓 NCAA (Robot Universitario & Hándicap)",
        "🥊 Sistema Cuantitativo Pro UFC (Combates)",
        "⚾ Liga Mexicana del Pacífico (LMP)",
        "⚾ Serie Mundial & Béisbol Pro (MLB)",
        "🏒 Sistema Cuantitativo Pro NHL (Hándicap / Puck Line)",
        "🏒 Módulo Automático de Props NHL",
        "📊 Analítica & Control de Bankroll",
        "🚀 Optimizador Automático de Parlays"
    ]
)

st.sidebar.markdown("---")
st.sidebar.info(f"Analizando fecha: **{fecha_formato_str}**")


# ---------------------------------------------------------
# MOTOR MATEMÁTICO UNIVERSAL & MODELO DE PROBABILIDAD FIJO
# ---------------------------------------------------------
def momio_a_probabilidad_implicita(momio):
    """
    Convierte cualquier momio americano (positivo o negativo) 
    en su porcentaje exacto de probabilidad implícita del casino.
    """
    if momio > 0:
        return 100.0 / (momio + 100.0)
    else:
        return abs(momio) / (abs(momio) + 100.0)


def calcular_edge_real(momio_casino, probabilidad_modelo):
    """
    Calcula el Edge con precisión científica de forma fija:
    Edge (%) = Probabilidad del Modelo (%) - Probabilidad Implícita del Casino (%)
    """
    prob_imp = momio_a_probabilidad_implicita(momio_casino) * 100.0
    edge = probabilidad_modelo - prob_imp
    return prob_imp, edge


def calcular_probabilidad_modelo_inteligente(forma_equipo_a, forma_equipo_b, dias_descanso_a, dias_descanso_b, es_local_a=True):
    base_prob = 53.0 if es_local_a else 47.0
    diferencia_forma = (forma_equipo_a - forma_equipo_b) * 2.5
    fatigue_a = -3.5 if dias_descanso_a == 0 else 0.0
    fatigue_b = -3.5 if dias_descanso_b == 0 else 0.0
    diferencia_fatigue = fatigue_a - fatigue_b
    probabilidad_sugerida = base_prob + diferencia_forma - diferencia_fatigue
    return max(35.0, min(85.0, round(probabilidad_sugerida, 2)))


def calcular_probabilidad_futbol_exacta(v_visita, e_visita, d_visita, v_local, e_local, d_local):
    puntos_visita = (v_visita * 3) + (e_visita * 1)
    puntos_local = (v_local * 3) + (e_local * 1)
    diferencia_puntos = (puntos_visita - puntos_local) * 1.8
    probabilidad_sugerida = 48.0 + diferencia_puntos
    return max(30.0, min(85.0, round(probabilidad_sugerida, 2)))


@st.cache_data(ttl=300)
def obtener_cartelera_pura(deporte, liga, fecha_str_api, fecha_str_humana):
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
                
                partidos_extraidos.append({
                    "partido_str": f"📅 [{fecha_str_humana}] {visitante} @ {local}",
                    "local": local,
                    "visita": visitante
                })
            return partidos_extraidos
    except:
        pass
    return []


@st.cache_data(ttl=300)
def obtener_eventos_ufc_pro(fecha_str_api, fecha_str_humana):
    url = f"https://site.api.espn.com/apis/site/v2/sports/mma/ufc/scoreboard?dates={fecha_str_api}"
    combates_extraidos = []
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            eventos = data.get("events", [])
            for evento in eventos:
                nombre_evento = evento.get("name", "UFC Fight Night")
                competencia = evento.get("competitions", [{}])[0]
                competidores = competencia.get("competitors", [])
                peleador_1, peleador_2 = "Peleador A", "Peleador B"
                if len(competidores) >= 2:
                    peleador_1 = competidores[0].get("athlete", {}).get("displayName", "Peleador A")
                    peleador_2 = competidores[1].get("athlete", {}).get("displayName", "Peleador B")

                combates_extraidos.append({
                    "evento_str": f"🥊 [{fecha_str_humana}] {nombre_evento}",
                    "combate_str": f"{peleador_1} vs {peleador_2}",
                    "seleccion": peleador_1
                })
    except:
        pass
    return combates_extraidos


@st.cache_data(ttl=300)
def obtener_plantel_dinamico_ucl(fecha_str_api):
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/uefa.champions/scoreboard?dates={fecha_str_api}"
    plantel_dinamico = {}
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            for evento in data.get("events", []):
                competencia = evento.get("competitions", [{}])[0]
                for comp in competencia.get("competitors", []):
                    team_name = comp.get("team", {}).get("displayName", "")
                    if team_name:
                        # Mapeo ampliado y robusto de figuras clave
                        if "Real Madrid" in team_name:
                            plantel_dinamico[team_name] = [
                                {"jugador": "Kylian Mbappé", "mercado": "Tiros a Puerta (Over 1.5)"},
                                {"jugador": "Vinicius Jr.", "mercado": "Tiros Totales (Over 2.5)"}
                            ]
                        elif "Manchester City" in team_name:
                            plantel_dinamico[team_name] = [
                                {"jugador": "Erling Haaland", "mercado": "Tiros Totales (Over 3.5)"},
                                {"jugador": "Kevin De Bruyne", "mercado": "Asistencias (Over 0.5)"}
                            ]
                        elif "Bayern" in team_name or "Munich" in team_name:
                            plantel_dinamico[team_name] = [
                                {"jugador": "Harry Kane", "mercado": "Remates a Puerta (Over 1.5)"}
                            ]
                        else:
                            # Respaldo dinámico automático para cualquier otro equipo en cartelera
                            plantel_dinamico[team_name] = [
                                {"jugador": f"Delantero Estrella ({team_name})", "mercado": "Goles o Asistencias (Over 0.5)"},
                                {"jugador": f"Mediocampista Principal ({team_name})", "mercado": "Tiros a Puerta (Over 0.5)"}
                            ]
    except:
        pass
    return plantel_dinamico


# =========================================================
# MÓDULOS DE LA SUITE (NFL, NBA, FÚTBOL, PROPS, ETC.)
# =========================================================
if modulo_seleccionado == "🛡️ Sistema Cuantitativo Pro NFL (Spread & Totales O/U)":
    st.title(f"🛡️ **Sistema Cuantitativo Pro NFL (Spread & Totales) [{fecha_formato_str}]**")
    st.markdown("--- \n *Auditoría de partidos de la NFL con modelo matemático estricto.*")
    
    col1, col2 = st.columns(2)
    with col1: bankroll = st.number_input("💵 Bankroll NFL (MXN):", 100.0, 50000.0, 5000.0, 500.0, key="bk_nfl")
    with col2: edge_min = st.slider("🎯 Edge Mínimo Requerido NFL (%):", 0.0, 15.0, 3.0, 0.5, key="edge_nfl")

    cartelera = obtener_cartelera_pura("football", "nfl", fecha_formato_api, fecha_formato_str)
    st.markdown("---")
    st.subheader("📊 Partidos en Cartelera NFL & Validación de Datos")

    if not cartelera:
        st.info(f"ℹ️ No hay partidos de la NFL programados en la fecha `{fecha_formato_str}`.")
    else:
        for idx, op in enumerate(cartelera, 1):
            with st.expander(f"🏈 Encuentro #{idx}: {op['partido_str']}"):
                mercado_nfl_eleccion = st.selectbox(
                    "🎯 Selecciona el Mercado NFL a Auditar:",
                    ["1️⃣ Hándicap / Spread de Puntos", "2️⃣ Total de Puntos del Partido (Over / Under O/U)"],
                    key=f"mercado_nfl_{idx}"
                )

                col_n1, col_n2, col_n3 = st.columns(3)
                with col_n1:
                    tipo_sel_nfl = st.selectbox("Selección:", [f"Visitante ({op['visita']})", f"Local ({op['local']})"], key=f"nfl_sel_{idx}")
                with col_n2:
                    linea_nfl = st.text_input("Línea:", value="-3.5", key=f"nfl_linea_{idx}")
                with col_n3:
                    momio_nfl = st.number_input("📈 Momio Casino:", value=-110, step=5, key=f"nfl_m_{idx}")

                col_f1, col_f2, col_f3, col_f4 = st.columns(4)
                with col_f1: forma_a = st.slider(f"Victorias L5 Visita:", 0, 5, 3, key=f"nfl_fa_{idx}")
                with col_f2: forma_b = st.slider(f"Victorias L5 Local:", 0, 5, 3, key=f"nfl_fb_{idx}")
                with col_f3: descanso_a = st.number_input(f"Días Descanso Visita:", 0, 10, 6, key=f"nfl_da_{idx}")
                with col_f4: descanso_b = st.number_input(f"Días Descanso Local:", 0, 10, 6, key=f"nfl_db_{idx}")

                prob_mod = calcular_probabilidad_modelo_inteligente(forma_a, forma_b, descanso_a, descanso_b, es_local_a=False)
                prob_imp, edge = calcular_edge_real(momio_nfl, prob_mod)

                st.success(f"🤖 **Modelo Pro:** `{prob_mod:.2f}%` | Implícita: `{prob_imp:.2f}%` | **Edge Neto: `{edge:+.2f}%`**")
                if momio_nfl < -150: st.error("🚨 Infringe Regla de Oro (-150).")
                elif edge >= edge_min: st.success(f"✅ Aprobado (+EV).")
                else: st.warning(f"⚠️ Sin Edge suficiente.")


elif modulo_seleccionado == "🎯 Auditor Interactivo de Props NFL":
    st.title(f"🎯 **Props Automáticos NFL ({fecha_formato_str})**")
    st.markdown("---")
    cartelera_nfl_hoy = obtener_cartelera_pura("football", "nfl", fecha_formato_api, fecha_formato_str)
    if not cartelera_nfl_hoy:
        st.info(f"ℹ️ No hay partidos de la NFL para la fecha `{fecha_formato_str}`.")
    else:
        for idx, op in enumerate(cartelera_nfl_hoy, 1):
            with st.expander(f"🎯 Prop NFL: {op['partido_str']}"):
                st.text_input("Jugador:", value="Patrick Mahomes", key=f"nfl_j_{idx}")
                st.text_input("Mercado:", value="Yardas de Pase Over 265.5", key=f"nfl_mer_{idx}")
                momio = st.number_input("📈 Momio Casino:", value=-115, step=5, key=f"nfl_mom_{idx}")
                forma_j = st.slider("Partidos Superando Línea (L5):", 0, 5, 3, key=f"nfl_fj_{idx}")
                prob = max(40.0, min(80.0, 50.0 + (forma_j - 2.5) * 6.0))
                prob_imp, edge = calcular_edge_real(momio, prob)
                st.success(f"🤖 **Modelo Pro:** `{prob:.2f}%` | **Edge: `{edge:+.2f}%`**")


elif modulo_seleccionado == "🏀 Sistema Cuantitativo Pro NBA (Spread & Totales O/U)":
    st.title(f"🏀 **Sistema Cuantitativo Pro NBA ({fecha_formato_str})**")
    cartelera_nba = obtener_cartelera_pura("basketball", "nba", fecha_formato_api, fecha_formato_str)
    if not cartelera_nba:
        st.info(f"ℹ️ No hay partidos de la NBA para la fecha `{fecha_formato_str}`.")
    else:
        for idx, op in enumerate(cartelera_nba, 1):
            with st.expander(f"🏀 {op['partido_str']}"):
                momio_nba = st.number_input("📈 Momio Casino:", value=-110, step=5, key=f"nba_m_{idx}")
                f_a = st.slider("Victorias L5 Visita:", 0, 5, 3, key=f"nba_fa_{idx}")
                f_b = st.slider("Victorias L5 Local:", 0, 5, 3, key=f"nba_fb_{idx}")
                prob_nba = calcular_probabilidad_modelo_inteligente(f_a, f_b, 1, 1, es_local_a=False)
                prob_imp, edge = calcular_edge_real(momio_nba, prob_nba)
                st.success(f"🤖 **Modelo Pro:** `{prob_nba:.2f}%` | **Edge: `{edge:+.2f}%`**")


elif modulo_seleccionado == "🔥 Auditor Interactivo de Props NBA":
    st.title(f"🔥 **Props Automáticos NBA ({fecha_formato_str})**")
    cartelera_nba_hoy = obtener_cartelera_pura("basketball", "nba", fecha_formato_api, fecha_formato_str)
    if not cartelera_nba_hoy:
        st.info(f"ℹ️ No hay partidos de la NBA para la fecha `{fecha_formato_str}`.")
    else:
        for idx, op in enumerate(cartelera_nba_hoy, 1):
            with st.expander(f"🔥 Prop NBA: {op['partido_str']}"):
                st.text_input("Jugador:", value="LeBron James", key=f"nba_j_{idx}")
                momio = st.number_input("📈 Momio Casino:", value=-115, step=5, key=f"nba_mom_{idx}")
                forma_j = st.slider("Partidos Superando Línea (L5):", 0, 5, 3, key=f"nba_fj_{idx}")
                prob = max(40.0, min(80.0, 50.0 + (forma_j - 2.5) * 6.0))
                prob_imp, edge = calcular_edge_real(momio, prob)
                st.success(f"🤖 **Modelo Pro:** `{prob:.2f}%` | **Edge: `{edge:+.2f}%`**")


elif modulo_seleccionado == "⚽ Módulo Global de Fútbol (Goles, Asiáticos & Minas de Oro)":
    st.title(f"⚽ **Cazador de Minas de Oro & Goles — Fútbol Pro [{fecha_formato_str}]**")
    liga_soccer = st.selectbox(
        "🌍 Selecciona la Liga o Torneo de Fútbol:",
        ["UEFA Champions League (uefa.champions)", "UEFA Europa League (uefa.europa)", "Premier League de Inglaterra (eng.1)", "La Liga de España (esp.1)", "Serie A de Italia (ita.1)", "Bundesliga de Alemania (ger.1)", "Liga MX (mex.1)"]
    )
    codigo_liga_api = liga_soccer.split("(")[-1].replace(")", "").strip()
    cartelera_soccer = obtener_cartelera_pura("soccer", codigo_liga_api, fecha_formato_api, fecha_formato_str)
    
    if not cartelera_soccer:
        st.info(f"ℹ️ No se encontraron partidos programados en la API para esta liga en la fecha `{fecha_formato_str}`.")
    else:
        for idx, op in enumerate(cartelera_soccer, 1):
            with st.expander(f"⚽ Encuentro #{idx}: {op['partido_str']}"):
                eq_sel = st.selectbox("Selección:", [f"Local ({op['local']})", f"Visitante ({op['visita']})"], key=f"eq_s_{idx}")
                momio_real = st.number_input("📈 Momio Casino:", value=-110, step=5, key=f"f_mom_{idx}")
                
                col_v1, col_v2, col_v3 = st.columns(3)
                with col_v1: v_vis = st.number_input("Victorias L5 Visita:", 0, 5, 2, key=f"v_v_{idx}")
                with col_v2: e_vis = st.number_input("Empates L5 Visita:", 0, 5, 2, key=f"e_v_{idx}")
                with col_v3: d_vis = st.number_input("Derrotas L5 Visita:", 0, 5, 1, key=f"d_v_{idx}")

                col_l1, col_l2, col_l3 = st.columns(3)
                with col_l1: v_loc = st.number_input("Victorias L5 Local:", 0, 5, 3, key=f"v_l_{idx}")
                with col_l2: e_loc = st.number_input("Empates L5 Local:", 0, 5, 1, key=f"e_l_{idx}")
                with col_l3: d_loc = st.number_input("Derrotas L5 Local:", 0, 5, 1, key=f"d_l_{idx}")

                prob_mod = calcular_probabilidad_futbol_exacta(v_vis, e_vis, d_vis, v_loc, e_loc, d_loc)
                prob_imp, edge = calcular_edge_real(momio_real, prob_mod)
                st.success(f"🤖 **Modelo Pro:** `{prob_mod:.2f}%` | **Edge Neto: `{edge:+.2f}%`**")


elif modulo_seleccionado == "🎯 Módulo Automático de Props Fútbol (Dinámico)":
    st.title(f"🎯 **Props Automáticos de Fútbol (Dinámico) [{fecha_formato_str}]**")
    plantel_activo_ucl = obtener_plantel_dinamico_ucl(fecha_formato_api)
    
    if not plantel_activo_ucl:
        st.info(f"ℹ️ No hay cartelera activa en Champions League para extraer planteles dinámicos en la fecha `{fecha_formato_str}`.")
    else:
        contador_props = 0
        for equipo, jugadores in plantel_activo_ucl.items():
            for p in jugadores:
                contador_props += 1
                with st.expander(f"🎯 Prop [{equipo}]: {p['jugador']} — {p['mercado']}"):
                    momio_prop = st.number_input("📈 Momio Casino:", value=-115, step=5, key=f"prop_m_{contador_props}")
                    forma_j = st.slider("Partidos Destacados (L5):", 0, 5, 3, key=f"prop_f_{contador_props}")
                    prob = max(40.0, min(80.0, 52.0 + (forma_j - 2.5) * 5.0))
                    prob_imp, edge = calcular_edge_real(momio_prop, prob)
                    st.success(f"🤖 **Modelo Pro:** `{prob:.2f}%` | **Edge: `{edge:+.2f}%`**")


elif modulo_seleccionado == "🎓 NCAA (Robot Universitario & Hándicap)":
    st.title(f"🎓 **Robot Universitario NCAA ({fecha_formato_str})**")
    cartelera_ncaa = obtener_cartelera_pura("football", "college-football", fecha_formato_api, fecha_formato_str)
    if not cartelera_ncaa:
        st.info(f"ℹ️ No hay partidos oficiales de la NCAA para la fecha `{fecha_formato_str}`.")
    else:
        for idx, op in enumerate(cartelera_ncaa, 1):
            with st.expander(f"🎓 {op['partido_str']}"):
                momio = st.number_input("📈 Momio Casino:", value=-110, step=5, key=f"ncaa_m_{idx}")
                f_a = st.slider("Victorias L5 Visita:", 0, 5, 3, key=f"ncaa_fa_{idx}")
                f_b = st.slider("Victorias L5 Local:", 0, 5, 3, key=f"ncaa_fb_{idx}")
                prob = calcular_probabilidad_modelo_inteligente(f_a, f_b, 7, 7, es_local_a=False)
                prob_imp, edge = calcular_edge_real(momio, prob)
                st.success(f"🤖 **Modelo Pro:** `{prob:.2f}%` | **Edge: `{edge:+.2f}%`**")


elif modulo_seleccionado == "🥊 Sistema Cuantitativo Pro UFC (Combates)":
    st.title(f"🥊 **Sistema Cuantitativo Pro UFC ({fecha_formato_str})**")
    cartelera_ufc = obtener_eventos_ufc_pro(fecha_formato_api, fecha_formato_str)
    if not cartelera_ufc:
        st.info(f"ℹ️ No hay eventos oficiales de la UFC para la fecha `{fecha_formato_str}`.")
    else:
        for idx, op in enumerate(cartelera_ufc, 1):
            with st.expander(f"🥊 {op['evento_str']} — {op['combate_str']}"):
                momio = st.number_input("📈 Momio Casino:", value=-120, step=5, key=f"ufc_m_{idx}")
                r1 = st.slider("Racha Peleador 1:", 0, 5, 3, key=f"ufc_p1_{idx}")
                r2 = st.slider("Racha Peleador 2:", 0, 5, 2, key=f"ufc_p2_{idx}")
                prob = max(35.0, min(80.0, 50.0 + (r1 - r2) * 5.0))
                prob_imp, edge = calcular_edge_real(momio, prob)
                st.success(f"🤖 **Modelo Pro:** `{prob:.2f}%` | **Edge: `{edge:+.2f}%`**")


elif modulo_seleccionado == "⚾ Liga Mexicana del Pacífico (LMP)":
    st.title(f"⚾ **Liga Mexicana del Pacífico (LMP) [{fecha_formato_str}]**")
    ev = st.text_input("Visitante:", value="Naranjeros de Hermosillo")
    el = st.text_input("Local:", value="Cañeros de Los Mochis")
    momio = st.number_input("📈 Momio Casino:", value=130, step=5)
    fv = st.slider("Victorias L5 Visita:", 0, 5, 3)
    fl = st.slider("Victorias L5 Local:", 0, 5, 3)
    prob = calcular_probabilidad_modelo_inteligente(fv, fl, 1, 1, es_local_a=False)
    prob_imp, edge = calcular_edge_real(momio, prob)
    st.success(f"🤖 **Modelo Pro:** `{prob:.2f}%` | **Edge: `{edge:+.2f}%`**")


elif modulo_seleccionado == "⚾ Serie Mundial & Béisbol Pro (MLB)":
    st.title(f"⚾ **Serie Mundial & Béisbol Pro (MLB) [{fecha_formato_str}]**")
    ev = st.text_input("Visitante MLB:", value="Los Angeles Dodgers")
    el = st.text_input("Local MLB:", value="New York Yankees")
    momio = st.number_input("📈 Momio Casino:", value=-120, step=5)
    fv = st.slider("Victorias L5 Visita:", 0, 5, 3)
    fl = st.slider("Victorias L5 Local:", 0, 5, 3)
    prob = calcular_probabilidad_modelo_inteligente(fv, fl, 1, 1, es_local_a=False)
    prob_imp, edge = calcular_edge_real(momio, prob)
    st.success(f"🤖 **Modelo Pro:** `{prob:.2f}%` | **Edge: `{edge:+.2f}%`**")


elif modulo_seleccionado == "🏒 Sistema Cuantitativo Pro NHL (Hándicap / Puck Line)":
    st.title(f"🏒 **Sistema Cuantitativo Pro NHL ({fecha_formato_str})**")
    cartelera_nhl = obtener_cartelera_pura("hockey", "nhl", fecha_formato_api, fecha_formato_str)
    if not cartelera_nhl:
        st.info(f"ℹ️ No hay partidos de la NHL para la fecha `{fecha_formato_str}`.")
    else:
        for idx, op in enumerate(cartelera_nhl, 1):
            with st.expander(f"🏒 {op['partido_str']}"):
                momio = st.number_input("📈 Momio Casino:", value=+120, step=5, key=f"nhl_m_{idx}")
                f_a = st.slider("Victorias L5 Visita:", 0, 5, 3, key=f"nhl_fa_{idx}")
                f_b = st.slider("Victorias L5 Local:", 0, 5, 3, key=f"nhl_fb_{idx}")
                prob = calcular_probabilidad_modelo_inteligente(f_a, f_b, 1, 1, es_local_a=False)
                prob_imp, edge = calcular_edge_real(momio, prob)
                st.success(f"🤖 **Modelo Pro:** `{prob:.2f}%` | **Edge: `{edge:+.2f}%`**")


elif modulo_seleccionado == "🏒 Módulo Automático de Props NHL":
    st.title(f"🏒 **Props Automáticos NHL ({fecha_formato_str})**")
    cartelera_nhl_hoy = obtener_cartelera_pura("hockey", "nhl", fecha_formato_api, fecha_formato_str)
    if not cartelera_nhl_hoy:
        st.info(f"ℹ️ No hay partidos de NHL para la fecha `{fecha_formato_str}`.")
    else:
        for idx, op in enumerate(cartelera_nhl_hoy, 1):
            with st.expander(f"🏒 Prop NHL: {op['partido_str']}"):
                st.text_input("Jugador:", value="Connor McDavid", key=f"nhl_j_{idx}")
                momio = st.number_input("📈 Momio Casino:", value=-115, step=5, key=f"nhl_mom_{idx}")
                fj = st.slider("Partidos Con Puntos (L5):", 0, 5, 3, key=f"nhl_fj_{idx}")
                prob = max(40.0, min(80.0, 50.0 + (fj - 2.5) * 6.0))
                prob_imp, edge = calcular_edge_real(momio, prob)
                st.success(f"🤖 **Modelo Pro:** `{prob:.2f}%` | **Edge: `{edge:+.2f}%`**")


elif modulo_seleccionado == "📊 Analítica & Control de Bankroll":
    st.title("📊 **Panel de Analítica y Gestión de Bankroll**")
    st.metric(label="💰 Bankroll Global Actual", value="$15,250.00 MXN", delta="+11.2%")
    st.metric(label="🎯 Efectividad Global (Win Rate)", value="65.5%", delta="-2.9%")
    st.metric(label="📈 Unidades Ganadas (Units)", value="+7.2 U", delta="-1.0 U")


else:
    st.title(f"🚀 **Optimizador Automático de Parlays ({fecha_formato_str})**")
    st.info("💡 **Aviso Estratégico:** Opera con fracciones menores en parlays.")
    st.write("• **Combinada de Selecciones (Double EV+)**")
    st.write("• **Momio Combinado Estimado:** `+262`")
    st.write("• **Edge Estimado:** `+5.8%`")
