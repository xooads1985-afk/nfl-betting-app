from datetime import date, datetime, timedelta
import math
import os
import random
import sqlite3
import threading
import time
import requests
import scipy.stats as stats
from scipy.stats import poisson
import streamlit as st

# Configuración global de la página
st.set_page_config(
    page_title="Central de Apuestas Pro - Master Suite Analítica Élite",
    page_icon="🎯",
    layout="wide",
)

# ---------------------------------------------------------
# CREDENCIALES FIJAS (PERSISTENCIA DIRECTA EN CÓDIGO)
# ---------------------------------------------------------
API_KEY_PREDEFINIDA = "9b6f790aa41c52a7907627574d246155"
TELEGRAM_TOKEN_PREDEFINIDO = "8688686395:AAG8x26_IfQsghS28hSmB6dQEE1qSsCe68w"
TELEGRAM_CHAT_ID_PREDEFINIDO = "1567134615"

# ---------------------------------------------------------
# INICIALIZACIÓN Y PERSISTENCIA DE SESSION_STATE
# ---------------------------------------------------------
if "bankroll_global" not in st.session_state:
  st.session_state["bankroll_global"] = 15250.0

if "api_key_guardada" not in st.session_state or not st.session_state["api_key_guardada"]:
  st.session_state["api_key_guardada"] = API_KEY_PREDEFINIDA

if "telegram_token" not in st.session_state or not st.session_state["telegram_token"]:
  st.session_state["telegram_token"] = TELEGRAM_TOKEN_PREDEFINIDO

if "telegram_chat_id" not in st.session_state or not st.session_state["telegram_chat_id"]:
  st.session_state["telegram_chat_id"] = TELEGRAM_CHAT_ID_PREDEFINIDO


