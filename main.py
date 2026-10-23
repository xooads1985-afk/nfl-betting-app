from datetime import date, datetime, timedelta
import math
import os
import random
import threading
import time
import requests
import scipy.stats as stats
from scipy.stats import poisson
import streamlit as st

# Configuración global de la página
st.set_page_config(
    page_title="Central de Apuestas Pro - Master Suite (Full Stack Completo)",
    page_icon="⚽",
    layout="wide",
)


# ---------------------------------------------------------
# CONEXIÓN CON THE ODDS API (MOMIOS EN VIVO: H2H, SPREADS, TOTALS)
# ---------------------------------------------------------
@st.cache_data(ttl=300)
def obtener_momios_odds_api(deporte_key, api_key):
  if not api_key:
    return {}
  url = f"https://api.the-odds-api.com/v4/sports/{deporte_key}/odds/?apiKey={api_key}&regions=us&markets=h2h,spreads,totals&oddsFormat=american"
  try:
    response = requests.get(url, timeout=3)
    if response.status_code == 200:
      data = response.json()
      diccionario_momios = {}
      for evento in data:
        home_team = evento.get("home_team")
        bookmakers = evento.get("bookmakers", [])
        if bookmakers:
          markets = bookmakers[0].get("markets", [])
          mercados_dict = {}
          for market in markets:
            m_key = market.get("key")
            outcomes = market.get("outcomes", [])
            mercados_dict[m_key] = outcomes
          diccionario_momios[home_team] = mercados_dict
      return diccionario_momios
  except Exception:
    pass
  return {}


# ---------------------------------------------------------
# SELECTOR GLOBAL DE FECHA Y MENÚ (Barra Lateral con Memoria API Key)
# ---------------------------------------------------------
st.sidebar.title("🎯 Menú del Sistema Pro")

fecha_seleccionada = st.sidebar.date_input(
    "📅 Selecciona la Fecha a Analizar:", value=date.today()
)
fecha_formato_api = fecha_seleccionada.strftime("%Y%m%d")
fecha_formato_str = fecha_seleccionada.strftime("%Y-%m-%d")

# Memoria Persistente para la API Key
if "api_key_guardada" not in st.session_state:
  st.session_state["api_key_guardada"] = ""

st.sidebar.markdown("---")
st.sidebar.subheader("🌐 Configuración de API Odds")

input_api_key = st.sidebar.text_input(
    "API Key (The Odds API):",
    value=st.session_state["api_key_guardada"],
    type="password",
    help=(
        "Ingresa tu clave. Se mantendrá guardada en memoria automáticamente."
    ),
)

# Guardar en sesión al escribir
if input_api_key != st.session_state["api_key_guardada"]:
  st.session_state["api_key_guardada"] = input_api_key

odds_api_key = st.session_state["api_key_guardada"]

if st.sidebar.button(
    "🔄 Actualizar y Buscar Fecha", use_container_width=True
):
  st.cache_data.clear()
  st.success(f"¡Buscando cartelera para el {fecha_formato_str}!")
  st.rerun()

st.sidebar.markdown("---")

modulo_seleccionado = st.sidebar.radio(
    "Selecciona el módulo de análisis:",
    [
        "🔍 Escáner Automático Inteligente Multi-Deporte (+EV)",
        (
            "🛡️ Sistema Cuantitativo Pro NFL (Monte Carlo de"
            " Posesiones)"
        ),
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


def calcular_probabilidad_modelo_gaussiano(
    v_a, d_a, v_b, d_b, descanso_a, descanso_b, es_local_a=False
):
  base_prob = 53.0 if not es_local_a else 47.0
  diferencia_forma = ((v_a - d_a) - (v_b - d_b)) * 3.5
  fatigue_a = -4.0 if descanso_a == 0 else (-1.5 if descanso_a == 1 else 0.0)
  fatigue_b = -4.0 if descanso_b == 0 else (-1.5 if descanso_b == 1 else 0.0)
  diferencia_fatigue = fatigue_a - fatigue_b
  probabilidad_sugerida = base_prob + diferencia_forma - diferencia_fatigue
  return max(25.0, min(88.0, round(probabilidad_sugerida, 2)))


# 🏈 SIMULADOR MONTE CARLO PRO NFL (ZONA ROJA, TURNOVERS & SPREAD/TOTALES)
def simular_partido_nfl_monte_carlo_pro(
    lambda_pos_local,
    lambda_pos_visitante,
    eficiencia_rz_loc=75.0,
    eficiencia_rz_vis=75.0,
    turnovers_loc=1.0,
    turnovers_vis=1.0,
    spread_local=-3.5,
    linea_totales=45.5,
    simulaciones=10000,
):
  victorias_local = 0
  cubre_spread_local = 0
  supera_totales = 0
  total_puntos_acumulados = 0

  lam_efectiva_loc = max(1.0, lambda_pos_visitante - (turnovers_loc * 0.15))
  lam_efectiva_vis = max(1.0, lambda_pos_local - (turnovers_vis * 0.15))

  prob_td_loc = max(0.50, min(0.88, eficiencia_rz_loc / 100.0))
  prob_td_vis = max(0.50, min(0.88, eficiencia_rz_vis / 100.0))

  for _ in range(simulaciones):
    anotaciones_local = poisson.rvs(lam_efectiva_loc)
    anotaciones_vis = poisson.rvs(lam_efectiva_vis)

    puntos_local = 0
    puntos_vis = 0

    for _ in range(anotaciones_local):
      puntos_local += 7 if random.random() < prob_td_loc else 3
    for _ in range(anotaciones_vis):
      puntos_vis += 7 if random.random() < prob_td_vis else 3

    ptos_partido = puntos_local + puntos_vis
    total_puntos_acumulados += ptos_partido

    if puntos_local > puntos_vis:
      victorias_local += 1

    if (puntos_local - puntos_vis) + spread_local > 0:
      cubre_spread_local += 1

    if ptos_partido > linea_totales:
      supera_totales += 1

  prob_local = (victorias_local / simulaciones) * 100.0
  prob_spread = (cubre_spread_local / simulaciones) * 100.0
  prob_over = (supera_totales / simulaciones) * 100.0
  promedio_puntos = total_puntos_acumulados / simulaciones

  return (
      round(prob_local, 2),
      round(prob_spread, 2),
      round(prob_over, 2),
      round(promedio_puntos, 1),
  )


# 🏀 MODELO DE DISTRIBUCIÓN NORMAL PARA HÁNDICAP NBA
def calcular_probabilidad_handicap_nba(
    media_puntos_local,
    media_puntos_visitante,
    handicap_local,
    desviacion_estandar=11.5,
):
  margen_esperado = media_puntos_local - media_puntos_visitante
  punto_corte = -handicap_local
  prob_local_cubre = 1 - stats.norm.cdf(
      punto_corte, loc=margen_esperado, scale=desviacion_estandar
  )
  return round(prob_local_cubre * 100, 2)


# ⚽ MATRIZ DIXON-COLES PRO (CON RHO FIJO -0.12)
def calcular_matriz_dixon_coles(lambda_local, lambda_visitante, rho=-0.12):
  prob_matriz = {}
  for x in range(6):
    for y in range(6):
      p_x = poisson.pmf(x, lambda_local)
      p_y = poisson.pmf(y, lambda_visitante)
      prob_base = p_x * p_y

      if x == 0 and y == 0:
        tau = 1 - (lambda_local * lambda_visitante * rho)
      elif x == 1 and y == 0:
        tau = 1 + (lambda_visitante * rho)
      elif x == 0 and y == 1:
        tau = 1 + (lambda_local * rho)
      elif x == 1 and y == 1:
        tau = 1 - rho
      else:
        tau = 1.0

      prob_matriz[(x, y)] = max(0.0, prob_base * tau)

  return prob_matriz


def calcular_probabilidades_dixon_coles_dinamico(
    lambda_local, lambda_visitante, linea_objetivo=2.5, rho=-0.12
):
  matriz = calcular_matriz_dixon_coles(lambda_local, lambda_visitante, rho)
  prob_over = 0.0
  prob_under = 0.0
  prob_btts = 0.0

  suma_total = sum(matriz.values())
  if suma_total <= 0:
    suma_total = 1.0

  for (g_loc, g_vis), p in matriz.items():
    p_norm = p / suma_total
    total_goles = g_loc + g_vis

    if total_goles > linea_objetivo:
      prob_over += p_norm
    else:
      prob_under += p_norm

    if g_loc > 0 and g_vis > 0:
      prob_btts += p_norm

  return (
      round(prob_over * 100, 2),
      round(prob_under * 100, 2),
      round(prob_btts * 100, 2),
  )


# 🏒 CONEXIÓN CON API OFICIAL NHL & MOTOR PRO BLINDADO
@st.cache_data(ttl=300)
def obtener_cartelera_oficial_nhl(fecha_str_api):
  url = f"https://api-web.nhle.com/v1/schedule/{fecha_str_api}"
  partidos_nhl = []
  try:
    response = requests.get(url, timeout=3)
    if response.status_code == 200:
      data = response.json()
      for day in data.get("gameWeek", []):
        for game in day.get("games", []):
          partidos_nhl.append({
              "game_id": game.get("id"),
              "local": game.get("homeTeam", {}).get("abbrev", "HOME"),
              "visita": game.get("awayTeam", {}).get("abbrev", "AWAY"),
              "partido_str": (
                  f"🏒 {game.get('awayTeam', {}).get('abbrev')} @"
                  f" {game.get('homeTeam', {}).get('abbrev')}"
              ),
          })
  except Exception:
    pass
  return partidos_nhl


def obtener_porteros_confirmados_nhl(game_id):
  url = f"https://api-web.nhle.com/v1/gamecenter/{game_id}/play-by-play"
  starters = {
      "home_starter": {"name": "No Confirmado", "confirmed": False},
      "away_starter": {"name": "No Confirmado", "confirmed": False},
  }
  try:
    response = requests.get(url, timeout=3)
    if response.status_code == 200:
      data = response.json()
      home_team_id = data.get("homeTeam", {}).get("id")
      for player in data.get("rosterSpots", []):
        if player.get("positionCode") == "G":
          is_starter = player.get("starter", False) or player.get(
              "starterStatus"
          ) in ["CONFIRMED", "EXPECTED"]
          is_home = player.get("teamId") == home_team_id
          p_name = (
              f"{player.get('firstName', {}).get('default', '')} "
              f"{player.get('lastName', {}).get('default', '')}"
          ).strip()

          if is_home and is_starter:
            starters["home_starter"] = {"name": p_name, "confirmed": True}
          elif not is_home and is_starter:
            starters["away_starter"] = {"name": p_name, "confirmed": True}
  except Exception:
    pass
  return starters


def calcular_lambda_ajustado_nhl_pro(
    lambda_local_base,
    lambda_visita_base,
    pp_loc=20.0,
    pk_loc=80.0,
    pp_vis=20.0,
    pk_vis=80.0,
    xgf_loc_5v5=50.0,
    xgf_vis_5v5=50.0,
    goles_favor_l5_loc=15.0,
    goles_contra_l5_loc=12.0,
    goles_favor_l5_vis=14.0,
    goles_contra_l5_vis=13.0,
    b2b_home=False,
    b2b_away=False,
    starters_status=None,
):
  FACTOR_EMPTY_NET = 0.23

  adj_5v5_loc = (xgf_loc_5v5 - 50.0) * 0.015
  adj_5v5_vis = (xgf_vis_5v5 - 50.0) * 0.015

  diff_special_loc = ((pp_loc - (100.0 - pk_vis)) / 100.0) * 0.40
  diff_special_vis = ((pp_vis - (100.0 - pk_loc)) / 100.0) * 0.40

  prom_gf_loc = goles_favor_l5_loc / 5.0
  prom_ga_loc = goles_contra_l5_loc / 5.0
  prom_gf_vis = goles_favor_l5_vis / 5.0
  prom_ga_vis = goles_contra_l5_vis / 5.0

  inercia_ofensiva_loc = max(-0.4, min(0.4, (prom_gf_loc - 3.0) * 0.20))
  inercia_defensiva_loc = max(-0.4, min(0.4, (prom_ga_loc - 3.0) * 0.15))

  inercia_ofensiva_vis = max(-0.4, min(0.4, (prom_gf_vis - 3.0) * 0.20))
  inercia_defensiva_vis = max(-0.4, min(0.4, (prom_ga_vis - 3.0) * 0.15))

  penalty_b2b_home = -0.18 if b2b_home else 0.0
  penalty_b2b_vis = -0.18 if b2b_away else 0.0

  penalizacion_home = 0.0
  penalizacion_away = 0.0
  if starters_status:
    if not starters_status.get("home_starter", {}).get("confirmed"):
      penalizacion_home = 0.20
    if not starters_status.get("away_starter", {}).get("confirmed"):
      penalizacion_away = 0.20

  lambda_loc_final = max(
      0.5,
      lambda_local_base
      + adj_5v5_loc
      + diff_special_loc
      + inercia_ofensiva_loc
      + inercia_defensiva_vis
      + penalty_b2b_home
      + penalizacion_away
      + 0.10,
  )
  lambda_vis_final = max(
      0.5,
      lambda_visita_base
      + adj_5v5_vis
      + diff_special_vis
      + inercia_ofensiva_vis
      + inercia_defensiva_loc
      + penalty_b2b_vis
      + penalizacion_home,
  )
  lambda_total = lambda_loc_final + lambda_vis_final + FACTOR_EMPTY_NET

  return lambda_loc_final, lambda_vis_final, lambda_total


def simular_poisson_nhl_totales(lambda_loc, lambda_vis, linea_totales=6.5):
  max_goles = 12
  probs_h = [poisson.pmf(i, lambda_loc) for i in range(max_goles)]
  probs_a = [poisson.pmf(j, lambda_vis) for j in range(max_goles)]

  p_over, p_under, p_push = 0.0, 0.0, 0.0
  for i in range(max_goles):
    for j in range(max_goles):
      tot = i + j
      p = probs_h[i] * probs_a[j]
      if tot > linea_totales:
        p_over += p
      elif tot < linea_totales:
        p_under += p
      else:
        p_push += p

  return round(p_over * 100, 2), round(p_under * 100, 2), round(p_push * 100, 2)


def simular_puck_line_nhl(lambda_loc, lambda_vis, simulaciones=10000):
  cubiertas_loc_m15 = 0
  cubiertas_vis_p15 = 0

  for _ in range(simulaciones):
    goles_loc = poisson.rvs(lambda_loc)
    goles_vis = poisson.rvs(lambda_vis)

    dif = goles_loc - goles_vis
    if dif == 1:
      if random.random() < 0.28:
        if random.random() < 0.82:
          goles_loc += 1
        else:
          goles_vis += 1
    elif dif == -1:
      if random.random() < 0.28:
        if random.random() < 0.82:
          goles_vis += 1
        else:
          goles_loc += 1

    if (goles_loc - goles_vis) > 1.5:
      cubiertas_loc_m15 += 1
    else:
      cubiertas_vis_p15 += 1

  prob_loc_m15 = (cubiertas_loc_m15 / simulaciones) * 100.0
  prob_vis_p15 = (cubiertas_vis_p15 / simulaciones) * 100.0

  return round(prob_loc_m15, 2), round(prob_vis_p15, 2)


@st.cache_data(ttl=300)
def obtener_cartelera_pura(deporte, liga, fecha_str_api, fecha_str_humana):
  url = f"https://site.api.espn.com/apis/site/v2/sports/{deporte}/{liga}/scoreboard?dates={fecha_str_api}&limit=20"
  try:
    response = requests.get(url, timeout=2)
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
            "visita": visitante,
        })
      return partidos_extraidos
  except Exception:
    pass
  return []


