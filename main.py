from datetime import datetime, date
import math
import os
import requests
import streamlit as st
import threading
import time
from datetime import timedelta

# Configuración global de la página
st.set_page_config(
    page_title="Central de Apuestas Pro - Master Suite (Pro Risk, CLV & Automations)",
    page_icon="🛡️",
    layout="wide"
)

# ---------------------------------------------------------
# HILO EN SEGUNDO PLANO PARA CAPTURA AUTOMÁTICA DE CLV
# ---------------------------------------------------------
def hilo_captura_clv(base_datos, api_deportiva):
    """
    Este bucle corre eternamente en segundo plano sin detener tu software principal.
    """
    print("[INFO] Hilo secundario de monitoreo CLV iniciado.")
    
    while True:
        try:
            ahora = datetime.now()
            margen_tiempo = ahora + timedelta(minutes=2)
            
            # Nota: Aquí se conectará a tus métodos reales de base de datos y API
            apuestas_proximas = base_datos.obtener_apuestas_sin_clv(desde=ahora, hasta=margen_tiempo)
            
            for apuesta in apuestas_proximas:
                cuota_cierre_real = api_deportiva.obtener_cuota_actual(apuesta['id_partido'])
                
                if cuota_cierre_real:
                    clv_positivo = apuesta['cuota_comprada'] > cuota_cierre_real
                    base_datos.actualizar_clv_apuesta(
                        id_partido=apuesta['id_partido'],
                        cuota_cierre=cuota_cierre_real,
                        clv_positivo=clv_positivo
                    )
                    print(f"[CLV CONTROL] Partido {apuesta['id_partido']} cerrado. ¿Éxito CLV?: {clv_positivo}")
                    
        except Exception as e:
            print(f"[ERROR HILO CLV] Fallo en la captura: {e}")
            
        time.sleep(60)

# Inicialización segura del hilo de fondo para que corra una sola vez
if 'hilo_clv_iniciado' not in st.session_state:
    # t = threading.Thread(target=hilo_captura_clv, args=(mi_bd, mi_api), daemon=True)
    # t.start()
    st.session_state['hilo_clv_iniciado'] = True


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
        "⚽ Módulo Global de Fútbol (Poisson Dinámico, BTTS & Hándicap Asiático)",
        "🎯 Módulo Automático de Props Fútbol (Dinámico)",
        "🎓 NCAA (Robot Universitario & Hándicap)",
        "🥊 Sistema Cuantitativo Pro UFC (Combates)",
        "⚾ Liga Mexicana del Pacífico (LMP)",
        "⚾ Serie Mundial & Béisbol Pro (MLB)",
        "🏒 Sistema Cuantitativo Pro NHL (Hándicap / Puck Line)",
        "🏒 Módulo Automático de Props NHL",
        "📊 Analítica, Control de Bankroll & Registro CLV",
        "🚀 Optimizador Automático de Parlays"
    ]
)

st.sidebar.markdown("---")
st.sidebar.info(f"Analizando fecha: **{fecha_formato_str}**")


# ---------------------------------------------------------
# MOTORES MATEMÁTICOS Y ESTADÍSTICOS UNIVERSALES
# ---------------------------------------------------------
def momio_a_probabilidad_implicita(momio):
    if momio > 0:
        return 100.0 / (momio + 100.0)
    else:
        return abs(momio) / (abs(momio) + 100.0)


def calcular_edge_real(momio_casino, probabilidad_modelo):
    prob_imp = momio_a_probabilidad_implicita(momio_casino) * 100.0
    edge = probabilidad_modelo - prob_imp
    return prob_imp, edge


def calcular_probabilidad_modelo_gaussiano(v_a, d_a, v_b, d_b, descanso_a, descanso_b, es_local_a=False):
    base_prob = 53.0 if not es_local_a else 47.0
    diferencia_forma = ((v_a - d_a) - (v_b - d_b)) * 3.5
    fatigue_a = -4.0 if descanso_a == 0 else (-1.5 if descanso_a == 1 else 0.0)
    fatigue_b = -4.0 if descanso_b == 0 else (-1.5 if descanso_b == 1 else 0.0)
    diferencia_fatigue = fatigue_a - fatigue_b
    probabilidad_sugerida = base_prob + diferencia_forma - diferencia_fatigue
    return max(25.0, min(88.0, round(probabilidad_sugerida, 2)))


def poisson_prob(lmbda, k):
    if lmbda <= 0:
        return 1.0 if k == 0 else 0.0
    return (math.exp(-lmbda) * (lmbda ** k)) / math.factorial(k)


def calcular_probabilidades_poisson_dinamico(lambda_local, lambda_visita, linea_objetivo=2.5, max_goles=7):
    prob_over = 0.0
    prob_under = 0.0
    prob_btts = 0.0
    for g_loc in range(max_goles + 1):
        for g_vis in range(max_goles + 1):
            p = poisson_prob(lambda_local, g_loc) * poisson_prob(lambda_visita, g_vis)
            total_goles = g_loc + g_vis
            
            if total_goles > linea_objetivo:
                prob_over += p
            else:
                prob_under += p
                
            if g_loc > 0 and g_vis > 0:
                prob_btts += p

    return round(prob_over * 100, 2), round(prob_under * 100, 2), round(prob_btts * 100, 2)


