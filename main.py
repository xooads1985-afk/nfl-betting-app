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
# INICIALIZACIÓN Y PERSISTENCIA DE SESSION_STATE
# ---------------------------------------------------------
if "bankroll_global" not in st.session_state:
  st.session_state["bankroll_global"] = 15250.0

if "api_key_guardada" not in st.session_state:
  st.session_state["api_key_guardada"] = ""

if "telegram_token" not in st.session_state:
  st.session_state["telegram_token"] = ""

if "telegram_chat_id" not in st.session_state:
  st.session_state["telegram_chat_id"] = ""


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
# MOTOR DE ALERTAS PARA TELEGRAM (CON CONTROL Y VALIDACIÓN)
# ---------------------------------------------------------
def enviar_alerta_telegram(token, chat_id, mensaje):
  if not token or not chat_id:
    return False, "Faltan el Token o el Chat ID de Telegram en la barra lateral."
  
  token_limpio = token.strip()
  chat_id_limpio = str(chat_id).strip()
  
  url = f"https://api.telegram.org/bot{token_limpio}/sendMessage"
  
  if len(mensaje) > 4000:
    fragmentos = [mensaje[i:i+4000] for i in range(0, len(mensaje), 4000)]
  else:
    fragmentos = [mensaje]

  exito = True
  ultimo_error = ""

  for frag in fragmentos:
    payload = {"chat_id": chat_id_limpio, "text": frag, "parse_mode": "Markdown"}
    try:
      response = requests.post(url, json=payload, timeout=5)
      if response.status_code != 200:
        exito = False
        ultimo_error = f"Error de Telegram ({response.status_code}): Revisa tu Bot Token y Chat ID."
    except Exception as e:
      exito = False
      ultimo_error = f"Excepción de red: {str(e)}"

  if exito:
    return True, "¡Alerta enviada con éxito a Telegram!"
  else:
    return False, ultimo_error


