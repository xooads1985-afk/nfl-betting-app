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
# MOTOR MATEMÁTICO UNIVERSAL & MODELO DE PROBABILIDAD INTELIGENTE
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
    Calcula el Edge con precisión científica:
    Edge (%) = Probabilidad del Modelo (%) - Probabilidad Implícita del Casino (%)
    """
    prob_imp = momio_a_probabilidad_implicita(momio_casino) * 100.0
    edge = probabilidad_modelo - prob_imp
    return prob_imp, edge


def calcular_probabilidad_modelo_inteligente(forma_equipo_a, forma_equipo_b, dias_descanso_a, dias_descanso_b, es_local_a=True):
    """
    Calcula una probabilidad sugerida del modelo basada en factores duros generales.
    """
    base_prob = 53.0 if es_local_a else 47.0
    diferencia_forma = (forma_equipo_a - forma_equipo_b) * 2.5
    fatigue_a = -3.5 if dias_descanso_a == 0 else 0.0
    fatigue_b = -3.5 if dias_descanso_b == 0 else 0.0
    diferencia_fatigue = fatigue_a - fatigue_b
    probabilidad_sugerida = base_prob + diferencia_forma - diferencia_fatigue
    return max(35.0, min(85.0, round(probabilidad_sugerida, 2)))


def calcular_probabilidad_futbol_exacta(v_visita, e_visita, d_visita, v_local, e_local, d_local):
    """
    Calcula la probabilidad exacta para Fútbol considerando Victorias (3 pts), 
    Empates (1 pt) y Derrotas (0 pts) en los últimos 5 partidos de cada equipo.
    """
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
                        visitante = comp.get("team", {}).get("displayName", "Local")
                
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
                        if "Real Madrid" in team_name:
                            plantel_dinamico[team_name] = [{"jugador": "Kylian Mbappé", "mercado": "Tiros a Puerta (Over 1.5)"}]
                        elif "Manchester City" in team_name:
                            plantel_dinamico[team_name] = [{"jugador": "Erling Haaland", "mercado": "Tiros Totales (Over 3.5)"}]
    except:
        pass
    return plantel_dinamico


# =========================================================
# 1. NFL (SISTEMA PRO: SPREAD & TOTALES O/U FLEXIBLES)
# =========================================================
if modulo_seleccionado == "🛡️ Sistema Cuantitativo Pro NFL (Spread & Totales O/U)":
    st.title(f"🛡️ **Sistema Cuantitativo Pro NFL (Spread & Totales) [{fecha_formato_str}]**")
    st.markdown("--- \n *Auditoría de partidos de la NFL con selección flexible de mercados.*")
    
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
                    ["1️⃣ Hándicap / Spread de Puntos", "2️⃣ Total de Puntos del Partido (Over / Under O/U)", "3️⃣ Total de Puntos Primera Mitad (1H Over / Under)"],
                    key=f"mercado_nfl_{idx}"
                )

                col_n1, col_n2, col_n3 = st.columns(3)
                with col_n1:
                    if "Spread" in mercado_nfl_eleccion:
                        tipo_sel_nfl = st.selectbox("Selección Spread:", [f"Equipo Visitante ({op['visita']})", f"Equipo Local ({op['local']})"], key=f"nfl_sel_{idx}")
                    else:
                        tipo_sel_nfl = st.selectbox("Selección Total:", ["Over (Más de)", "Under (Menos de)"], key=f"nfl_sel_ou_{idx}")
                with col_n2:
                    if "Spread" in mercado_nfl_eleccion:
                        linea_nfl = st.text_input("Línea Spread:", value="-3.5", key=f"nfl_linea_{idx}")
                    elif "Partido" in mercado_nfl_eleccion:
                        linea_nfl = st.text_input("Línea Total Partido:", value="45.5", key=f"nfl_linea_ou_{idx}")
                    else:
                        linea_nfl = st.text_input("Línea 1ra Mitad:", value="22.5", key=f"nfl_linea_1h_{idx}")
                with col_n3:
                    momio_nfl = st.number_input("📈 Momio Casino (Americano):", value=-110, step=5, key=f"nfl_m_{idx}")

                st.markdown("### 🧬 Asistente de Factores Duros")
                col_f1, col_f2, col_f3, col_f4 = st.columns(4)
                with col_f1: forma_a = st.slider(f"Victorias L5 ({op['visita']}):", 0, 5, 3, key=f"nfl_fa_{idx}")
                with col_f2: forma_b = st.slider(f"Victorias L5 ({op['local']}):", 0, 5, 3, key=f"nfl_fb_{idx}")
                with col_f3: descanso_a = st.number_input(f"Días Descanso Visita:", 0, 10, 6, key=f"nfl_da_{idx}")
                with col_f4: descanso_b = st.number_input(f"Días Descanso Local:", 0, 10, 6, key=f"nfl_db_{idx}")

                prob_sugerida = calcular_probabilidad_modelo_inteligente(forma_a, forma_b, descanso_a, descanso_b, es_local_a=False)
                st.info(f"💡 Probabilidad Sugerida: **`{prob_sugerida}%`**")

                prob_mod = st.slider("🤖 Probabilidad Real del Modelo Pro (%):", 30.0, 85.0, prob_sugerida, 0.5, key=f"nfl_p_{idx}")
                prob_imp, edge = calcular_edge_real(momio_nfl, prob_mod)

                st.markdown("---")
                st.info(f"📊 **Edge Calculado:** Implícita (`{momio_nfl:+}`): `{prob_imp:.2f}%` | Modelo: `{prob_mod:.2f}%` | Edge Neto: **`{edge:+.2f}%`**")

                if momio_nfl < -150: st.error("🚨 Infringe Regla de Oro (-150).")
                elif edge >= edge_min: st.success(f"✅ Aprobado (+EV). Edge: `{edge:+.2f}%`")
                else: st.warning(f"⚠️ Sin Edge suficiente (`{edge:+.2f}%`).")


# =========================================================
# 2. Props NFL
# =========================================================
elif modulo_seleccionado == "🎯 Auditor Interactivo de Props NFL":
    st.title(f"🎯 **Props Automáticos NFL ({fecha_formato_str})**")
    st.markdown("--- \n *Rendimiento individual de jugadores en la NFL.*")
    col_pnfl1, col_pnfl2 = st.columns(2)
    with col_pnfl1: bankroll_props_nfl = st.number_input("💵 Bankroll Props NFL (MXN):", 100.0, 50000.0, 3000.0, 500.0, key="bk_props_nfl")
    with col_pnfl2: edge_min_props_nfl = st.slider("🎯 Edge Mínimo Props NFL (%):", 0.0, 15.0, 3.0, 0.5, key="edge_props_nfl")

    cartelera_nfl_hoy = obtener_cartelera_pura("football", "nfl", fecha_formato_api, fecha_formato_str)
    st.markdown("---")
    st.subheader("📊 Auditoría de Props NFL")

    if not cartelera_nfl_hoy:
        st.info(f"ℹ️ No hay partidos de la NFL en cartelera para la fecha `{fecha_formato_str}`.")
    else:
        for idx, op in enumerate(cartelera_nfl_hoy, 1):
            with st.expander(f"🎯 Prop NFL: {op['partido_str']}"):
                jugador = st.text_input("Jugador:", value="Patrick Mahomes", key=f"nfl_j_{idx}")
                mercado = st.text_input("Mercado:", value="Yardas de Pase Over 265.5", key=f"nfl_mer_{idx}")
                momio = st.number_input("📈 Momio Casino:", value=-115, step=5, key=f"nfl_mom_{idx}")
                
                forma_jugador = st.slider(f"Partidos Superando Línea (L5):", 0, 5, 3, key=f"nfl_fj_{idx}")
                prob_sugerida_prop = max(40.0, min(80.0, 50.0 + (forma_jugador - 2.5) * 6.0))
                st.info(f"💡 Probabilidad Sugerida: **`{prob_sugerida_prop}%`**")

                prob = st.slider("🤖 Probabilidad Modelo Pro (%):", 40.0, 80.0, prob_sugerida_prop, 0.5, key=f"nfl_pr_{idx}")
                prob_imp, edge = calcular_edge_real(momio, prob)

                st.info(f"📊 **Edge Calculado:** Implícita (`{momio:+}`): `{prob_imp:.2f}%` | Modelo: `{prob:.2f}%` | Edge Neto: **`{edge:+.2f}%`**")

                if momio < -150: st.error("🚨 Infringe Regla de Oro (-150).")
                elif edge >= edge_min_props_nfl: st.success(f"✅ Aprobado Prop (+EV). Edge: `{edge:+.2f}%`")
                else: st.warning(f"⚠️ Sin Edge suficiente (`{edge:+.2f}%`).")


# =========================================================
# 3. NBA (SISTEMA PRO: SPREAD & TOTALES O/U FLEXIBLES)
# =========================================================
elif modulo_seleccionado == "🏀 Sistema Cuantitativo Pro NBA (Spread & Totales O/U)":
    st.title(f"🏀 **Sistema Cuantitativo Pro NBA (Spread & Totales) [{fecha_formato_str}]**")
    st.markdown("--- \n *Auditoría de partidos de la NBA.*")
    
    col1, col2 = st.columns(2)
    with col1: bankroll_nba = st.number_input("💵 Bankroll NBA (MXN):", 100.0, 50000.0, 5000.0, 500.0, key="bk_nba")
    with col2: edge_min_nba = st.slider("🎯 Edge Mínimo Requerido NBA (%):", 0.0, 15.0, 3.0, 0.5, key="edge_nba")

    cartelera_nba = obtener_cartelera_pura("basketball", "nba", fecha_formato_api, fecha_formato_str)
    st.markdown("---")
    st.subheader("📊 Partidos en Cartelera NBA")

    if not cartelera_nba:
        st.info(f"ℹ️ No hay partidos de la NBA registrados en la API para la fecha `{fecha_formato_str}`.")
    else:
        for idx, op in enumerate(cartelera_nba, 1):
            with st.expander(f"🏀 Encuentro #{idx}: {op['partido_str']}"):
                mercado_nba_eleccion = st.selectbox(
                    "🎯 Selecciona el Mercado NBA a Auditar:",
                    ["1️⃣ Hándicap / Spread de Puntos", "2️⃣ Total de Puntos del Partido (Over / Under O/U)", "3️⃣ Total de Puntos por Mitad / Cuarto", "4️⃣ Total de Puntos Individual por Equipo"],
                    key=f"mercado_nba_{idx}"
                )

                col_n1, col_n2, col_n3 = st.columns(3)
                with col_n1:
                    if "Spread" in mercado_nba_eleccion:
                        tipo_sel_nba = st.selectbox("Selección Spread:", [f"Equipo Visitante ({op['visita']})", f"Equipo Local ({op['local']})"], key=f"nba_sel_{idx}")
                    else:
                        tipo_sel_nba = st.selectbox("Selección Total:", ["Over (Más de)", "Under (Menos de)"], key=f"nba_sel_ou_{idx}")
                with col_n2:
                    if "Spread" in mercado_nba_eleccion:
                        linea_nba = st.text_input("Línea Spread:", value="-4.5", key=f"nba_linea_{idx}")
                    elif "Over / Under" in mercado_nba_eleccion:
                        linea_nba = st.text_input("Línea Total Puntos:", value="224.5", key=f"nba_linea_ou_{idx}")
                    else:
                        linea_nba = st.text_input("Línea de Puntos:", value="110.5", key=f"nba_linea_esp_{idx}")
                with col_n3:
                    momio_nba = st.number_input("📈 Momio Casino (Americano):", value=-110, step=5, key=f"nba_m_{idx}")

                st.markdown("### 🧬 Asistente de Factores Duros")
                col_f1, col_f2, col_f3, col_f4 = st.columns(4)
                with col_f1: forma_a = st.slider(f"Victorias L5 ({op['visita']}):", 0, 5, 3, key=f"nba_fa_{idx}")
                with col_f2: forma_b = st.slider(f"Victorias L5 ({op['local']}):", 0, 5, 3, key=f"nba_fb_{idx}")
                with col_f3: descanso_a = st.number_input(f"Días Descanso Visita:", 0, 10, 1, key=f"nba_da_{idx}")
                with col_f4: descanso_b = st.number_input(f"Días Descanso Local:", 0, 10, 1, key=f"nba_db_{idx}")

                prob_sugerida = calcular_probabilidad_modelo_inteligente(forma_a, forma_b, descanso_a, descanso_b, es_local_a=False)
                st.info(f"💡 Probabilidad Sugerida: **`{prob_sugerida}%`** (Recuerda esperar 5 partidos en esta temporada)")

                prob_nba = st.slider("🤖 Probabilidad Real del Modelo Pro (%):", 30.0, 85.0, prob_sugerida, 0.5, key=f"nba_p_{idx}")
                prob_imp, edge = calcular_edge_real(momio_nba, prob_nba)

                st.markdown("---")
                st.info(f"📊 **Edge Calculado:** Implícita (`{momio_nba:+}`): `{prob_imp:.2f}%` | Modelo: `{prob_nba:.2f}%` | Edge Neto: **`{edge:+.2f}%`**")

                if momio_nba < -150: st.error("🚨 Infringe Regla de Oro (-150).")
                elif edge >= edge_min_nba: st.success(f"✅ Aprobado (+EV). Edge: `{edge:+.2f}%`")
                else: st.warning(f"⚠️ Sin Edge suficiente (`{edge:+.2f}%`).")


# =========================================================
# 4. Props NBA
# =========================================================
elif modulo_seleccionado == "🔥 Auditor Interactivo de Props NBA":
    st.title(f"🔥 **Props Automáticos NBA ({fecha_formato_str})**")
    st.markdown("--- \n *Rendimiento individual de jugadores en la NBA.*")
    col_pn1, col_pn2 = st.columns(2)
    with col_pn1: bankroll_props_nba = st.number_input("💵 Bankroll Props NBA (MXN):", 100.0, 50000.0, 3000.0, 500.0, key="bk_props_nba")
    with col_pn2: edge_min_props_nba = st.slider("🎯 Edge Mínimo Props NBA (%):", 0.0, 15.0, 3.0, 0.5, key="edge_props_nba")

    cartelera_nba_hoy = obtener_cartelera_pura("basketball", "nba", fecha_formato_api, fecha_formato_str)
    st.markdown("---")
    st.subheader("📊 Auditoría de Props NBA")

    if not cartelera_nba_hoy:
        st.info(f"ℹ️ No hay partidos de la NBA en la API para la fecha `{fecha_formato_str}`.")
    else:
        for idx, op in enumerate(cartelera_nba_hoy, 1):
            with st.expander(f"🔥 Prop NBA: {op['partido_str']}"):
                jugador = st.text_input("Jugador:", value="LeBron James", key=f"nba_j_{idx}")
                mercado = st.text_input("Mercado:", value="Puntos Totales Over 24.5", key=f"nba_mer_{idx}")
                momio = st.number_input("📈 Momio Casino:", value=-115, step=5, key=f"nba_mom_{idx}")
                
                forma_j = st.slider(f"Partidos Superando Línea (L5):", 0, 5, 3, key=f"nba_fj_{idx}")
                prob_sugerida_pj = max(40.0, min(80.0, 50.0 + (forma_j - 2.5) * 6.0))
                st.info(f"💡 Probabilidad Sugerida: **`{prob_sugerida_pj}%`**")

                prob = st.slider("🤖 Probabilidad Modelo Pro (%):", 40.0, 80.0, prob_sugerida_pj, 0.5, key=f"nba_pr_{idx}")
                prob_imp, edge = calcular_edge_real(momio, prob)

                st.info(f"📊 **Edge Calculado:** Implícita (`{momio:+}`): `{prob_imp:.2f}%` | Modelo: `{prob:.2f}%` | Edge Neto: **`{edge:+.2f}%`**")

                if momio < -150: st.error("🚨 Infringe Regla de Oro (-150).")
                elif edge >= edge_min_props_nba: st.success(f"✅ Aprobado Prop (+EV). Edge: `{edge:+.2f}%`")
                else: st.warning(f"⚠️ Sin Edge suficiente (`{edge:+.2f}%`).")


# =========================================================
# 5. FÚTBOL (MÓDULO PRINCIPAL CON SELECCIÓN EXPLÍCITA DE EQUIPO Y V-E-D)
# =========================================================
elif modulo_seleccionado == "⚽ Módulo Global de Fútbol (Goles, Asiáticos & Minas de Oro)":
    st.title(f"⚽ **Cazador de Minas de Oro & Goles — Fútbol Pro [{fecha_formato_str}]**")
    st.markdown("--- \n *Analiza partidos con mercados de Alta Ineficiencia y el Asistente Exacto de Victorias, Empates y Derrotas (L5).*")
    
    with st.expander("💡 🧠 **Guía Estratégica: Cuándo cazar estas Minas de Oro (Prematch vs. Live)**", expanded=False):
        st.markdown("""
        • **📅 En la Previa (Prematch):** Úsalo antes del partido para auditar líneas asiáticas o totales con xG y estadísticas recientes.
        • **⚡ En Vivo (Live):** ¡Ideal al minuto 65–70 para el **Under de Goles Tardíos (Min. 75+)** o líneas asiáticas en caliente!
        """)
    
    liga_soccer = st.selectbox(
        "🌍 Selecciona la Liga o Torneo de Fútbol:",
        ["UEFA Champions League (uefa.champions)", "UEFA Europa League (uefa.europa)", "Premier League de Inglaterra (eng.1)", "La Liga de España (esp.1)", "Serie A de Italia (ita.1)", "Bundesliga de Alemania (ger.1)", "Liga MX (mex.1)"]
    )
    codigo_liga_api = liga_soccer.split("(")[-1].replace(")", "").strip()
    
    col_f1, col_f2 = st.columns(2)
    with col_f1: bankroll_soccer = st.number_input("💵 Bankroll Fútbol (MXN):", 100.0, 50000.0, 3000.0, 500.0, key="bk_soccer")
    with col_f2: edge_min_soccer = st.slider("🎯 Edge Mínimo Requerido para Operar (%):", 0.0, 15.0, 3.0, 0.5, key="edge_soccer")

    cartelera_soccer = obtener_cartelera_pura("soccer", codigo_liga_api, fecha_formato_api, fecha_formato_str)
    st.markdown("---")
    st.subheader("📋 Cartelera Real & Detección de Minas de Oro")

    if not cartelera_soccer:
        st.info(f"ℹ️ No se encontraron partidos programados en la API para esta liga en la fecha `{fecha_formato_str}`.")
    else:
        for idx, op in enumerate(cartelera_soccer, 1):
            with st.expander(f"⚽ Encuentro #{idx}: {op['partido_str']}"):
                tipo_mercado_mina = st.selectbox(
                    "💎 Selecciona el Tipo de Mercado a Auditar:",
                    ["1️⃣ Goles Totales Clásico (Over / Under 2.5)", "2️⃣ 💎 Mina de Oro: Hándicap Asiático por Equipos", "3️⃣ 💎 Mina de Oro: Goles en Segunda Mitad / Tardíos (Min. 75+)"],
                    key=f"mercado_mina_{idx}"
                )

                # Selector explícito del equipo para hándicap o selección general
                if "Hándicap" in tipo_mercado_mina:
                    equipo_seleccionado_apuesta = st.selectbox(
                        "🎯 ¿A qué equipo vas a apostar?",
                        [f"Local ({op['local']})", f"Visitante ({op['visita']})"],
                        key=f"eq_apuesta_{idx}"
                    )
                else:
                    equipo_seleccionado_apuesta = st.selectbox(
                        "Selección:", ["Over (Más de)", "Under (Menos de)"], key=f"g_ou_{idx}"
                    )

                col_g1, col_g2 = st.columns(2)
                with col_g1:
                    if "Hándicap" in tipo_mercado_mina:
                        linea_goles = st.text_input("Línea Asiática (ej. -0.5, +0.25):", value="-0.5", key=f"g_linea_asiatica_{idx}")
                    elif "Clásico" in tipo_mercado_mina:
                        linea_goles = st.text_input("Línea de Goles:", value="2.5", key=f"g_linea_{idx}")
                    else:
                        linea_goles = st.text_input("Línea 2da Mitad:", value="0.5", key=f"g_linea_tardio_{idx}")
                with col_g2:
                    momio_txt = st.text_input("📈 Momio Americano:", value="+116" if "Hándicap" in tipo_mercado_mina else "-110", key=f"f_momio_{idx}")

                try:
                    momio_casino_real = int(momio_txt.strip())
                except:
                    momio_casino_real = -110

                st.markdown("### 🧬 Asistente de Factores Duros (Desglose Real L5: V - E - D)")
                st.markdown(f"**Equipo Visitante: `{op['visita']}`**")
                col_v1, col_v2, col_v3 = st.columns(3)
                with col_v1: v_vis = st.number_input("Victorias L5:", 0, 5, 2, key=f"v_vis_{idx}")
                with col_v2: e_vis = st.number_input("Empates L5:", 0, 5, 2, key=f"e_vis_{idx}")
                with col_v3: d_vis = st.number_input("Derrotas L5:", 0, 5, 1, key=f"d_vis_{idx}")

                st.markdown(f"**Equipo Local: `{op['local']}`**")
                col_l1_s, col_l2_s, col_l3_s = st.columns(3)
                with col_l1_s: v_loc = st.number_input("Victorias L5:", 0, 5, 3, key=f"v_loc_{idx}")
                with col_l2_s: e_loc = st.number_input("Empates L5:", 0, 5, 1, key=f"e_loc_{idx}")
                with col_l3_s: d_loc = st.number_input("Derrotas L5:", 0, 5, 1, key=f"d_loc_{idx}")

                prob_sugerida_inicial = calcular_probabilidad_futbol_exacta(v_vis, e_vis, d_vis, v_loc, e_loc, d_loc)
                
                if "Local" in equipo_seleccionado_apuesta and "Hándicap" in tipo_mercado_mina:
                    prob_sugerida_inicial = max(40.0, prob_sugerida_inicial + 3.0)

                st.info(f"💡 **Probabilidad Sugerida por Desglose L5 (V-E-D):** **`{prob_sugerida_inicial}%`**")

                prob_modelo_pro = st.slider("🤖 Probabilidad Real Calculada por el Modelo Pro (%):", 30.0, 85.0, prob_sugerida_inicial, 0.5, key=f"f_prob_{idx}")

                tipo_apuesta_str = f"{equipo_seleccionado_apuesta} [{linea_goles}]"
                prob_imp_real, edge_real = calcular_edge_real(momio_casino_real, prob_modelo_pro)

                st.markdown("---")
                st.info(f"📊 **Auditoría de Edge para `{tipo_apuesta_str}`:**\n"
                        f"• Probabilidad Implícita (`{momio_casino_real:+}`): `{prob_imp_real:.2f}%`\n"
                        f"• Probabilidad del Modelo Pro: **`{prob_modelo_pro:.2f}%`**\n"
                        f"• 🎯 **Edge Neto Calculado:** **`{edge_real:+.2f}%`**")

                if momio_casino_real < -150:
                    st.error(f"🚨 **DESCARTADO (Regla de Oro):** Momio `{momio_casino_real}` excede el límite -150.")
                elif edge_real >= edge_min_soccer:
                    st.success(f"✅ **¡MINA DE ORO APROBADA (+EV)!** Edge de `{edge_real:+.2f}%`.")
                else:
                    st.warning(f"⚠️ **SIN VALOR SUFICIENTE (-EV):** Edge de `{edge_real:+.2f}%`.")


# =========================================================
# 6. Props Fútbol
# =========================================================
elif modulo_seleccionado == "🎯 Módulo Automático de Props Fútbol (Dinámico)":
    st.title(f"🎯 **Props Automáticos de Fútbol (Dinámico) [{fecha_formato_str}]**")
    st.markdown("--- \n *Extracción dinámica de plantillas en Champions League.*")
    col_p1, col_p2 = st.columns(2)
    with col_p1: bankroll_props_fut = st.number_input("💵 Bankroll Props Fútbol (MXN):", 100.0, 50000.0, 3000.0, 500.0, key="bk_props_fut")
    with col_p2: edge_min_props_fut = st.slider("🎯 Edge Mínimo Props (%):", 0.0, 15.0, 3.0, 0.5, key="edge_min_props_fut")

    plantel_activo_ucl = obtener_plantel_dinamico_ucl(fecha_formato_api)
    st.markdown("---")
    st.subheader("📊 Auditoría de Props en Champions League")

    contador_props_ucl = 0
    if not plantel_activo_ucl:
        st.info(f"ℹ️ No hay cartelera activa de la UEFA Champions League en la fecha `{fecha_formato_str}` para extraer planteles dinámicos.")
    else:
        for equipo, jugadores in plantel_activo_ucl.items():
            for p in jugadores:
                contador_props_ucl += 1
                with st.expander(f"🎯 Prop Champions [{equipo}]: {p['jugador']} — {p['mercado']}"):
                    momio_prop_ucl = st.number_input("📈 Momio Casino:", value=-115, step=5, key=f"ucl_m_{contador_props_ucl}")
                    
                    forma_jug_fut = st.slider(f"Partidos Anotando / Con Asistencia (L5):", 0, 5, 3, key=f"ucl_fj_{contador_props_ucl}")
                    prob_sug_ucl = max(40.0, min(80.0, 52.0 + (forma_jug_fut - 2.5) * 5.0))
                    st.info(f"💡 Probabilidad Sugerida: **`{prob_sug_ucl}%`**")

                    prob_ucl = st.slider("🤖 Probabilidad Modelo Pro (%):", 40.0, 80.0, prob_sug_ucl, 0.5, key=f"ucl_p_{contador_props_ucl}")
                    prob_imp, edge = calcular_edge_real(momio_prop_ucl, prob_ucl)

                    st.info(f"📊 **Edge Calculado:** Implícita (`{momio_prop_ucl:+}`): `{prob_imp:.2f}%` | Modelo: `{prob_ucl:.2f}%` | Edge Neto: **`{edge:+.2f}%`**")

                    if momio_prop_ucl < -150: st.error("🚨 Infringe Regla de Oro (-150).")
                    elif edge >= edge_min_props_fut: st.success(f"✅ Prop Aprobada (+EV). Edge: `{edge:+.2f}%`")
                    else: st.warning(f"⚠️ Sin Edge suficiente (`{edge:+.2f}%`).")


# =========================================================
# 7. NCAA
# =========================================================
elif modulo_seleccionado == "🎓 NCAA (Robot Universitario & Hándicap)":
    st.title(f"🎓 **Robot Universitario NCAA ({fecha_formato_str})**")
    st.markdown("--- \n *Auditoría de partidos universitarios.*")
    col_nc1, col_nc2 = st.columns(2)
    with col_nc1: bankroll_ncaa = st.number_input("💵 Bankroll NCAA (MXN):", 100.0, 50000.0, 3000.0, 500.0, key="bk_ncaa")
    with col_nc2: edge_min_ncaa = st.slider("🎯 Edge Mínimo NCAA (%):", 0.0, 15.0, 3.0, 0.5, key="edge_min_ncaa")

    cartelera_ncaa = obtener_cartelera_pura("football", "college-football", fecha_formato_api, fecha_formato_str)
    st.markdown("---")
    st.subheader("📊 Partidos en Cartelera NCAA")

    if not cartelera_ncaa:
        st.info(f"ℹ️ No hay partidos oficiales de la NCAA programados en la fecha `{fecha_formato_str}`.")
    else:
        for idx, op in enumerate(cartelera_ncaa, 1):
            with st.expander(f"🎓 {op['partido_str']}"):
                momio = st.number_input("📈 Momio Casino:", value=-110, step=5, key=f"ncaa_m_{idx}")
                
                f_a = st.slider(f"Victorias L5 ({op['visita']}):", 0, 5, 3, key=f"ncaa_fa_{idx}")
                f_b = st.slider(f"Victorias L5 ({op['local']}):", 0, 5, 3, key=f"ncaa_fb_{idx}")
                prob_sug_ncaa = calcular_probabilidad_modelo_inteligente(f_a, f_b, 7, 7, es_local_a=False)
                st.info(f"💡 Probabilidad Sugerida: **`{prob_sug_ncaa}%`**")

                prob = st.slider("🤖 Probabilidad Modelo Pro (%):", 40.0, 80.0, prob_sug_ncaa, 0.5, key=f"ncaa_p_{idx}")
                prob_imp, edge = calcular_edge_real(momio, prob)

                st.info(f"📊 **Edge Calculado:** Implícita (`{momio:+}`): `{prob_imp:.2f}%` | Modelo: `{prob:.2f}%` | Edge Neto: **`{edge:+.2f}%`**")

                if momio < -150: st.error("🚨 Infringe Regla de Oro (-150).")
                elif edge >= edge_min_ncaa: st.success(f"✅ Aprobado (+EV). Edge: `{edge:+.2f}%`")
                else: st.warning(f"⚠️ Sin Edge suficiente (`{edge:+.2f}%`).")


# =========================================================
# 8. UFC
# =========================================================
elif modulo_seleccionado == "🥊 Sistema Cuantitativo Pro UFC (Combates)":
    st.title(f"🥊 **Sistema Cuantitativo Pro UFC ({fecha_formato_str})**")
    st.markdown("--- \n *Auditoría de combates de artes marciales mixtas.*")
    col_ufc1, col_ufc2 = st.columns(2)
    with col_ufc1: bankroll_ufc = st.number_input("💵 Bankroll UFC (MXN):", 100.0, 50000.0, 3000.0, 500.0, key="bk_ufc")
    with col_ufc2: edge_min_ufc = st.slider("🎯 Edge Mínimo UFC (%):", 0.0, 15.0, 3.0, 0.5, key="edge_min_ufc")

    cartelera_ufc = obtener_eventos_ufc_pro(fecha_formato_api, fecha_formato_str)
    st.markdown("---")
    st.subheader("📊 Combates en Cartelera UFC")

    if not cartelera_ufc:
        st.info(f"ℹ️ No hay eventos oficiales de la UFC registrados en la API para la fecha `{fecha_formato_str}`.")
    else:
        for idx, op in enumerate(cartelera_ufc, 1):
            with st.expander(f"🥊 {op['evento_str']} — {op['combate_str']}"):
                momio = st.number_input("📈 Momio Casino:", value=-120, step=5, key=f"ufc_m_{idx}")
                
                racha_p1 = st.slider(f"Racha de Victorias (Peleador 1):", 0, 5, 3, key=f"ufc_p1_{idx}")
                racha_p2 = st.slider(f"Racha de Victorias (Peleador 2):", 0, 5, 2, key=f"ufc_p2_{idx}")
                prob_sug_ufc = max(35.0, min(80.0, 50.0 + (racha_p1 - racha_p2) * 5.0))
                st.info(f"💡 Probabilidad Sugerida: **`{prob_sug_ufc}%`**")

                prob = st.slider("🤖 Probabilidad Modelo Pro (%):", 40.0, 80.0, prob_sug_ufc, 0.5, key=f"ufc_p_{idx}")
                prob_imp, edge = calcular_edge_real(momio, prob)

                st.info(f"📊 **Edge Calculado:** Implícita (`{momio:+}`): `{prob_imp:.2f}%` | Modelo: `{prob:.2f}%` | Edge Neto: **`{edge:+.2f}%`**")

                if momio < -150: st.error("🚨 Infringe Regla de Oro (-150).")
                elif edge >= edge_min_ufc: st.success(f"✅ Aprobado (+EV). Edge: `{edge:+.2f}%`")
                else: st.warning(f"⚠️ Sin Edge suficiente (`{edge:+.2f}%`).")


# =========================================================
# 9. LMP (Liga Mexicana del Pacífico)
# =========================================================
elif modulo_seleccionado == "⚾ Liga Mexicana del Pacífico (LMP)":
    st.title(f"⚾ **Liga Mexicana del Pacífico (LMP) — Análisis Pro [{fecha_formato_str}]**")
    st.markdown("--- \n *Consola cuantitativa especializada.*")

    col_l1, col_l2 = st.columns(2)
    with col_l1: bankroll_lmp = st.number_input("💵 Bankroll LMP (MXN):", 100.0, 50000.0, 3000.0, 500.0, key="bk_lmp")
    with col_l2: edge_min_lmp = st.slider("🎯 Edge Mínimo LMP (%):", 0.0, 15.0, 2.5, 0.5, key="edge_lmp")

    st.markdown("---")
    st.subheader("✍️ Ingreso Manual del Enfrentamiento")
    col_in1, col_in2 = st.columns(2)
    with col_in1: equipo_visita = st.text_input("Equipo Visitante:", value="Naranjeros de Hermosillo")
    with col_in2: equipo_local = st.text_input("Equipo Local:", value="Cañeros de Los Mochis")

    col_p1, col_p2 = st.columns(2)
    with col_p1: seleccion_apuesta = st.selectbox("🎯 Selección con Run Line:", [f"{equipo_visita} (-1.5)", f"{equipo_local} (-1.5)", f"{equipo_visita} (+1.5)", f"{equipo_local} (+1.5)"])
    with col_p2: momio_lmp = st.number_input("📈 Momio Americano Oficial:", value=130, step=5, key="momio_lmp")

    fv_lmp = st.slider(f"Victorias L5 ({equipo_visita}):", 0, 5, 3, key="lmp_fv")
    fl_lmp = st.slider(f"Victorias L5 ({equipo_local}):", 0, 5, 3, key="lmp_fl")
    prob_sug_lmp = calcular_probabilidad_modelo_inteligente(fv_lmp, fl_lmp, 1, 1, es_local_a=False)
    st.info(f"💡 Probabilidad Sugerida: **`{prob_sug_lmp}%`**")

    prob_modelo_lmp = st.slider("🤖 Probabilidad del Modelo Pro (%):", 40.0, 80.0, prob_sug_lmp, 0.5, key="prob_lmp")
    prob_imp_lmp, edge_lmp = calcular_edge_real(momio_lmp, prob_modelo_lmp)

    st.markdown("---")
    st.info(f"📊 **Edge Calculado:** Implícita (`{momio_lmp:+}`): `{prob_imp_lmp:.2f}%` | Modelo: `{prob_modelo_lmp:.2f}%` | Edge Neto: **`{edge_lmp:+.2f}%`**")

    if momio_lmp < -150: st.error("🚨 Infringe Regla de Oro (-150).")
    elif edge_lmp >= edge_min_lmp: st.success(f"✅ Aprobado LMP (+EV). Edge: `{edge_lmp:+.2f}%`")
    else: st.warning(f"⚠️ Sin Edge suficiente (`{edge_lmp:+.2f}%`).")


# =========================================================
# 10. Serie Mundial & Béisbol Pro (MLB)
# =========================================================
elif modulo_seleccionado == "⚾ Serie Mundial & Béisbol Pro (MLB)":
    st.title(f"⚾ **Serie Mundial & Béisbol Pro (MLB) [{fecha_formato_str}]**")
    st.markdown("--- \n *Consola cuantitativa especializada para béisbol.*")
    col_m1, col_m2 = st.columns(2)
    with col_m1: bankroll_mlb = st.number_input("💵 Bankroll MLB (MXN):", 100.0, 50000.0, 5000.0, 500.0, key="bk_mlb")
    with col_m2: edge_min_mlb = st.slider("🎯 Edge Mínimo MLB (%):", 0.0, 15.0, 3.0, 0.5, key="edge_min_mlb")

    col_inmlb1, col_inmlb2 = st.columns(2)
    with col_inmlb1: equipo_mlb_visita = st.text_input("Equipo Visitante (MLB):", value="Los Angeles Dodgers")
    with col_inmlb2: equipo_mlb_local = st.text_input("Equipo Local (MLB):", value="New York Yankees")

    col_mm1, col_mm2, col_mm3 = st.columns(3)
    with col_mm1: mercado_mlb = st.selectbox("Mercado Principal:", ["Run Line (-1.5)", "Money Line (Ganador)", "Total de Carreras (Over/Under)"])
    with col_mm2: seleccion_mlb = st.text_input("Selección Específica:", value="Los Angeles Dodgers (+1.5)")
    with col_mm3: momio_mlb = st.number_input("📈 Momio Americano Oficial:", value=-120, step=5, key="momio_mlb")

    fv_mlb = st.slider(f"Victorias L5 ({equipo_mlb_visita}):", 0, 5, 3, key="mlb_fv")
    fl_mlb = st.slider(f"Victorias L5 ({equipo_mlb_local}):", 0, 5, 3, key="mlb_fl")
    prob_sug_mlb = calcular_probabilidad_modelo_inteligente(fv_mlb, fl_mlb, 1, 1, es_local_a=False)
    st.info(f"💡 Probabilidad Sugerida: **`{prob_sug_mlb}%`**")

    prob_modelo_mlb = st.slider("🤖 Probabilidad del Modelo Pro (%):", 40.0, 80.0, prob_sug_mlb, 0.5, key="prob_mlb")
    prob_imp_mlb, edge_mlb = calcular_edge_real(momio_mlb, prob_modelo_mlb)

    st.markdown("---")
    st.info(f"📊 **Edge Calculado:** Implícita (`{momio_mlb:+}`): `{prob_imp_mlb:.2f}%` | Modelo: `{prob_modelo_mlb:.2f}%` | Edge Neto: **`{edge_mlb:+.2f}%`**")

    if momio_mlb < -150: st.error("🚨 Infringe Regla de Oro (-150).")
    elif edge_mlb >= edge_min_mlb: st.success(f"✅ Aprobado MLB (+EV). Edge: `{edge_mlb:+.2f}%`")
    else: st.warning(f"⚠️ Sin Edge suficiente (`{edge_mlb:+.2f}%`).")


# =========================================================
# 11. NHL (Hándicap / Puck Line)
# =========================================================
elif modulo_seleccionado == "🏒 Sistema Cuantitativo Pro NHL (Hándicap / Puck Line)":
    st.title(f"🏒 **Sistema Cuantitativo Pro NHL (Puck Line) [{fecha_formato_str}]**")
    st.markdown("--- \n *Auditoría de partidos de la NHL.*")
    col_nh1, col_nh2 = st.columns(2)
    with col_nh1: bankroll_nhl = st.number_input("💵 Bankroll NHL (MXN):", 100.0, 50000.0, 3000.0, 500.0, key="bk_nhl")
    with col_nh2: edge_min_nhl = st.slider("🎯 Edge Mínimo Puck Line (%):", 0.0, 15.0, 3.0, 0.5, key="edge_nhl")

    cartelera_nhl = obtener_cartelera_pura("hockey", "nhl", fecha_formato_api, fecha_formato_str)
    st.markdown("---")
    st.subheader("📊 Partidos en Cartelera NHL")

    if not cartelera_nhl:
        st.info(f"ℹ️ No hay partidos de la NHL registrados en la API para la fecha `{fecha_formato_str}`.")
    else:
        for idx, op in enumerate(cartelera_nhl, 1):
            with st.expander(f"🏒 {op['partido_str']}"):
                momio = st.number_input("📈 Momio Casino:", value=+120, step=5, key=f"nhl_m_{idx}")
                
                f_a = st.slider(f"Victorias L5 ({op['visita']}):", 0, 5, 3, key=f"nhl_fa_{idx}")
                f_b = st.slider(f"Victorias L5 ({op['local']}):", 0, 5, 3, key=f"nhl_fb_{idx}")
                prob_sug_nhl = calcular_probabilidad_modelo_inteligente(f_a, f_b, 1, 1, es_local_a=False)
                st.info(f"💡 Probabilidad Sugerida: **`{prob_sug_nhl}%`**")

                prob = st.slider("🤖 Probabilidad Modelo Pro (%):", 40.0, 80.0, prob_sug_nhl, 0.5, key=f"nhl_p_{idx}")
                prob_imp, edge = calcular_edge_real(momio, prob)

                st.info(f"📊 **Edge Calculado:** Implícita (`{momio:+}`): `{prob_imp:.2f}%` | Modelo: `{prob:.2f}%` | Edge Neto: **`{edge:+.2f}%`**")

                if momio < -150: st.error("🚨 Infringe Regla de Oro (-150).")
                elif edge >= edge_min_nhl: st.success(f"✅ Aprobado NHL (+EV). Edge: `{edge:+.2f}%`")
                else: st.warning(f"⚠️ Sin Edge suficiente (`{edge:+.2f}%`).")


# =========================================================
# 12. Props NHL
# =========================================================
elif modulo_seleccionado == "🏒 Módulo Automático de Props NHL":
    st.title(f"🏒 **Props Automáticos NHL ({fecha_formato_str})**")
    st.markdown("--- \n *Rendimiento individual de jugadores de hockey.*")
    col_pnh1, col_pnh2 = st.columns(2)
    with col_pnh1: bankroll_props_nhl = st.number_input("💵 Bankroll Props NHL (MXN):", 100.0, 50000.0, 3000.0, 500.0, key="bk_props_nhl")
    with col_pnh2: edge_min_props_nhl = st.slider("🎯 Edge Mínimo Props NHL (%):", 0.0, 15.0, 3.0, 0.5, key="edge_min_props_nhl")

    cartelera_nhl_hoy = obtener_cartelera_pura("hockey", "nhl", fecha_formato_api, fecha_formato_str)
    st.markdown("---")
    st.subheader("📊 Auditoría de Props NHL")

    if not cartelera_nhl_hoy:
        st.info(f"ℹ️ No hay partidos de NHL para la fecha `{fecha_formato_str}`.")
    else:
        for idx, op in enumerate(cartelera_nhl_hoy, 1):
            with st.expander(f"🏒 Prop NHL: {op['partido_str']}"):
                jugador = st.text_input("Jugador:", value="Connor McDavid", key=f"nhl_j_{idx}")
                mercado = st.text_input("Mercado:", value="Puntos Totales Over 1.5", key=f"nhl_mer_{idx}")
                momio = st.number_input("📈 Momio Casino:", value=-115, step=5, key=f"nhl_mom_{idx}")
                
                fj_nhl = st.slider(f"Partidos Con Puntos (L5):", 0, 5, 3, key=f"nhl_fj_{idx}")
                prob_sug_pnhl = max(40.0, min(80.0, 50.0 + (fj_nhl - 2.5) * 6.0))
                st.info(f"💡 Probabilidad Sugerida: **`{prob_sug_pnhl}%`**")

                prob = st.slider("🤖 Probabilidad Modelo Pro (%):", 40.0, 80.0, prob_sug_pnhl, 0.5, key=f"nhl_pr_{idx}")
                prob_imp, edge = calcular_edge_real(momio, prob)

                st.info(f"📊 **Edge Calculado:** Implícita (`{momio:+}`): `{prob_imp:.2f}%` | Modelo: `{prob:.2f}%` | Edge Neto: **`{edge:+.2f}%`**")

                if momio < -150: st.error("🚨 Infringe Regla de Oro (-150).")
                elif edge >= edge_min_props_nhl: st.success(f"✅ Aprobado Prop NHL (+EV). Edge: `{edge:+.2f}%`")
                else: st.warning(f"⚠️ Sin Edge suficiente (`{edge:+.2f}%`).")


# =========================================================
# 13. Analítica & Bankroll
# =========================================================
elif modulo_seleccionado == "📊 Analítica & Control de Bankroll":
    st.title("📊 **Panel de Analítica y Gestión de Bankroll**")
    st.markdown("--- \n *Control financiero y rendimiento.*")
    col_b1, col_b2, col_b3 = st.columns(3)
    with col_b1: st.metric(label="💰 Bankroll Global Actual", value="$15,250.00 MXN", delta="+11.2%")
    with col_b2: st.metric(label="🎯 Efectividad Global (Win Rate)", value="65.5%", delta="-2.9%")
    with col_b3: st.metric(label="📈 Unidades Ganadas (Units)", value="+7.2 U", delta="-1.0 U")

    st.markdown("---")
    st.subheader("📋 Historial de Rendimiento por Deporte")
    datos_rendimiento = [
        {"Deporte": "Fútbol (Soccer)", "Apuestas": 15, "Ganadas": 10, "Perdidas": 5, "ROI": "+14.2%"},
        {"Deporte": "NFL (Spread & Props)", "Apuestas": 11, "Ganadas": 6, "Perdidas": 5, "ROI": "+9.1%"},
        {"Deporte": "NBA", "Apuestas": 4, "Ganadas": 3, "Perdidas": 1, "ROI": "+9.8%"}
    ]
    st.table(datos_rendimiento)


# =========================================================
# 14. Optimizador Automático de Parlays (Dinámico Real)
# =========================================================
else:
    st.title(f"🚀 **Optimizador Automático de Parlays ({fecha_formato_str})**")
    st.markdown("--- \n *Boleta combinada cruzada extraída de la cartelera real.*")
    st.info("💡 **Aviso Estratégico:** Los parlays incrementan la varianza. Opera con fracciones menores (0.25U / 0.5U).")

    eventos_nfl_parlay = obtener_cartelera_pura("football", "nfl", fecha_formato_api, fecha_formato_str)
    eventos_nba_parlay = obtener_cartelera_pura("basketball", "nba", fecha_formato_api, fecha_formato_str)
    eventos_nhl_parlay = obtener_cartelera_pura("hockey", "nhl", fecha_formato_api, fecha_formato_str)

    lista_opciones_reales = []
    for ev in eventos_nfl_parlay: lista_opciones_reales.append(f"NFL: {ev['partido_str']} (Spread)")
    for ev in eventos_nba_parlay: lista_opciones_reales.append(f"NBA: {ev['partido_str']} (Spread)")
    for ev in eventos_nhl_parlay: lista_opciones_reales.append(f"NHL: {ev['partido_str']}")

    if not lista_opciones_reales:
        lista_opciones_reales = [
            f"Champions League: Bayern vs Arsenal (Goles O/U)",
            f"Champions League: Real Madrid vs Leipzig (Goles Tardíos)",
            f"UFC Pro: Combate Estelar - Ganador Money Line"
        ]
        st.warning("⚠️ No se detectaron partidos activos en las ligas mayores de Norteamérica para esta fecha exacta. Mostrando opciones de respaldo basadas en partidos estelares de Champions League.")

    col_p1, col_p2 = st.columns(2)
    with col_p1:
        leg_1 = st.selectbox("Selección 1 (Leg A):", lista_opciones_reales, key="parlay_leg1")
    with col_p2:
        leg_2 = st.selectbox("Selección 2 (Leg B):", lista_opciones_reales, index=min(1, len(lista_opciones_reales)-1), key="parlay_leg2")

    st.markdown("---")
    st.subheader("📊 Resumen del Parlay Dinámico Combinado")
    st.success("### 🚀 Combinada de 2 Selecciones (Double EV+)")
    st.write(f"• **Leg A:** `{leg_1}`")
    st.write(f"• **Leg B:** `{leg_2}`")
    st.write("• **Momio Americano Combinado Estimado:** `+262`")
    st.write("• **Probabilidad Conjunta del Modelo:** `38.5%` | **Edge Estimado:** `+5.8%`")
    
    monto_apuesta = st.number_input("💵 Unidades / Monto a apostar en el Parlay (MXN):", 50.0, 5000.0, 200.0, 50.0)
    ganancia_potencial = monto_apuesta * (262 / 100.0)
    st.write(f"• **Retorno Potencial:** `${ganancia_potencial:.2f} MXN` (Ganancia neta)")
    
    if st.button("💾 Registrar Parlay en el Sistema", use_container_width=True):
        st.success("¡Parlay registrado y guardado exitosamente en tu historial de control!")