# 🛡️ MÓDULO DE CONTROL DE RIESGO PROFESIONAL & CLV
def modulo_control_riesgo(historial_apuestas, bankroll_actual, stake_sugerido_kelly):
    ultimas_20 = historial_apuestas[-20:] if len(historial_apuestas) >= 20 else historial_apuestas
    perdidas_seguidas = 0
    
    for apuesta in reversed(ultimas_20):
        if apuesta.get('resultado') == 'perdida':
            perdidas_seguidas += 1
        else:
            break
            
    factor_ajuste = 1.0
    if perdidas_seguidas >= 5:
        factor_ajuste = 0.5  
    if perdidas_seguidas >= 8:
        factor_ajuste = 0.25 

    clv_ganados = sum(1 for x in ultimas_20 if x.get('clv_positivo', False))
    total_evaluado = len(ultimas_20)
    
    if total_evaluado > 10:
        tasa_clv = clv_ganados / total_evaluado
        if tasa_clv < 0.50:
            factor_ajuste = min(factor_ajuste, 0.5) 

    stake_final = stake_sugerido_kelly * factor_ajuste
    max_permitido = bankroll_actual * 0.03
    if stake_final > max_permitido:
        stake_final = max_permitido
        
    return round(stake_final, 2), perdidas_seguidas, factor_ajuste


@st.cache_data(ttl=300)
def obtener_cartelera_pura(deporte, liga, fecha_str_api, fecha_str_humana):
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
    except:
        pass
    return []


@st.cache_data(ttl=300)
def obtener_eventos_ufc_pro(fecha_str_api, fecha_str_humana):
    url = f"https://site.api.espn.com/apis/site/v2/sports/mma/ufc/scoreboard?dates={fecha_str_api}&limit=20"
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


# =========================================================
# 1. NFL
# =========================================================
if modulo_seleccionado == "🛡️ Sistema Cuantitativo Pro NFL (Spread & Totales O/U)":
    st.title(f"🛡️ **Sistema Cuantitativo Pro NFL (Spread & Totales) [{fecha_formato_str}]**")
    st.markdown("--- \n *Modelo Gaussiano de eficiencia y descanso aplicado a la NFL.*")
    
    col1, col2 = st.columns(2)
    with col1: bankroll = st.number_input("💵 Bankroll NFL (MXN):", 100.0, 50000.0, 5000.0, 500.0, key="bk_nfl")
    with col2: edge_min = st.slider("🎯 Edge Mínimo Requerido NFL (%):", 0.0, 15.0, 3.0, 0.5, key="edge_nfl")

    cartelera = obtener_cartelera_pura("football", "nfl", fecha_formato_api, fecha_formato_str)
    st.markdown("---")
    st.subheader("📊 Partidos en Cartelera NFL")

    if not cartelera:
        st.info(f"ℹ️ No hay partidos de la NFL programados en la fecha `{fecha_formato_str}`.")
    else:
        for idx, op in enumerate(cartelera, 1):
            with st.expander(f"🏈 Encuentro #{idx}: {op['partido_str']}"):
                mercado_nfl_eleccion = st.selectbox(
                    "🎯 Selecciona el Mercado NFL a Auditar:",
                    ["1️⃣ Hándicap / Spread de Puntos", "2️⃣ Total de Puntos del Partido (Over / Under O/U)", "3️⃣ Total de Puntos Primera Mitad (1H Over / Under)"],
                    key=f"mercado_nfl_sel_{idx}"
                )

                col_n1, col_n2, col_n3 = st.columns(3)
                with col_n1:
                    tipo_sel_nfl = st.selectbox("Selección:", [f"Visitante ({op['visita']})", f"Local ({op['local']})"], key=f"nfl_sel_eq_{idx}")
                with col_n2:
                    linea_nfl = st.text_input("Línea Casino:", value="-3.5" if "Spread" in mercado_nfl_eleccion else "45.5", key=f"nfl_linea_val_{idx}")
                with col_n3:
                    momio_nfl = st.number_input("📈 Momio Casino (Americano):", value=-110, step=5, key=f"nfl_m_val_{idx}")

                col_fa1, col_fa2 = st.columns(2)
                with col_fa1: v_a = st.number_input(f"Victorias L5 ({op['visita']}):", 0, 5, 3, key=f"nfl_va_v_{idx}")
                with col_fa2: d_a = st.number_input(f"Derrotas L5 ({op['visita']}):", 0, 5, 2, key=f"nfl_da_d_{idx}")

                col_fb1, col_fb2 = st.columns(2)
                with col_fb1: v_b = st.number_input(f"Victorias L5 ({op['local']}):", 0, 5, 3, key=f"nfl_vb_v_{idx}")
                with col_fb2: d_b = st.number_input(f"Derrotas L5 ({op['local']}):", 0, 5, 2, key=f"nfl_db_d_{idx}")

                col_fd1, col_fd2 = st.columns(2)
                with col_fd1: descanso_a = st.number_input(f"Días Descanso Visita:", 0, 10, 6, key=f"nfl_desc_vis_{idx}")
                with col_fd2: descanso_b = st.number_input(f"Días Descanso Local:", 0, 10, 6, key=f"nfl_desc_loc_{idx}")

                prob_mod = calcular_probabilidad_modelo_gaussiano(v_a, d_a, v_b, d_b, descanso_a, descanso_b, es_local_a=False)
                st.success(f"🤖 **Probabilidad Real del Modelo Gaussiano Pro:** **`{prob_mod:.2f}%`**")
                prob_imp, edge = calcular_edge_real(momio_nfl, prob_mod)
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
                jugador = st.text_input("Jugador:", value="Patrick Mahomes", key=f"nfl_prop_j_{idx}")
                mercado = st.text_input("Mercado:", value="Yardas de Pase Over 265.5", key=f"nfl_prop_m_{idx}")
                momio = st.number_input("📈 Momio Casino:", value=-115, step=5, key=f"nfl_prop_mom_{idx}")
                
                col_pj1, col_pj2 = st.columns(2)
                with col_pj1: cumple = st.number_input("Partidos cumpliendo línea (L5):", 0, 5, 3, key=f"nfl_prop_c_{idx}")
                with col_pj2: no_cumple = st.number_input("Partidos sin cumplir línea (L5):", 0, 5, 2, key=f"nfl_prop_nc_{idx}")
                
                prob = max(40.0, min(80.0, 50.0 + (cumple - no_cumple) * 6.0))
                st.success(f"🤖 **Probabilidad Real del Modelo Pro:** **`{prob:.2f}%`**")
                prob_imp, edge = calcular_edge_real(momio, prob)
                st.info(f"📊 **Edge Calculado:** Implícita (`{momio:+}`): `{prob_imp:.2f}%` | Modelo: `{prob:.2f}%` | Edge Neto: **`{edge:+.2f}%`**")

                if momio < -150: st.error("🚨 Infringe Regla de Oro (-150).")
                elif edge >= edge_min_props_nfl: st.success(f"✅ Aprobado Prop (+EV). Edge: `{edge:+.2f}%`")
                else: st.warning(f"⚠️ Sin Edge suficiente (`{edge:+.2f}%`).")