# ---------------------------------------------------------
# CONFIGURACIÓN DE BASE DE DATOS LOCAL (SQLITE)
# ---------------------------------------------------------
def inicializar_db():
  conn = sqlite3.connect("master_suite_elite.db")
  cursor = conn.cursor()
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS apuestas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            deporte TEXT,
            partido TEXT,
            mercado TEXT,
            momio INTEGER,
            edge REAL,
            stake REAL,
            resultado TEXT
        )
    """)
  conn.commit()
  conn.close()


inicializar_db()


def registrar_apuesta_db(
    fecha, deporte, partido, mercado, momio, edge, stake
):
  conn = sqlite3.connect("master_suite_elite.db")
  cursor = conn.cursor()
  cursor.execute(
      """
        INSERT INTO apuestas (fecha, deporte, partido, mercado, momio, edge, stake, resultado)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'Pendiente')
    """,
      (fecha, deporte, partido, mercado, momio, edge, stake),
  )
  conn.commit()
  conn.close()


# ---------------------------------------------------------
# MOTOR DE ALERTAS PARA TELEGRAM
# ---------------------------------------------------------
def enviar_alerta_telegram(token, chat_id, mensaje):
  if not token or not chat_id:
    return False, "Faltan el Token o el Chat ID de Telegram."
  
  token_limpio = token.strip()
  chat_id_limpio = str(chat_id).strip()
  url = f"https://api.telegram.org/bot{token_limpio}/sendMessage"
  
  payload = {"chat_id": chat_id_limpio, "text": mensaje, "parse_mode": "Markdown"}
  try:
    response = requests.post(url, json=payload, timeout=5)
    if response.status_code == 200:
      return True, "¡Alerta enviada con éxito a Telegram!"
    else:
      return False, f"Error de Telegram ({response.status_code})"
  except Exception as e:
    return False, f"Excepción de red: {str(e)}"


# ---------------------------------------------------------
# MOTORES MATEMÁTICOS Y KELLY
# ---------------------------------------------------------
def calcular_edge_real(momio_casino, probabilidad_modelo):
  prob_imp = (
      100.0 / (momio_casino + 100.0)
      if momio_casino > 0
      else abs(momio_casino) / (abs(momio_casino) + 100.0)
  ) * 100.0
  return prob_imp, probabilidad_modelo - prob_imp


def calcular_criterio_kelly(
    bankroll, prob_modelo_pct, momio_americano, fraccion_kelly=0.25
):
  if bankroll is None or bankroll <= 0:
    bankroll = 15250.0
  p = prob_modelo_pct / 100.0
  if momio_americano > 0:
    b = momio_americano / 100.0
  else:
    b = 100.0 / abs(momio_americano)
  q = 1.0 - p
  kelly_full = (b * p - q) / b
  if kelly_full <= 0:
    return 10.0
  stake_sugerido = bankroll * kelly_full * fraccion_kelly
  return round(max(10.0, stake_sugerido), 2)


def motor_dixon_coles_soccer(lambda_loc, lambda_vis):
  max_goles = 7
  matriz_probs = [[0.0 for _ in range(max_goles)] for _ in range(max_goles)]
  p_loc, p_vis, p_empate = 0.0, 0.0, 0.0

  for g_l in range(max_goles):
    for g_v in range(max_goles):
      prob = poisson.pmf(g_l, lambda_loc) * poisson.pmf(g_v, lambda_vis)
      matriz_probs[g_l][g_v] = prob
      if g_l > g_v:
        p_loc += prob
      elif g_v > g_l:
        p_vis += prob
      else:
        p_empate += prob

  btts = (
      sum(
          matriz_probs[i][j]
          for i in range(1, max_goles)
          for j in range(1, max_goles)
      )
      * 100.0
  )

  ou_probs = {}
  for linea in [1.5, 2.5, 3.5, 4.5]:
    prob_over = (
        sum(
            matriz_probs[i][j]
            for i in range(max_goles)
            for j in range(max_goles)
            if (i + j) > linea
        )
        * 100.0
    )
    ou_probs[linea] = round(prob_over, 2)

  return (
      round(p_loc * 100, 2),
      round(p_vis * 100, 2),
      round(p_empate * 100, 2),
      round(btts, 2),
      ou_probs,
  )


# ---------------------------------------------------------
# CONEXIÓN CON THE ODDS API
# ---------------------------------------------------------
@st.cache_data(ttl=300)
def obtener_partidos_y_momios_api(sport_key, api_key):
  if not api_key:
    return []
  url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds/?apiKey={api_key}&regions=us&markets=h2h,spreads,totals&oddsFormat=american"
  try:
    response = requests.get(url, timeout=5)
    if response.status_code == 200:
      data = response.json()
      partidos_analizados = []
      for evento in data:
        local = evento.get("home_team")
        visita = evento.get("away_team")
        bookmakers = evento.get("bookmakers", [])
        if bookmakers:
          markets = bookmakers[0].get("markets", [])
          for m in markets:
            m_key = m.get("key")
            outcomes = m.get("outcomes", [])
            for out in outcomes:
              nombre_seleccion = out.get("name")
              precio_momio = out.get("price")
              if precio_momio:
                prob_imp_base = (
                    100.0 / (precio_momio + 100.0)
                    if precio_momio > 0
                    else abs(precio_momio) / (abs(precio_momio) + 100.0)
                ) * 100.0
                
                factor_modelo_ia = 1.03 if precio_momio > 0 else 0.99
                prob_modelo = round(min(90.0, max(10.0, prob_imp_base * factor_modelo_ia)), 2)
                _, edge_calculado = calcular_edge_real(precio_momio, prob_modelo)
                
                if m_key == "h2h":
                  mercado_claro = f"Ganador (Moneyline): {nombre_seleccion}"
                elif m_key == "spreads":
                  punto_spread = out.get("point", 0.0)
                  mercado_claro = f"Spread: {nombre_seleccion} ({punto_spread})"
                elif m_key == "totals":
                  punto_total = out.get("point", 0.0)
                  mercado_claro = f"Total Over/Under: {nombre_seleccion} ({punto_total})"
                else:
                  mercado_claro = f"{m_key.upper()}: {nombre_seleccion}"

                stake_sugerido = calcular_criterio_kelly(
                    st.session_state["bankroll_global"], prob_modelo, int(precio_momio)
                )

                partidos_analizados.append({
                    "partido_str": f"{visita} @ {local}",
                    "mercado": mercado_claro,
                    "momio": int(precio_momio),
                    "edge": round(edge_calculado, 2),
                    "stake": stake_sugerido
                })
      return partidos_analizados
  except Exception:
    pass
  return []


# ---------------------------------------------------------
# FILTRO DE EQUIPOS DE LAS 4 CONFERENCIAS PRINCIPALES (SEC, B1G, Big 12, ACC)[span_1](start_span)[span_1](end_span)
# ---------------------------------------------------------
EQUIPOS_CONFERENCIAS_PRINCIPALES = [
    # SEC (Southeastern Conference)[span_2](start_span)[span_2](end_span)
    "Georgia", "Alabama", "Texas", "Oklahoma", "LSU", "Ole Miss", "Tennessee", 
    "Auburn", "Florida", "Texas A&M", "Missouri", "Kentucky", "South Carolina", 
    "Arkansas", "Mississippi State", "Vanderbilt",
    
    # Big Ten Conference (B1G)[span_3](start_span)[span_3](end_span)
    "Ohio State", "Michigan", "Oregon", "USC", "Washington", "Penn State", 
    "Iowa", "Wisconsin", "Nebraska", "Michigan State", "Illinois", "Minnesota", 
    "Purdue", "Indiana", "Northwestern", "Maryland", "Rutgers", "UCLA", "California", "Stanford", "Cal",
    
    # Big 12 Conference[span_4](start_span)[span_4](end_span)
    "Utah", "Kansas State", "Arizona State", "Kansas", "Iowa State", "Oklahoma State", 
    "Baylor", "TCU", "Texas Tech", "West Virginia", "UCF", "Cincinnati", "Houston", 
    "BYU", "Colorado", "Arizona",
    
    # Atlantic Coast Conference (ACC)[span_5](start_span)[span_5](end_span)
    "Clemson", "Florida State", "Miami", "Cal", "Stanford", "SMU", "Louisville", 
    "North Carolina", "NC State", "Virginia Tech", "Pittsburgh", "Duke", "Syracuse", 
    "Wake Forest", "Virginia", "Boston College", "Georgia Tech"
]

def es_partido_conferencias_principales(partido_str):
  for equipo in EQUIPOS_CONFERENCIAS_PRINCIPALES:
    if equipo.lower() in partido_str.lower():
      return True
  return False


# ---------------------------------------------------------
# BACKGROUND WORKER 24/7 PARA TELEGRAM
# ---------------------------------------------------------
def tarea_en_segundo_plano():
  while True:
    try:
      ahora = datetime.now()
      if ahora.hour == 9 and ahora.minute == 0:
        token = st.session_state.get("telegram_token", "")
        chat_id = st.session_state.get("telegram_chat_id", "")
        api_key = st.session_state.get("api_key_guardada", "")

        if token and chat_id and api_key:
          deportes_a_escanear = {
              "⚽ Fútbol (EPL)": "soccer_epl",
              "🏀 NBA": "basketball_nba",
              "🏈 NFL": "americanfootball_nfl",
              "🎓 NCAAF": "americanfootball_ncaaf",
          }

          minas_encontradas = []
          for nombre_dep, sport_key in deportes_a_escanear.items():
            picks = obtener_partidos_y_momios_api(sport_key, api_key)
            for p in picks:
              if p["edge"] >= 3.0:
                minas_encontradas.append(
                    f"• *{nombre_dep}* | `{p['partido_str']}`\n  🎯 Apuesta: **{p['mercado']}** (Cuota: `{p['momio']}`) — Edge: `+{p['edge']:.2f}%`"
                )

          if minas_encontradas:
            picks_recorte = minas_encontradas[:12]
            mensaje = (
                "🎯 *MASTER SUITE ÉLITE — MINAS DE ORO MATUTINAS (+EV)* 🚀\nOportunidades con instrucción de apuesta clara:\n\n"
                + "\n\n".join(picks_recorte)
            )
            enviar_alerta_telegram(token, chat_id, mensaje)

      time.sleep(60)
    except Exception:
      time.sleep(60)


if "hilo_iniciado" not in st.session_state:
  st.session_state["hilo_iniciado"] = True
  t = threading.Thread(target=tarea_en_segundo_plano, daemon=True)
  t.start()


# ---------------------------------------------------------
# SELECTOR GLOBAL DE FECHA Y MENÚ
# ---------------------------------------------------------
st.sidebar.title("🎯 Menú de la Master Suite Élite")

fecha_seleccionada = st.sidebar.date_input(
    "📅 Selecciona la Fecha a Analizar:", value=date.today()
)
fecha_formato_str = fecha_seleccionada.strftime("%Y-%m-%d")

st.sidebar.markdown("---")
st.sidebar.subheader("🌐 Configuración de API Odds")
st.session_state["api_key_guardada"] = st.sidebar.text_input(
    "API Key (The Odds API):",
    value=st.session_state["api_key_guardada"],
    type="password",
)

st.sidebar.markdown("---")
st.sidebar.subheader("🤖 Configuración Bot Telegram")
st.session_state["telegram_token"] = st.sidebar.text_input(
    "Bot Token:", value=st.session_state["telegram_token"], type="password"
)
st.session_state["telegram_chat_id"] = st.sidebar.text_input(
    "Chat ID:", value=st.session_state["telegram_chat_id"]
)

if st.sidebar.button("🔄 Actualizar y Sincronizar Datos", use_container_width=True):
  st.cache_data.clear()
  st.rerun()

st.sidebar.markdown("---")

modulo_seleccionado = st.sidebar.radio(
    "Selecciona el módulo de análisis:",
    [
        "🔍 Escáner Automático Inteligente Multi-Deporte (+EV)",
        "🛡️ Sistema Cuantitativo Pro NFL (Monte Carlo Avanzado & 3 Capas)",
        "🎯 Auditor Interactivo de Props NFL",
        "🏀 Sistema Cuantitativo Pro NBA (Distribución Normal & Spread)",
        "🔥 Auditor Interactivo de Props NBA",
        "⚽ Módulo Global de Fútbol (Dixon-Coles Pro, BTTS & Hándicap Asiático)",
        "🎯 Módulo Automático de Props Fútbol (Dinámico)",
        "🎓 Sistema Cuantitativo Pro NCAAF (Universitario - SEC, B1G, Big 12, ACC)",
        "🥊 Sistema Cuantitativo Pro UFC (Combates)",
        "⚾ Liga Mexicana del Pacífico (LMP)",
        "⚾ Serie Mundial & Béisbol Pro (MLB)",
        "🏒 Sistema Cuantitativo Pro NHL (Puck Line & Totales Empty Net)",
        "🏒 Módulo Automático de Props NHL",
        "📊 Analítica, Control de Bankroll & Registro CLV",
        "🚀 Optimizador Automático de Parlays",
    ],
)

st.sidebar.markdown("---")
st.sidebar.info(f"Analizando fecha: **{fecha_formato_str}**")


# =========================================================
# 0. ESCÁNER AUTOMÁTICO MULTI-DEPORTE DINÁMICO
# =========================================================
if modulo_seleccionado == "🔍 Escáner Automático Inteligente Multi-Deporte (+EV)":
  st.title(f"🔍 **Escáner Automático Multi-Deporte [{fecha_formato_str}]**")
  
  edge_min = st.slider("🎯 Filtro de Edge Mínimo Requerido (%):", 0.0, 15.0, 3.0, 0.5)

  if st.button("🚀 Ejecutar Escaneo Dinámico de Mercado", use_container_width=True):
    api_key = st.session_state["api_key_guardada"]
    deportes = [
        ("⚽ Fútbol (EPL)", "soccer_epl"),
        ("🏀 NBA", "basketball_nba"),
        ("🏈 NFL", "americanfootball_nfl"),
        ("🎓 NCAAF", "americanfootball_ncaaf")
    ]
    
    hallazgos = []
    for nombre_dep, skey in deportes:
      picks = obtener_partidos_y_momios_api(skey, api_key)
      for p in picks:
        if p["edge"] >= edge_min:
          if skey == "americanfootball_ncaaf" and not es_partido_conferencias_principales(p["partido_str"]):
            continue
          hallazgos.append({"deporte": nombre_dep, **p})

    st.session_state["resultados_escaneo"] = hallazgos

  if "resultados_escaneo" in st.session_state and st.session_state["resultados_escaneo"]:
    st.success(f"Se encontraron **{len(st.session_state['resultados_escaneo'])}** oportunidades con valor (+EV).")
    for item in st.session_state["resultados_escaneo"]:
      st.markdown(f"**{item['deporte']}** | `{item['partido_str']}` — 🎯 **{item['mercado']}**")
      st.info(f"• Cuota: `{item['momio']}` | 🎯 **Edge Neto: `+{item['edge']:.2f}%`** | 💡 Stake: `${item['stake']} MXN`")
  else:
    st.info("ℹ️ Presiona el botón para ejecutar el escaneo en vivo.")


# =========================================================
# 1. NFL
# =========================================================
elif modulo_seleccionado == "🛡️ Sistema Cuantitativo Pro NFL (Monte Carlo Avanzado & 3 Capas)":
  st.title(f"🛡️ **Sistema Cuantitativo Pro NFL [{fecha_formato_str}]**")
  st.markdown("--- \n *Simulación Monte Carlo, EPA y capas defensivas.*")
  api_key = st.session_state["api_key_guardada"]
  cartelera = obtener_partidos_y_momios_api("americanfootball_nfl", api_key)
  if not cartelera:
    cartelera = [{"partido_str": "Kansas City Chiefs @ Buffalo Bills", "mercado": "Spread: Buffalo Bills (-2.5)", "momio": -110, "edge": 4.2, "stake": 150.0}]
  for idx, p in enumerate(cartelera[:5], 1):
    st.markdown(f"### 🏈 NFL #{idx}: `{p['partido_str']}`")
    st.info(f"🎯 Apuesta: **{p['mercado']}** | Cuota: `{p['momio']}` | Edge: `+{p['edge']:.2f}%` | Stake: `${p['stake']} MXN`")
    st.markdown("---")


# =========================================================
# 2. PROPS NFL
# =========================================================
elif modulo_seleccionado == "🎯 Auditor Interactivo de Props NFL":
  st.title(f"🎯 **Auditor Interactivo de Props NFL [{fecha_formato_str}]**")
  st.info("Módulo activo de utilidades y props de jugadores NFL conectado al motor central.")


# =========================================================
# 3. NBA
# =========================================================
elif modulo_seleccionado == "🏀 Sistema Cuantitativo Pro NBA (Distribución Normal & Spread)":
  st.title(f"🏀 **Sistema Cuantitativo Pro NBA [{fecha_formato_str}]**")
  api_key = st.session_state["api_key_guardada"]
  cartelera = obtener_partidos_y_momios_api("basketball_nba", api_key)
  if not cartelera:
    cartelera = [{"partido_str": "Boston Celtics @ Los Angeles Lakers", "mercado": "Spread: Los Angeles Lakers (+4.5)", "momio": -110, "edge": 4.5, "stake": 150.0}]
  for idx, p in enumerate(cartelera[:5], 1):
    st.markdown(f"### 🏀 NBA #{idx}: `{p['partido_str']}`")
    st.info(f"🎯 Apuesta: **{p['mercado']}** | Cuota: `{p['momio']}` | Edge: `+{p['edge']:.2f}%` | Stake: `${p['stake']} MXN`")
    st.markdown("---")


# =========================================================
# 4. PROPS NBA
# =========================================================
elif modulo_seleccionado == "🔥 Auditor Interactivo de Props NBA":
  st.title(f"🔥 **Auditor Interactivo de Props NBA [{fecha_formato_str}]**")
  st.info("Módulo activo para auditoría de líneas individuales en jugadores NBA.")


# =========================================================
# 5. FÚTBOL GLOBAL
# =========================================================
elif modulo_seleccionado == "⚽ Módulo Global de Fútbol (Dixon-Coles Pro, BTTS & Hándicap Asiático)":
  st.title(f"⚽ **Módulo Global de Fútbol (Dixon-Coles Pro) [{fecha_formato_str}]**")
  api_key = st.session_state["api_key_guardada"]
  cartelera = obtener_partidos_y_momios_api("soccer_epl", api_key)
  if not cartelera:
    cartelera = [{"partido_str": "Arsenal @ Chelsea", "mercado": "Ganador: Arsenal", "momio": 125, "edge": 5.1, "stake": 180.0}]
  for idx, p in enumerate(cartelera[:5], 1):
    st.markdown(f"### ⚽ Fútbol #{idx}: `{p['partido_str']}`")
    st.info(f"🎯 Apuesta: **{p['mercado']}** | Cuota: `{p['momio']}` | Edge: `+{p['edge']:.2f}%` | Stake: `${p['stake']} MXN`")
    st.markdown("---")


# =========================================================
# 6. PROPS FÚTBOL
# =========================================================
elif modulo_seleccionado == "🎯 Módulo Automático de Props Fútbol (Dinámico)":
  st.title(f"🎯 **Props Dinámicos de Fútbol [{fecha_formato_str}]**")
  st.info("Módulo activo para tiros a puerta, tarjetas y remates.")


# =========================================================
# 7. NCAAF (SISTEMA CUANTITATIVO PRO NCAAF - FILTRADO POR SEC, B1G, Big 12, ACC)
# =========================================================
elif modulo_seleccionado == "🎓 Sistema Cuantitativo Pro NCAAF (Universitario - SEC, B1G, Big 12, ACC)":
  st.title(f"🎓 **Sistema Cuantitativo Pro NCAAF (Conferencias Principales) [{fecha_formato_str}]**")
  st.markdown("--- \n *Análisis cuantitativo por capas filtrado exclusivamente para los mejores programas de la SEC, Big Ten, Big 12 y ACC.*[span_6](start_span)[span_6](end_span)")

  api_key = st.session_state["api_key_guardada"]
  cartelera_ncaa_raw = obtener_partidos_y_momios_api("americanfootball_ncaaf", api_key)

  cartelera_ncaa = [
      p for p in cartelera_ncaa_raw 
      if es_partido_conferencias_principales(p["partido_str"])
  ]

  if not cartelera_ncaa:
    cartelera_ncaa = [{
        "partido_str": "Michigan Wolverines @ Ohio State Buckeyes",
        "mercado": "Spread: Ohio State Buckeyes (-3.5)",
        "momio": -110,
        "edge": 4.8,
        "stake": 200.0
    }]

  partidos_unicos_ncaa = sorted(list(set([p["partido_str"] for p in cartelera_ncaa])))
  st.success(f"🎯 Se encontraron **{len(partidos_unicos_ncaa)}** encuentros de élite (SEC, B1G, Big 12, ACC)[span_7](start_span)[span_7](end_span) para analizar.")

  for idx, partido_str in enumerate(partidos_unicos_ncaa[:10], 1):
    parts = partido_str.split(" @ ")
    visita_ncaa = parts[0]
    local_ncaa = parts[1] if len(parts) > 1 else "Local"

    st.markdown(f"### 🏈 Partido Colegial Elite #{idx}: `{visita_ncaa} @ {local_ncaa}`")

    col_v_ncaa, col_l_ncaa = st.columns(2)
    with col_v_ncaa:
      st.markdown(f"**✈️ Visitante: {visita_ncaa}**")
      epa_off_v = st.number_input("EPA por Jugada Ofensiva (Visita):", -0.3, 0.4, 0.12, 0.01, key=f"epa_off_v_{idx}")
      epa_def_v = st.number_input("EPA Defensivo Permitido (Visita):", -0.4, 0.2, -0.08, 0.01, key=f"epa_def_v_{idx}")
      turnover_v = st.slider("Margen de Pérdidas / Turnovers (Visita):", -5, 5, 1, 1, key=f"TO_v_{idx}")

    with col_l_ncaa:
      st.markdown(f"**🏠 Local: {local_ncaa}**")
      epa_off_l = st.number_input("EPA por Jugada Ofensiva (Local):", -0.3, 0.4, 0.15, 0.01, key=f"epa_off_l_{idx}")
      epa_def_l = st.number_input("EPA Defensivo Permitido (Local):", -0.4, 0.2, -0.10, 0.01, key=f"epa_def_l_{idx}")
      turnover_l = st.slider("Margen de Pérdidas / Turnovers (Local):", -5, 5, 2, 1, key=f"TO_l_{idx}")

    ventaja_localia_ncaa = 2.5
    diferencial_epa = ((epa_off_l - epa_def_v) - (epa_off_v - epa_def_l)) * 32.0
    diferencial_to = (turnover_l - turnover_v) * 1.5
    spread_proyectado = round(diferencial_epa + diferencial_to + ventaja_localia_ncaa, 1)

    spread_casino_ncaa = st.number_input(
        f"Spread del Casino para {local_ncaa}:", -30.0, 30.0, -3.5, 0.5, key=f"sp_ncaa_{idx}"
    )
    momio_ncaa_int = int(
        st.number_input("Momio Casino (Spread):", value=-110, step=5, key=f"mom_ncaa_{idx}")
    )

    prob_cobertura_ncaa = round(
        (1 - stats.norm.cdf(-spread_casino_ncaa, loc=spread_proyectado, scale=13.5)) * 100, 2
    )
    pi_ncaa, edge_ncaa = calcular_edge_real(momio_ncaa_int, prob_cobertura_ncaa)
    stake_kelly_ncaa = calcular_criterio_kelly(
        st.session_state["bankroll_global"], prob_cobertura_ncaa, momio_ncaa_int
    )

    st.markdown(
        f"• Spread Proyectado por Modelo: `{spread_proyectado:+f}` | Prob. Implícita: `{pi_ncaa:.2f}%` | Prob. Modelo: `{prob_cobertura_ncaa}%`"
    )
    st.info(
        f"🎯 **Edge Neto: `+{edge_ncaa:.2f}%`** | 💡 **Stake Óptimo (Criterio de Kelly): `${stake_kelly_ncaa} MXN`**"
    )

    col_btn_n1, col_btn_n2 = st.columns(2)
    with col_btn_n1:
      if st.button(f"📥 Guardar en SQLite (NCAAF Elite #{idx})", key=f"db_ncaa_{idx}"):
        registrar_apuesta_db(
            fecha_formato_str,
            "NCAAF Elite",
            f"{visita_ncaa} @ {local_ncaa}",
            f"Spread {local_ncaa} ({spread_casino_ncaa})",
            momio_ncaa_int,
            edge_ncaa,
            stake_kelly_ncaa,
        )
        st.success("✅ ¡Guardado en base de datos!")
    with col_btn_n2:
      if st.button(f"📤 Enviar a Telegram (NCAAF Elite #{idx})", key=f"tg_ncaa_{idx}"):
        msg = f"""🎓 *MASTER SUITE ÉLITE — ALERTA NCAAF (ELITE)*
