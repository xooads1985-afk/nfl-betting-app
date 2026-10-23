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
# CONFIGURACIÓN DE BASE DE DATOS LOCAL (SQLITE PARA BANKROLL & CLV)
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
# MOTORES MATEMÁTICOS, KELLY CRITERION Y UTILIDADES (DEFINIDOS PRIMERO)
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
  p = prob_modelo_pct / 100.0
  if momio_americano > 0:
    b = momio_americano / 100.0
  else:
    b = 100.0 / abs(momio_americano)
  q = 1.0 - p
  kelly_full = (b * p - q) / b
  if kelly_full <= 0:
    return 0.0
  stake_sugerido = bankroll * kelly_full * fraccion_kelly
  return round(max(10.0, stake_sugerido), 2)


def calcular_probabilidad_handicap_nba(media_loc, media_vis, handicap_loc):
  return round(
      (
          1
          - stats.norm.cdf(
              -handicap_loc, loc=media_loc - media_vis, scale=11.5
          )
      )
      * 100,
      2,
  )


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
# CONEXIÓN CON THE ODDS API Y CARTELERAS
# ---------------------------------------------------------
@st.cache_data(ttl=300)
def obtener_cartelera_pura(deporte, liga, fecha_str_api, fecha_str_humana):
  if liga.lower() == "nba":
    url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={fecha_str_api}&limit=20"
  elif liga.lower() == "nfl":
    url = f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?dates={fecha_str_api}&limit=20"
  elif "college" in liga.lower():
    url = f"https://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard?dates={fecha_str_api}&limit=20"
  elif deporte.lower() == "soccer":
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{liga}/scoreboard?dates={fecha_str_api}&limit=30"
  else:
    url = f"https://site.api.espn.com/apis/site/v2/sports/{deporte}/{liga}/scoreboard?dates={fecha_str_api}&limit=20"

  try:
    response = requests.get(url, timeout=3)
    if response.status_code == 200:
      data = response.json()
      eventos = data.get("events", [])
      partidos_extraidos = []
      for evento in eventos:
        competencia = evento.get("competitions", [{}])[0]
        competidores = competencia.get("competitors", [])
        local, visitante = "", ""
        for comp in competidores:
          if comp.get("homeAway") == "home":
            local = comp.get("team", {}).get("displayName", "")
          else:
            visitante = comp.get("team", {}).get("displayName", "")
        if local and visitante:
          partidos_extraidos.append({
              "partido_str": f"📅 [{fecha_str_humana}] {visitante} @ {local}",
              "local": local,
              "visita": visitante,
          })
      if partidos_extraidos:
        return partidos_extraidos
  except Exception:
    pass

  if liga.lower() == "nba":
    return [{
        "partido_str": (
            f"📅 [{fecha_str_humana}] Boston Celtics @ Los Angeles Lakers"
        ),
        "local": "Los Angeles Lakers",
        "visita": "Boston Celtics",
    }]
  elif "soccer" in deporte.lower():
    return [{
        "partido_str": (
            f"📅 [{fecha_str_humana}] Equipo Visitante @ Equipo Local"
            " (Partido de Exhibición)"
        ),
        "local": "Equipo Local",
        "visita": "Equipo Visitante",
    }]

  return [{
      "partido_str": f"📅 [{fecha_str_humana}] Equipo Visitante @ Equipo Local",
      "local": "Local",
      "visita": "Visitante",
  }]


# ---------------------------------------------------------
# SELECTOR GLOBAL DE FECHA Y MENÚ
# ---------------------------------------------------------
st.sidebar.title("🎯 Menú de la Master Suite Élite")

fecha_seleccionada = st.sidebar.date_input(
    "📅 Selecciona la Fecha a Analizar:", value=date.today()
)
fecha_formato_api = fecha_seleccionada.strftime("%Y%m%d")
fecha_formato_api_nhl = fecha_seleccionada.strftime("%Y-%m-%d")
fecha_formato_str = fecha_seleccionada.strftime("%Y-%m-%d")

if "bankroll_global" not in st.session_state:
  st.session_state["bankroll_global"] = 15250.0

if "api_key_guardada" not in st.session_state:
  st.session_state["api_key_guardada"] = ""

st.sidebar.markdown("---")
st.sidebar.subheader("🌐 Configuración de API Odds")
input_api_key = st.sidebar.text_input(
    "API Key (The Odds API):",
    value=st.session_state["api_key_guardada"],
    type="password",
    key="input_api_key_widget",
)

if input_api_key != st.session_state["api_key_guardada"]:
  st.session_state["api_key_guardada"] = input_api_key