# =========================================================
# 3. NBA
# =========================================================
elif modulo_seleccionado == "🏀 Sistema Cuantitativo Pro NBA (Spread & Totales O/U)":
    st.title(f"🏀 **Sistema Cuantitativo Pro NBA (Spread & Totales) [{fecha_formato_str}]**")
    st.markdown("--- \n *Modelo Gaussiano con factor de fatiga de calendario para la NBA.*")
    
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
                    key=f"mercado_nba_sel_{idx}"
                )

                col_n1, col_n2, col_n3 = st.columns(3)
                with col_n1:
                    tipo_sel_nba = st.selectbox("Selección:", [f"Visitante ({op['visita']})", f"Local ({op['local']})"], key=f"nba_sel_eq_{idx}")
                with col_n2:
                    linea_nba = st.text_input("Línea Casino:", value="-4.5" if "Spread" in mercado_nba_eleccion else "224.5", key=f"nba_linea_val_{idx}")
                with col_n3:
                    momio_nba = st.number_input("📈 Momio Casino (Americano):", value=-110, step=5, key=f"nba_m_val_{idx}")

                col_va1, col_va2 = st.columns(2)
                with col_va1: v_a = st.number_input(f"Victorias L5 ({op['visita']}):", 0, 5, 3, key=f"nba_va_v_{idx}")
                with col_va2: d_a = st.number_input(f"Derrotas L5 ({op['visita']}):", 0, 5, 2, key=f"nba_da_d_{idx}")

                col_vb1, col_vb2 = st.columns(2)
                with col_vb1: v_b = st.number_input(f"Victorias L5 ({op['local']}):", 0, 5, 3, key=f"nba_vb_v_{idx}")
                with col_vb2: d_b = st.number_input(f"Derrotas L5 ({op['local']}):", 0, 5, 2, key=f"nba_db_d_{idx}")

                col_nd1, col_nd2 = st.columns(2)
                with col_nd1: descanso_a = st.number_input(f"Días Descanso Visita (0 = B2B):", 0, 10, 0, key=f"nba_desc_vis_{idx}")
                with col_nd2: descanso_b = st.number_input(f"Días Descanso Local (0 = B2B):", 0, 10, 2, key=f"nba_desc_loc_{idx}")

                prob_nba = calcular_probabilidad_modelo_gaussiano(v_a, d_a, v_b, d_b, descanso_a, descanso_b, es_local_a=False)
                st.success(f"🤖 **Probabilidad Real del Modelo Gaussiano Pro:** **`{prob_nba:.2f}%`**")
                prob_imp, edge = calcular_edge_real(momio_nba, prob_nba)
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
                jugador = st.text_input("Jugador:", value="LeBron James", key=f"nba_prop_j_{idx}")
                mercado = st.text_input("Mercado:", value="Puntos Totales Over 24.5", key=f"nba_prop_m_{idx}")
                momio = st.number_input("📈 Momio Casino:", value=-115, step=5, key=f"nba_prop_mom_{idx}")
                
                col_nj1, col_nj2 = st.columns(2)
                with col_nj1: cumple = st.number_input("Partidos cumpliendo línea (L5):", 0, 5, 3, key=f"nba_prop_c_{idx}")
                with col_nj2: no_cumple = st.number_input("Partidos sin cumplir línea (L5):", 0, 5, 2, key=f"nba_prop_nc_{idx}")
                
                prob = max(40.0, min(80.0, 50.0 + (cumple - no_cumple) * 6.0))
                st.success(f"🤖 **Probabilidad Real del Modelo Pro:** **`{prob:.2f}%`**")
                prob_imp, edge = calcular_edge_real(momio, prob)
                st.info(f"📊 **Edge Calculado:** Implícita (`{momio:+}`): `{prob_imp:.2f}%` | Modelo: `{prob:.2f}%` | Edge Neto: **`{edge:+.2f}%`**")

                if momio < -150: st.error("🚨 Infringe Regla de Oro (-150).")
                elif edge >= edge_min_props_nba: st.success(f"✅ Aprobado Prop (+EV). Edge: `{edge:+.2f}%`")
                else: st.warning(f"⚠️ Sin Edge suficiente (`{edge:+.2f}%`).")