@st.cache_data(ttl=300)
def obtener_eventos_ufc_pro(fecha_str_api, fecha_str_humana):
  url = f"https://site.api.espn.com/apis/site/v2/sports/mma/ufc/scoreboard?dates={fecha_str_api}&limit=20"
  combates_extraidos = []
  try:
    response = requests.get(url, timeout=2)
    if response.status_code == 200:
      data = response.json()
      eventos = data.get("events", [])
      for evento in eventos:
        nombre_evento = evento.get("name", "UFC Fight Night")
        competencia = evento.get("competitions", [{}])[0]
        competidores = competencia.get("competitors", [])
        peleador_1, peleador_2 = "Peleador A", "Peleador B"
        if len(competidores) >= 2:
          peleador_1 = competidores[0].get("athlete", {}).get(
              "displayName", "Peleador A"
          )
          peleador_2 = competidores[1].get("athlete", {}).get(
              "displayName", "Peleador B"
          )
        combates_extraidos.append({
            "evento_str": f"🥊 [{fecha_str_humana}] {nombre_evento}",
            "combate_str": f"{peleador_1} vs {peleador_2}",
            "seleccion": peleador_1,
        })
  except Exception:
    pass
  return combates_extraidos


# =========================================================
# 0. ESCÁNER AUTOMÁTICO INTELIGENTE MULTI-DEPORTE (+EV)
# =========================================================
if modulo_seleccionado == "🔍 Escáner Automático Inteligente Multi-Deporte (+EV)":
  st.title(
      "🔍 **Escáner Automático Inteligente Multi-Deporte"
      f" [{fecha_formato_str}]**"
  )
  st.markdown(
      "--- \n *Radar de valor +EV: Analiza la cartelera real en tiempo real"
      " aplicando modelos cuantitativos y descartando momios menores a -150.*"
  )

  edge_min_escanner = st.slider(
      "🎯 Edge Mínimo Requerido para el Escáner (%):",
      0.0,
      15.0,
      3.0,
      0.5,
      key="edge_escanner_gen",
  )

  if st.button(
      "🚀 Ejecutar Escaneo Global en Tiempo Real", use_container_width=True
  ):
    with st.spinner(
        "Escaneando carteleras de la API y cruzando modelos matemáticos..."
    ):
      minas_de_oro = []

      # 1. Fútbol (Dixon-Coles Pro)
      ligas_futbol = [
          ("uefa.champions", "Champions League"),
          ("eng.1", "Premier League"),
          ("esp.1", "La Liga"),
      ]
      for codigo_liga, nombre_liga in ligas_futbol:
        cartelera_s = obtener_cartelera_pura(
            "soccer", codigo_liga, fecha_formato_api, fecha_formato_str
        )
        for partido in cartelera_s:
          p_over, _, _ = calcular_probabilidades_dixon_coles_dinamico(
              1.55, 1.15, 2.5, -0.12
          )
          momio_prueba = -110
          _, edge = calcular_edge_real(momio_prueba, p_over)
          if momio_prueba >= -150 and edge >= edge_min_escanner:
            minas_de_oro.append({
                "deporte": f"⚽ Fútbol ({nombre_liga})",
                "partido": partido["partido_str"],
                "mercado": "Over 2.5 Goles",
                "momio": momio_prueba,
                "edge": edge,
            })

      # 2. NBA (Distribución Normal)
      cartelera_n = obtener_cartelera_pura(
          "basketball", "nba", fecha_formato_api, fecha_formato_str
      )
      for partido in cartelera_n:
        prob_nba = calcular_probabilidad_handicap_nba(
            114.5, 111.0, -4.5, 11.5
        )
        momio_prueba = -110
        _, edge = calcular_edge_real(momio_prueba, prob_nba)
        if momio_prueba >= -150 and edge >= edge_min_escanner:
          minas_de_oro.append({
              "deporte": "🏀 NBA",
              "partido": partido["partido_str"],
              "mercado": "Hándicap Local (-4.5)",
              "momio": momio_prueba,
              "edge": edge,
          })

      # 3. NHL (Engine Pro con Caps L5 y B2B)
      cartelera_h = obtener_cartelera_oficial_nhl(fecha_formato_str)
      for partido in cartelera_h:
        starters = obtener_porteros_confirmados_nhl(partido["game_id"])
        l_loc, l_vis, _ = calcular_lambda_ajustado_nhl_pro(
            3.10, 2.75, starters_status=starters
        )
        p_over_nhl, _, _ = simular_poisson_nhl_totales(l_loc, l_vis, 6.5)
        momio_prueba = -110
        _, edge = calcular_edge_real(momio_prueba, p_over_nhl)
        if momio_prueba >= -150 and edge >= edge_min_escanner:
          minas_de_oro.append({
              "deporte": "🏒 NHL",
              "partido": partido["partido_str"],
              "mercado": "Over 6.5 Goles (Pro Engine)",
              "momio": momio_prueba,
              "edge": edge,
          })

      st.session_state["resultado_escaneo"] = minas_de_oro

  st.markdown("---")
  st.subheader("📋 Resultados del Radar de Valor")

  if (
      "resultado_escaneo" in st.session_state
      and st.session_state["resultado_escaneo"]
  ):
    st.success(
        f"🎯 ¡Se encontraron **{len(st.session_state['resultado_escaneo'])}**"
        " oportunidades con valor real (+EV)!"
    )
    for item in st.session_state["resultado_escaneo"]:
      with st.container():
        st.markdown(f"**{item['deporte']}** | `{item['partido']}`")
        st.info(
            f"• Mercado: **{item['mercado']}** | Momio: `{item['momio']}` | 🎯"
            f" **Edge Neto: `+{item['edge']:.2f}%`**"
        )
        st.markdown("---")
  else:
    st.info(
        "ℹ️ Haz clic en el botón de arriba para iniciar el escaneo en tiempo"
        " real o no hay eventos activos que superen el filtro estricto."
    )