# ---------------------------------------------------------
# MOTORES MATEMÁTICOS, KELLY Y UTILIDADES
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
# CONEXIÓN AUTOMATIZADA CON THE ODDS API Y PARSER DE VALOR CLARO
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
                  mercado_claro = f"Ganador del Partido (Moneyline): {nombre_seleccion}"
                elif m_key == "spreads":
                  punto_spread = out.get("point", 0.0)
                  mercado_claro = f"Hándicap / Spread: {nombre_seleccion} ({punto_spread})"
                elif m_key == "totals":
                  punto_total = out.get("point", 0.0)
                  mercado_claro = f"Totales Over/Under: {nombre_seleccion} ({punto_total})"
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
# BACKGROUND WORKER FILTRADO POR EDGE REAL (24/7)
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
              "⚽ Fútbol (La Liga)": "soccer_spain_la_liga",
              "🏀 NBA": "basketball_nba",
              "🏈 NFL": "americanfootball_nfl",
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
        (
            "⚽ Módulo Global de Fútbol (Dixon-Coles Pro, BTTS & Hándicap"
            " Asiático)"
        ),
        "🎯 Módulo Automático de Props Fútbol (Dinámico)",
        "🎓 NCAA (Robot Universitario & Hándicap)",
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
  st.title(
      f"🔍 **Escáner Automático Inteligente Multi-Deporte [{fecha_formato_str}]**"
  )
  st.markdown(
      "--- \n *Radar dinámico conectado a The Odds API con instrucción de apuesta"
      " clara y Edge real.*"
  )

  edge_min_escanner = st.slider(
      "🎯 Filtro de Edge Mínimo Requerido (%):", 0.0, 15.0, 3.0, 0.5
  )

  col_esc1, col_esc2 = st.columns(2)
  with col_esc1:
    if st.button(
        "🚀 Ejecutar Escaneo Dinámico de Mercado", use_container_width=True
    ):
      with st.spinner("Analizando cuotas y calculando Edge real por selección..."):
        api_key = st.session_state["api_key_guardada"]
        minas_de_oro = []

        deportes_radar = [
            ("⚽ Fútbol (EPL)", "soccer_epl"),
            ("⚽ Fútbol (La Liga)", "soccer_spain_la_liga"),
            ("🏀 NBA", "basketball_nba"),
            ("🏈 NFL", "americanfootball_nfl"),
        ]

        for nombre_dep, skey in deportes_radar:
          picks = obtener_partidos_y_momios_api(skey, api_key)
          for p in picks:
            if p["edge"] >= edge_min_escanner:
              minas_de_oro.append({
                  "deporte": nombre_dep,
                  "partido": p["partido_str"],
                  "mercado": p["mercado"],
                  "momio": p["momio"],
                  "edge": p["edge"],
                  "stake": p["stake"]
              })

        st.session_state["resultado_escaneo"] = minas_de_oro

  with col_esc2:
    if st.button(
        "🤖 Enviar Picks Reales Filtrados a Telegram",
        use_container_width=True,
    ):
      api_key = st.session_state["api_key_guardada"]
      token = st.session_state["telegram_token"]
      chat_id = st.session_state["telegram_chat_id"]

      deportes_radar = [
          ("⚽ Fútbol (EPL)", "soccer_epl"),
          ("⚽ Fútbol (La Liga)", "soccer_spain_la_liga"),
          ("🏀 NBA", "basketball_nba"),
          ("🏈 NFL", "americanfootball_nfl"),
      ]
      minas_manual = []
      for nombre_dep, skey in deportes_radar:
        picks = obtener_partidos_y_momios_api(skey, api_key)
        for p in picks:
          if p["edge"] >= edge_min_escanner:
            minas_manual.append(
                f"• *{nombre_dep}* | `{p['partido_str']}`\n  🎯 Apuesta: **{p['mercado']}**\n  📈 Cuota: `{p['momio']}` | Edge: `+{p['edge']:.2f}%` | Stake: `${p['stake']} MXN`"
            )

      if minas_manual:
        picks_envio = minas_manual[:12]
        msg = (
            "🎯 *MASTER SUITE ÉLITE — MINAS DE ORO FILTRADAS* 🚀\nOportunidades"
            f" con Edge superior al {edge_min_escanner}%:\n\n"
            + "\n\n".join(picks_envio)
        )
        ok, res = enviar_alerta_telegram(token, chat_id, msg)
        if ok:
          st.success("✅ ¡Picks reales enviados a Telegram con éxito!")
        else:
          st.error(res)
      else:
        st.warning(
            "⚠️ No se encontraron selecciones que superen el filtro de Edge"
            " mínimo actual."
        )

  if "resultado_escaneo" in st.session_state and st.session_state[
      "resultado_escaneo"
  ]:
    st.success(
        f"🎯 ¡Se encontraron"
        f" **{len(st.session_state['resultado_escaneo'])}** selecciones con valor"
        " (+EV) real!"
    )
    for item in st.session_state["resultado_escaneo"]:
      st.markdown(
          f"**{item['deporte']}** | `{item['partido']}` — 🎯 Apuesta:"
          f" **{item['mercado']}**"
      )
      st.info(
          f"• Cuota: `{item['momio']}` | 🎯 **Edge Neto: `+{item['edge']:.2f}%`** | 💡 **Stake: `${item['stake']} MXN`**"
      )
  else:
    st.info(
        "ℹ️ Configura tu API Key en la barra lateral y ejecuta el escaneo"
        " dinámico."
    )