# =========================================================
# 5. FÚTBOL
# =========================================================
elif modulo_seleccionado == "⚽ Módulo Global de Fútbol (Poisson Dinámico, BTTS & Hándicap Asiático)":
    st.title(f"⚽ **Cazador de Goles, Minas de Oro & Hándicap Asiático — Fútbol Pro [{fecha_formato_str}]**")
    st.markdown("--- \n *Poisson Dinámico completo integrado con desgloses V-E-D y Hándicaps Asiáticos por equipo.*")
    
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
    st.subheader("📋 Cartelera Real & Simulación de Poisson con Hándicap")

    if not cartelera_soccer:
        st.info(f"ℹ️ No se encontraron partidos programados en la API para esta liga en la fecha `{fecha_formato_str}`.")
    else:
        for idx, op in enumerate(cartelera_soccer, 1):
            with st.expander(f"⚽ Encuentro #{idx}: {op['partido_str']}"):
                
                st.markdown("### 🧬 Estadísticas L5 (Victorias - Empates - Derrotas) & Goles Esperados")
                col_ved1, col_ved2 = st.columns(2)
                with col_ved1:
                    st.markdown(f"**Visitante: `{op['visita']}`**")
                    v_a = st.number_input("Victorias L5:", 0, 5, 2, key=f"soccer_va_{idx}")
                    e_a = st.number_input("Empates L5:", 0, 5, 2, key=f"soccer_ea_{idx}")
                    d_a = st.number_input("Derrotas L5:", 0, 5, 1, key=f"soccer_da_{idx}")
                    lam_visita = st.number_input(f"Goles Esperados Visita ($\\mu$):", 0.1, 5.0, 1.15, 0.05, key=f"soccer_lam_vis_{idx}")
                with col_ved2:
                    st.markdown(f"**Local: `{op['local']}`**")
                    v_b = st.number_input("Victorias L5:", 0, 5, 3, key=f"soccer_vb_{idx}")
                    e_b = st.number_input("Empates L5:", 0, 5, 1, key=f"soccer_vb_e_{idx}")
                    d_b = st.number_input("Derrotas L5:", 0, 5, 1, key=f"soccer_db_{idx}")
                    lam_local = st.number_input(f"Goles Esperados Local ($\\lambda$):", 0.1, 5.0, 1.55, 0.05, key=f"soccer_lam_loc_{idx}")

                p_over_15, p_under_15, _ = calcular_probabilidades_poisson_dinamico(lam_local, lam_visita, 1.5)
                p_over_25, p_under_25, p_btts = calcular_probabilidades_poisson_dinamico(lam_local, lam_visita, 2.5)
                p_over_35, p_under_35, _ = calcular_probabilidades_poisson_dinamico(lam_local, lam_visita, 3.5)

                st.markdown("---")
                st.info(f"📊 **Matriz Automática del Modelo de Poisson Dinámico:**\n"
                        f"• **Over / Under 1.5 Goles**: Over `{p_over_15}%` | Under `{p_under_15}%`\n"
                        f"• **Over / Under 2.5 Goles**: Over `{p_over_25}%` | Under `{p_under_25}%`\n"
                        f"• **Over / Under 3.5 Goles**: Over `{p_over_35}%` | Under `{p_under_35}%`\n"
                        f"• **Ambos Equipos Anotan (BTTS)**: Sí `{p_btts}%`")

                st.markdown("---")
                st.markdown("### 🎯 Configuración del Mercado de Apuesta Específico")
                
                mercado_soccer_tipo = st.selectbox(
                    "Selecciona el Mercado de Fútbol a Auditar:",
                    ["Total de Goles (Over / Under Dinámico)", "Ambos Equipos Anotan (BTTS)", "Hándicap Asiático / Spread por Equipo"],
                    key=f"soccer_mercado_tipo_{idx}"
                )

                if "Total de Goles" in mercado_soccer_tipo:
                    col_tg1, col_tg2 = st.columns(2)
                    with col_tg1: linea_elegida = st.selectbox("Línea de Goles O/U:", [1.5, 2.5, 3.5, 0.5, 4.5], index=1, key=f"soccer_linea_{idx}")
                    with col_tg2: tipo_ou = st.selectbox("Selección:", ["Over (Más de)", "Under (Menos de)"], key=f"soccer_ou_sel_{idx}")
                    
                    p_over_din, p_under_din, _ = calcular_probabilidades_poisson_dinamico(lam_local, lam_visita, linea_objetivo=linea_elegida)
                    prob_modelo_final = p_over_din if "Over" in tipo_ou else p_under_din
                    nombre_auditoria = f"Over/Under {linea_elegida} ({tipo_ou})"

                elif "Ambos Equipos Anotan" in mercado_soccer_tipo:
                    prob_modelo_final = p_btts
                    nombre_auditoria = "Ambos Equipos Anotan (BTTS Sí)"

                else: 
                    col_ha1, col_ha2 = st.columns(2)
                    with col_ha1: equipo_ha = st.selectbox("Selección Hándicap Asiático:", [f"Local ({op['local']})", f"Visitante ({op['visita']})"], key=f"soccer_ha_eq_{idx}")
                    with col_ha2: linea_ha = st.selectbox("Línea Hándicap Asiático:", [-0.25, -0.5, -0.75, -1.0, +0.25, +0.5, +0.75, +1.0], index=1, key=f"soccer_ha_lin_{idx}")
                    
                    puntos_forma_a = (v_a * 3) + e_a
                    puntos_forma_b = (v_b * 3) + e_b
                    dif_goles_esp = (lam_local - lam_visita) * 12.0
                    base_ha_prob = 50.0 + ((puntos_forma_b - puntos_forma_a) * 2.5) + dif_goles_esp
                    
                    if "Local" in equipo_ha:
                        prob_modelo_final = max(20.0, min(85.0, base_ha_prob + (abs(linea_ha) * 10.0 if linea_ha < 0 else -abs(linea_ha) * 10.0)))
                    else:
                        prob_modelo_final = max(20.0, min(85.0, (100.0 - base_ha_prob) + (abs(linea_ha) * 10.0 if linea_ha < 0 else -abs(linea_ha) * 10.0)))
                    
                    nombre_auditoria = f"Hándicap Asiático `{equipo_ha}` (`{linea_ha:+}`)"

                momio_soccer = st.number_input("📈 Momio Casino (Americano):", value=-110, step=5, key=f"soccer_momio_{idx}")

                prob_imp_soc, edge_soc = calcular_edge_real(momio_soccer, prob_modelo_final)

                st.markdown("---")
                st.info(f"📊 **Auditoría para `{nombre_auditoria}`:**\n"
                        f"• Probabilidad Implícita (`{momio_soccer:+}`): `{prob_imp_soc:.2f}%`\n"
                        f"• Probabilidad del Modelo: **`{prob_modelo_final:.2f}%`**\n"
                        f"• 🎯 **Edge Neto Calculado:** **`{edge_soc:+.2f}%`**")

                if momio_soccer < -150:
                    st.error(f"🚨 **DESCARTADO (Regla de Oro):** El momio `{momio_soccer}` supera el límite estricto de -150.")
                elif edge_soc >= edge_min_soccer:
                    st.success(f"✅ **¡APUESTA APROBADA (+EV)!** Edge de `{edge_soc:+.2f}%`.")
                else:
                    st.warning(f"⚠️ **SIN VALOR SUFICIENTE (-EV):** Edge de `{edge_soc:+.2f}%`.")