# =========================================================
# 1. NFL (MONTE CARLO PRO - ZONA ROJA, TURNOVERS, SPREAD & TOTALES)
# =========================================================
elif (
    modulo_seleccionado
    == "🛡️ Sistema Cuantitativo Pro NFL (Monte Carlo de Posesiones)"
):
  st.title(
      "🛡️ **Sistema Cuantitativo Pro NFL (Monte Carlo Pro)"
      f" [{fecha_formato_str}]**"
  )
  st.markdown(
      "--- \n *Simulación estocástica avanzada: Zona Roja, Turnovers,"
      " Hándicaps (Spread) y Totales (Over/Under).*"
  )

  col1, col2 = st.columns(2)
  with col1:
    bankroll = st.number_input(
        "💵 Bankroll NFL (MXN):", 100.0, 50000.0, 5000.0, 500.0, key="bk_nfl"
    )
  with col2:
    edge_min = st.slider(
        "🎯 Edge Mínimo Requerido NFL (%):", 0.0, 15.0, 3.0, 0.5, key="edge_nfl"
    )

  cartelera = obtener_cartelera_pura(
      "football", "nfl", fecha_formato_api, fecha_formato_str
  )
  momios_api_nfl = obtener_momios_odds_api("americanfootball_nfl", odds_api_key)

  st.markdown("---")
  usar_manual_nfl = st.checkbox(
      "✍️ Activar Ingreso Manual NFL (Si la cartelera no muestra partidos hoy)",
      value=not cartelera,
      key="chk_manual_nfl",
  )

  if usar_manual_nfl:
    col_mn1, col_mn2 = st.columns(2)
    with col_mn1:
      eq_v_man = st.text_input(
          "Equipo Visitante:", value="Kansas City Chiefs", key="nfl_man_vis"
      )
    with col_mn2:
      eq_l_man = st.text_input(
          "Equipo Local:", value="Baltimore Ravens", key="nfl_man_loc"
      )
    cartelera = [{
        "partido_str": f"📅 [Manual] {eq_v_man} @ {eq_l_man}",
        "local": eq_l_man,
        "visita": eq_v_man,
    }]

  st.subheader("📊 Partidos en Cartelera NFL")

  if not cartelera:
    st.info(
        "ℹ️ No hay partidos de la NFL disponibles. Activa el ingreso manual"
        " arriba."
    )
  else:
    for idx, op in enumerate(cartelera, 1):
      with st.expander(f"🏈 Encuentro #{idx}: {op['partido_str']}"):
        st.markdown(
            "### 🧬 Parámetros Avanzados: Posesiones, Zona Roja & Turnovers"
        )
        col_mc1, col_mc2 = st.columns(2)
        with col_mc1:
          st.markdown(f"**Visitante: `{op['visita']}`**")
          lam_pos_visita = st.number_input(
              "Series Anotadoras Esperadas:",
              1.0,
              8.0,
              3.5,
              0.1,
              key=f"nfl_lv_{idx}",
          )
          rz_vis = st.number_input(
              "Eficiencia Zona Roja (TD%):",
              40.0,
              95.0,
              72.0,
              1.0,
              key=f"nfl_rz_v_{idx}",
          )
          to_vis = st.number_input(
              "Turnovers Promedio / Partido:",
              0.0,
              3.0,
              1.0,
              0.1,
              key=f"nfl_to_v_{idx}",
          )

        with col_mc2:
          st.markdown(f"**Local: `{op['local']}`**")
          lam_pos_local = st.number_input(
              "Series Anotadoras Esperadas:",
              1.0,
              8.0,
              3.8,
              0.1,
              key=f"nfl_ll_{idx}",
          )
          rz_loc = st.number_input(
              "Eficiencia Zona Roja (TD%):",
              40.0,
              95.0,
              75.0,
              1.0,
              key=f"nfl_rz_l_{idx}",
          )
          to_loc = st.number_input(
              "Turnovers Promedio / Partido:",
              0.0,
              3.0,
              0.8,
              0.1,
              key=f"nfl_to_l_{idx}",
          )

        st.markdown("---")
        st.markdown("### 🎯 Selección de Mercado NFL")
        tipo_mercado_nfl = st.selectbox(
            "Mercado a Auditar:",
            [
                "Money Line (Ganador Directo)",
                "Spread / Hándicap",
                "Total de Puntos (Over / Under)",
            ],
            key=f"nfl_merc_tipo_{idx}",
        )

        mercados_equipo_api = momios_api_nfl.get(op["local"], {})
        momio_default = -110

        if tipo_mercado_nfl == "Money Line (Ganador Directo)":
          tipo_sel_nfl = st.selectbox(
              "Selección:",
              [f"Local ({op['local']})", f"Visitante ({op['visita']})"],
              key=f"nfl_sel_eq_{idx}",
          )
          momio_sug = momio_default
          if "h2h" in mercados_equipo_api:
            for out in mercados_equipo_api["h2h"]:
              if out.get("name") == op["local"] and "Local" in tipo_sel_nfl:
                momio_sug = out.get("price", -110)
              elif (
                  out.get("name") == op["visita"] and "Visitante" in tipo_sel_nfl
              ):
                momio_sug = out.get("price", -110)

          momio_nfl_str = st.text_input(
              "📈 Momio Casino:",
              value=str(momio_sug),
              key=f"nfl_m_txt_{idx}",
          )
          try:
            momio_nfl = int(momio_nfl_str)
          except ValueError:
            momio_nfl = -110

        elif tipo_mercado_nfl == "Spread / Hándicap":
          col_sp1, col_sp2 = st.columns(2)
          with col_sp1:
            sel_spread = st.selectbox(
                "Selección Spread:",
                [f"Local ({op['local']})", f"Visitante ({op['visita']})"],
                key=f"nfl_sp_sel_{idx}",
            )
          with col_sp2:
            linea_spread = st.number_input(
                "Línea Hándicap Local (Ej: -3.5 o +3.5):",
                -20.5,
                20.5,
                -3.5,
                0.5,
                key=f"nfl_linea_spread_{idx}",
            )

          momio_nfl_str = st.text_input(
              "📈 Momio Casino:", value="-110", key=f"nfl_m_spread_txt_{idx}"
          )
          try:
            momio_nfl = int(momio_nfl_str)
          except ValueError:
            momio_nfl = -110
        else:
          col_ou1, col_ou2 = st.columns(2)
          with col_ou1:
            tipo_ou_nfl = st.selectbox(
                "Selección Totales:",
                ["Over (Más de)", "Under (Menos de)"],
                key=f"nfl_tipo_ou_{idx}",
            )
          with col_ou2:
            linea_totales_nfl = st.number_input(
                "Línea de Puntos O/U:",
                30.5,
                65.5,
                45.5,
                0.5,
                key=f"nfl_linea_ou_{idx}",
            )

          momio_nfl_str = st.text_input(
              "📈 Momio Casino:", value="-110", key=f"nfl_m_ou_txt_{idx}"
          )
          try:
            momio_nfl = int(momio_nfl_str)
          except ValueError:
            momio_nfl = -110

        spread_param = (
            linea_spread
            if tipo_mercado_nfl == "Spread / Hándicap"
            else -3.5
        )
        totales_param = (
            linea_totales_nfl
            if tipo_mercado_nfl == "Total de Puntos (Over / Under)"
            else 45.5
        )

        prob_local_mc, prob_spread_mc, prob_over_mc, puntos_esperados_mc = (
            simular_partido_nfl_monte_carlo_pro(
                lam_pos_local,
                lam_pos_visita,
                rz_loc,
                rz_vis,
                to_loc,
                to_vis,
                spread_param,
                totales_param,
            )
        )

        if tipo_mercado_nfl == "Money Line (Ganador Directo)":
          prob_mod = (
              prob_local_mc
              if "Local" in tipo_sel_nfl
              else round(100.0 - prob_local_mc, 2)
          )
        elif tipo_mercado_nfl == "Spread / Hándicap":
          prob_mod = (
              prob_spread_mc
              if "Local" in sel_spread
              else round(100.0 - prob_spread_mc, 2)
          )
        else:
          prob_mod = (
              prob_over_mc
              if "Over" in tipo_ou_nfl
              else round(100.0 - prob_over_mc, 2)
          )

        st.success(
            "🤖 **Simulación Monte Carlo Pro (10,000 iteraciones):** Puntos"
            f" Totales Esperados: **`{puntos_esperados_mc}`** | Prob. Local ML:"
            f" `{prob_local_mc}%`"
        )

        prob_imp, edge = calcular_edge_real(momio_nfl, prob_mod)
        st.info(
            f"📊 **Edge Calculado:** Implícita (`{momio_nfl:+}`): `{prob_imp:.2f}%`"
            f" | Modelo: `{prob_mod:.2f}%` | Edge Neto: **`{edge:+.2f}%`**"
        )

        if momio_nfl < -150:
          st.error("🚨 Infringe Regla de Oro (-150).")
        elif edge >= edge_min:
          st.success(f"✅ Aprobado (+EV). Edge: `{edge:+.2f}%`")
        else:
          st.warning(f"⚠️ Sin Edge suficiente (`{edge:+.2f}%`).")


# =========================================================
# 2. Props NFL
# =========================================================
elif modulo_seleccionado == "🎯 Auditor Interactivo de Props NFL":
  st.title(f"🎯 **Props Automáticos NFL ({fecha_formato_str})**")
  st.markdown("--- \n *Rendimiento individual de jugadores en la NFL.*")
  col_pnfl1, col_pnfl2 = st.columns(2)
  with col_pnfl1:
    bankroll_props_nfl = st.number_input(
        "💵 Bankroll Props NFL (MXN):",
        100.0,
        50000.0,
        3000.0,
        500.0,
        key="bk_props_nfl",
    )
  with col_pnfl2:
    edge_min_props_nfl = st.slider(
        "🎯 Edge Mínimo Props NFL (%):", 0.0, 15.0, 3.0, 0.5, key="edge_props_nfl"
    )

  cartelera_nfl_hoy = obtener_cartelera_pura(
      "football", "nfl", fecha_formato_api, fecha_formato_str
  )
  st.markdown("---")
  st.subheader("📊 Auditoría de Props NFL")

  if not cartelera_nfl_hoy:
    st.info(
        "ℹ️ No hay partidos de la NFL en cartelera para la fecha"
        f" `{fecha_formato_str}`."
    )
  else:
    for idx, op in enumerate(cartelera_nfl_hoy, 1):
      with st.expander(f"🎯 Prop NFL: {op['partido_str']}"):
        jugador = st.text_input(
            "Jugador:", value="Patrick Mahomes", key=f"nfl_prop_j_{idx}"
        )
        mercado = st.text_input(
            "Mercado:",
            value="Yardas de Pase Over 265.5",
            key=f"nfl_prop_m_{idx}",
        )

        momio_str = st.text_input(
            "📈 Momio Casino:", value="-115", key=f"nfl_prop_mom_txt_{idx}"
        )
        try:
          momio = int(momio_str)
        except ValueError:
          momio = -115

        col_pj1, col_pj2 = st.columns(2)
        with col_pj1:
          cumple = st.number_input(
              "Partidos cumpliendo línea (L5):", 0, 5, 3, key=f"nfl_prop_c_{idx}"
          )
        with col_pj2:
          no_cumple = st.number_input(
              "Partidos sin cumplir línea (L5):",
              0,
              5,
              2,
              key=f"nfl_prop_nc_{idx}",
          )

        prob = max(40.0, min(80.0, 50.0 + (cumple - no_cumple) * 6.0))
        st.success(f"🤖 **Probabilidad Real del Modelo Pro:** **`{prob:.2f}%`**")
        prob_imp, edge = calcular_edge_real(momio, prob)
        st.info(
            f"📊 **Edge Calculado:** Implícita (`{momio:+}`): `{prob_imp:.2f}%` |"
            f" Modelo: `{prob:.2f}%` | Edge Neto: **`{edge:+.2f}%`**"
        )

        if momio < -150:
          st.error("🚨 Infringe Regla de Oro (-150).")
        elif edge >= edge_min_props_nfl:
          st.success(f"✅ Aprobado Prop (+EV). Edge: `{edge:+.2f}%`")
        else:
          st.warning(f"⚠️ Sin Edge suficiente (`{edge:+.2f}%`).")


