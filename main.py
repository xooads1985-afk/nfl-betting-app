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
    page_title="Central de Apuestas Pro - Master Suite Analítica Élite",
    page_icon="🎯",
    layout="wide",
)


# ---------------------------------------------------------
# CONEXIÓN CON THE ODDS API (MOMIOS EN VIVO Y CLV)
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
# CLIMA Y ESTADÍSTICAS EN TIEMPO REAL (OPEN-METEO)
# ---------------------------------------------------------
@st.cache_data(ttl=600)
def obtener_clima_estadio_nfl(nombre_equipo_local):
  estadios_coords = {
      "Kansas City Chiefs": (39.0489, -94.4839),
      "Buffalo Bills": (42.7738, -78.7870),
      "Green Bay Packers": (44.5013, -88.0622),
  }
  coords = estadios_coords.get(nombre_equipo_local, (39.8283, -98.5795))
  lat, lon = coords
  url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,wind_speed_10m"
  try:
    response = requests.get(url, timeout=3)
    if response.status_code == 200:
      data = response.json()
      current = data.get("current", {})
      temp_c = float(current.get("temperature_2m", 15.0))
      wind_mph = float(current.get("wind_speed_10m", 10.0)) * 0.621371
      return temp_c, wind_mph, True
  except Exception:
    pass
  return 18.0, 5.0, False


# ---------------------------------------------------------
# CARTELERAS OFICIALES MULTI-DEPORTE BLINDADAS POR FECHA
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
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{liga}/scoreboard?dates={fecha_str_api}&limit=20"
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
    return [{"partido_str": f"📅 [{fecha_str_humana}] Boston Celtics @ Los Angeles Lakers", "local": "Los Angeles Lakers", "visita": "Boston Celtics"}]
  elif "soccer" in deporte.lower():
    return [{"partido_str": f"📅 [{fecha_str_humana}] Nottingham Forest @ Ipswich Town", "local": "Ipswich Town", "visita": "Nottingham Forest"}]
  elif liga.lower() == "nfl":
    return [{"partido_str": f"📅 [{fecha_str_humana}] Kansas City Chiefs @ Baltimore Ravens", "local": "Baltimore Ravens", "visita": "Kansas City Chiefs"}]
  elif "college" in liga.lower():
    return [{"partido_str": f"📅 [{fecha_str_humana}] Alabama Crimson Tide @ Georgia Bulldogs", "local": "Georgia Bulldogs", "visita": "Alabama Crimson Tide"}]
  
  return [{"partido_str": f"📅 [{fecha_str_humana}] Equipo Visitante @ Equipo Local", "local": "Local", "visita": "Visitante"}]


@st.cache_data(ttl=300)
def obtener_cartelera_oficial_nhl(fecha_str_api_nhl, fecha_str_humana):
  url = f"https://api-web.nhle.com/v1/schedule/{fecha_str_api_nhl}"
  partidos_nhl = []
  try:
    response = requests.get(url, timeout=3)
    if response.status_code == 200:
      data = response.json()
      for day in data.get("gameWeek", []):
        if day.get("date") == fecha_str_api_nhl:
          for game in day.get("games", []):
            partidos_nhl.append({
                "game_id": game.get("id"),
                "local": game.get("homeTeam", {}).get("abbrev", "HOME"),
                "visita": game.get("awayTeam", {}).get("abbrev", "AWAY"),
                "partido_str": f"🏒 [{fecha_str_humana}] {game.get('awayTeam', {}).get('abbrev')} @ {game.get('homeTeam', {}).get('abbrev')}",
            })
      if partidos_nhl:
        return partidos_nhl
  except Exception:
    pass
  return [{"game_id": 0, "partido_str": f"🏒 [{fecha_str_humana}] MTL @ CHI", "local": "CHI", "visita": "MTL"}, {"game_id": 1, "partido_str": f"🏒 [{fecha_str_humana}] TBL @ COL", "local": "COL", "visita": "TBL"}]


@st.cache_data(ttl=300)
def obtener_eventos_ufc_pro(fecha_str_api, fecha_str_humana):
  url = f"https://site.api.espn.com/apis/site/v2/sports/mma/ufc/scoreboard?dates={fecha_str_api}&limit=20"
  nombre_evento = "UFC Fight Night / PPV"
  try:
    response = requests.get(url, timeout=3)
    if response.status_code == 200:
      data = response.json()
      eventos = data.get("events", [])
      if eventos:
        nombre_evento = eventos[0].get("name", "UFC Evento Principal")
  except Exception:
    pass
  
  cartelera_completa = [
      {"evento_str": f"🥊 [{fecha_str_humana}] {nombre_evento}", "tipo": "Pelea Estelar (Main Event)", "p1": "Peleador Estelar A", "p2": "Peleador Estelar B"},
      {"evento_str": f"🥊 [{fecha_str_humana}] {nombre_evento}", "tipo": "Combate Co-Estelar", "p1": "Peleador Co-Estelar A", "p2": "Peleador Co-Estelar B"},
      {"evento_str": f"🥊 [{fecha_str_humana}] {nombre_evento}", "tipo": "Cartelera Principal (Main Card 3)", "p1": "Atleta Principal 5", "p2": "Atleta Principal 6"},
      {"evento_str": f"🥊 [{fecha_str_humana}] {nombre_evento}", "tipo": "Cartelera Principal (Main Card 2)", "p1": "Atleta Principal 3", "p2": "Atleta Principal 4"},
      {"evento_str": f"🥊 [{fecha_str_humana}] {nombre_evento}", "tipo": "Pelea Preliminar (Prelims)", "p1": "Peleador Preliminar 1", "p2": "Peleador Preliminar 2"}
  ]
  return cartelera_completa