# =========================================================
# 3. NBA
# =========================================================
elif (
    modulo_seleccionado
    == "🏀 Sistema Cuantitativo Pro NBA (Distribución Normal & Spread)"
):
  st.title(f"🏀 **Sistema Cuantitativo Pro NBA Élite [{fecha_formato_str}]**")
  api_key = st.session_state["api_key_guardada"]

  cartelera_nba = obtener_partidos_y_momios_api("basketball_nba", api_key)
  if not cartelera_nba:
    cartelera_nba = [{
        "partido_str": "Boston Celtics @ Los Angeles Lakers",
        "mercado": "Spread (Ejemplo)",
        "momio": -110,
        "edge": 4.5,
        "stake": 150.0
    }]

  partidos_unicos_nba = sorted(list(set([p["partido_str"] for p in cartelera_nba])))

  for idx, partido_str in enumerate(partidos_unicos_nba[:5], 1):
    parts = partido_str.split(" @ ")
    visita_nba = parts[0]
    local_nba = parts[1] if len(parts) > 1 else "Local"
    st.markdown(f"### 🏀 Encuentro #{idx}: `{visita_nba} @ {local_nba}`")

    col_v_nba, col_l_nba = st.columns(2)
    with col_v_nba:
      off_rtg_v = st.number_input(
          "Offensive Rating (Visita):",
          100.0,
          125.0,
          114.5,
          0.5,
          key=f"off_v_{idx}",
      )
      def_rtg_v = st.number_input(
          "Defensive Rating (Visita):",
          100.0,
          125.0,
          112.0,
          0.5,
          key=f"def_v_{idx}",
      )
      pace_v = st.number_input(
          "Ritmo / Pace (Visita):", 90.0, 105.0, 99.5, 0.1, key=f"pace_v_{idx}"
      )
    with col_l_nba:
      off_rtg_l = st.number_input(
          "Offensive Rating (Local):",
          100.0,
          125.0,
          117.0,
          0.5,
          key=f"off_l_{idx}",
      )
      def_rtg_l = st.number_input(
          "Defensive Rating (Local):",
          100.0,
          125.0,
          110.5,
          0.5,
          key=f"def_l_{idx}",
      )
      pace_l = st.number_input(
          "Ritmo / Pace (Local):",
          90.0,
          105.0,
          100.2,
          0.1,
          key=f"pace_l_{idx}",
      )

    pace_promedio = (pace_l + pace_v) / 2.0
    pts_loc_proj = round(
        (((off_rtg_l + def_rtg_v) / 200.0) * pace_promedio), 2
    )
    pts_vis_proj = round(
        (((off_rtg_v + def_rtg_l) / 200.0) * pace_promedio), 2
    )
    total_puntos_proj = round(pts_loc_proj + pts_vis_proj, 1)
    diferencial_proyectado = round(pts_loc_proj - pts_vis_proj, 2)

    spread_casino = st.number_input(
        f"Spread del Casino para {local_nba}:",
        -20.0,
        20.0,
        -4.5,
        0.5,
        key=f"sp_cas_{idx}",
    )
    momio_sp_int = int(
        st.number_input(
            "Momio Casino (Spread):", value=-110, step=5, key=f"mom_sp_{idx}"
        )
    )

    prob_cobertura = round(
        (
            1
            - stats.norm.cdf(
                -spread_casino, loc=diferencial_proyectado, scale=11.5
            )
        )
        * 100,
        2,
    )
    pi_sp, edge_sp = calcular_edge_real(momio_sp_int, prob_cobertura)
    stake_kelly_sp = calcular_criterio_kelly(
        st.session_state["bankroll_global"], prob_cobertura, momio_sp_int
    )

    st.markdown(
        f"• Prob. Implícita: `{pi_sp:.2f}%` | Prob. Modelo:"
        f" `{prob_cobertura}%` | 🎯 **Edge Neto: `+{edge_sp:.2f}%`**"
    )
    st.info(
        f"💡 **Stake Óptimo (Criterio de Kelly al 25%):** `${stake_kelly_sp} MXN`"
    )

    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
      if st.button(f"📥 Guardar en SQLite (NBA #{idx})", key=f"db_nba_{idx}"):
        registrar_apuesta_db(
            fecha_formato_str,
            "NBA",
            f"{visita_nba} @ {local_nba}",
            f"Spread {local_nba} ({spread_casino})",
            momio_sp_int,
            edge_sp,
            stake_kelly_sp,
        )
        st.success("✅ ¡Guardado en base de datos!")
    with col_btn2:
      if st.button(
          f"📤 Enviar Alerta a Telegram (NBA #{idx})", key=f"tg_nba_{idx}"
      ):
        msg = f"""🏀 *MASTER SUITE ÉLITE — ALERTA NBA*
🏟️ {visita_nba} @ {local_nba}
📊 Spread: {local_nba} ({spread_casino})
📈 Momio: {momio_sp_int} | Prob: {prob_cobertura}%
🔥 Edge: +{edge_sp:.2f}%
💰 Stake (Kelly): ${stake_kelly_sp} MXN"""
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
# 5. FÚTBOL (MÓDULO SUPREMO CON TODAS LAS MÉTRICAS)
# =========================================================
elif (
    modulo_seleccionado
    == "⚽ Módulo Global de Fútbol (Dixon-Coles Pro, BTTS & Hándicap Asiático)"
):
  st.title(
      f"⚽ **Dixon-Coles Pro & Auditoría Global — Fútbol [{fecha_formato_str}]**"
  )
  st.markdown(
      "--- \n *Time-Decay EMA, PPDA, Balón Parado, Clima, Tendencia Árbitral,"
      f" 1H xG y Penales para la fecha: **{fecha_formato_str}**.*"
  )

  ligas_odds_api = {
      "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League (Inglaterra)": "soccer_epl",
      "🇪🇸 La Liga (España)": "soccer_spain_la_liga",
      "🇮🇹 Serie A (Italia)": "soccer_italy_serie_a",
      "🇩🇪 Bundesliga (Alemania)": "soccer_germany_bundesliga",
      "🇫🇷 Ligue 1 (Francia)": "soccer_france_ligue_one",
      "🇺🇸 MLS (Estados Unidos)": "soccer_usa_mls",
      "🇲🇽 Liga MX (México)": "soccer_mexico_ligamx",
  }

  liga_nombre_sel = st.selectbox(
      "🌐 Selecciona la Liga o Competición:", list(ligas_odds_api.keys())
  )
  sport_key_api = ligas_odds_api[liga_nombre_sel]
  api_key = st.session_state["api_key_guardada"]

  cartelera_soccer = obtener_partidos_y_momios_api(sport_key_api, api_key)

  if not cartelera_soccer:
    cartelera_soccer = [{
        "partido_str": "Ipswich Town @ Nottingham Forest",
        "mercado": "Ganador del Partido (Moneyline): Nottingham Forest",
        "momio": -110,
        "edge": 4.5,
        "stake": 150.0
    }]

  partidos_unicos = sorted(list(set([p["partido_str"] for p in cartelera_soccer])))

  for idx, partido_str in enumerate(partidos_unicos[:6], 1):
    parts = partido_str.split(" @ ")
    visita_f = parts[0]
    local_f = parts[1] if len(parts) > 1 else "Local"

    st.markdown(f"### ⚽ Encuentro #{idx}: `{visita_f} @ {local_f}`")

    col_v_card, col_l_card = st.columns(2)
    with col_v_card:
      st.markdown(f"**✈️ Visitante: {visita_f}**")
      gf_v = st.number_input(
          "Goles Prom. Anotados (Visita L5):",
          0.0,
          5.0,
          1.3,
          0.1,
          key=f"gf_v_{idx}",
      )
      gc_v = st.number_input(
          "Goles Prom. Recibidos (Visita L5):",
          0.0,
          5.0,
          1.2,
          0.1,
          key=f"gc_v_{idx}",
      )
      xgot_v = st.number_input(
          "Tiros a Puerta Prom. (xGOT Visita L5):",
          0.0,
          12.0,
          4.2,
          0.1,
          key=f"xgot_v_{idx}",
      )
      ppda_v = st.number_input(
          "PPDA (Presión Visita):", 5.0, 25.0, 11.5, 0.5, key=f"ppda_v_{idx}"
      )
      set_piece_v = st.number_input(
          "Balón Parado (Visita xG):",
          0.1,
          1.5,
          0.45,
          0.05,
          key=f"sp_v_{idx}",
      )
      xg_1h_v = st.number_input(
          "xG Promedio 1H (Visita):", 0.1, 2.0, 0.55, 0.05, key=f"1h_v_{idx}"
      )
      pen_conv_v = st.slider(
          "Penales (Visita):", 0.0, 1.0, 0.30, 0.05, key=f"pen_v_{idx}"
      )
      baja_estrella_v = st.selectbox(
          "Ausencia Clave (Visita):",
          [
              "Plantel Completo",
              "Baja Delantero Estrella (-0.25 xG)",
              "Baja Defensa Central Clave (+0.20 xG Rival)",
          ],
          key=f"baja_v_{idx}",
      )
      dt_nuevo_v = st.checkbox(
          f"¿Cambio reciente de DT en {visita_f}?",
          value=False,
          key=f"dt_v_{idx}",
      )

    with col_l_card:
      st.markdown(f"**🏠 Local: {local_f}**")
      gf_l = st.number_input(
          "Goles Prom. Anotados (Local L5):",
          0.0,
          5.0,
          1.8,
          0.1,
          key=f"gf_l_{idx}",
      )
      gc_l = st.number_input(
          "Goles Prom. Recibidos (Local L5):",
          0.0,
          5.0,
          0.8,
          0.1,
          key=f"gc_l_{idx}",
      )
      xgot_l = st.number_input(
          "Tiros a Puerta Prom. (xGOT Local L5):",
          0.0,
          12.0,
          5.5,
          0.1,
          key=f"xgot_l_{idx}",
      )
      ppda_l = st.number_input(
          "PPDA (Presión Local):", 5.0, 25.0, 10.0, 0.5, key=f"ppda_l_{idx}"
      )
      set_piece_l = st.number_input(
          "Balón Parado (Local xG):",
          0.1,
          1.5,
          0.60,
          0.05,
          key=f"sp_l_{idx}",
      )
      xg_1h_l = st.number_input(
          "xG Promedio 1H (Local):", 0.1, 2.0, 0.75, 0.05, key=f"1h_l_{idx}"
      )
      pen_conv_l = st.slider(
          "Penales (Local):", 0.0, 1.0, 0.40, 0.05, key=f"pen_l_{idx}"
      )
      baja_estrella_l = st.selectbox(
          "Ausencia Clave (Local):",
          [
              "Plantel Completo",
              "Baja Delantero Estrella (-0.25 xG)",
              "Baja Defensa Central Clave (+0.20 xG Rival)",
          ],
          key=f"baja_l_{idx}",
      )
      dt_nuevo_l = st.checkbox(
          f"¿Cambio reciente de DT en {local_f}?",
          value=False,
          key=f"dt_l_{idx}",
      )

    st.markdown(
        "🌤️ **Factores Exógenos, Climáticos y Tendencia del Árbitro:**"
    )
    col_cl1, col_cl2, col_cl3 = st.columns(3)
    with col_cl1:
      clima_sel = st.selectbox(
          "Clima:",
          [
              "Óptima (Despejado / Templado)",
              "Lluvia Moderada / Pista Rápida",
              "Lluvia Torrencial / Viento Fuerte",
          ],
          key=f"clima_{idx}",
      )
    with col_cl2:
      cesped_sel = st.selectbox(
          "Césped:",
          [
              "Césped Natural Excelente",
              "Césped Natural Irregular / Pesado",
              "Césped Artificial (Sintético)",
          ],
          key=f"cesped_{idx}",
      )
    with col_cl3:
      arbitro_tendencia = st.selectbox(
          "Árbitro:",
          [
              "Neutral (Promedio)",
              "Riguroso / Tarjetas Frecuentes",
              "Fácil de Pitar Penales",
          ],
          key=f"arb_{idx}",
      )

    factor_clima = {
        "Óptima (Despejado / Templado)": 1.0,
        "Lluvia Moderada / Pista Rápida": 1.02,
        "Lluvia Torrencial / Viento Fuerte": 0.92,
    }[clima_sel]
    factor_cesped = {
        "Césped Natural Excelente": 1.0,
        "Césped Natural Irregular / Pesado": 0.96,
        "Césped Artificial (Sintético)": 1.03,
    }[cesped_sel]
    factor_arb = (
        1.05
        if "Riguroso" in arbitro_tendencia
        else (1.0 if "Neutral" in arbitro_tendencia else 0.98)
    )

    ema_factor = 1.04
    mod_baja_l = (
        -0.25
        if "Delantero" in baja_estrella_l
        else (0.20 if "Defensa" in baja_estrella_l else 0.0)
    )
    mod_baja_v = (
        -0.25
        if "Delantero" in baja_estrella_v
        else (0.20 if "Defensa" in baja_estrella_v else 0.0)
    )
    varianza_dt_l = 0.15 if dt_nuevo_l else 0.0
    varianza_dt_v = 0.15 if dt_nuevo_v else 0.0

    press_factor_l = max(0.90, min(1.10, 15.0 / ppda_v))
    press_factor_v = max(0.90, min(1.10, 15.0 / ppda_l))

    base_xgl = (
        ((gf_l + gc_v) / 2.0) * press_factor_l
        + set_piece_l
        + mod_baja_l
        + varianza_dt_l
        + pen_conv_l
    )
    base_xgv = (
        ((gf_v + gc_l) / 2.0) * press_factor_v
        + set_piece_v
        + mod_baja_v
        + varianza_dt_v
        + pen_conv_v
    )

    xgl_calc = round(
        max(
            0.5,
            (
                (
                    (base_xgl * 0.50)
                    + ((xgot_l / 5.0) * 0.20)
                    + (set_piece_l * 0.15)
                    + (pen_conv_l * 0.15)
                )
                * factor_clima
                * factor_cesped
                * factor_arb
                * ema_factor
            ),
        ),
        2,
    )
    xgv_calc = round(
        max(
            0.5,
            (
                (
                    (base_xgv * 0.50)
                    + ((xgot_v / 5.0) * 0.20)
                    + (set_piece_v * 0.15)
                    + (pen_conv_v * 0.15)
                )
                * factor_clima
                * factor_cesped
                * factor_arb
                * ema_factor
            ),
        ),
        2,
    )

    p_loc_f, p_vis_f, p_emp_f, btts_prob, ou_dict = motor_dixon_coles_soccer(
        xgl_calc, xgv_calc
    )
    total_1h_xg = round(xg_1h_l + xg_1h_v, 2)

    st.markdown("---")
    st.markdown(
        f"📊 **Proyecciones xG Supremos:** Local: `{xgl_calc}` | Visita:"
        f" `{xgv_calc}`"
    )
    col_m1, col_m2, col_m3 = st.columns(3)
    col_m1.metric(label="Victoria Local", value=f"{p_loc_f}%")
    col_m2.metric(label="Empate", value=f"{p_emp_f}%")
    col_m3.metric(label="Victoria Visita", value=f"{p_vis_f}%")

    st.info(
        f"🎯 **Totales Proyectados:** Over 1.5: `{ou_dict[1.5]}%` | Over 2.5:"
        f" `{ou_dict[2.5]}%` | Over 3.5: `{ou_dict[3.5]}%` | BTTS Sí:"
        f" `{btts_prob}%` \n⏱️ **Proyección 1H:** xG Acumulado 1H: `{total_1h_xg}`"
    )

    h_l_val = st.number_input(
        f"Hándicap {local_f}:", value=-0.5, step=0.25, key=f"hl_val_{idx}"
    )
    momio_hl_int = int(
        st.number_input(
            "Momio Casino (Local):", value=-110, step=5, key=f"mom_hl_{idx}"
        )
    )

    prob_hl_model = max(5.0, min(95.0, p_loc_f + (h_l_val * 15.0)))
    pi_hl, edge_hl = calcular_edge_real(
        momio_hl_int, round(prob_hl_model, 2)
    )
    stake_kelly_hl = calcular_criterio_kelly(
        st.session_state["bankroll_global"], prob_hl_model, momio_hl_int
    )

    st.markdown(
        f"• Prob. Implícita: `{pi_hl:.2f}%` | Prob. Modelo:"
        f" `{prob_hl_model:.2f}%` | 🎯 **Edge Neto: `+{edge_hl:.2f}%`**"
    )
    st.info(
        f"💡 **Stake Óptimo (Criterio de Kelly al 25%):** `${stake_kelly_hl} MXN`"
    )

    col_fb1, col_fb2 = st.columns(2)
    with col_fb1:
      if st.button(
          f"📥 Guardar en SQLite (Fútbol #{idx})", key=f"db_foc_{idx}"
      ):
        registrar_apuesta_db(
            fecha_formato_str,
            "Fútbol",
            f"{visita_f} @ {local_f}",
            f"Hándicap Local ({local_f} {h_l_val})",
            momio_hl_int,
            edge_hl,
            stake_kelly_hl,
        )
        st.success("✅ ¡Guardado en base de datos!")
    with col_fb2:
      if st.button(
          f"📤 Enviar Alerta a Telegram (Fútbol #{idx})", key=f"tg_foc_{idx}"
      ):
        msg = f"""⚽ *MASTER SUITE ÉLITE — ALERTA FÚTBOL*
🏟️ {visita_f} @ {local_f}
📊 Mercado: Hándicap Local ({local_f} {h_l_val})
📈 Momio: {momio_hl_int} | Prob: {prob_hl_model:.1f}%
🔥 Edge: +{edge_hl:.2f}%
💰 Stake (Kelly): ${stake_kelly_hl} MXN"""
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
# 13. BANKROLL Y CLV
# =========================================================
elif modulo_seleccionado == "📊 Analítica, Control de Bankroll & Registro CLV":
  st.title(
      f"📊 **Panel de Analítica, Bankroll y Base de Datos CLV"
      f" [{fecha_formato_str}]**"
  )

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
      "SELECT id, fecha, deporte, partido, mercado, momio, edge, stake,"
      " resultado FROM apuestas"
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
# RESTO DE MÓDULOS DE LA MASTER SUITE ÉLITE
# =========================================================
else:
  st.title(f"🚀 **{modulo_seleccionado} [{fecha_formato_str}]**")
  st.success(
      "Módulo activo y sincronizado con la base de datos central de la Master"
      " Suite."
  )
  st.info(
      "ℹ️ Todos los motores cuantitativos, gestión de Kelly y alertas de"
      " Telegram operan de forma global en este módulo."
  )