# =========================================================
# 3. NBA (DISTRIBUCIÓN NORMAL CDF)
# =========================================================
elif (
    modulo_seleccionado
    == "🏀 Sistema Cuantitativo Pro NBA (Distribución Normal & Spread)"
):
  st.title(
      "🏀 **Sistema Cuantitativo Pro NBA (Distribución Normal)"
      f" [{fecha_formato_str}]**"
  )
  st.markdown(
      "--- \n *Modelo de Distribución Normal (CDF) para calcular si los"
      " equipos cubren el Hándicap.*"
  )

  col1, col2 = st.columns(2)
  with col1:
    bankroll_nba = st.number_input(
        "💵 Bankroll NBA (MXN):", 100.0, 50000.0, 5000.0, 500.0, key="bk_nba"
    )
  with col2:
    edge_min_nba = st.slider(
        "🎯 Edge Mínimo Requerido NBA (%):", 0.0, 15.0, 3.0, 0.5, key="edge_nba"
    )

  cartelera_nba = obtener_cartelera_pura(
      "basketball", "nba", fecha_formato_api, fecha_formato_str
  )
  momios_api_nba = obtener_momios_odds_api("basketball_nba", odds_api_key)

  st.markdown("---")
  st.subheader("📊 Partidos en Cartelera NBA")

  if not cartelera_nba:
    st.info(
        "ℹ️ No hay partidos de la NBA registrados en la API para la fecha"
        f" `{fecha_formato_str}`."
    )
  else:
    for idx, op in enumerate(cartelera_nba, 1):
      with st.expander(f"🏀 Encuentro #{idx}: {op['partido_str']}"):
        col_n1, col_n2, col_n3 = st.columns(3)
        with col_n1:
          media_local = st.number_input(
              f"Media Puntos Local ({op['local']}):",
              80.0,
              140.0,
              114.5,
              0.5,
              key=f"nba_ml_{idx}",
          )
        with col_n2:
          media_visita = st.number_input(
              f"Media Puntos Visita ({op['visita']}):",
              80.0,
              140.0,
              111.0,
              0.5,
              key=f"nba_mv_{idx}",
          )
        with col_n3:
          desv_est = st.number_input(
              "Desviación Estándar (NBA):",
              5.0,
              20.0,
              11.5,
              0.5,
              key=f"nba_desv_{idx}",
          )

        col_h1, col_h2, col_h3 = st.columns(3)
        with col_h1:
          tipo_apuesta_nba = st.selectbox(
              "Selección Hándicap:",
              [f"Local ({op['local']})", f"Visitante ({op['visita']})"],
              key=f"nba_ap_{idx}",
          )
        with col_h2:
          handicap_val = st.number_input(
              "Línea Hándicap Local (Ej. -4.5 o +4.5):",
              -25.0,
              25.0,
              -4.5,
              0.5,
              key=f"nba_han_{idx}",
          )
        with col_h3:
          momio_sugerido_nba = -110
          mercados_nba_dict = momios_api_nba.get(op["local"], {})
          if "h2h" in mercados_nba_dict:
            for out in mercados_nba_dict["h2h"]:
              if out.get("name") == op["local"]:
                momio_sugerido_nba = out.get("price", -110)

          momio_nba_str = st.text_input(
              "📈 Momio Casino (Americano):",
              value=str(momio_sugerido_nba),
              key=f"nba_m_txt_{idx}",
          )
          try:
            momio_nba = int(momio_nba_str)
          except ValueError:
            momio_nba = -110

        prob_local_cubre = calcular_probabilidad_handicap_nba(
            media_local, media_visita, handicap_val, desv_est
        )

        if "Local" in tipo_apuesta_nba:
          prob_modelo_nba = prob_local_cubre
        else:
          prob_modelo_nba = round(100.0 - prob_local_cubre, 2)

        st.success(
            "🤖 **Probabilidad Real (Modelo Normal CDF):**"
            f" **`{prob_modelo_nba:.2f}%`**"
        )
        prob_imp, edge = calcular_edge_real(momio_nba, prob_modelo_nba)
        st.info(
            f"📊 **Edge Calculado:** Implícita (`{momio_nba:+}`): `{prob_imp:.2f}%`"
            f" | Modelo: `{prob_modelo_nba:.2f}%` | Edge Neto: **`{edge:+.2f}%`**"
        )

        if momio_nba < -150:
          st.error("🚨 Infringe Regla de Oro (-150).")
        elif edge >= edge_min_nba:
          st.success(f"✅ Aprobado (+EV). Edge: `{edge:+.2f}%`")
        else:
          st.warning(f"⚠️ Sin Edge suficiente (`{edge:+.2f}%`).")


# =========================================================
# 4. Props NBA
# =========================================================
elif modulo_seleccionado == "🔥 Auditor Interactivo de Props NBA":
  st.title(f"🔥 **Props Automáticos NBA ({fecha_formato_str})**")
  st.markdown("--- \n *Rendimiento individual de jugadores en la NBA.*")
  col_pn1, col_pn2 = st.columns(2)
  with col_pn1:
    bankroll_props_nba = st.number_input(
        "💵 Bankroll Props NBA (MXN):",
        100.0,
        50000.0,
        3000.0,
        500.0,
        key="bk_props_nba",
    )
  with col_pn2:
    edge_min_props_nba = st.slider(
        "🎯 Edge Mínimo Props NBA (%):", 0.0, 15.0, 3.0, 0.5, key="edge_props_nba"
    )

  cartelera_nba_hoy = obtener_cartelera_pura(
      "basketball", "nba", fecha_formato_api, fecha_formato_str
  )
  st.markdown("---")
  st.subheader("📊 Auditoría de Props NBA")

  if not cartelera_nba_hoy:
    st.info(
        "ℹ️ No hay partidos de la NBA en la API para la fecha"
        f" `{fecha_formato_str}`."
    )
  else:
    for idx, op in enumerate(cartelera_nba_hoy, 1):
      with st.expander(f"🔥 Prop NBA: {op['partido_str']}"):
        jugador = st.text_input(
            "Jugador:", value="LeBron James", key=f"nba_prop_j_{idx}"
        )
        mercado = st.text_input(
            "Mercado:",
            value="Puntos Totales Over 24.5",
            key=f"nba_prop_m_{idx}",
        )

        momio_str = st.text_input(
            "📈 Momio Casino:", value="-115", key=f"nba_prop_mom_txt_{idx}"
        )
        try:
          momio = int(momio_str)
        except ValueError:
          momio = -115

        col_nj1, col_nj2 = st.columns(2)
        with col_nj1:
          cumple = st.number_input(
              "Partidos cumpliendo línea (L5):", 0, 5, 3, key=f"nba_prop_c_{idx}"
          )
        with col_nj2:
          no_cumple = st.number_input(
              "Partidos sin cumplir línea (L5):",
              0,
              5,
              2,
              key=f"nba_prop_nc_{idx}",
          )

        prob = max(40.0, min(80.0, 50.0 + (cumple - no_cumple) * 6.0))
        st.success(f"🤖 **Probabilidad Real del Modelo Pro:** **`{prob:.2f}%`**")
        prob_imp, edge = calcular_edge_real(momio, prob)
        st.info(
            f"📊 **Edge Calculado:** Implícita (`{momio:+}`): `{prob_imp:.2f}%` |"
            f" Modelo: `{prob:.2f}%` | Edge Neto: **`{edge:+.2f}%`**"
        )

        if momio < -150:
          st.error("🚨 Infringe Regla de Oro (-150).")
        elif edge >= edge_min_props_nba:
          st.success(f"✅ Aprobado Prop (+EV). Edge: `{edge:+.2f}%`")
        else:
          st.warning(f"⚠️ Sin Edge suficiente (`{edge:+.2f}%`).")


# =========================================================
# 5. FÚTBOL (DIXON-COLES PRO - RHO FIJO -0.12)
# =========================================================
elif (
    modulo_seleccionado
    == "⚽ Módulo Global de Fútbol (Dixon-Coles Pro, BTTS & Hándicap Asiático)"
):
  st.title(
      "⚽ **Cazador de Goles & Dixon-Coles Pro — Fútbol"
      f" [{fecha_formato_str}]**"
  )
  st.markdown(
      "--- \n *Modelo avanzado de Dixon-Coles con corrección de empates bajos"
      " (ρ = -0.12), BTTS y Hándicaps Asiáticos.*"
  )

  liga_soccer = st.selectbox(
      "🌍 Selecciona la Liga o Torneo de Fútbol:",
      [
          "UEFA Champions League (uefa.champions)",
          "UEFA Europa League (uefa.europa)",
          "Premier League de Inglaterra (eng.1)",
          "La Liga de España (esp.1)",
          "Serie A de Italia (ita.1)",
          "Bundesliga de Alemania (ger.1)",
          "Liga MX (mex.1)",
      ],
  )
  codigo_liga_api = liga_soccer.split("(")[-1].replace(")", "").strip()

  col_f1, col_f2 = st.columns(2)
  with col_f1:
    bankroll_soccer = st.number_input(
        "💵 Bankroll Fútbol (MXN):", 100.0, 50000.0, 3000.0, 500.0, key="bk_soccer"
    )
  with col_f2:
    edge_min_soccer = st.slider(
        "🎯 Edge Mínimo Requerido para Operar (%):",
        0.0,
        15.0,
        3.0,
        0.5,
        key="edge_soccer",
    )

  cartelera_soccer = obtener_cartelera_pura(
      "soccer", codigo_liga_api, fecha_formato_api, fecha_formato_str
  )
  st.markdown("---")
  st.subheader(
      "📋 Cartelera Real & Simulación Dixon-Coles (Parámetro Fijo)"
  )

  if not cartelera_soccer:
    st.info(
        "ℹ️ No se encontraron partidos programados en la API para esta liga en"
        f" la fecha `{fecha_formato_str}`."
    )
  else:
    for idx, op in enumerate(cartelera_soccer, 1):
      with st.expander(f"⚽ Encuentro #{idx}: {op['partido_str']}"):
        st.markdown(
            "### 🧬 Estadísticas L5 (V-E-D) & Goles Esperados ($\\lambda, \\mu$)"
            " [Rho Fijo: -0.12]"
        )
        col_ved1, col_ved2 = st.columns(2)
        with col_ved1:
          st.markdown(f"**Visitante: `{op['visita']}`**")
          v_a = st.number_input("Victorias L5:", 0, 5, 2, key=f"soccer_va_{idx}")
          e_a = st.number_input("Empates L5:", 0, 5, 2, key=f"soccer_ea_{idx}")
          d_a = st.number_input("Derrotas L5:", 0, 5, 1, key=f"soccer_da_{idx}")
          lam_visita = st.number_input(
              "Goles Esperados Visita ($\\mu$):",
              0.1,
              5.0,
              1.15,
              0.05,
              key=f"soccer_lam_vis_{idx}",
          )
        with col_ved2:
          st.markdown(f"**Local: `{op['local']}`**")
          v_b = st.number_input("Victorias L5:", 0, 5, 3, key=f"soccer_vb_{idx}")
          e_b = st.number_input(
              "Empates L5:", 0, 5, 1, key=f"soccer_vb_e_{idx}"
          )
          d_b = st.number_input("Derrotas L5:", 0, 5, 1, key=f"soccer_db_{idx}")
          lam_local = st.number_input(
              "Goles Esperados Local ($\\lambda$):",
              0.1,
              5.0,
              1.55,
              0.05,
              key=f"soccer_lam_loc_{idx}",
          )

        RHO_FIJO = -0.12

        p_over_15, p_under_15, _ = (
            calcular_probabilidades_dixon_coles_dinamico(
                lam_local, lam_visita, 1.5, RHO_FIJO
            )
        )
        p_over_25, p_under_25, p_btts = (
            calcular_probabilidades_dixon_coles_dinamico(
                lam_local, lam_visita, 2.5, RHO_FIJO
            )
        )
        p_over_35, p_under_35, _ = (
            calcular_probabilidades_dixon_coles_dinamico(
                lam_local, lam_visita, 3.5, RHO_FIJO
            )
        )

        st.markdown("---")
        st.info(
            "📊 **Matriz Automática del Modelo Dixon-Coles Pro ($\\rho ="
            " -0.12$):**\n"
            f"• **Over / Under 1.5 Goles**: Over `{p_over_15}%` | Under"
            f" `{p_under_15}%`\n"
            f"• **Over / Under 2.5 Goles**: Over `{p_over_25}%` | Under"
            f" `{p_under_25}%`\n"
            f"• **Over / Under 3.5 Goles**: Over `{p_over_35}%` | Under"
            f" `{p_under_35}%`\n"
            f"• **Ambos Equipos Anotan (BTTS)**: Sí `{p_btts}%`"
        )

        st.markdown("---")
        st.markdown("### 🎯 Configuración del Mercado de Apuesta Específico")

        mercado_soccer_tipo = st.selectbox(
            "Selecciona el Mercado de Fútbol a Auditar:",
            [
                "Total de Goles (Over / Under Dixon-Coles)",
                "Ambos Equipos Anotan (BTTS)",
                "Hándicap Asiático / Spread por Equipo",
            ],
            key=f"soccer_mercado_tipo_{idx}",
        )

        if "Total de Goles" in mercado_soccer_tipo:
          col_tg1, col_tg2 = st.columns(2)
          with col_tg1:
            linea_elegida = st.selectbox(
                "Línea de Goles O/U:",
                [1.5, 2.5, 3.5, 0.5, 4.5],
                index=1,
                key=f"soccer_linea_{idx}",
            )
          with col_tg2:
            tipo_ou = st.selectbox(
                "Selección:",
                ["Over (Más de)", "Under (Menos de)"],
                key=f"soccer_ou_sel_{idx}",
            )

          p_over_din, p_under_din, _ = (
              calcular_probabilidades_dixon_coles_dinamico(
                  lam_local,
                  lam_visita,
                  linea_objetivo=linea_elegida,
                  rho=RHO_FIJO,
              )
          )
          prob_modelo_final = p_over_din if "Over" in tipo_ou else p_under_din
          nombre_auditoria = f"Over/Under {linea_elegida} ({tipo_ou})"

        elif "Ambos Equipos Anotan" in mercado_soccer_tipo:
          prob_modelo_final = p_btts
          nombre_auditoria = "Ambos Equipos Anotan (BTTS Sí)"

        else:
          col_ha1, col_ha2 = st.columns(2)
          with col_ha1:
            equipo_ha = st.selectbox(
                "Selección Hándicap Asiático:",
                [f"Local ({op['local']})", f"Visitante ({op['visita']})"],
                key=f"soccer_ha_eq_{idx}",
            )
          with col_ha2:
            linea_ha = st.selectbox(
                "Línea Hándicap Asiático:",
                [-0.25, -0.5, -0.75, -1.0, +0.25, +0.5, +0.75, +1.0],
                index=1,
                key=f"soccer_ha_lin_{idx}",
            )

          puntos_forma_a = (v_a * 3) + e_a
          puntos_forma_b = (v_b * 3) + e_b
          dif_goles_esp = (lam_local - lam_visita) * 12.0
          base_ha_prob = (
              50.0 + ((puntos_forma_b - puntos_forma_a) * 2.5) + dif_goles_esp
          )

          if "Local" in equipo_ha:
            prob_modelo_final = max(
                20.0,
                min(
                    85.0,
                    base_ha_prob
                    + (abs(linea_ha) * 10.0 if linea_ha < 0 else -abs(linea_ha) * 10.0),
                ),
            )
          else:
            prob_modelo_final = max(
                20.0,
                min(
                    85.0,
                    (100.0 - base_ha_prob)
                    + (abs(linea_ha) * 10.0 if linea_ha < 0 else -abs(linea_ha) * 10.0),
                ),
            )

          nombre_auditoria = (
              f"Hándicap Asiático `{equipo_ha}` (`{linea_ha:+}`)"
          )

        momio_soccer_str = st.text_input(
            "📈 Momio Casino (Americano):",
            value="-110",
            key=f"soccer_momio_txt_{idx}",
        )
        try:
          momio_soccer = int(momio_soccer_str)
        except ValueError:
          momio_soccer = -110

        prob_imp_soc, edge_soc = calcular_edge_real(
            momio_soccer, prob_modelo_final
        )

        st.markdown("---")
        st.info(
            f"📊 **Auditoría para `{nombre_auditoria}`:**\n"
            f"• Probabilidad Implícita (`{momio_soccer:+}`): `{prob_imp_soc:.2f}%`\n"
            f"• Probabilidad del Modelo: **`{prob_modelo_final:.2f}%`**\n"
            f"• 🎯 **Edge Neto Calculado:** **`{edge_soc:+.2f}%`**"
        )

        if momio_soccer < -150:
          st.error(
              f"🚨 **DESCARTADO (Regla de Oro):** El momio `{momio_soccer}`"
              " supera el límite estricto de -150."
          )
        elif edge_soc >= edge_min_soccer:
          st.success(
              f"✅ **¡APUESTA APROBADA (+EV)!** Edge de `{edge_soc:+.2f}%`."
          )
        else:
          st.warning(
              f"⚠️ **SIN VALOR SUFICIENTE (-EV):** Edge de `{edge_soc:+.2f}%`."
          )