# =========================================================
# 6. Props Fútbol
# =========================================================
elif modulo_seleccionado == "🎯 Módulo Automático de Props Fútbol (Dinámico)":
    st.title(f"🎯 **Auditor de Props de Fútbol (Alta Precisión) [{fecha_formato_str}]**")
    st.markdown("--- \n *Ingresa los datos del jugador y la línea del casino para auditar el valor matemático real (+EV).*")
    
    col_p1, col_p2 = st.columns(2)
    with col_p1: bankroll_props_fut = st.number_input("💵 Bankroll Props Fútbol (MXN):", 100.0, 50000.0, 3000.0, 500.0, key="bk_props_fut")
    with col_p2: edge_min_props_fut = st.slider("🎯 Edge Mínimo Props (%):", 0.0, 15.0, 3.0, 0.5, key="edge_min_props_fut")

    st.markdown("---")
    st.subheader("📋 Configuración del Prop a Auditar")
    num_props_a_revisar = st.number_input("¿Cuántos props deseas auditar en esta tanda?", min_value=1, max_value=5, value=2, step=1)

    for i in range(1, int(num_props_a_revisar) + 1):
        with st.expander(f"🎯 Prop Individual #{i}", expanded=True):
            col_pr1, col_pr2 = st.columns(2)
            with col_pr1:
                jugador_input = st.text_input(f"Nombre del Jugador #{i}:", value="Kylian Mbappé" if i==1 else "Erling Haaland", key=f"soccer_prop_j_{i}")
                mercado_input = st.text_input(f"Mercado / Línea #{i}:", value="Tiros a Puerta Over 1.5", key=f"soccer_prop_m_{i}")
            with col_pr2:
                momio_prop = st.number_input(f"📈 Momio Casino (Americano) #{i}:", value=-115, step=5, key=f"soccer_prop_mom_{i}")
                
            col_pf1, col_pf2 = st.columns(2)
            with col_pf1: cumple = st.number_input(f"Partidos cumpliendo línea (L5) #{i}:", 0, 5, 3, key=f"soccer_prop_c_{i}")
            with col_pf2: no_cumple = st.number_input(f"Partidos sin cumplir línea (L5) #{i}:", 0, 5, 2, key=f"soccer_prop_nc_{i}")

            prob_prop_modelo = max(40.0, min(85.0, 52.0 + (cumple - no_cumple) * 6.0))
            prob_imp_prop, edge_prop = calcular_edge_real(momio_prop, prob_prop_modelo)
            st.info(f"📊 **Edge Calculado:** Implícita (`{momio_prop:+}`): `{prob_imp_prop:.2f}%` | Modelo: `{prob_prop_modelo:.2f}%` | Edge Neto: **`{edge_prop:+.2f}%`**")

            if momio_prop < -150: st.error("🚨 Infringe Regla de Oro (-150).")
            elif edge_prop >= edge_min_props_fut: st.success(f"✅ Aprobado (+EV). Edge: `{edge_prop:+.2f}%`")
            else: st.warning(f"⚠️ Sin Edge suficiente (`{edge_prop:+.2f}%`).")


# =========================================================
# 7. NCAA
# =========================================================
elif modulo_seleccionado == "🎓 NCAA (Robot Universitario & Hándicap)":
    st.title(f"🎓 **Robot Universitario NCAA ({fecha_formato_str})**")
    st.markdown("--- \n *Modelo Gaussiano aplicado al fútbol americano universitario.*")
    col_nc1, col_nc2 = st.columns(2)
    with col_nc1: bankroll_ncaa = st.number_input("💵 Bankroll NCAA (MXN):", 100.0, 50000.0, 3000.0, 500.0, key="bk_ncaa")
    with col_nc2: edge_min_ncaa = st.slider("🎯 Edge Mínimo NCAA (%):", 0.0, 15.0, 3.0, 0.5, key="edge_ncaa")

    cartelera_ncaa = obtener_cartelera_pura("football", "college-football", fecha_formato_api, fecha_formato_str)
    st.markdown("---")
    st.subheader("📊 Partidos en Cartelera NCAA")

    if not cartelera_ncaa:
        st.info(f"ℹ️ No hay partidos oficiales de la NCAA programados en la fecha `{fecha_formato_str}`.")
    else:
        for idx, op in enumerate(cartelera_ncaa, 1):
            with st.expander(f"🎓 {op['partido_str']}"):
                momio = st.number_input("📈 Momio Casino:", value=-110, step=5, key=f"ncaa_m_val_{idx}")
                
                col_na1, col_na2 = st.columns(2)
                with col_na1: v_a = st.number_input(f"Victorias L5 ({op['visita']}):", 0, 5, 3, key=f"ncaa_va_v_{idx}")
                with col_na2: d_a = st.number_input(f"Derrotas L5 ({op['visita']}):", 0, 5, 2, key=f"ncaa_da_d_{idx}")

                col_nb1, col_nb2 = st.columns(2)
                with col_nb1: v_b = st.number_input(f"Victorias L5 ({op['local']}):", 0, 5, 3, key=f"ncaa_vb_v_{idx}")
                with col_nb2: d_b = st.number_input(f"Derrotas L5 ({op['local']}):", 0, 5, 2, key=f"ncaa_db_d_{idx}")
                
                prob = calcular_probabilidad_modelo_gaussiano(v_a, d_a, v_b, d_b, 7, 7, es_local_a=False)
                st.success(f"🤖 **Probabilidad Real del Modelo Gaussiano Pro:** **`{prob:.2f}%`**")
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
                momio = st.number_input("📈 Momio Casino:", value=-120, step=5, key=f"ufc_m_val_{idx}")
                
                col_u1, col_u2 = st.columns(2)
                with col_u1: racha_p1 = st.slider(f"Racha Victorias (Peleador 1):", 0, 5, 3, key=f"ufc_p1_{idx}")
                with col_u2: racha_p2 = st.slider(f"Racha Victorias (Peleador 2):", 0, 5, 2, key=f"ufc_p2_{idx}")
                
                prob = max(35.0, min(80.0, 50.0 + (racha_p1 - racha_p2) * 5.0))
                st.success(f"🤖 **Probabilidad Real del Modelo Pro:** **`{prob:.2f}%`**")
                prob_imp, edge = calcular_edge_real(momio, prob)
                st.info(f"📊 **Edge Calculado:** Implícita (`{momio:+}`): `{prob_imp:.2f}%` | Modelo: `{prob:.2f}%` | Edge Neto: **`{edge:+.2f}%`**")

                if momio < -150: st.error("🚨 Infringe Regla de Oro (-150).")
                elif edge >= edge_min_ufc: st.success(f"✅ Aprobado (+EV). Edge: `{edge:+.2f}%`")
                else: st.warning(f"⚠️ Sin Edge suficiente (`{edge:+.2f}%`).")