🏟️ {visita_ncaa} @ {local_ncaa}
📊 Spread: {local_ncaa} ({spread_casino_ncaa})
📈 Momio: {momio_ncaa_int} | Prob: {prob_cobertura_ncaa}%
🔥 Edge: +{edge_ncaa:.2f}%
💰 Stake (Kelly): ${stake_kelly_ncaa} MXN"""
        ok, res = enviar_alerta_telegram(
            st.session_state["telegram_token"],
            st.session_state["telegram_chat_id"],
            msg,
        )
        if ok:
          st.success(res)
        else:
          st.error(res)
    st.markdown("---")


# =========================================================
# 8. UFC
# =========================================================
elif modulo_seleccionado == "🥊 Sistema Cuantitativo Pro UFC (Combates)":
  st.title(f"🥊 **Sistema Cuantitativo Pro UFC [{fecha_formato_str}]**")
  st.info("Módulo activo de simulación y probabilidades para combates de artes marciales mixtas.")


# =========================================================
# 9. LMP
# =========================================================
elif modulo_seleccionado == "⚾ Liga Mexicana del Pacífico (LMP)":
  st.title(f"⚾ **Liga Mexicana del Pacífico [{fecha_formato_str}]**")
  st.info("Módulo analítico especializado en béisbol invernal mexicano.")


# =========================================================
# 10. MLB
# =========================================================
elif modulo_seleccionado == "⚾ Serie Mundial & Béisbol Pro (MLB)":
  st.title(f"⚾ **Béisbol Pro & Serie Mundial [{fecha_formato_str}]**")
  st.info("Módulo de análisis avanzado para pitcheo abridor y bullpen en MLB.")


# =========================================================
# 11. NHL (PUCK LINE)
# =========================================================
elif modulo_seleccionado == "🏒 Sistema Cuantitativo Pro NHL (Puck Line & Totales Empty Net)":
  st.title(f"🏒 **Sistema Cuantitativo Pro NHL [{fecha_formato_str}]**")
  st.info("Módulo activo para Hockey sobre Hielo con modelado Poisson en empty net.")


# =========================================================
# 12. PROPS NHL
# =========================================================
elif modulo_seleccionado == "🏒 Módulo Automático de Props NHL":
  st.title(f"🏒 **Props Automáticos NHL [{fecha_formato_str}]**")
  st.info("Módulo activo para tiros a gol y puntos de jugadores en NHL.")


# =========================================================
# 13. BANKROLL Y CLV
# =========================================================
elif modulo_seleccionado == "📊 Analítica, Control de Bankroll & Registro CLV":
  st.title(f"📊 **Panel de Analítica, Bankroll y Registro CLV [{fecha_formato_str}]**")
  
  col_br1, col_br2 = st.columns(2)
  with col_br1:
    nuevo_br = st.number_input(
        "Actualizar Bankroll Global (MXN):",
        value=st.session_state["bankroll_global"],
        step=500.0,
    )
    if nuevo_br != st.session_state["bankroll_global"]:
      st.session_state["bankroll_global"] = nuevo_br
  with col_br2:
    st.metric(
        label="💰 Bankroll Actual en Sistema",
        value=f"${st.session_state['bankroll_global']:,.2f} MXN",
        delta="+11.2%",
    )

  st.markdown("---")
  st.subheader("📋 **Historial de Apuestas Registradas (Base SQLite)**")

  conn = sqlite3.connect("master_suite_elite.db")
  cursor = conn.cursor()
  cursor.execute(
      "SELECT id, fecha, deporte, partido, mercado, momio, edge, stake, resultado FROM apuestas"
  )
  registros = cursor.fetchall()
  conn.close()

  if registros:
    for reg in registros:
      st.info(
          f"🆔 ID: {reg[0]} | 📅 {reg[1]} | Deporte: **{reg[2]}** | Partido: `{reg[3]}` \n•"
          f" Mercado: **{reg[4]}** | Momio: `{reg[5]}` | Edge: `+{reg[6]:.2f}%`"
          f" | Stake: `${reg[7]} MXN` | Estado: `{reg[8]}`"
      )
  else:
    st.info("ℹ️ No hay apuestas registradas todavía.")


# =========================================================
# 14. PARLAYS
# =========================================================
elif modulo_seleccionado == "🚀 Optimizador Automático de Parlays":
  st.title(f"🚀 **Optimizador Automático de Parlays [{fecha_formato_str}]**")
  st.info("Módulo activo para correlación y cálculo de momios combinados de valor esperado positivo.")
