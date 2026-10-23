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
# INICIALIZACIÓN SEGURA DE SESSION_STATE (EVITA ERRORES DE SESIÓN)
# ---------------------------------------------------------
if "bankroll_global" not in st.session_state:
  st.session_state["bankroll_global"] = 15250.0

if "api_key_guardada" not in st.session_state:
  st.session_state["api_key_guardada"] = ""


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
# MOTORES MATEMÁTICOS, KELLY CRITERION Y UTILIDADES
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
    st.markdown("---")


# =========================================================
# 5. FÚTBOL (CON PPDA, BALÓN PARADO, CLIMA, KELLY Y SQLITE)
# =========================================================
elif (
    modulo_seleccionado
    == "⚽ Módulo Global de Fútbol (Dixon-Coles Pro, BTTS & Hándicap Asiático)"
):
  st.title(
      f"⚽ **Dixon-Coles Pro & Auditoría Global — Fútbol [{fecha_formato_str}]**"
  )
  st.markdown(
      "--- \n *Time-Decay EMA, PPDA, Balón Parado, Clima, Criterio de Kelly y"
      f" SQLite para la fecha: **{fecha_formato_str}**.*"
  )

  ligas_dict = {
      "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League (Inglaterra)": "eng.1",
      "🇪🇸 La Liga (España)": "esp.1",
      "🇮🇹 Serie A (Italia)": "ita.1",
      "🇩🇪 Bundesliga (Alemania)": "ger.1",
      "🇫🇷 Ligue 1 (Francia)": "fra.1",
      "⭐ UEFA Champions League": "uefa.champions",
      "🇪🇺 UEFA Europa League": "uefa.europa",
      "🇧🇷 Brasileirão (Brasil)": "bra.1",
      "🇺🇸 MLS (Estados Unidos)": "usa.1",
      "🇲🇽 Liga MX (México)": "mex.1",
      "🇯🇵 J1 League (Japón)": "jpn.1",
      "🇹🇷 Süper Lig (Turquía)": "tur.1",
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
        f"⚠️ No se encontraron encuentros oficiales para {liga_nombre_sel} en la"
        f" fecha {fecha_formato_str}."
    )

  for idx, op in enumerate(cartelera_soccer, 1):
    local_f = op["local"]
    visita_f = op["visita"]

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
          "PPDA (Intensidad Presión Visita):",
          5.0,
          25.0,
          11.5,
          0.5,
          key=f"ppda_v_{idx}",
      )
      set_piece_v = st.number_input(
          "Peligro Balón Parado (Visita xG):",
          0.1,
          1.5,
          0.45,
          0.05,
          key=f"sp_v_{idx}",
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
      descanso_v = st.selectbox(
          "Días de Descanso (Visitante):",
          [
              "3 días o menos (Fatiga)",
              "4 a 5 días (Normal)",
              "6+ días (Descansado)",
          ],
          index=1,
          key=f"desc_v_{idx}",
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
          "PPDA (Intensidad Presión Local):",
          5.0,
          25.0,
          10.0,
          0.5,
          key=f"ppda_l_{idx}",
      )
      set_piece_l = st.number_input(
          "Peligro Balón Parado (Local xG):",
          0.1,
          1.5,
          0.60,
          0.05,
          key=f"sp_l_{idx}",
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
      descanso_l = st.selectbox(
          "Días de Descanso (Local):",
          [
              "3 días o menos (Fatiga)",
              "4 a 5 días (Normal)",
              "6+ días (Descansado)",
          ],
          index=1,
          key=f"desc_l_{idx}",
      )

    st.markdown("🌤️ **Factores Exógenos y Climáticos del Partido:**")
    col_cl1, col_cl2 = st.columns(2)
    with col_cl1:
      clima_sel = st.selectbox(
          "Condición Climática:",
          [
              "Óptima (Despejado / Templado)",
              "Lluvia Moderada / Pista Rápida",
              "Lluvia Torrencial / Viento Fuerte",
          ],
          key=f"clima_{idx}",
      )
    with col_cl2:
      cesped_sel = st.selectbox(
          "Estado del Terreno de Juego:",
          [
              "Césped Natural Excelente",
              "Césped Natural Irregular / Pesado",
              "Césped Artificial (Sintético)",
          ],
          key=f"cesped_{idx}",
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

    factor_fatiga = {
        "3 días o menos (Fatiga)": 0.90,
        "4 a 5 días (Normal)": 1.0,
        "6+ días (Descansado)": 1.05,
    }
    f_l = factor_fatiga[descanso_l]
    f_v = factor_fatiga[descanso_v]

    press_factor_l = max(0.90, min(1.10, 15.0 / ppda_v))
    press_factor_v = max(0.90, min(1.10, 15.0 / ppda_l))

    base_xgl = (
        ((gf_l + gc_v) / 2.0) * press_factor_l
        + set_piece_l
        + mod_baja_l
        + varianza_dt_l
    )
    base_xgv = (
        ((gf_v + gc_l) / 2.0) * press_factor_v
        + set_piece_v
        + mod_baja_v
        + varianza_dt_v
    )

    calidad_tiros_l = xgot_l / 5.0
    calidad_tiros_v = xgot_v / 5.0

    xgl_calc = round(
        max(
            0.5,
            (
                (
                    (base_xgl * 0.55)
                    + (calidad_tiros_l * 0.25)
                    + (set_piece_l * 0.20)
                )
                * f_l
                * factor_clima
                * factor_cesped
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
                    (base_xgv * 0.55)
                    + (calidad_tiros_v * 0.25)
                    + (set_piece_v * 0.20)
                )
                * f_v
                * factor_clima
                * factor_cesped
                * ema_factor
            ),
        ),
        2,
    )

    p_loc_f, p_vis_f, p_emp_f, btts_prob, ou_dict = motor_dixon_coles_soccer(
        xgl_calc, xgv_calc
    )
    btts_no_prob = round(100.0 - btts_prob, 2)

    st.markdown("---")
    st.markdown(
        f"📊 **Proyecciones del Modelo (xG Local: `{xgl_calc}` | xG Visita:"
        f" `{xgv_calc}`):**"
    )
    col_m1, col_m2, col_m3 = st.columns(3)
    col_m1.metric(label="Victoria Local", value=f"{p_loc_f}%")
    col_m2.metric(label="Empate", value=f"{p_emp_f}%")
    col_m3.metric(label="Victoria Visita", value=f"{p_vis_f}%")

    st.info(
        f"🎯 **Totales Proyectados:** Over 1.5: `{ou_dict[1.5]}%` | Over 2.5:"
        f" `{ou_dict[2.5]}%` | Over 3.5: `{ou_dict[3.5]}%` | BTTS Sí:"
        f" `{btts_prob}%`"
    )

    st.markdown("💰 **Auditoría de Momios, Criterio de Kelly & CLV:**")
    tab_ah_l, tab_ah_v, tab_ou, tab_btts, tab_clv = st.tabs([
        f"⚖️ Hándicap Local ({local_f})",
        f"⚖️ Hándicap Visita ({visita_f})",
        "📈 Over / Under",
        "🤝 Ambos Anotan (BTTS)",
        "📊 Auditoría CLV",
    ])

    edges_partido = []

    with tab_ah_l:
      col_hl1, col_hl2 = st.columns(2)
      with col_hl1:
        h_l_str = st.text_input(
            f"Hándicap {local_f}:", value="-0.5", key=f"hl_val_{idx}"
        )
        try:
          h_l_val = float(h_l_str)
        except ValueError:
          h_l_val = -0.5
      with col_hl2:
        momio_hl_str = st.text_input(
            "Momio Casino (Local):", value="-110", key=f"mom_hl_{idx}"
        )
        try:
          mom_hl_int = int(momio_hl_str)
        except ValueError:
          mom_hl_int = -110

      prob_hl_model = max(5.0, min(95.0, p_loc_f + (h_l_val * 15.0)))
      pi_hl, edge_hl = calcular_edge_real(
          mom_hl_int, round(prob_hl_model, 2)
      )
      stake_kelly_hl = calcular_criterio_kelly(
          st.session_state["bankroll_global"], prob_hl_model, mom_hl_int
      )
      edges_partido.append((
          f"Hándicap Local ({local_f} {h_l_val})",
          edge_hl,
          mom_hl_int,
          "AH_LOC",
          prob_hl_model,
          stake_kelly_hl,
      ))

      st.markdown(
          f"• Prob. Implícita: `{pi_hl:.2f}%` | Prob. Modelo:"
          f" `{prob_hl_model:.2f}%` | 🎯 **Edge Neto: `+{edge_hl:.2f}%`**"
      )
      st.info(
          f"💡 **Stake Óptimo (Criterio de Kelly al 25%):**"
          f" `${stake_kelly_hl} MXN`"
      )
      if edge_hl >= 3.0:
        st.success("✅ **¡Mina de Oro (+EV)!**")
      else:
        st.warning("⚠️ Sin margen suficiente.")

    with tab_ah_v:
      col_hv1, col_hv2 = st.columns(2)
      with col_hv1:
        h_v_str = st.text_input(
            f"Hándicap {visita_f}:", value="+0.5", key=f"hv_val_{idx}"
        )
        try:
          h_v_val = float(h_v_str)
        except ValueError:
          h_v_val = 0.5
      with col_hv2:
        momio_hv_str = st.text_input(
            "Momio Casino (Visita):", value="+120", key=f"mom_hv_{idx}"
        )
        try:
          mom_hv_int = int(momio_hv_str)
        except ValueError:
          mom_hv_int = 120

      prob_hv_model = max(5.0, min(95.0, p_vis_f + (h_v_val * 15.0)))
      pi_hv, edge_hv = calcular_edge_real(
          mom_hv_int, round(prob_hv_model, 2)
      )
      stake_kelly_hv = calcular_criterio_kelly(
          st.session_state["bankroll_global"], prob_hv_model, mom_hv_int
      )
      edges_partido.append((
          f"Hándicap Visita ({visita_f} {h_v_val})",
          edge_hv,
          mom_hv_int,
          "AH_VIS",
          prob_hv_model,
          stake_kelly_hv,
      ))

      st.markdown(
          f"• Prob. Implícita: `{pi_hv:.2f}%` | Prob. Modelo:"
          f" `{prob_hv_model:.2f}%` | 🎯 **Edge Neto: `+{edge_hv:.2f}%`**"
      )
      st.info(
          f"💡 **Stake Óptimo (Criterio de Kelly al 25%):**"
          f" `${stake_kelly_hv} MXN`"
      )
      if edge_hv >= 3.0:
        st.success("✅ **¡Mina de Oro (+EV)!**")
      else:
        st.warning("⚠️ Sin margen suficiente.")

    with tab_ou:
      col_ou1, col_ou2, col_ou3 = st.columns(3)
      with col_ou1:
        sel_tipo_ou = st.selectbox(
            "Mercado O/U:",
            ["Over (Más de)", "Under (Menos de)"],
            key=f"sel_tipo_ou_{idx}",
        )
      with col_ou2:
        linea_ou_sel = st.selectbox(
            "Línea de Goles:", [1.5, 2.5, 3.5, 4.5], index=1, key=f"linea_ou_{idx}"
        )
      with col_ou3:
        momio_ou_str = st.text_input(
            "Momio Casino (O/U):", value="-115", key=f"mom_ou_{idx}"
        )
        try:
          mom_ou_int = int(momio_ou_str)
        except ValueError:
          mom_ou_int = -115

      prob_over_sel = ou_dict[linea_ou_sel]
      prob_ou_model = (
          prob_over_sel
          if "Over" in sel_tipo_ou
          else round(100.0 - prob_over_sel, 2)
      )
      pi_ou, edge_ou = calcular_edge_real(mom_ou_int, prob_ou_model)
      stake_kelly_ou = calcular_criterio_kelly(
          st.session_state["bankroll_global"], prob_ou_model, mom_ou_int
      )
      nombre_mercado_ou = f"{sel_tipo_ou} {linea_ou_sel}"
      tag_ou = "OVER" if "Over" in sel_tipo_ou else "UNDER"
      edges_partido.append((
          nombre_mercado_ou,
          edge_ou,
          mom_ou_int,
          tag_ou,
          prob_ou_model,
          stake_kelly_ou,
      ))

      st.markdown(
          f"• Prob. Implícita: `{pi_ou:.2f}%` | Prob. Modelo:"
          f" `{prob_ou_model}%` | 🎯 **Edge Neto: `+{edge_ou:.2f}%`**"
      )
      st.info(
          f"💡 **Stake Óptimo (Criterio de Kelly al 25%):**"
          f" `${stake_kelly_ou} MXN`"
      )
      if edge_ou >= 3.0:
        st.success("✅ **¡Mina de Oro (+EV)!**")
      else:
        st.warning("⚠️ Sin margen suficiente.")

    with tab_btts:
      col_b1, col_b2 = st.columns(2)
      with col_b1:
        sel_btts = st.selectbox(
            "Selección BTTS:",
            ["Ambos Anotan (Sí)", "No Anotan (No)"],
            key=f"sel_btts_{idx}",
        )
      with col_b2:
        momio_b_str = st.text_input(
            "Momio Casino (BTTS):", value="-120", key=f"mom_b_{idx}"
        )
        try:
          mom_b_int = int(momio_b_str)
        except ValueError:
          mom_b_int = -120

      prob_b_model = btts_prob if "Sí" in sel_btts else btts_no_prob
      pi_b, edge_b = calcular_edge_real(mom_b_int, prob_b_model)
      stake_kelly_b = calcular_criterio_kelly(
          st.session_state["bankroll_global"], prob_b_model, mom_b_int
      )
      edges_partido.append(
          (sel_btts, edge_b, mom_b_int, "BTTS", prob_b_model, stake_kelly_b)
      )

      st.markdown(
          f"• Prob. Implícita: `{pi_b:.2f}%` | Prob. Modelo:"
          f" `{prob_b_model}%` | 🎯 **Edge Neto: `+{edge_b:.2f}%`**"
      )
      st.info(
          f"💡 **Stake Óptimo (Criterio de Kelly al 25%):**"
          f" `${stake_kelly_b} MXN`"
      )
      if edge_b >= 3.0:
        st.success("✅ **¡Mina de Oro (+EV)!**")
      else:
        st.warning("⚠️ Sin margen suficiente.")

    with tab_clv:
      st.markdown("📈 **Seguimiento Histórico del CLV:**")
      c_clv1, c_clv2 = st.columns(2)
      with c_clv1:
        momio_tomado = st.number_input(
            "Momio al Tomar la Apuesta:", value=-110, key=f"m_tomado_{idx}"
        )
      with c_clv2:
        momio_cierre = st.number_input(
            "Momio de Cierre del Mercado:", value=-125, key=f"m_cierre_{idx}"
        )

      if momio_tomado > momio_cierre:
        st.success("🔥 **¡CLV POSITIVO CONSEGUIDO!**")
      else:
        st.warning("⚠️ El mercado cerró con mejor cuota.")

    mejor_mercado, mejor_edge, mejor_momio, mejor_tag, mejor_prob, mejor_stake = (
        max(edges_partido, key=lambda x: x[1])
    )

    bloqueo_activo = False
    if mejor_tag == "OVER" and xgl_calc + xgv_calc < 1.8:
      bloqueo_activo = True
    elif mejor_tag == "UNDER" and xgl_calc + xgv_calc > 3.2:
      bloqueo_activo = True

    if bloqueo_activo:
      st.warning(
          f"🛡️ **Filtro Anti-Correlaciones Negativas:** Sello en"
          f" *{mejor_mercado}* bloqueado."
      )
      alternativas = [e for e in edges_partido if e[3] != mejor_tag]
      if alternativas:
        mejor_mercado, mejor_edge, mejor_momio, _, mejor_prob, mejor_stake = max(
            alternativas, key=lambda x: x[1]
        )

    if mejor_edge >= 3.0 and not bloqueo_activo:
      st.success(
          f"🔥 **SELLO DEL MODELO (MEJOR PICK): ¡{mejor_mercado}!** (Edge:"
          f" `+{mejor_edge:.2f}%` | Cuota: `{mejor_momio}` | Stake:"
          f" `${mejor_stake} MXN`)"
      )

      with st.expander(
          "📤 **Generar Tarjeta de Pick (Para Telegram / Comunidades)**"
      ):
        texto_tarjeta = f"""🎯 **MASTER SUITE ANALÍTICA ÉLITE — PICK OFICIAL** ⚽
🏟️ **Encuentro:** {visita_f} @ {local_f}
📊 **Mercado Seleccionado:** {mejor_mercado}
📈 **Momio Casino:** {mejor_momio} | **Prob. Modelo:** {mejor_prob:.1f}%
🔥 **Edge Neto (+EV):** +{mejor_edge:.2f}%
💰 **Stake Sugerido (Kelly):** ${mejor_stake} MXN
📌 *Análisis respaldado por Dixon-Coles Pro, Time-Decay EMA y xGOT.*"""
        st.text_area(
            "Copia el texto de abajo:",
            value=texto_tarjeta,
            height=150,
            key=f"tarjeta_{idx}",
        )

        if st.button(
            "📥 Guardar Apuesta en Base de Datos", key=f"btn_db_{idx}"
        ):
          registrar_apuesta_db(
              fecha_formato_str,
              "Fútbol",
              f"{visita_f} @ {local_f}",
              mejor_mercado,
              mejor_momio,
              mejor_edge,
              mejor_stake,
          )
          st.success("✅ ¡Apuesta guardada exitosamente en el historial SQLite!")
    else:
      st.info(
          f"⚖️ **Sello del Modelo:** Mejor proyección en **{mejor_mercado}**"
          f" (`+{mejor_edge:.2f}%`)."
      )

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