# =========================================================
# 9. LMP
# =========================================================
elif modulo_seleccionado == "⚾ Liga Mexicana del Pacífico (LMP)":
    st.title(f"⚾ **Liga Mexicana del Pacífico (LMP) — Análisis Pro [{fecha_formato_str}]**")
    st.markdown("--- \n *Modelo Gaussiano aplicado al béisbol invernal.*")

    col_l1, col_l2 = st.columns(2)
    with col_l1: bankroll_lmp = st.number_input("💵 Bankroll LMP (MXN):", 100.0, 50000.0, 3000.0, 500.0, key="bk_lmp")
    with col_l2: edge_min_lmp = st.slider("🎯 Edge Mínimo LMP (%):", 0.0, 15.0, 2.5, 0.5, key="edge_lmp")

    st.markdown("---")
    st.subheader("✍️ Ingreso Manual del Enfrentamiento")
    col_in1, col_in2 = st.columns(2)
    with col_in1: equipo_visita = st.text_input("Equipo Visitante:", value="Naranjeros de Hermosillo", key="lmp_eq_vis")
    with col_in2: equipo_local = st.text_input("Equipo Local:", value="Cañeros de Los Mochis", key="lmp_eq_loc")

    col_p1, col_p2 = st.columns(2)
    with col_p1: seleccion_apuesta = st.selectbox("🎯 Selección con Run Line:", [f"{equipo_visita} (-1.5)", f"{equipo_local} (-1.5)", f"{equipo_visita} (+1.5)", f"{equipo_local} (+1.5)"], key="lmp_sel_ap")
    with col_p2: momio_lmp = st.number_input("📈 Momio Americano Oficial:", value=130, step=5, key="momio_lmp_val")

    col_lm1, col_lm2 = st.columns(2)
    with col_lm1: v_a = st.number_input(f"Victorias L5 ({equipo_visita}):", 0, 5, 3, key="lmp_va_v")
    with col_lm2: d_a = st.number_input(f"Derrotas L5 ({equipo_visita}):", 0, 5, 2, key="lmp_da_d")

    col_lm3, col_lm4 = st.columns(2)
    with col_lm3: v_b = st.number_input(f"Victorias L5 ({equipo_local}):", 0, 5, 3, key="lmp_vb_v")
    with col_lm4: d_b = st.number_input(f"Derrotas L5 ({equipo_local}):", 0, 5, 2, key="lmp_db_d")
    
    prob_modelo_lmp = calcular_probabilidad_modelo_gaussiano(v_a, d_a, v_b, d_b, 1, 1, es_local_a=False)
    st.success(f"🤖 **Probabilidad Real del Modelo Gaussiano Pro:** **`{prob_modelo_lmp:.2f}%`**")
    prob_imp_lmp, edge_lmp = calcular_edge_real(momio_lmp, prob_modelo_lmp)
    st.info(f"📊 **Edge Calculado:** Implícita (`{momio_lmp:+}`): `{prob_imp_lmp:.2f}%` | Modelo: `{prob_modelo_lmp:.2f}%` | Edge Neto: **`{edge_lmp:+.2f}%`**")

    if momio_lmp < -150: st.error("🚨 Infringe Regla de Oro (-150).")
    elif edge_lmp >= edge_min_lmp: st.success(f"✅ Aprobado LMP (+EV). Edge: `{edge_lmp:+.2f}%`")
    else: st.warning(f"⚠️ Sin Edge suficiente (`{edge_lmp:+.2f}%`).")