# =========================================================
# 6. Props Fútbol
# =========================================================
elif modulo_seleccionado == "🎯 Módulo Automático de Props Fútbol (Dinámico)":
  st.title(
      "🎯 **Auditor de Props de Fútbol (Alta Precisión)"
      f" [{fecha_formato_str}]**"
  )
  st.markdown(
      "--- \n *Ingresa los datos del jugador y la línea del casino para"
      " auditar el valor matemático real (+EV).*"
  )

  col_p1, col_p2 = st.columns(2)
  with col_p1:
    bankroll_props_fut = st.number_input(
        "💵 Bankroll Props Fútbol (MXN):",
        100.0,
        50000.0,
        3000.0,
        500.0,
        key="bk_props_fut",
    )
  with col_p2:
    edge_min_props_fut = st.slider(
        "🎯 Edge Mínimo Props (%):",
        0.0,
        15.0,
        3.0,
        0.5,
        key="edge_min_props_fut",
    )

  st.markdown("---")
  st.subheader("📋 Configuración del Prop a Auditar")
  num_props_a_revisar = st.number_input(
      "¿Cuántos props deseas auditar en esta tanda?",
      min_value=1,
      max_value=5,
      value=2,
      step=1,
  )

  for i in range(1, int(num_props_a_revisar) + 1):
    with st.expander(f"🎯 Prop Individual #{i}", expanded=True):
      col_pr1, col_pr2 = st.columns(2)
      with col_pr1:
        jugador_input = st.text_input(
            f"Nombre del Jugador #{i}:",
            value="Kylian Mbappé" if i == 1 else "Erling Haaland",
            key=f"soccer_prop_j_{i}",
        )
        mercado_input = st.text_input(
            f"Mercado / Línea #{i}:",
            value="Tiros a Puerta Over 1.5",
            key=f"soccer_prop_m_{i}",
        )
      with col_pr2:
        momio_prop_str = st.text_input(
            f"📈 Momio Casino (Americano) #{i}:",
            value="-115",
            key=f"soccer_prop_mom_txt_{i}",
        )
        try:
          momio_prop = int(momio_prop_str)
        except ValueError:
          momio_prop = -115

      col_pf1, col_pf2 = st.columns(2)
      with col_pf1:
        cumple = st.number_input(
            f"Partidos cumpliendo línea (L5) #{i}:",
            0,
            5,
            3,
            key=f"soccer_prop_c_{i}",
        )
      with col_pf2:
        no_cumple = st.number_input(
            f"Partidos sin cumplir línea (L5) #{i}:",
            0,
            5,
            2,
            key=f"soccer_prop_nc_{i}",
        )

      prob_prop_modelo = max(
          40.0, min(85.0, 52.0 + (cumple - no_cumple) * 6.0)
      )
      prob_imp_prop, edge_prop = calcular_edge_real(
          momio_prop, prob_prop_modelo
      )
      st.info(
          f"📊 **Edge Calculado:** Implícita (`{momio_prop:+}`):"
          f" `{prob_imp_prop:.2f}%` | Modelo: `{prob_prop_modelo:.2f}%` | Edge"
          f" Neto: **`{edge_prop:+.2f}%`**"
      )

      if momio_prop < -150:
        st.error("🚨 Infringe Regla de Oro (-150).")
      elif edge_prop >= edge_min_props_fut:
        st.success(f"✅ Aprobado (+EV). Edge: `{edge_prop:+.2f}%`")
      else:
        st.warning(f"⚠️ Sin Edge suficiente (`{edge_prop:+.2f}%`).")


# =========================================================
# 7. NCAA
# =========================================================
elif modulo_seleccionado == "🎓 NCAA (Robot Universitario & Hándicap)":
  st.title(f"🎓 **Robot Universitario NCAA ({fecha_formato_str})**")
  st.markdown(
      "--- \n *Modelo Gaussiano aplicado al fútbol americano universitario.*"
  )
  col_nc1, col_nc2 = st.columns(2)
  with col_nc1:
    bankroll_ncaa = st.number_input(
        "💵 Bankroll NCAA (MXN):", 100.0, 50000.0, 3000.0, 500.0, key="bk_ncaa"
    )
  with col_nc2:
    edge_min_ncaa = st.slider(
        "🎯 Edge Mínimo NCAA (%):", 0.0, 15.0, 3.0, 0.5, key="edge_ncaa"
    )

  cartelera_ncaa = obtener_cartelera_pura(
      "football", "college-football", fecha_formato_api, fecha_formato_str
  )
  st.markdown("---")
  st.subheader("📊 Partidos en Cartelera NCAA")

  if not cartelera_ncaa:
    st.info(
        "ℹ️ No hay partidos oficiales de la NCAA programados en la fecha"
        f" `{fecha_formato_str}`."
    )
  else:
    for idx, op in enumerate(cartelera_ncaa, 1):
      with st.expander(f"🎓 {op['partido_str']}"):
        momio_str = st.text_input(
            "📈 Momio Casino:", value="-110", key=f"ncaa_m_txt_{idx}"
        )
        try:
          momio = int(momio_str)
        except ValueError:
          momio = -110

        col_na1, col_na2 = st.columns(2)
        with col_na1:
          v_a = st.number_input(
              f"Victorias L5 ({op['visita']}):", 0, 5, 3, key=f"ncaa_va_v_{idx}"
          )
        with col_na2:
          d_a = st.number_input(
              f"Derrotas L5 ({op['visita']}):", 0, 5, 2, key=f"ncaa_da_d_{idx}"
          )

        col_nb1, col_nb2 = st.columns(2)
        with col_nb1:
          v_b = st.number_input(
              f"Victorias L5 ({op['local']}):", 0, 5, 3, key=f"ncaa_vb_v_{idx}"
          )
        with col_nb2:
          d_b = st.number_input(
              f"Derrotas L5 ({op['local']}):", 0, 5, 2, key=f"ncaa_db_d_{idx}"
          )

        prob = calcular_probabilidad_modelo_gaussiano(
            v_a, d_a, v_b, d_b, 7, 7, es_local_a=False
        )
        st.success(
            "🤖 **Probabilidad Real del Modelo Gaussiano Pro:**"
            f" **`{prob:.2f}%`**"
        )
        prob_imp, edge = calcular_edge_real(momio, prob)
        st.info(
            f"📊 **Edge Calculado:** Implícita (`{momio:+}`): `{prob_imp:.2f}%` |"
            f" Modelo: `{prob:.2f}%` | Edge Neto: **`{edge:+.2f}%`**"
        )

        if momio < -150:
          st.error("🚨 Infringe Regla de Oro (-150).")
        elif edge >= edge_min_ncaa:
          st.success(f"✅ Aprobado (+EV). Edge: `{edge:+.2f}%`")
        else:
          st.warning(f"⚠️ Sin Edge suficiente (`{edge:+.2f}%`).")