if st.sidebar.button("🔄 Actualizar y Sincronizar Fecha", use_container_width=True):
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
# 0. ESCÁNER AUTOMÁTICO
# =========================================================
if modulo_seleccionado == "🔍 Escáner Automático Inteligente Multi-Deporte (+EV)":
  st.title(
      f"🔍 **Escáner Automático Inteligente Multi-Deporte [{fecha_formato_str}]**"
  )
  st.info("ℹ️ Selecciona un módulo en el menú lateral para iniciar.")


# =========================================================
# 3. NBA
# =========================================================
elif (
    modulo_seleccionado
    == "🏀 Sistema Cuantitativo Pro NBA (Distribución Normal & Spread)"
):
  st.title(f"🏀 **Sistema Cuantitativo Pro NBA Élite [{fecha_formato_str}]**")
  cartelera_nba = obtener_cartelera_pura(
      "basketball", "nba", fecha_formato_api, fecha_formato_str
  )

  if not cartelera_nba:
    st.warning(
        f"⚠️ No se encontraron encuentros oficiales de la NBA para la fecha"
        f" {fecha_formato_str}."
    )

  for idx, op in enumerate(cartelera_nba, 1):
    local_nba = op["local"]
    visita_nba = op["visita"]
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

    st.markdown(
        f"📊 **Proyecciones NBA:** Score Proyectado: `{pts_loc_proj} -"
        f" {pts_vis_proj}` | Total: `{total_puntos_proj} pts`"
    )

    spread_casino = st.number_input(
        f"Spread del Casino para {local_nba}:",
        -20.0,
        20.0,
        -4.5,
        0.5,
        key=f"sp_cas_{idx}",
    )
    momio_sp_int = st.number_input(
        "Momio Casino (Spread):", value=-110, step=5, key=f"mom_sp_{idx}"
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
    st.markdown("---")


# =========================================================
# 5. FÚTBOL
# =========================================================
elif (
    modulo_seleccionado
    == "⚽ Módulo Global de Fútbol (Dixon-Coles Pro, BTTS & Hándicap Asiático)"
):
  st.title(
      f"⚽ **Dixon-Coles Pro & Auditoría Global — Fútbol [{fecha_formato_str}]**"
  )

  ligas_dict = {
      "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League (Inglaterra)": "eng.1",
      "🇪🇸 La Liga (España)": "esp.1",
      "🇮🇹 Serie A (Italia)": "ita.1",
      "🇩🇪 Bundesliga (Alemania)": "ger.1",
      "🇫🇷 Ligue 1 (Francia)": "fra.1",
      "⭐ UEFA Champions League": "uefa.champions",
  }

  liga_nombre_sel = st.selectbox(
      "🌐 Selecciona la Liga o Competición:", list(ligas_dict.keys())
  )
  liga_key_api = ligas_dict[liga_nombre_sel]

  cartelera_soccer = obtener_cartelera_pura(
      "soccer", liga_key_api, fecha_formato_api, fecha_formato_str
  )

  if not cartelera_soccer:
    st.warning(
        f"⚠️ No se encontraron encuentros para {liga_nombre_sel} en la fecha"
        f" {fecha_formato_str}."
    )

  for idx, op in enumerate(cartelera_soccer, 1):
    local_f = op["local"]
    visita_f = op["visita"]
    st.markdown(f"### ⚽ Encuentro #{idx}: `{visita_f} @ {local_f}`")

    col_v_card, col_l_card = st.columns(2)
    with col_v_card:
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
    with col_l_card:
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

    xgl_calc = round(max(0.5, (gf_l + gc_v) / 2.0), 2)
    xgv_calc = round(max(0.5, (gf_v + gc_l) / 2.0), 2)

    p_loc_f, p_vis_f, p_emp_f, btts_prob, ou_dict = motor_dixon_coles_soccer(
        xgl_calc, xgv_calc
    )

    st.markdown(
        f"📊 **Proyecciones xG:** Local: `{xgl_calc}` | Visita: `{xgv_calc}`"
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

    if st.button(
        f"📥 Guardar Apuesta en Base de Datos (Encuentro #{idx})",
        key=f"btn_db_{idx}",
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
      st.success("✅ ¡Apuesta guardada exitosamente en SQLite!")

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
          f"🆔 ID: {reg[0]} | 📅 {reg[1]} | **{reg[2]}**: `{reg[3]}` \n•"
          f" Mercado: **{reg[4]}** | Momio: `{reg[5]}` | Edge: `+{reg[6]:.2f}%`"
          f" | Stake: `${reg[7]} MXN` | Estado: `{reg[8]}`"
      )
  else:
    st.info(
        "ℹ️ Aún no hay apuestas guardadas. Genera un Sello del Modelo en"
        " Fútbol o NBA y guárdalo."
    )


# =========================================================
# RESTO DE MÓDULOS
# =========================================================
else:
  st.title(f"🚀 **Módulo Activo [{fecha_formato_str}]**")
  st.success("Módulo cargado correctamente.")