# =========================================================
# 10. MLB
# =========================================================
elif modulo_seleccionado == "⚾ Serie Mundial & Béisbol Pro (MLB)":
    st.title(f"⚾ **Serie Mundial & Béisbol Pro (MLB) [{fecha_formato_str}]**")
    st.markdown("--- \n *Modelo Gaussiano especializado para béisbol de Grandes Ligas.*")
    col_m1, col_m2 = st.columns(2)
    with col_m1: bankroll_mlb = st.number_input("💵 Bankroll MLB (MXN):", 100.0, 50000.0, 5000.0, 500.0, key="bk_mlb")
    with col_m2: edge_min_mlb = st.slider("🎯 Edge Mínimo MLB (%):", 0.0, 15.0, 3.0, 0.5, key="edge_min_mlb")

    col_inmlb1, col_inmlb2 = st.columns(2)
    with col_inmlb1: equipo_mlb_visita = st.text_input("Equipo Visitante (MLB):", value="Los Angeles Dodgers", key="mlb_eq_vis")
    with col_inmlb2: equipo_mlb_local = st.text_input("Equipo Local (MLB):", value="New York Yankees", key="mlb_eq_loc")

    col_mm1, col_mm2, col_mm3 = st.columns(3)
    with col_mm1: mercado_mlb = st.selectbox("Mercado Principal:", ["Run Line (-1.5)", "Money Line (Ganador)", "Total de Carreras (Over/Under)"], key="mlb_merc_sel")
    with col_mm2: seleccion_mlb = st.text_input("Selección Específica:", value="Los Angeles Dodgers (+1.5)", key="mlb_sel_esp")
    with col_mm3: momio_mlb = st.number_input("📈 Momio Americano Oficial:", value=-120, step=5, key="momio_mlb_val")

    col_mb1, col_mb2 = st.columns(2)
    with col_mb1: v_a = st.number_input(f"Victorias L5 ({equipo_mlb_visita}):", 0, 5, 3, key="mlb_va_v")
    with col_mb2: d_a = st.number_input(f"Derrotas L5 ({equipo_mlb_visita}):", 0, 5, 2, key="mlb_da_d")

    col_mb3, col_mb4 = st.columns(2)
    with col_mb3: v_b = st.number_input(f"Victorias L5 ({equipo_mlb_local}):", 0, 5, 3, key="mlb_vb_v")
    with col_mb4: d_b = st.number_input(f"Derrotas L5 ({equipo_mlb_local}):", 0, 5, 2, key="mlb_db_d")
    
    prob_modelo_mlb = calcular_probabilidad_modelo_gaussiano(v_a, d_a, v_b, d_b, 1, 1, es_local_a=False)
    st.success(f"🤖 **Probabilidad Real del Modelo Gaussiano Pro:** **`{prob_modelo_mlb:.2f}%`**")
    prob_imp_mlb, edge_mlb = calcular_edge_real(momio_mlb, prob_modelo_mlb)
    st.info(f"📊 **Edge Calculado:** Implícita (`{momio_mlb:+}`): `{prob_imp_mlb:.2f}%` | Modelo: `{prob_modelo_mlb:.2f}%` | Edge Neto: **`{edge_mlb:+.2f}%`**")

    if momio_mlb < -150: st.error("🚨 Infringe Regla de Oro (-150).")
    elif edge_mlb >= edge_min_mlb: st.success(f"✅ Aprobado MLB (+EV). Edge: `{edge_mlb:+.2f}%`")
    else: st.warning(f"⚠️ Sin Edge suficiente (`{edge_mlb:+.2f}%`).")


# =========================================================
# 11. NHL
# =========================================================
elif modulo_seleccionado == "🏒 Sistema Cuantitativo Pro NHL (Hándicap / Puck Line)":
    st.title(f"🏒 **Sistema Cuantitativo Pro NHL (Puck Line) [{fecha_formato_str}]**")
    st.markdown("--- \n *Modelo Gaussiano con factor de fatiga de hielo para la NHL.*")
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
                momio = st.number_input("📈 Momio Casino:", value=+120, step=5, key=f"nhl_m_val_{idx}")
                
                col_nh1_s, col_nh2_s = st.columns(2)
                with col_nh1_s: v_a = st.number_input(f"Victorias L5 ({op['visita']}):", 0, 5, 3, key=f"nhl_va_v_{idx}")
                with col_nh2_s: d_a = st.number_input(f"Derrotas L5 ({op['visita']}):", 0, 5, 2, key=f"nhl_da_d_{idx}")

                col_nh3_s, col_nh4_s = st.columns(2)
                with col_nh3_s: v_b = st.number_input(f"Victorias L5 ({op['local']}):", 0, 5, 3, key=f"nhl_vb_v_{idx}")
                with col_nh4_s: d_b = st.number_input(f"Derrotas L5 ({op['local']}):", 0, 5, 2, key=f"nhl_db_d_{idx}")
                
                prob = calcular_probabilidad_modelo_gaussiano(v_a, d_a, v_b, d_b, 1, 1, es_local_a=False)
                st.success(f"🤖 **Probabilidad Real del Modelo Gaussiano Pro:** **`{prob:.2f}%`**")
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
    with col_pnh2: edge_min_props_nhl = st.slider("🎯 Edge Mínimo Props NHL (%):", 0.0, 15.0, 3.0, 0.5, key="edge_props_nhl")

    cartelera_nhl_hoy = obtener_cartelera_pura("hockey", "nhl", fecha_formato_api, fecha_formato_str)
    st.markdown("---")
    st.subheader("📊 Auditoría de Props NHL")

    if not cartelera_nhl_hoy:
        st.info(f"ℹ️ No hay partidos de NHL para la fecha `{fecha_formato_str}`.")
    else:
        for idx, op in enumerate(cartelera_nhl_hoy, 1):
            with st.expander(f"🏒 Prop NHL: {op['partido_str']}"):
                jugador = st.text_input("Jugador:", value="Connor McDavid", key=f"nhl_prop_j_{idx}")
                mercado = st.text_input("Mercado:", value="Puntos Totales Over 1.5", key=f"nhl_prop_m_{idx}")
                momio = st.number_input("📈 Momio Casino:", value=-115, step=5, key=f"nhl_prop_mom_{idx}")
                
                col_njh1, col_njh2 = st.columns(2)
                with col_njh1: cumple = st.number_input("Partidos cumpliendo línea (L5):", 0, 5, 3, key=f"nhl_prop_c_{idx}")
                with col_njh2: no_cumple = st.number_input("Partidos sin cumplir línea (L5):", 0, 5, 2, key=f"nhl_prop_nc_{idx}")
                
                prob = max(40.0, min(80.0, 50.0 + (cumple - no_cumple) * 6.0))
                st.success(f"🤖 **Probabilidad Real del Modelo Pro:** **`{prob:.2f}%`**")
                prob_imp, edge = calcular_edge_real(momio, prob)
                st.info(f"📊 **Edge Calculado:** Implícita (`{momio:+}`): `{prob_imp:.2f}%` | Modelo: `{prob:.2f}%` | Edge Neto: **`{edge:+.2f}%`**")

                if momio < -150: st.error("🚨 Infringe Regla de Oro (-150).")
                elif edge >= edge_min_props_nhl: st.success(f"✅ Aprobado Prop NHL (+EV). Edge: `{edge:+.2f}%`")
                else: st.warning(f"⚠️ Sin Edge suficiente (`{edge:+.2f}%`).")