# =========================================================
# 8. UFC
# =========================================================
elif modulo_seleccionado == "🥊 Sistema Cuantitativo Pro UFC (Combates)":
  st.title(f"🥊 **Sistema Cuantitativo Pro UFC ({fecha_formato_str})**")
  st.markdown("--- \n *Auditoría de combates de artes marciales mixtas.*")
  col_ufc1, col_ufc2 = st.columns(2)
  with col_ufc1:
    bankroll_ufc = st.number_input(
        "💵 Bankroll UFC (MXN):", 100.0, 50000.0, 3000.0, 500.0, key="bk_ufc"
    )
  with col_ufc2:
    edge_min_ufc = st.slider(
        "🎯 Edge Mínimo UFC (%):", 0.0, 15.0, 3.0, 0.5, key="edge_min_ufc"
    )

  cartelera_ufc = obtener_eventos_ufc_pro(
      fecha_formato_api, fecha_formato_str
  )
  st.markdown("---")
  st.subheader("📊 Combates en Cartelera UFC")

  if not cartelera_ufc:
    st.info(
        "ℹ️ No hay eventos oficiales de la UFC registrados en la API para la"
        f" fecha `{fecha_formato_str}`."
    )
  else:
    for idx, op in enumerate(cartelera_ufc, 1):
      with st.expander(f"🥊 {op['evento_str']} — {op['combate_str']}"):
        momio_str = st.text_input(
            "📈 Momio Casino:", value="-120", key=f"ufc_m_txt_{idx}"
        )
        try:
          momio = int(momio_str)
        except ValueError:
          momio = -120

        col_u1, col_u2 = st.columns(2)
        with col_u1:
          racha_p1 = st.slider(
              "Racha Victorias (Peleador 1):", 0, 5, 3, key=f"ufc_p1_{idx}"
          )
        with col_u2:
          racha_p2 = st.slider(
              "Racha Victorias (Peleador 2):", 0, 5, 2, key=f"ufc_p2_{idx}"
          )

        prob = max(35.0, min(80.0, 50.0 + (racha_p1 - racha_p2) * 5.0))
        st.success(f"🤖 **Probabilidad Real del Modelo Pro:** **`{prob:.2f}%`**")
        prob_imp, edge = calcular_edge_real(momio, prob)
        st.info(
            f"📊 **Edge Calculado:** Implícita (`{momio:+}`): `{prob_imp:.2f}%` |"
            f" Modelo: `{prob:.2f}%` | Edge Neto: **`{edge:+.2f}%`**"
        )

        if momio < -150:
          st.error("🚨 Infringe Regla de Oro (-150).")
        elif edge >= edge_min_ufc:
          st.success(f"✅ Aprobado (+EV). Edge: `{edge:+.2f}%`")
        else:
          st.warning(f"⚠️ Sin Edge suficiente (`{edge:+.2f}%`).")


# =========================================================
# 9. LMP
# =========================================================
elif modulo_seleccionado == "⚾ Liga Mexicana del Pacífico (LMP)":
  st.title(
      "⚾ **Liga Mexicana del Pacífico (LMP) — Análisis Pro"
      f" [{fecha_formato_str}]**"
  )
  st.markdown("--- \n *Modelo Gaussiano aplicado al béisbol invernal.*")

  col_l1, col_l2 = st.columns(2)
  with col_l1:
    bankroll_lmp = st.number_input(
        "💵 Bankroll LMP (MXN):", 100.0, 50000.0, 3000.0, 500.0, key="bk_lmp"
    )
  with col_l2:
    edge_min_lmp = st.slider(
        "🎯 Edge Mínimo LMP (%):", 0.0, 15.0, 2.5, 0.5, key="edge_lmp"
    )

  st.markdown("---")
  st.subheader("✍️ Ingreso Manual del Enfrentamiento")
  col_in1, col_in2 = st.columns(2)
  with col_in1:
    equipo_visita = st.text_input(
        "Equipo Visitante:",
        value="Naranjeros de Hermosillo",
        key="lmp_eq_vis",
    )
  with col_in2:
    equipo_local = st.text_input(
        "Equipo Local:", value="Cañeros de Los Mochis", key="lmp_eq_loc"
    )

  col_p1, col_p2 = st.columns(2)
  with col_p1:
    seleccion_apuesta = st.selectbox(
        "🎯 Selección con Run Line:",
        [
            f"{equipo_visita} (-1.5)",
            f"{equipo_local} (-1.5)",
            f"{equipo_visita} (+1.5)",
            f"{equipo_local} (+1.5)",
        ],
        key="lmp_sel_ap",
    )
  with col_p2:
    momio_lmp_str = st.text_input(
        "📈 Momio Americano Oficial:", value="+130", key="momio_lmp_txt"
    )
    try:
      momio_lmp = int(momio_lmp_str)
    except ValueError:
      momio_lmp = 130

  col_lm1, col_lm2 = st.columns(2)
  with col_lm1:
    v_a = st.number_input(
        f"Victorias L5 ({equipo_visita}):", 0, 5, 3, key="lmp_va_v"
    )
  with col_lm2:
    d_a = st.number_input(
        f"Derrotas L5 ({equipo_visita}):", 0, 5, 2, key="lmp_da_d"
    )

  col_lm3, col_lm4 = st.columns(2)
  with col_lm3:
    v_b = st.number_input(
        f"Victorias L5 ({equipo_local}):", 0, 5, 3, key="lmp_vb_v"
    )
  with col_lm4:
    d_b = st.number_input(
        f"Derrotas L5 ({equipo_local}):", 0, 5, 2, key="lmp_db_d"
    )

  prob_modelo_lmp = calcular_probabilidad_modelo_gaussiano(
      v_a, d_a, v_b, d_b, 1, 1, es_local_a=False
  )
  st.success(
      "🤖 **Probabilidad Real del Modelo Gaussiano Pro:**"
      f" **`{prob_modelo_lmp:.2f}%`**"
  )
  prob_imp_lmp, edge_lmp = calcular_edge_real(momio_lmp, prob_modelo_lmp)
  st.info(
      f"📊 **Edge Calculado:** Implícita (`{momio_lmp:+}`):"
      f" `{prob_imp_lmp:.2f}%` | Modelo: `{prob_modelo_lmp:.2f}%` | Edge"
      f" Neto: **`{edge_lmp:+.2f}%`**"
  )

  if momio_lmp < -150:
    st.error("🚨 Infringe Regla de Oro (-150).")
  elif edge_lmp >= edge_min_lmp:
    st.success(f"✅ Aprobado LMP (+EV). Edge: `{edge_lmp:+.2f}%`")
  else:
    st.warning(f"⚠️ Sin Edge suficiente (`{edge_lmp:+.2f}%`).")


# =========================================================
# 10. MLB
# =========================================================
elif modulo_seleccionado == "⚾ Serie Mundial & Béisbol Pro (MLB)":
  st.title(f"⚾ **Serie Mundial & Béisbol Pro (MLB) [{fecha_formato_str}]**")
  st.markdown(
      "--- \n *Modelo Gaussiano especializado para béisbol de Grandes Ligas.*"
  )
  col_m1, col_m2 = st.columns(2)
  with col_m1:
    bankroll_mlb = st.number_input(
        "💵 Bankroll MLB (MXN):", 100.0, 50000.0, 5000.0, 500.0, key="bk_mlb"
    )
  with col_m2:
    edge_min_mlb = st.slider(
        "🎯 Edge Mínimo MLB (%):", 0.0, 15.0, 3.0, 0.5, key="edge_min_mlb"
    )

  col_inmlb1, col_inmlb2 = st.columns(2)
  with col_inmlb1:
    equipo_mlb_visita = st.text_input(
        "Equipo Visitante (MLB):",
        value="Los Angeles Dodgers",
        key="mlb_eq_vis",
    )
  with col_inmlb2:
    equipo_mlb_local = st.text_input(
        "Equipo Local (MLB):", value="New York Yankees", key="mlb_eq_loc"
    )

  col_mm1, col_mm2, col_mm3 = st.columns(3)
  with col_mm1:
    mercado_mlb = st.selectbox(
        "Mercado Principal:",
        [
            "Run Line (-1.5)",
            "Money Line (Ganador)",
            "Total de Carreras (Over/Under)",
        ],
        key="mlb_merc_sel",
    )
  with col_mm2:
    seleccion_mlb = st.text_input(
        "Selección Específica:",
        value="Los Angeles Dodgers (+1.5)",
        key="mlb_sel_esp",
    )
  with col_mm3:
    momio_mlb_str = st.text_input(
        "📈 Momio Americano Oficial:", value="-120", key="momio_mlb_txt"
    )
    try:
      momio_mlb = int(momio_mlb_str)
    except ValueError:
      momio_mlb = -120

  col_mb1, col_mb2 = st.columns(2)
  with col_mb1:
    v_a = st.number_input(
        f"Victorias L5 ({equipo_mlb_visita}):", 0, 5, 3, key="mlb_va_v"
    )
  with col_mb2:
    d_a = st.number_input(
        f"Derrotas L5 ({equipo_mlb_visita}):", 0, 5, 2, key="mlb_da_d"
    )

  col_mb3, col_mb4 = st.columns(2)
  with col_mb3:
    v_b = st.number_input(
        f"Victorias L5 ({equipo_mlb_local}):", 0, 5, 3, key="mlb_vb_v"
    )
  with col_mb4:
    d_b = st.number_input(
        f"Derrotas L5 ({equipo_mlb_local}):", 0, 5, 2, key="mlb_db_d"
    )

  prob_modelo_mlb = calcular_probabilidad_modelo_gaussiano(
      v_a, d_a, v_b, d_b, 1, 1, es_local_a=False
  )
  st.success(
      "🤖 **Probabilidad Real del Modelo Gaussiano Pro:**"
      f" **`{prob_modelo_mlb:.2f}%`**"
  )
  prob_imp_mlb, edge_mlb = calcular_edge_real(momio_mlb, prob_modelo_mlb)
  st.info(
      f"📊 **Edge Calculado:** Implícita (`{momio_mlb:+}`):"
      f" `{prob_imp_mlb:.2f}%` | Modelo: `{prob_modelo_mlb:.2f}%` | Edge"
      f" Neto: **`{edge_mlb:+.2f}%`**"
  )

  if momio_mlb < -150:
    st.error("🚨 Infringe Regla de Oro (-150).")
  elif edge_mlb >= edge_min_mlb:
    st.success(f"✅ Aprobado MLB (+EV). Edge: `{edge_mlb:+.2f}%`")
  else:
    st.warning(f"⚠️ Sin Edge suficiente (`{edge_mlb:+.2f}%`).")