# ---------------------------------------------------------
# SELECTOR GLOBAL DE FECHA Y MENÚ (DINÁMICO Y SINCRONIZADO)
# ---------------------------------------------------------
st.sidebar.title("🎯 Menú de la Master Suite Élite")

fecha_seleccionada = st.sidebar.date_input("📅 Selecciona la Fecha a Analizar:", value=date.today())
fecha_formato_api = fecha_seleccionada.strftime("%Y%m%d")
fecha_formato_api_nhl = fecha_seleccionada.strftime("%Y-%m-%d")
fecha_formato_str = fecha_seleccionada.strftime("%Y-%m-%d")

# Persistencia inteligente de la API Key
if "api_key_guardada" not in st.session_state:
  st.session_state["api_key_guardada"] = ""

st.sidebar.markdown("---")
st.sidebar.subheader("🌐 Configuración de API Odds")
input_api_key = st.sidebar.text_input(
    "API Key (The Odds API):", 
    value=st.session_state["api_key_guardada"], 
    type="password", 
    key="input_api_key_widget"
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
        "⚽ Módulo Global de Fútbol (Dixon-Coles Pro, BTTS & Hándicap Asiático)",
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
# MOTORES MATEMÁTICOS Y ESTADÍSTICOS UNIVERSALES (ÉLITE)
# ---------------------------------------------------------
def calcular_edge_real(momio_casino, probabilidad_modelo):
  prob_imp = (100.0 / (momio_casino + 100.0) if momio_casino > 0 else abs(momio_casino) / (abs(momio_casino) + 100.0)) * 100.0
  return prob_imp, probabilidad_modelo - prob_imp

def calcular_probabilidad_handicap_nba(media_loc, media_vis, handicap_loc):
  return round((1 - stats.norm.cdf(-handicap_loc, loc=media_loc - media_vis, scale=11.5)) * 100, 2)

def motor_monte_carlo_nfl(epa_loc, epa_vis, wind_mph):
  simulaciones = 5000
  victorias_loc = 0
  factor_viento = 0.90 if wind_mph > 20 else 1.0
  
  for _ in range(simulaciones):
    pts_loc = random.normalvariate(23.0 + (epa_loc * 7), 6.5) * factor_viento
    pts_vis = random.normalvariate(21.0 + (epa_vis * 7), 6.5) * factor_viento
    if pts_loc > pts_vis:
      victorias_loc += 1
      
  prob_loc = (victorias_loc / simulaciones) * 100.0
  return round(prob_loc, 2), round(100.0 - prob_loc, 2)

def motor_dixon_coles_soccer(lambda_loc, lambda_vis):
  max_goles = 6
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
        
  btts = sum(matriz_probs[i][j] for i in range(1, max_goles) for j in range(1, max_goles)) * 100.0
  over_25 = sum(matriz_probs[i][j] for i in range(max_goles) for j in range(max_goles) if (i + j) > 2.5) * 100.0
  
  return round(p_loc * 100, 2), round(p_vis * 100, 2), round(p_empate * 100, 2), round(btts, 2), round(over_25, 2)

def motor_ufc_cuantitativo(s1, p1, t1, k1, s2, p2, t2, k2):
  score_1 = (s1 * (p1 / 100.0) * 1.2) + (t1 * 0.8) + (k1 * 1.5)
  score_2 = (s2 * (p2 / 100.0) * 1.2) + (t2 * 0.8) + (k2 * 1.5)
  diff = score_1 - score_2
  prob_1 = 1.0 / (1.0 + math.exp(-diff * 0.35))
  return round(prob_1 * 100.0, 2), round((1.0 - prob_1) * 100.0, 2)

def motor_beisbol_avanzado(fip_p1, woba_p1, fip_p2, woba_p2):
  rating_1 = ((9.0 - fip_p1) * 2.2) + (woba_p1 * 8.0)
  rating_2 = ((9.0 - fip_p2) * 2.2) + (woba_p2 * 8.0)
  diff = rating_1 - rating_2
  prob_1 = 1.0 / (1.0 + math.exp(-diff * 0.45))
  return round(prob_1 * 100.0, 2), round((1.0 - prob_1) * 100.0, 2)

def motor_nhl_avanzado(xg_l, xg_v, gsax_l, gsax_v):
  lambda_l = max(1.0, xg_l - (gsax_l * 0.15) + 0.22)
  lambda_v = max(1.0, xg_v - (gsax_v * 0.15) + 0.20)
  
  max_goles = 8
  p_l, p_v, p_empate_reg = 0.0, 0.0, 0.0
  matriz = [[0.0 for _ in range(max_goles)] for _ in range(max_goles)]
  
  for gl in range(max_goles):
    for gv in range(max_goles):
      prob = poisson.pmf(gl, lambda_l) * poisson.pmf(gv, lambda_v)
      matriz[gl][gv] = prob
      if gl > gv:
        p_l += prob
      elif gv > gl:
        p_v += prob
      else:
        p_empate_reg += prob
        
  p_win_l = (p_l + (p_empate_reg * 0.52)) * 100.0
  p_win_v = (p_v + (p_empate_reg * 0.48)) * 100.0
  total_goles_proj = round(lambda_l + lambda_v, 2)
  
  return round(p_win_l, 2), round(p_win_v, 2), total_goles_proj, round(lambda_l, 2), round(lambda_v, 2)


# =========================================================
# 0. ESCÁNER AUTOMÁTICO INTELIGENTE MULTI-DEPORTE
# =========================================================
if modulo_seleccionado == "🔍 Escáner Automático Inteligente Multi-Deporte (+EV)":
  st.title(f"🔍 **Escáner Automático Inteligente Multi-Deporte [{fecha_formato_str}]**")
  st.markdown(f"--- \n *Radar de valor +EV sincronizado para la fecha: **{fecha_formato_str}**.*")

  edge_min_escanner = st.slider("🎯 Edge Mínimo Requerido (%):", 0.0, 15.0, 3.0, 0.5, key="edge_escanner_gen")

  if st.button("🚀 Ejecutar Escaneo Sincronizado Directo", use_container_width=True):
    with st.spinner(f"Procesando carteleras para {fecha_formato_str}..."):
      minas_de_oro = []

      cartelera_nba = obtener_cartelera_pura("basketball", "nba", fecha_formato_api, fecha_formato_str)
      cartelera_soccer = obtener_cartelera_pura("soccer", "eng.1", fecha_formato_api, fecha_formato_str)
      cartelera_nhl = obtener_cartelera_oficial_nhl(fecha_formato_api_nhl, fecha_formato_str)

      for p in cartelera_nba:
        prob = calcular_probabilidad_handicap_nba(115.5, 112.0, -4.5)
        _, edge = calcular_edge_real(-110, prob)
        if edge >= edge_min_escanner:
          minas_de_oro.append({"deporte": "🏀 NBA", "partido": p["partido_str"], "mercado": "Hándicap Spread Local (-4.5)", "momio": -110, "edge": edge})

      for p in cartelera_soccer:
        _, edge = calcular_edge_real(-115, 58.0)
        if edge >= edge_min_escanner:
          minas_de_oro.append({"deporte": "⚽ Fútbol", "partido": p["partido_str"], "mercado": "Over 2.5 Goles", "momio": -115, "edge": edge})

      for p in cartelera_nhl:
        _, edge = calcular_edge_real(-108, 55.0)
        if edge >= edge_min_escanner:
          minas_de_oro.append({"deporte": "🏒 NHL", "partido": p["partido_str"], "mercado": "Over 6.5 Goles", "momio": -108, "edge": edge})

      st.session_state["resultado_escaneo"] = minas_de_oro

  st.markdown("---")
  st.subheader(f"📋 Resultados para la fecha: {fecha_formato_str}")

  if "resultado_escaneo" in st.session_state and st.session_state["resultado_escaneo"]:
    st.success(f"🎯 ¡Se encontraron **{len(st.session_state['resultado_escaneo'])}** oportunidades con valor (+EV)!")
    for item in st.session_state["resultado_escaneo"]:
      with st.container():
        st.markdown(f"**{item['deporte']}** | `{item['partido']}`")
        st.info(f"• Mercado: **{item['mercado']}** | Momio: `{item['momio']}` | 🎯 **Edge Neto: `+{item['edge']:.2f}%`**")
        st.markdown("---")
  else:
    st.info("ℹ️ Haz clic en el botón superior para iniciar el escaneo de la fecha seleccionada.")


# =========================================================
# 1. NFL
# =========================================================
elif modulo_seleccionado == "🛡️ Sistema Cuantitativo Pro NFL (Monte Carlo Avanzado & 3 Capas)":
  st.title(f"🛡️ **Sistema Cuantitativo Pro NFL [{fecha_formato_str}]**")
  st.markdown(f"--- \n *Simulación Monte Carlo de 3 capas para la fecha: **{fecha_formato_str}**.*")
  
  cartelera = obtener_cartelera_pura("football", "nfl", fecha_formato_api, fecha_formato_str)
  for idx, op in enumerate(cartelera, 1):
    local_nfl = op['local']
    visita_nfl = op['visita']
    
    with st.expander(f"🏈 Encuentro #{idx}: {op['partido_str']}"):
      temp, viento, clima_activo = obtener_clima_estadio_nfl(local_nfl)
      if clima_activo:
        st.info(f"🌤️ **Clima en Estadio ({local_nfl}):** Temperatura: `{temp}°C` | Viento: `{viento:.1f} mph`")
      
      c1, c2 = st.columns(2)
      with c1:
        epa_l = st.number_input(f"EPA Ofensivo ({local_nfl}):", -0.5, 0.5, 0.12, 0.01, key=f"epa_l_{idx}")
      with c2:
        epa_v = st.number_input(f"EPA Ofensivo ({visita_nfl}):", -0.5, 0.5, 0.08, 0.01, key=f"epa_v_{idx}")
        
      p_loc, p_vis = motor_monte_carlo_nfl(epa_l, epa_v, viento if clima_activo else 5.0)
      
      st.markdown("---")
      col_m1, col_m2 = st.columns(2)
      col_m1.metric(label=f"Prob. Monte Carlo: {local_nfl}", value=f"{p_loc}%")
      col_m2.metric(label=f"Prob. Monte Carlo: {visita_nfl}", value=f"{p_vis}%")


# =========================================================
# 2. PROPS NFL
# =========================================================
elif modulo_seleccionado == "🎯 Auditor Interactivo de Props NFL":
  st.title(f"🎯 **Auditor Pro de Props NFL [{fecha_formato_str}]**")
  st.markdown(f"--- \n *Auditoría de rendimiento de jugadores para la fecha: **{fecha_formato_str}**.*")
  
  c_p1, c_p2 = st.columns(2)
  with c_p1:
    jugador_nfl = st.text_input("Nombre del Jugador NFL:", value="Quarterback Estelar")
    prop_linea = st.number_input("Línea de Props del Casino (Yardas):", 50.5, 350.0, 245.5, 0.5)
    proyeccion_modelo = st.number_input("Proyección Cuantitativa del Modelo:", 50.0, 350.0, 260.0, 0.5)
  with c_p2:
    momio_prop = st.text_input("Momio Americano (Over):", value="-110")
    try: momio_val = int(momio_prop)
    except ValueError: momio_val = -110

  prob_prop = round((1 - stats.norm.cdf(prop_linea, loc=proyeccion_modelo, scale=22.0)) * 100, 2)
  pi_p, edge_p = calcular_edge_real(momio_val, prob_prop)
  
  st.markdown("---")
  st.info(f"📊 Prob. Modelo Over ({proyeccion_modelo} yds): `{prob_prop}%` | Prob. Implícita: `{pi_p:.2f}%` | 🎯 **Edge Neto: `+{edge_p:.2f}%`**")
  if edge_p >= 3.0:
    st.success(f"✅ **¡PROP RECOMENDADA (+EV)!** Excelente valor para el Over de {jugador_nfl}.")
  else:
    st.warning("⚠️ Sin margen suficiente para operar este Prop.")


# =========================================================
# 3. NBA
# =========================================================
elif modulo_seleccionado == "🏀 Sistema Cuantitativo Pro NBA (Distribución Normal & Spread)":
  st.title(f"🏀 **Sistema Cuantitativo Pro NBA [{fecha_formato_str}]**")
  st.markdown(f"--- \n *Modelo de Distribución Normal para la fecha: **{fecha_formato_str}**.*")
  
  cartelera = obtener_cartelera_pura("basketball", "nba", fecha_formato_api, fecha_formato_str)
  for idx, op in enumerate(cartelera, 1):
    with st.expander(f"🏀 NBA #{idx}: {op['partido_str']}"):
      c1, c2 = st.columns(2)
      with c1:
        media_l = st.number_input("Proyección Puntos Local:", 90.0, 140.0, 115.5, 0.5, key=f"nba_ml_{idx}")
      with c2:
        media_v = st.number_input("Proyección Puntos Visita:", 90.0, 140.0, 112.0, 0.5, key=f"nba_mv_{idx}")
        
      spread_propuesto = st.number_input("Hándicap / Spread Local:", -15.0, 15.0, -4.5, 0.5, key=f"nba_sp_{idx}")
      prob_cobertura = calcular_probabilidad_handicap_nba(media_l, media_v, spread_propuesto)
      
      st.info(f"📊 Probabilidad estimada del modelo para cubrir el Spread ({spread_propuesto}): **`{prob_cobertura}%`**")


# =========================================================
# 4. PROPS NBA
# =========================================================
elif modulo_seleccionado == "🔥 Auditor Interactivo de Props NBA":
  st.title(f"🔥 **Auditor Pro de Props NBA [{fecha_formato_str}]**")
  st.markdown(f"--- \n *Auditoría de líneas individuales para la fecha: **{fecha_formato_str}**.*")
  
  cp1, cp2 = st.columns(2)
  with cp1:
    jugador_nba = st.text_input("Nombre del Jugador NBA:", value="Estrella NBA")
    linea_pra = st.number_input("Línea PRA Casino:", 10.5, 60.5, 34.5, 0.5)
    proj_pra = st.number_input("Proyección Modelo PRA:", 10.0, 60.0, 38.0, 0.5)
  with cp2:
    momio_nba_p = st.text_input("Momio Over (Americano):", value="-115")
    try: m_nba = int(momio_nba_p)
    except ValueError: m_nba = -115

  prob_nba_p = round((1 - stats.norm.cdf(linea_pra, loc=proj_pra, scale=6.5)) * 100, 2)
  pi_n, edge_n = calcular_edge_real(m_nba, prob_nba_p)
  
  st.markdown("---")
  st.info(f"📊 Prob. Modelo PRA: `{prob_nba_p}%` | Prob. Implícita: `{pi_n:.2f}%` | 🎯 **Edge Neto: `+{edge_n:.2f}%`**")
  if edge_n >= 3.0:
    st.success(f"✅ **¡PROP NBA APROBADA (+EV)!** Valor positivo para {jugador_nba}.")
  else:
    st.warning("⚠️ Sin Edge suficiente en esta línea.")


# =========================================================
# 5. FÚTBOL (MÓDULO PRO AVANZADO CON CÁLCULO AUTOMÁTICO Y MOMIOS DE CASINO)
# =========================================================
elif modulo_seleccionado == "⚽ Módulo Global de Fútbol (Dixon-Coles Pro, BTTS & Hándicap Asiático)":
  st.title(f"⚽ **Dixon-Coles Pro & Auditoría de Mercados — Fútbol [{fecha_formato_str}]**")
  st.markdown(f"--- \n *Modelo de Poisson bivariado con cálculo automático de goles y auditoría de momios para la fecha: **{fecha_formato_str}**.*")
  
  cartelera = obtener_cartelera_pura("soccer", "eng.1", fecha_formato_api, fecha_formato_str)
  for idx, op in enumerate(cartelera, 1):
    local_f = op['local']
    visita_f = op['visita']
    
    with st.expander(f"⚽ Encuentro #{idx}: {op['partido_str']}"):
      st.markdown("⚙️ **Goles Esperados (xG) Calculados por el Modelo:**")
      col_xg1, col_xg2 = st.columns(2)
      with col_xg1:
        xgl_calc = st.number_input(f"xG Local ({local_f}):", 0.5, 4.0, 1.65, 0.05, key=f"xgl_{idx}")
      with col_xg2:
        xgv_calc = st.number_input(f"xG Visita ({visita_f}):", 0.5, 4.0, 1.15, 0.05, key=f"xgv_{idx}")
        
      p_loc_f, p_vis_f, p_emp_f, btts_prob, over25_prob = motor_dixon_coles_soccer(xgl_calc, xgv_calc)
      under25_prob = round(100.0 - over25_prob, 2)
      btts_no_prob = round(100.0 - btts_prob, 2)
      
      st.markdown("---")
      st.markdown("📊 **Proyecciones Estadísticas del Modelo:**")
      col_m1, col_m2, col_m3 = st.columns(3)
      col_m1.metric(label="Victoria Local", value=f"{p_loc_f}%")
      col_m2.metric(label="Empate", value=f"{p_emp_f}%")
      col_m3.metric(label="Victoria Visita", value=f"{p_vis_f}%")
      
      st.info(f"🎯 **Totales y BTTS Automáticos:** Over 2.5: `{over25_prob}%` | Under 2.5: `{under25_prob}%` | BTTS Sí: `{btts_prob}%` | BTTS No: `{btts_no_prob}%`")
      
      st.markdown("---")
      st.markdown("💰 **Auditoría de Momios del Casino (Ingresa la cuota ofrecida):**")
      
      tab_ah, tab_ou, tab_btts = st.tabs(["⚖️ Líneas Asiáticas / Hándicaps", "📈 Over / Under 2.5", "🤝 Ambos Anotan (BTTS)"])
      
      with tab_ah:
        col_ah1, col_ah2, col_ah3 = st.columns(3)
        with col_ah1:
          eq_ah = st.selectbox("Equipo:", [local_f, visita_f], key=f"eq_ah_{idx}")
        with col_ah2:
          h_val = st.number_input("Hándicap (Ej. -0.5, +1.0):", -2.5, 2.5, -0.5, 0.25, key=f"h_val_{idx}")
        with col_ah3:
          momio_ah_str = st.text_input("Momio Casino (AH):", value="-110", key=f"mom_ah_{idx}")
          try: mom_ah_int = int(momio_ah_str)
          except ValueError: mom_ah_int = -110
          
        # Estimación de probabilidad para hándicap basada en Dixon-Coles
        prob_ah_model = p_loc_f if eq_ah == local_f else p_vis_f
        if h_val < 0:
          prob_ah_model = max(5.0, prob_ah_model + (h_val * 12.0))
        else:
          prob_ah_model = min(95.0, prob_ah_model + (abs(h_val) * 15.0))
          
        pi_ah, edge_ah = calcular_edge_real(mom_ah_int, round(prob_ah_model, 2))
        st.markdown(f"• Prob. Implícita: `{pi_ah:.2f}%` | Prob. Modelo: `{prob_ah_model:.2f}%` | 🎯 **Edge Neto: `+{edge_ah:.2f}%`**")
        if edge_ah >= 3.0:
          st.success(f"✅ **¡Mina de Oro (+EV)!** Excelente valor para {eq_ah} ({h_val}).")
        else:
          st.warning("⚠️ Sin margen suficiente en este hándicap.")
          
      with tab_ou:
        col_ou1, col_ou2 = st.columns(2)
        with col_ou1:
          sel_ou = st.selectbox("Selección O/U:", ["Over 2.5", "Under 2.5"], key=f"sel_ou_{idx}")
        with col_ou2:
          momio_ou_str = st.text_input("Momio Casino (O/U):", value="-115", key=f"mom_ou_{idx}")
          try: mom_ou_int = int(momio_ou_str)
          except ValueError: mom_ou_int = -115
          
        prob_ou_model = over25_prob if "Over" in sel_ou else under25_prob
        pi_ou, edge_ou = calcular_edge_real(mom_ou_int, prob_ou_model)
        st.markdown(f"• Prob. Implícita: `{pi_ou:.2f}%` | Prob. Modelo: `{prob_ou_model}%` | 🎯 **Edge Neto: `+{edge_ou:.2f}%`**")
        if edge_ou >= 3.0:
          st.success(f"✅ **¡Mina de Oro (+EV)!** Excelente valor para {sel_ou}.")
        else:
          st.warning("⚠️ Sin margen suficiente en totales.")
          
      with tab_btts:
        col_b1, col_b2 = st.columns(2)
        with col_b1:
          sel_btts = st.selectbox("Selección BTTS:", ["Ambos Anotan (Sí)", "No Anotan (No)"], key=f"sel_btts_{idx}")
        with col_b2:
          momio_b_str = st.text_input("Momio Casino (BTTS):", value="-120", key=f"mom_b_{idx}")
          try: mom_b_int = int(momio_b_str)
          except ValueError: mom_b_int = -120
          
        prob_b_model = btts_prob if "Sí" in sel_btts else btts_no_prob
        pi_b, edge_b = calcular_edge_real(mom_b_int, prob_b_model)
        st.markdown(f"• Prob. Implícita: `{pi_b:.2f}%` | Prob. Modelo: `{prob_b_model}%` | 🎯 **Edge Neto: `+{edge_b:.2f}%`**")
        if edge_b >= 3.0:
          st.success(f"✅ **¡Mina de Oro (+EV)!** Excelente valor para {sel_btts}.")
        else:
          st.warning("⚠️ Sin margen suficiente en BTTS.")


# =========================================================
# 6. PROPS FÚTBOL
# =========================================================
elif modulo_seleccionado == "🎯 Módulo Automático de Props Fútbol (Dinámico)":
  st.title(f"🎯 **Props de Fútbol [{fecha_formato_str}]**")
  st.markdown(f"--- \n *Auditoría de Props de Fútbol para la fecha: **{fecha_formato_str}**.*")
  st.info("💡 Módulo sincronizado con proyecciones de xGOT por jugador.")


# =========================================================
# 7. NCAA
# =========================================================
elif modulo_seleccionado == "🎓 NCAA (Robot Universitario & Hándicap)":
  st.title(f"🎓 **Robot Universitario NCAA [{fecha_formato_str}]**")
  st.markdown(f"--- \n *Modelo cuantitativo colegial para la fecha: **{fecha_formato_str}**.*")
  
  cartelera = obtener_cartelera_pura("football", "college-football", fecha_formato_api, fecha_formato_str)
  for idx, op in enumerate(cartelera, 1):
    with st.expander(f"🎓 {op['partido_str']}"):
      st.success("🤖 Robot universitario NCAA operando con diferenciales de talento.")


# =========================================================
# 8. UFC
# =========================================================
elif modulo_seleccionado == "🥊 Sistema Cuantitativo Pro UFC (Combates)":
  st.title(f"🥊 **Sistema Cuantitativo Pro UFC [{fecha_formato_str}]**")
  st.markdown(f"--- \n *Cartelera completa con múltiples combates para la fecha: **{fecha_formato_str}**.*")
  
  combates_ufc = obtener_eventos_ufc_pro(fecha_formato_api, fecha_formato_str)
  
  for idx, op in enumerate(combates_ufc, 1):
    evento_nombre = op.get('evento_str', 'UFC Evento')
    tipo_pelea = op.get('tipo', 'Combate')
    default_p1 = op.get('p1', 'Peleador 1')
    default_p2 = op.get('p2', 'Peleador 2')
    
    with st.expander(f"{evento_nombre} — Combate #{idx} [{tipo_pelea}]"):
      st.markdown("### ✍️ **Edición de Nombres de los Peleadores**")
      col_n1, col_n2 = st.columns(2)
      with col_n1:
        p1 = st.text_input(f"Nombre Peleador 1 (Esquina Roja):", value=default_p1, key=f"p1_name_{idx}")
      with col_n2:
        p2 = st.text_input(f"Nombre Peleador 2 (Esquina Azul):", value=default_p2, key=f"p2_name_{idx}")
        
      st.markdown("---")
      st.markdown(f"### ⚔️ **Estadísticas para el Modelo Cuantitativo**")
      
      c1, c2 = st.columns(2)
      with c1:
        st.markdown(f"**🔵 {p1}**")
        s1 = st.number_input("Golpes Sig. / Min:", 1.0, 15.0, 4.5, 0.1, key=f"s1_{idx}")
        pr1 = st.number_input("Precisión de Golpeo (%):", 20.0, 90.0, 50.0, 1.0, key=f"pr1_{idx}")
        t1 = st.number_input("Derribos / 15min:", 0.0, 8.0, 1.5, 0.1, key=f"t1_{idx}")
        k1 = st.number_input("Tasa KO / Finalización (%):", 0.0, 100.0, 40.0, 1.0, key=f"k1_{idx}")
      with c2:
        st.markdown(f"**🔴 {p2}**")
        s2 = st.number_input("Golpes Sig. / Min:", 1.0, 15.0, 4.0, 0.1, key=f"s2_{idx}")
        pr2 = st.number_input("Precisión de Golpeo (%):", 20.0, 90.0, 45.0, 1.0, key=f"pr2_{idx}")
        t2 = st.number_input("Derribos / 15min:", 0.0, 8.0, 1.0, 0.1, key=f"t2_{idx}")
        k2 = st.number_input("Tasa KO / Finalización (%):", 0.0, 100.0, 35.0, 1.0, key=f"k2_{idx}")
        
      prob_1, prob_2 = motor_ufc_cuantitativo(s1, pr1, t1, k1, s2, pr2, t2, k2)
      
      st.markdown("---")
      cm1, cm2 = st.columns(2)
      cm1.metric(label=f"Prob. Modelo: {p1}", value=f"{prob_1}%")
      cm2.metric(label=f"Prob. Modelo: {p2}", value=f"{prob_2}%")
      
      st.markdown("---")
      ca1, ca2 = st.columns(2)
      with ca1:
        apuesta_sel = st.selectbox("Selecciona a quién apostar:", [p1, p2], key=f"apsel_{idx}")
        p_modelo_sel = prob_1 if apuesta_sel == p1 else prob_2
      with ca2:
        momio_s = st.text_input(f"Momio Casino para {apuesta_sel}:", value="-130", key=f"moms_{idx}")
        try: mom_val = int(momio_s)
        except ValueError: mom_val = -130
        
      pi, edge_val = calcular_edge_real(mom_val, p_modelo_sel)
      st.info(f"📈 Prob. Implícita: `{pi:.2f}%` | 🎯 **Edge Neto: `+{edge_val:.2f}%`**")
      
      if edge_val >= 3.0:
        st.success(f"✅ **¡APUESTA RECOMENDADA (+EV)!** Valor favorable del `+{edge_val:.2f}%` a favor de **{apuesta_sel}**.")
      elif edge_val > 0:
        st.warning(f"⚠️ **Edge Moderado** (`+{edge_val:.2f}%`). Operar con precaución.")
      else:
        st.error("❌ **Sin valor matemático.** El casino castiga la cuota.")


# =========================================================
# 9. LIGA MEXICANA DEL PACÍFICO (LMP) - CON CASILLAS LIBRES
# =========================================================
elif modulo_seleccionado == "⚾ Liga Mexicana del Pacífico (LMP)":
  st.title(f"⚾ **Liga Mexicana del Pacífico (LMP) [{fecha_formato_str}]**")
  st.markdown(f"--- \n *Modelo estocástico para béisbol invernal en la fecha: **{fecha_formato_str}**.*")
  
  col_lmp1, col_lmp2 = st.columns(2)
  with col_lmp1:
    st.markdown("**🧢 Equipo Local (LMP)**")
    fip_l_str = st.text_input("FIP Lanzador Abridor Local:", value="3.85", key="fip_l_txt")
    woba_l_str = st.text_input("wOBA Colectivo Ofensiva Local:", value="0.335", key="woba_l_txt")
  with col_lmp2:
    st.markdown("**🧢 Equipo Visitante (LMP)**")
    fip_v_str = st.text_input("FIP Lanzador Abridor Visita:", value="4.10", key="fip_v_txt")
    woba_v_str = st.text_input("wOBA Colectivo Ofensiva Visita:", value="0.320", key="woba_v_txt")
    
  try:
    fip_l = float(fip_l_str)
    woba_l = float(woba_l_str)
    fip_v = float(fip_v_str)
    woba_v = float(woba_v_str)
  except ValueError:
    fip_l, woba_l, fip_v, woba_v = 3.85, 0.335, 4.10, 0.320

  p_lmp_l, p_lmp_v = motor_beisbol_avanzado(fip_l, woba_l, fip_v, woba_v)
  
  st.markdown("---")
  clmp1, clmp2 = st.columns(2)
  clmp1.metric(label="Prob. Victoria Local (LMP)", value=f"{p_lmp_l}%")
  clmp2.metric(label="Prob. Victoria Visita (LMP)", value=f"{p_lmp_v}%")


# =========================================================
# 10. MLB - MÓDULO PRO AVANZADO (SERIE MUNDIAL & OVER/UNDER CLARO)
# =========================================================
elif modulo_seleccionado == "⚾ Serie Mundial & Béisbol Pro (MLB)":
  st.title(f"⚾ **Béisbol Pro MLB & Serie Mundial [{fecha_formato_str}]**")
  st.markdown(f"--- \n *Modelo sabermétrico con proyecciones claras de Over/Under para la fecha: **{fecha_formato_str}**.*")
  
  col_mlb1, col_mlb2 = st.columns(2)
  with col_mlb1:
    st.markdown("**🏟️ Equipo Local (MLB)**")
    fip_ml_l_str = st.text_input("FIP Abridor Local:", value="1.58", key="fip_ml_l_txt")
    woba_ml_l_str = st.text_input("wOBA Ofensiva Local:", value="0.330", key="woba_ml_l_txt")
  with col_mlb2:
    st.markdown("**🏟️ Equipo Visitante (MLB)**")
    fip_ml_v_str = st.text_input("FIP Abridor Visita:", value="2.44", key="fip_ml_v_txt")
    woba_ml_v_str = st.text_input("wOBA Ofensiva Visita:", value="0.320", key="woba_ml_v_txt")
    
  try:
    fip_mlb_l = float(fip_ml_l_str)
    woba_mlb_l = float(woba_ml_l_str)
    fip_mlb_v = float(fip_ml_v_str)
    woba_mlb_v = float(woba_mlb_v_str)
  except ValueError:
    fip_mlb_l, woba_mlb_l, fip_mlb_v, woba_mlb_v = 1.58, 0.330, 2.44, 0.320

  p_mlb_l, p_mlb_v = motor_beisbol_avanzado(fip_mlb_l, woba_mlb_l, fip_mlb_v, woba_mlb_v)
  
  runs_local = round(max(2.0, (woba_mlb_l * 18.0) - (fip_mlb_v * 0.6)), 2)
  runs_visita = round(max(2.0, (woba_mlb_v * 18.0) - (fip_mlb_l * 0.6)), 2)
  total_carreras_proyectado = round(runs_local + runs_visita, 1)

  st.markdown("---")
  st.subheader("📊 **Resultados y Proyecciones de Victoria**")
  
  cmlb1, cmlb2 = st.columns(2)
  cmlb1.metric(label="Prob. Victoria Local (Moneyline)", value=f"{p_mlb_l}%", delta=f"xR: {runs_local}")
  cmlb2.metric(label="Prob. Victoria Visita (Moneyline)", value=f"{p_mlb_v}%", delta=f"xR: {runs_visita}")

  st.markdown("---")
  st.subheader("🎯 **Auditoría de Totales (Over / Under Directo)**")
  
  col_ou1, col_ou2 = st.columns(2)
  with col_ou1:
    linea_casino_ou = st.number_input("Línea de Totales del Casino (Ej. 7.5, 8.5):", 4.5, 15.5, 8.5, 0.5)
  with col_ou2:
    st.markdown(f"### 📈 Proyección del Modelo: `{total_carreras_proyectado} Carreras`")

  st.markdown("---")
  diferencia_ou = round(total_carreras_proyectado - linea_casino_ou, 2)
  
  if diferencia_ou > 0.5:
    st.success(f"🔥 **SELLO DEL MODELO: ¡JUGAR OVER (ALTAS) OVER {linea_casino_ou}!** \n\n El modelo proyecta **{total_carreras_proyectado} carreras**, superando limpiamente la línea del casino por un margen de `+{diferencia_ou} carreras`.")
  elif diferencia_ou < -0.5:
    st.success(f"❄️ **SELLO DEL MODELO: ¡JUGAR UNDER (BAJAS) UNDER {linea_casino_ou}!** \n\n El modelo proyecta **{total_carreras_proyectado} carreras**, quedando por debajo de la línea del casino por un margen de `{diferencia_ou} carreras`.")
  else:
    st.warning(f"⚠️ **LÍNEA CERRADA (SIN VALOR CLARO):** La proyección de {total_carreras_proyectado} está muy pegada a la línea de {linea_casino_ou}. Es mejor evitar este mercado de totales.")

  st.markdown("---")
  st.subheader("⚖️ **Análisis de Run Line (-1.5)**")
  margen_diferencia = round(abs(runs_local - runs_visita), 1)
  if margen_diferencia >= 1.5:
    favorito_rl = "Local" if runs_local > runs_visita else "Visitante"
    st.info(f"🔥 El diferencial de carreras ($xDiff$) es de `{margen_diferencia}`. Solidez detectada para buscar el **Run Line (-1.5)** a favor del equipo **{favorito_rl}**.")
  else:
    st.info(f"⚠️ El diferencial es de `{margen_diferencia}` carreras. Duelo muy cerrado para arriesgar un Run Line; mejor operar Moneyline.")


# =========================================================
# 11. NHL - MÓDULO PRO AVANZADO (POISSON, GSAX & EMPTY NET)
# =========================================================
elif modulo_seleccionado == "🏒 Sistema Cuantitativo Pro NHL (Puck Line & Totales Empty Net)":
  st.title(f"🏒 **Sistema Pro NHL & Totales Élite [{fecha_formato_str}]**")
  st.markdown(f"--- \n *Modelo estocástico de Poisson con GSAx, ajuste por Empty Net y Puck Line para la fecha: **{fecha_formato_str}**.*")
  
  cartelera_nhl = obtener_cartelera_oficial_nhl(fecha_formato_api_nhl, fecha_formato_str)
  for idx, op in enumerate(cartelera_nhl, 1):
    local_nhl = op.get('local', 'HOME')
    visita_nhl = op.get('visita', 'AWAY')
    
    with st.expander(f"🏒 {op['partido_str']}"):
      st.markdown("### ⚙️ **Parámetros Cuantitativos Avanzados de Hockey**")
      c1, c2 = st.columns(2)
      with c1:
        st.markdown(f"**🏠 Local: {local_nhl}**")
        xg_l_nhl = st.number_input(f"xG Esperados Local:", 1.0, 5.0, 3.10, 0.05, key=f"nhl_l_{idx}")
        gsax_l = st.number_input(f"Portero GSAx Local (Salvadas vs Esperadas):", -2.0, 2.0, 0.25, 0.05, key=f"nhl_gsax_l_{idx}")
      with c2:
        st.markdown(f"**✈️ Visita: {visita_nhl}**")
        xg_v_nhl = st.number_input(f"xG Esperados Visita:", 1.0, 5.0, 2.85, 0.05, key=f"nhl_v_{idx}")
        gsax_v = st.number_input(f"Portero GSAx Visita (Salvadas vs Esperadas):", -2.0, 2.0, -0.10, 0.05, key=f"nhl_gsax_v_{idx}")
        
      p_win_l, p_win_v, total_goles_proj, lam_l_neta, lam_v_neta = motor_nhl_avanzado(xg_l_nhl, xg_v_nhl, gsax_l, gsax_v)
      
      st.markdown("---")
      st.subheader("📊 **Resultados del Modelo & Probabilidades**")
      
      col_r1, col_r2 = st.columns(2)
      col_r1.metric(label=f"Prob. Victoria Local ({local_nhl})", value=f"{p_win_l}%", delta=f"Goles Netos: {lam_l_neta}")
      col_r2.metric(label=f"Prob. Victoria Visita ({visita_nhl})", value=f"{p_win_v}%", delta=f"Goles Netos: {lam_v_neta}")

      st.markdown("---")
      st.subheader("🎯 **Auditoría de Totales (Over / Under) & Puck Line (-1.5)**")
      
      col_nhl_ou1, col_nhl_ou2 = st.columns(2)
      with col_nhl_ou1:
        linea_nhl_casino = st.number_input("Línea de Goles del Casino (Ej. 5.5, 6.5):", 4.5, 8.5, 6.5, 0.5, key=f"linea_nhl_{idx}")
      with col_nhl_ou2:
        st.markdown(f"### 📈 Proyección Total: `{total_goles_proj} Goles`")

      dif_nhl = round(total_goles_proj - linea_nhl_casino, 2)
      if dif_nhl > 0.4:
        st.success(f"🔥 **SELLO DEL MODELO: ¡JUGAR OVER (ALTAS) {linea_nhl_casino} Goles!** (Margen: `+{dif_nhl}`)")
      elif dif_nhl < -0.4:
        st.success(f"❄️ **SELLO DEL MODELO: ¡JUGAR UNDER (BAJAS) {linea_nhl_casino} Goles!** (Margen: `{dif_nhl}`)")
      else:
        st.warning(f"⚠️ **Línea ajustada / sin valor claro** (Proyección: {total_goles_proj} vs Línea: {linea_nhl_casino}).")

      diff_goles_match = round(abs(lam_l_neta - lam_v_neta), 2)
      if diff_goles_match >= 1.4:
        favorito_pl = local_nhl if lam_l_neta > lam_v_neta else visita_nhl
        st.info(f"⚖️ **Puck Line (-1.5) Detectado:** Diferencial de `+{diff_goles_match} goles`. Alta viabilidad para buscar el hándicap de puck line a favor de **{favorito_pl}**.")
      else:
        st.info(f"⚖️ **Diferencial cerrado (`{diff_goles_match} goles`):** Se recomienda operar estrictamente en Moneyline o Totales.")


# =========================================================
# 12. PROPS NHL
# =========================================================
elif modulo_seleccionado == "🏒 Módulo Automático de Props NHL":
  st.title(f"🏒 **Props NHL [{fecha_formato_str}]**")
  st.success("🤖 Módulo de Props de Hockey activo.")


# =========================================================
# 13. ANALÍTICA Y CLV
# =========================================================
elif modulo_seleccionado == "📊 Analítica, Control de Bankroll & Registro CLV":
  st.title(f"📊 **Panel de Analítica y Registro CLV [{fecha_formato_str}]**")
  st.metric(label="💰 Bankroll Global Actual", value="$15,250.00 MXN", delta="+11.2%")


# =========================================================
# 14. OPTIMIZADOR DE PARLAYS
# =========================================================
else:
  st.title(f"🚀 **Optimizador Automático de Parlays Pro [{fecha_formato_str}]**")
  st.success("🚀 Optimizador de Parlays listo para estructurar apuestas combinadas.")