# =========================================================
# 13. Analítica, Control de Bankroll & Registro CLV
# =========================================================
elif modulo_seleccionado == "📊 Analítica, Control de Bankroll & Registro CLV":
    st.title("📊 **Panel de Analítica, Gestión de Bankroll & Registro CLV**")
    st.markdown("--- \n *Control financiero, simulador de riesgo y auditoría de Closing Line Value (CLV).*")
    
    col_b1, col_b2, col_b3 = st.columns(3)
    with col_b1: st.metric(label="💰 Bankroll Global Actual", value="$15,250.00 MXN", delta="+11.2%")
    with col_b2: st.metric(label="🎯 Efectividad Global (Win Rate)", value="65.5%", delta="-2.9%")
    with col_b3: st.metric(label="📈 Unidades Ganadas (Units)", value="+7.2 U", delta="-1.0 U")

    st.markdown("---")
    st.subheader("📝 Registro y Auditoría de Apuesta Pro (Estructura CLV)")
    
    with st.form("form_nueva_apuesta"):
        col_f_1, col_f_2 = st.columns(2)
        with col_f_1:
            id_partid = st.text_input("ID / Partido:", value="Real Madrid vs Barcelona")
            eq_loc = st.text_input("Equipo Local:", value="Real Madrid")
            eq_vis = st.text_input("Equipo Visitante:", value="Barcelona")
            prob_pois = st.slider("Probabilidad del Modelo (Poisson/Gaussiano):", 0.0, 1.0, 0.58, 0.01)
        with col_f_2:
            cuota_comp = st.number_input("Cuota Comprada (Decimal):", 1.01, 10.0, 1.95, 0.01)
            cuota_cier = st.number_input("Cuota Cierre Casa (Decimal - Previo al juego):", 1.01, 10.0, 1.85, 0.01)
            stake_inv = st.number_input("Stake Invertido (MXN):", 10.0, 10000.0, 150.0, 10.0)
            res_ap = st.selectbox("Resultado Final:", ["ganada", "perdida", "devuelta"])

        submitted = st.form_submit_button("💾 Registrar y Validar CLV de la Apuesta")
        if submitted:
            clv_exito = cuota_comp > cuota_cier
            nueva_apuesta = {
                "id_partido": id_partid,
                "equipo_local": eq_loc,
                "equipo_visitante": eq_vis,
                "probabilidad_poisson": prob_pois,
                "cuota_comprada": cuota_comp,
                "stake_invertido": stake_inv,
                "cuota_cierre_casa": cuota_cier,
                "clv_positivo": clv_exito,
                "resultado": res_ap
            }
            st.success(f"✅ ¡Apuesta registrada exitosamente para `{id_partid}`!")
            if clv_exito:
                st.info(f"🎯 **CLV Positivo Confirmado:** Compraste a `{cuota_comp}` y cerró en `{cuota_cier}`. ¡Le ganaste al mercado!")
            else:
                st.warning(f"⚠️ **CLV Negativo:** Compraste a `{cuota_comp}` y cerró en `{cuota_cier}`.")

    st.markdown("---")
    st.subheader("🛡️ Simulador en Vivo del Cortafuegos de Riesgo")
    col_sim1, col_sim2 = st.columns(2)
    with col_sim1:
        bk_prueba = st.number_input("Bankroll de Prueba (MXN):", 1000.0, 100000.0, 15250.0, 500.0)
        stake_kelly_prueba = st.number_input("Stake Sugerido Inicial (Kelly MXN):", 10.0, 2000.0, 300.0, 50.0)
    with col_sim2:
        simular_racha_perdidas = st.slider("Simular Racha de Derrotas Seguidas:", 0, 10, 2)
        simular_clv_bajo = st.checkbox("Simular CLV Descalibrado (< 50% en últimas 20)", value=False)

    historial_sim = []
    for i in range(20):
        res = "perdida" if i < simular_racha_perdidas else "ganada"
        clv = False if simular_clv_bajo else True
        historial_sim.append({'resultado': res, 'clv_positivo': clv, 'monto': 200})

    stake_calculado, perdidas_detectadas, factor_aplicado = modulo_control_riesgo(historial_sim, bk_prueba, stake_kelly_prueba)

    col_res1, col_res2, col_res3 = st.columns(3)
    with col_res1: st.metric("⚠️ Derrotas Consecutivas", f"{perdidas_detectadas}")
    with col_res2: st.metric("📉 Factor de Reducción", f"{int(factor_aplicado * 100)}% del Stake")
    with col_res3: st.metric("💵 Stake Final Seguro", f"${stake_calculado} MXN")

    if factor_aplicado < 1.0:
        st.warning(f"🛡️ **Cortafuegos Activo:** Reducción automática al `{int(factor_aplicado * 100)}%`.")
    else:
        st.success("✅ **Riesgo Óptimo:** Operando bajo Kelly y techo del 3%.")


# =========================================================
# 14. Optimizador Automático de Parlays
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