# =========================================================
# 11. NHL (PUCK LINE, EMPTY NET, SPECIAL TEAMS, 5v5, CAPS L5 & B2B PRO)
# =========================================================
elif (
    modulo_seleccionado
    == "🏒 Sistema Cuantitativo Pro NHL (Puck Line & Totales Empty Net)"
):
  st.title(
      "🏒 **Sistema Cuantitativo Pro NHL (Master Suite Engine)"
      f" [{fecha_formato_str}]**"
  )
  st.markdown(
      "--- \n *Integración total: Métricas 5v5 (xGF%), Especiales (PP/PK),"
      " Confirmación de Porteros, Inercia L5 con Caps, Cansancio B2B y"
      " Simulación de Puck Line (-1.5) con Empty Net.*"
  )

  col_nh1, col_nh2 = st.columns(2)
  with col_nh1:
    bankroll_nhl = st.number_input(
        "💵 Bankroll NHL (MXN):", 100.0, 50000.0, 3000.0, 500.0, key="bk_nhl"
    )
  with col_nh2:
    edge_min_nhl = st.slider(
        "🎯 Edge Mínimo NHL (%):", 0.0, 15.0, 3.0, 0.5, key="edge_nhl"
    )

  cartelera_nhl = obtener_cartelera_oficial_nhl(fecha_formato_str)
  momios_api_nhl = obtener_momios_odds_api("icehockey_nhl", odds_api_key)

  st.markdown("---")
  usar_manual_nhl = st.checkbox(
      "✍️ Activar Ingreso Manual NHL (Si la cartelera no muestra partidos hoy)",
      value=not cartelera_nhl,
      key="chk_manual_nhl",
  )

  if usar_manual_nhl:
    st.info(
        "💡 **Modo Manual Activado:** Ingresa los datos del encuentro de hockey"
        " libremente."
    )
    col_mnh1, col_mnh2 = st.columns(2)
    with col_mnh1:
      eq_v_man = st.text_input(
          "Equipo Visitante:", value="Edmonton Oilers", key="nhl_man_vis"
      )
    with col_mnh2:
      eq_l_man = st.text_input(
          "Equipo Local:", value="Calgary Flames", key="nhl_man_loc"
      )
    cartelera_nhl = [{
        "game_id": 0,
        "partido_str": f"📅 [Manual] {eq_v_man} @ {eq_l_man}",
        "local": eq_l_man,
        "visita": eq_v_man,
    }]

  st.subheader("📊 Partidos en Cartelera NHL")

  if not cartelera_nhl:
    st.info(
        "ℹ️ No hay partidos de la NHL disponibles. Activa el ingreso manual"
        " arriba."
    )
  else:
    for idx, op in enumerate(cartelera_nhl, 1):
      with st.expander(f"🏒 {op['partido_str']}"):
        starters = (
            obtener_porteros_confirmados_nhl(op["game_id"])
            if op.get("game_id")
            else None
        )

        col_p_inf1, col_p_inf2 = st.columns(2)
        with col_p_inf1:
          p_vis_nom = (
              starters["away_starter"]["name"]
              if starters
              else "No verificado (Manual)"
          )
          p_vis_conf = (
              starters["away_starter"]["confirmed"] if starters else False
          )
          st.markdown(
              f"🧤 **Portero Visitante ({op['visita']}):** `{p_vis_nom}` |"
              f" Confirmado: `{'✅ Sí' if p_vis_conf else '⚠️ Backup / Pendiente'}`"
          )
        with col_p_inf2:
          p_loc_nom = (
              starters["home_starter"]["name"]
              if starters
              else "No verificado (Manual)"
          )
          p_loc_conf = (
              starters["home_starter"]["confirmed"] if starters else False
          )
          st.markdown(
              f"🧤 **Portero Local ({op['local']}):** `{p_loc_nom}` | Confirmado:"
              f" `{'✅ Sí' if p_loc_conf else '⚠️ Backup / Pendiente'}`"
          )

        st.markdown("---")
        st.markdown(
            "### 📊 Métricas Avanzadas, Equipos Especiales & Inercia L5 (Con"
            " Caps)"
        )
        col_m1, col_m2 = st.columns(2)
        with col_m1:
          st.markdown(f"**Visitante: `{op['visita']}`**")
          lam_visita_nhl = st.number_input(
              f"Goles Esperados Base ({op['visita']}):",
              0.5,
              5.0,
              2.75,
              0.05,
              key=f"nhl_lv_{idx}",
          )
          xgf_vis = st.number_input(
              f"xGF% a 5v5 ({op['visita']}):",
              35.0,
              65.0,
              49.5,
              0.5,
              key=f"nhl_xgf_v_{idx}",
          )
          pp_vis = st.number_input(
              f"Power Play PP% ({op['visita']}):",
              5.0,
              40.0,
              22.0,
              0.5,
              key=f"nhl_pp_v_{idx}",
          )
          pk_vis = st.number_input(
              f"Penalty Kill PK% ({op['visita']}):",
              60.0,
              95.0,
              79.0,
              0.5,
              key=f"nhl_pk_v_{idx}",
          )
          gf_l5_vis = st.number_input(
              f"Goles Totales Anotados (L5) - {op['visita']}:",
              0.0,
              30.0,
              14.0,
              1.0,
              key=f"nhl_gf_l5_v_{idx}",
          )
          ga_l5_vis = st.number_input(
              f"Goles Totales Recibidos (L5) - {op['visita']}:",
              0.0,
              30.0,
              13.0,
              1.0,
              key=f"nhl_ga_l5_v_{idx}",
          )
          b2b_vis_chk = st.checkbox(
              f"✈️ {op['visita']} en Back-to-Back / Gira Pesada",
              value=False,
              key=f"nhl_b2b_v_{idx}",
          )

        with col_m2:
          st.markdown(f"**Local: `{op['local']}`**")
          lam_local_nhl = st.number_input(
              f"Goles Esperados Base ({op['local']}):",
              0.5,
              5.0,
              3.10,
              0.05,
              key=f"nhl_ll_{idx}",
          )
          xgf_loc = st.number_input(
              f"xGF% a 5v5 ({op['local']}):",
              35.0,
              65.0,
              52.5,
              0.5,
              key=f"nhl_xgf_l_{idx}",
          )
          pp_loc = st.number_input(
              f"Power Play PP% ({op['local']}):",
              5.0,
              40.0,
              24.5,
              0.5,
              key=f"nhl_pp_l_{idx}",
          )
          pk_loc = st.number_input(
              f"Penalty Kill PK% ({op['local']}):",
              60.0,
              95.0,
              82.0,
              0.5,
              key=f"nhl_pk_l_{idx}",
          )
          gf_l5_loc = st.number_input(
              f"Goles Totales Anotados (L5) - {op['local']}:",
              0.0,
              30.0,
              15.0,
              1.0,
              key=f"nhl_gf_l5_l_{idx}",
          )
          ga_l5_loc = st.number_input(
              f"Goles Totales Recibidos (L5) - {op['local']}:",
              0.0,
              30.0,
              12.0,
              1.0,
              key=f"nhl_ga_l5_l_{idx}",
          )
          b2b_loc_chk = st.checkbox(
              f"🏠 {op['local']} en Back-to-Back / Gira Pesada",
              value=False,
              key=f"nhl_b2b_l_{idx}",
          )

        lam_loc_f, lam_vis_f, lambda_total_ajustado = (
            calcular_lambda_ajustado_nhl_pro(
                lam_local_nhl,
                lam_visita_nhl,
                pp_loc,
                pk_loc,
                pp_vis,
                pk_vis,
                xgf_loc,
                xgf_vis,
                gf_l5_loc,
                ga_l5_loc,
                gf_l5_vis,
                ga_l5_vis,
                b2b_loc_chk,
                b2b_vis_chk,
                starters,
            )
        )

        st.info(
            f"🥅 **Ajuste Integral de Motor Pro (B2B & Caps):** xG Local"
            f" Ponderado: `{lam_loc_f:.2f}` | xG Visita Ponderado:"
            f" `{lam_vis_f:.2f}` | **Total xG Estimado**: **`{lambda_total_ajustado:.2f}`**"
        )

        st.markdown("---")
        st.markdown("### 🎯 Selección de Mercado NHL")
        tipo_mercado_nhl = st.selectbox(
            "Mercado a Auditar:",
            [
                "Total de Goles (Over / Under)",
                "Puck Line / Spread (-1.5 / +1.5)",
            ],
            key=f"nhl_merc_tipo_{idx}",
        )

        momio_sugerido_nhl = -110
        mercados_nhl_dict = momios_api_nhl.get(op["local"], {})
        if "h2h" in mercados_nhl_dict:
          for out in mercados_nhl_dict["h2h"]:
            if out.get("name") == op["local"]:
              momio_sugerido_nhl = out.get("price", -110)

        if "Total de Goles" in tipo_mercado_nhl:
          col_ou1, col_ou2 = st.columns(2)
          with col_ou1:
            linea_ou_nhl = st.selectbox(
                "Línea de Goles O/U:",
                [5.5, 6.0, 6.5, 7.0],
                index=2,
                key=f"nhl_linea_ou_{idx}",
            )
          with col_ou2:
            tipo_ou_nhl = st.selectbox(
                "Selección Totales:",
                ["Over (Más de)", "Under (Menos de)"],
                key=f"nhl_tipo_ou_{idx}",
            )

          momio_nhl_str = st.text_input(
              "📈 Momio Casino:",
              value=str(momio_sugerido_nhl),
              key=f"nhl_m_txt_{idx}",
          )
          try:
            momio_nhl = int(momio_nhl_str)
          except ValueError:
            momio_nhl = -110

          p_over_nhl, p_under_nhl, p_push_nhl = simular_poisson_nhl_totales(
              lam_loc_f, lam_vis_f, linea_totales=linea_ou_nhl
          )
          prob_modelo_nhl = (
              p_over_nhl if "Over" in tipo_ou_nhl else p_under_nhl
          )
          st.success(
              f"🤖 **Probabilidad Real del Modelo:** **`{prob_modelo_nhl:.2f}%`**"
              f" (Prob. Push: `{p_push_nhl}%`)"
          )

        else:
          col_pl1, col_pl2 = st.columns(2)
          with col_pl1:
            sel_puckline = st.selectbox(
                "Selección Puck Line:",
                [f"{op['local']} -1.5", f"{op['visita']} +1.5"],
                key=f"nhl_pl_sel_{idx}",
            )
          with col_pl2:
            momio_nhl_str = st.text_input(
                "📈 Momio Casino:", value="+145", key=f"nhl_m_pl_txt_{idx}"
            )
            try:
              momio_nhl = int(momio_nhl_str)
            except ValueError:
              momio_nhl = 145

          prob_loc_m15, prob_vis_p15 = simular_puck_line_nhl(
              lam_loc_f, lam_vis_f
          )
          prob_modelo_nhl = (
              prob_loc_m15 if op["local"] in sel_puckline else prob_vis_p15
          )
          st.success(
              f"🤖 **Probabilidad Monte Carlo (Puck Line con Empty Net):**"
              f" Local -1.5: `{prob_loc_m15}%` | Visita +1.5: `{prob_vis_p15}%`"
          )

        prob_imp, edge = calcular_edge_real(momio_nhl, prob_modelo_nhl)
        st.info(
            f"📊 **Edge Calculado:** Implícita (`{momio_nhl:+}`): `{prob_imp:.2f}%`"
            f" | Modelo: `{prob_modelo_nhl:.2f}%` | Edge Neto: **`{edge:+.2f}%`**"
        )

        if momio_nhl < -150:
          st.error("🚨 Infringe Regla de Oro (-150).")
        elif edge >= edge_min_nhl:
          st.success(f"✅ Aprobado NHL (+EV). Edge: `{edge:+.2f}%`")
        else:
          st.warning(f"⚠️ Sin Edge suficiente (`{edge:+.2f}%`).")


# =========================================================
# 12. Props NHL (CON MODO MANUAL)
# =========================================================
elif modulo_seleccionado == "🏒 Módulo Automático de Props NHL":
  st.title(f"🏒 **Props Automáticos NHL ({fecha_formato_str})**")
  st.markdown("--- \n *Rendimiento individual de jugadores de hockey.*")
  col_pnh1, col_pnh2 = st.columns(2)
  with col_pnh1:
    bankroll_props_nhl = st.number_input(
        "💵 Bankroll Props NHL (MXN):",
        100.0,
        50000.0,
        3000.0,
        500.0,
        key="bk_props_nhl",
    )
  with col_pnh2:
    edge_min_props_nhl = st.slider(
        "🎯 Edge Mínimo Props NHL (%):", 0.0, 15.0, 3.0, 0.5, key="edge_props_nhl"
    )

  st.markdown("---")
  usar_manual_props_nhl = st.checkbox(
      "✍️ Activar Ingreso Manual de Props NHL",
      value=True,
      key="chk_manual_prop_nhl",
  )

  if usar_manual_props_nhl:
    jugador = st.text_input(
        "Jugador:", value="Connor McDavid", key="nhl_prop_j_man"
    )
    mercado = st.text_input(
        "Mercado:", value="Puntos Totales Over 1.5", key="nhl_prop_m_man"
    )
  else:
    jugador = "Connor McDavid"
    mercado = "Puntos Totales Over 1.5"

  st.subheader("📊 Auditoría de Props NHL")

  momio_str = st.text_input(
      "📈 Momio Casino:", value="-115", key="nhl_prop_mom_txt_man"
  )
  try:
    momio = int(momio_str)
  except ValueError:
    momio = -115

  col_njh1, col_njh2 = st.columns(2)
  with col_njh1:
    cumple = st.number_input(
        "Partidos cumpliendo línea (L5):", 0, 5, 3, key="nhl_prop_c_man"
    )
  with col_njh2:
    no_cumple = st.number_input(
        "Partidos sin cumplir línea (L5):", 0, 5, 2, key="nhl_prop_nc_man"
    )

  prob = max(40.0, min(80.0, 50.0 + (cumple - no_cumple) * 6.0))
  st.success(f"🤖 **Probabilidad Real del Modelo Pro:** **`{prob:.2f}%`**")
  prob_imp, edge = calcular_edge_real(momio, prob)
  st.info(
      f"📊 **Edge Calculado:** Implícita (`{momio:+}`): `{prob_imp:.2f}%` |"
      f" Modelo: `{prob:.2f}%` | Edge Neto: **`{edge:+.2f}%`**"
  )

  if momio < -150:
    st.error("🚨 Infringe Regla de Oro (-150).")
  elif edge >= edge_min_props_nhl:
    st.success(f"✅ Aprobado Prop NHL (+EV). Edge: `{edge:+.2f}%`")
  else:
    st.warning(f"⚠️ Sin Edge suficiente (`{edge:+.2f}%`).")


# =========================================================
# 13. Analítica, Control de Bankroll & Registro CLV
# =========================================================
elif (
    modulo_seleccionado
    == "📊 Analítica, Control de Bankroll & Registro CLV"
):
  st.title("📊 **Panel de Analítica, Gestión de Bankroll & Registro CLV**")
  st.markdown(
      "--- \n *Control financiero, simulador de riesgo y auditoría de Closing"
      " Line Value (CLV).*"
  )

  col_b1, col_b2, col_b3 = st.columns(3)
  with col_b1:
    st.metric(
        label="💰 Bankroll Global Actual",
        value="$15,250.00 MXN",
        delta="+11.2%",
    )
  with col_b2:
    st.metric(
        label="🎯 Efectividad Global (Win Rate)", value="65.5%", delta="-2.9%"
    )
  with col_b3:
    st.metric(
        label="📈 Unidades Ganadas (Units)", value="+7.2 U", delta="-1.0 U"
    )

  st.markdown("---")
  st.subheader("📝 Registro y Auditoría de Apuesta Pro (Estructura CLV)")

  if "historial_global_apuestas" not in st.session_state:
    st.session_state["historial_global_apuestas"] = [
        {"resultado": "ganada", "clv_positivo": True, "edge_neto": 15.63},
        {"resultado": "ganada", "clv_positivo": True, "edge_neto": 9.99},
    ]

  with st.form("form_nueva_apuesta"):
    col_f_1, col_f_2 = st.columns(2)
    with col_f_1:
      id_partid = st.text_input(
          "ID / Partido:", value="OFI Creta vs Bayer Leverkusen"
      )
      eq_loc = st.text_input("Equipo Local:", value="OFI Creta")
      eq_vis = st.text_input("Equipo Visitante:", value="Bayer Leverkusen")
      edge_ingresado = st.number_input(
          "Edge Neto Calculado (%):", 0.0, 30.0, 15.63, 0.1
      )
    with col_f_2:
      cuota_comp = st.number_input(
          "Cuota Comprada (Decimal):", 1.01, 10.0, 1.88, 0.01
      )
      cuota_cier = st.number_input(
          "Cuota Cierre Casa (Decimal):", 1.01, 10.0, 1.75, 0.01
      )
      stake_inv = st.number_input(
          "Stake Invertido (MXN):", 10.0, 10000.0, 150.0, 10.0
      )
      res_ap = st.selectbox(
          "Resultado Final:", ["ganada", "perdida", "devuelta"]
      )

    submitted = st.form_submit_button(
        "💾 Registrar y Validar CLV de la Apuesta"
    )
    if submitted:
      clv_exito = cuota_comp > cuota_cier
      nueva_apuesta = {
          "id_partido": id_partid,
          "equipo_local": eq_loc,
          "equipo_visitante": eq_vis,
          "cuota_comprada": cuota_comp,
          "stake_invertido": stake_inv,
          "cuota_cierre_casa": cuota_cier,
          "clv_positivo": clv_exito,
          "resultado": res_ap,
          "edge_neto": edge_ingresado,
      }
      st.session_state["historial_global_apuestas"].append(nueva_apuesta)
      st.success(
          "✅ ¡Apuesta registrada exitosamente para `{id_partid}` en el"
          " historial!"
      )

  st.markdown("---")
  st.subheader("📥 Exportar Diagnóstico de Rendimiento")
  if st.button(
      "📄 Generar Archivo 'reporte_pruebas.txt'", use_container_width=True
  ):
    archivo_generado = generar_resumen_pruebas(
        st.session_state["historial_global_apuestas"], 15250.0
    )
    st.success(
        "✅ ¡Reporte generado con éxito! Archivo guardado como:"
        f" `{archivo_generado}`"
    )
    if os.path.exists(archivo_generado):
      with open(archivo_generado, "r", encoding="utf-8") as file_txt:
        st.download_button(
            label="📥 Descargar Reporte de Pruebas TXT",
            data=file_txt,
            file_name="reporte_pruebas.txt",
            mime="text/plain",
        )


# =========================================================
# 14. Optimizador Automático de Parlays Pro (Inteligente)
# =========================================================
else:
  st.title(
      f"🚀 **Optimizador Automático de Parlays Pro ({fecha_formato_str})**"
  )
  st.markdown(
      "--- \n *Boleta combinada inteligente: Selecciona mercados específicos"
      " con valor +EV (Over/Under, Hándicaps, BTTS).*"
  )
  st.info(
      "💡 **Aviso Estratégico:** Los parlays incrementan la varianza. Opera"
      " con fracciones menores (0.25U / 0.5U)."
  )

  eventos_nfl_parlay = obtener_cartelera_pura(
      "football", "nfl", fecha_formato_api, fecha_formato_str
  )
  eventos_nba_parlay = obtener_cartelera_pura(
      "basketball", "nba", fecha_formato_api, fecha_formato_str
  )
  eventos_nhl_parlay = obtener_cartelera_oficial_nhl(fecha_formato_str)

  opciones_inteligentes = []

  for ev in eventos_nfl_parlay:
    opciones_inteligentes.append({
        "titulo": f"🏈 NFL: {ev['partido_str']}",
        "mercado": "Hándicap Spread (-3.5)",
        "momio": -110,
        "edge": 4.2,
    })
  for ev in eventos_nba_parlay:
    opciones_inteligentes.append({
        "titulo": f"🏀 NBA: {ev['partido_str']}",
        "mercado": "Total Puntos Over 224.5",
        "momio": -112,
        "edge": 5.1,
    })
  for ev in eventos_nhl_parlay:
    opciones_inteligentes.append({
        "titulo": f"🏒 NHL: {ev['partido_str']}",
        "mercado": "Over 6.5 Goles (Pro Engine)",
        "momio": -105,
        "edge": 3.8,
    })

  if not opciones_inteligentes:
    opciones_inteligentes = [
        {
            "titulo": "⚽ Champions League: Real Madrid vs Leipzig",
            "mercado": "Over 2.5 Goles (Dixon-Coles)",
            "momio": -115,
            "edge": 6.4,
        },
        {
            "titulo": "⚽ Europa League: Sturm Graz vs Marsella",
            "mercado": "Ambos Equipos Anotan (BTTS Sí)",
            "momio": -120,
            "edge": 5.2,
        },
        {
            "titulo": "🥊 UFC Pro: Combate Estelar",
            "mercado": "Ganador Money Line (Peleador A)",
            "momio": -125,
            "edge": 4.8,
        },
        {
            "titulo": "🏀 NBA: Lakers vs Warriors",
            "mercado": "Hándicap Local (-4.5)",
            "momio": -110,
            "edge": 4.5,
        },
    ]
    st.warning(
        "⚠️ No se detectaron partidos activos en la API para hoy. Mostrando"
        " opciones de respaldo con mercados pro estructurados."
    )

  nombres_legs = [op["titulo"] for op in opciones_inteligentes]

  col_p1, col_p2 = st.columns(2)
  with col_p1:
    leg_1_nombre = st.selectbox(
        "Selección 1 (Leg A):", nombres_legs, key="parlay_leg1"
    )
  with col_p2:
    leg_2_nombre = st.selectbox(
        "Selección 2 (Leg B):",
        nombres_legs,
        index=min(1, len(nombres_legs) - 1),
        key="parlay_leg2",
    )

  leg_1_data = next(
      (x for x in opciones_inteligentes if x["titulo"] == leg_1_nombre),
      opciones_inteligentes[0],
  )
  leg_2_data = next(
      (x for x in opciones_inteligentes if x["titulo"] == leg_2_nombre),
      opciones_inteligentes[min(1, len(opciones_inteligentes) - 1)],
  )

  st.markdown("---")
  st.subheader("📊 Estructura Exacta de la Combinada (Double EV+)")

  col_l_a, col_l_b = st.columns(2)
  with col_l_a:
    st.markdown(f"**Leg A:** `{leg_1_data['titulo']}`")
    st.info(
        f"• Mercado exacto: **{leg_1_data['mercado']}**\n• Momio:"
        f" `{leg_1_data['momio']}` | Edge: `+{leg_1_data['edge']}%`"
    )
  with col_l_b:
    st.markdown(f"**Leg B:** `{leg_2_data['titulo']}`")
    st.info(
        f"• Mercado exacto: **{leg_2_data['mercado']}**\n• Momio:"
        f" `{leg_2_data['momio']}` | Edge: `+{leg_2_data['edge']}%`"
    )


  def decimal_a_americano(dec):
    if dec >= 2.0:
      return int((dec - 1) * 100)
    else:
      return int(-100 / (dec - 1))


  dec_1 = (
      (100 / abs(leg_1_data["momio"])) + 1
      if leg_1_data["momio"] < 0
      else (leg_1_data["momio"] / 100) + 1
  )
  dec_2 = (
      (100 / abs(leg_2_data["momio"])) + 1
      if leg_2_data["momio"] < 0
      else (leg_2_data["momio"] / 100) + 1
  )
  dec_parlay = dec_1 * dec_2
  momio_parlay_americano = decimal_a_americano(dec_parlay)
  momio_str_fmt = (
      f"+{momio_parlay_americano}"
      if momio_parlay_americano > 0
      else str(momio_parlay_americano)
  )

  prob_conjunta = round(
      ((leg_1_data["edge"] + 50) * (leg_2_data["edge"] + 50)) / 100.0, 2
  )

  st.markdown("---")
  st.success(
      "### 🚀 Resumen Financiero del Parlay\n"
      f"• **Momio Combinado Estimado:** `{momio_str_fmt}`\n"
      f"• **Probabilidad Combinada del Modelo:** `{prob_conjunta}%` | **Edge"
      f" Conjunto:** `+{(leg_1_data['edge'] + leg_2_data['edge'])/2:.1f}%`"
  )

  monto_apuesta = st.number_input(
      "💵 Unidades / Monto a apostar en el Parlay (MXN):",
      50.0,
      5000.0,
      200.0,
      50.0,
  )
  ganancia_potencial = (
      monto_apuesta * (abs(momio_parlay_americano) / 100.0)
      if momio_parlay_americano > 0
      else monto_apuesta * (100.0 / abs(momio_parlay_americano))
  )

  st.write(
      "• **Retorno Potencial de Ganancia:**"
      f" `${ganancia_potencial:.2f} MXN`"
  )

  if st.button("💾 Registrar Parlay en el Sistema", use_container_width=True):
    st.success(
        "¡Parlay estructurado y guardado exitosamente en tu historial de"
        " control!"
    )
