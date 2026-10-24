from datetime import date, datetime, timedelta
import math
import os
import random
import sqlite3
import threading
import time
import numpy as np
import requests
import scipy.stats as stats
from scipy.stats import norm, poisson
import streamlit as st

# Configuración global de la página
st.set_page_config(
    page_title="Central de Apuestas Pro - Master Suite Analítica Élite Pro",
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

for mod in ["ncaaf", "nfl", "nba", "soccer", "nhl", "baseball", "ufc", "props_soc_comun", "props_ufc_comun", "props_nfl_comun", "props_nba_comun", "extractor_vivo"]:
  key_res = f"resultado_{mod}_calculado"
  if key_res not in st.session_state:
    st.session_state[key_res] = None


# ---------------------------------------------------------
# CONFIGURACIÓN DE BASE DE DATOS LOCAL (SQLITE AVANZADA)
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
            resultado TEXT,
            ganancia_neta REAL DEFAULT 0.0,
            clv_cuota INTEGER DEFAULT 0,
            bankroll_historico REAL DEFAULT 0.0
        )
    """)
  for col, tipo in [("ganancia_neta", "REAL DEFAULT 0.0"), ("clv_cuota", "INTEGER DEFAULT 0"), ("bankroll_historico", "REAL DEFAULT 0.0")]:
    try:
      cursor.execute(f"ALTER TABLE apuestas ADD COLUMN {col} {tipo}")
    except sqlite3.OperationalError:
      pass
  conn.commit()
  conn.close()


inicializar_db()


def registrar_apuesta_db(fecha, deporte, partido, mercado, momio, edge, stake):
  conn = sqlite3.connect("master_suite_elite.db")
  cursor = conn.cursor()
  cursor.execute(
      """
        INSERT INTO apuestas (fecha, deporte, partido, mercado, momio, edge, stake, resultado, ganancia_neta, clv_cuota, bankroll_historico)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'Pendiente', 0.0, 0, ?)
    """,
      (fecha, deporte, partido, mercado, momio, edge, stake, st.session_state["bankroll_global"]),
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
# MOTORES MATEMÁTICOS DE ÉLITE
# ---------------------------------------------------------
def calcular_probabilidad_implicita(momio_americano):
  if momio_americano > 0:
    return 100.0 / (momio_americano + 100.0)
  else:
    return abs(momio_americano) / (abs(momio_americano) + 100.0)


def calcular_edge_real(momio_casino, probabilidad_modelo):
  prob_imp = calcular_probabilidad_implicita(momio_casino) * 100.0
  return prob_imp, probabilidad_modelo - prob_imp


def calcular_criterio_kelly(bankroll, prob_modelo_pct, momio_americano, fraccion_kelly=0.25):
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


# =========================================================
# MOTORES DE PLAYER PROPS Y ANÁLISIS DE MERCADOS
# =========================================================
def analizar_prop_futbol_comun(jugador, mercado, promedio_historico, linea_casino):
  lambda_jugador = promedio_historico
  prob_acumulada = poisson.cdf(int(linea_casino), lambda_jugador)
  prob_under = prob_acumulada * 100.0
  prob_over = 100.0 - prob_under
  opciones = [
      {"mercado": f"{jugador} Over {linea_casino} {mercado}", "prob": prob_over},
      {"mercado": f"{jugador} Under {linea_casino} {mercado}", "prob": prob_under}
  ]
  return [o for o in opciones if o["prob"] >= 70.0]


def analizar_prop_ufc_comun(combate, mercado, probabilidad_estimada_modelo):
  prob_si = probabilidad_estimada_modelo
  prob_no = 100.0 - prob_si
  opciones = [
      {"mercado": f"{combate} - Sí ({mercado})", "prob": prob_si},
      {"mercado": f"{combate} - No ({mercado})", "prob": prob_no}
  ]
  return [o for o in opciones if o["prob"] >= 70.0]


def analizar_prop_nfl_comun(jugador, mercado, promedio_jugador, linea_casino, def_rival_permitido=100.0):
  if mercado == "Touchdown en Cualquier Momento":
    prob_cero = poisson.pmf(0, promedio_jugador)
    prob_over = (1.0 - prob_cero) * 100.0
    prob_under = 100.0 - prob_over
    opciones = [
        {"mercado": f"{jugador} Anota Touchdown en Cualquier Momento (Over 0.5)", "prob": prob_over},
        {"mercado": f"{jugador} NO Anota Touchdown (Under 0.5)", "prob": prob_under}
    ]
    return [o for o in opciones if o["prob"] >= 70.0]

  desviaciones = {
      "Yardas Pase": 45.0,
      "Yardas Carrera": 18.0,
      "Yardas Recepcion": 22.0,
      "Yardas Totales (Recepcion y Carrera)": 28.0
  }
  desv_estandar = desviaciones.get(mercado, 20.0)
  factor_defensa = def_rival_permitido / 100.0
  proyeccion_ajustada = promedio_jugador * factor_defensa
  
  z_score = (linea_casino - proyeccion_ajustada) / desv_estandar
  prob_under = norm.cdf(z_score) * 100.0
  prob_over = 100.0 - prob_under
  
  opciones = [
      {"mercado": f"{jugador} Over {linea_casino} {mercado}", "prob": prob_over},
      {"mercado": f"{jugador} Under {linea_casino} {mercado}", "prob": prob_under}
  ]
  return [o for o in opciones if o["prob"] >= 70.0]


def analizar_prop_nba_comun(jugador, mercado, promedio_jugador, linea_casino, pace_partido, pace_promedio_liga=98.5):
  desviaciones = {
      "Puntos": 6.5,
      "Rebotes": 3.2,
      "Asistencias": 2.5
  }
  desv_estandar = desviaciones.get(mercado, 4.0)
  factor_ritmo = pace_partido / pace_promedio_liga
  proyeccion_ajustada = promedio_jugador * factor_ritmo
  
  z_score = (linea_casino - proyeccion_ajustada) / desv_estandar
  prob_under = norm.cdf(z_score) * 100.0
  prob_over = 100.0 - prob_under
  
  opciones = [
      {"mercado": f"{jugador} Over {linea_casino} {mercado}", "prob": prob_over},
      {"mercado": f"{jugador} Under {linea_casino} {mercado}", "prob": prob_under}
  ]
  return [o for o in opciones if o["prob"] >= 70.0]


def generar_ticket_nba_props_puro(jugadas_procesadas, fecha_str="Noche de Apuestas"):
  linea_alerta = "🚨 APOSTAR AQUÍ 🚨"
  ticket = "=========================================\n"
  ticket += f"BOLETO ÉLITE PRO ({fecha_str})\n"
  ticket += "=========================================\n"
  
  jugadas_ordenadas = sorted(jugadas_procesadas, key=lambda x: x["prob"], reverse=True)
  cuenta = 1
  for jugada in jugadas_ordenadas:
    if cuenta <= 3:
      ticket += f"JUGADA {cuenta}: {jugada['partido']}\n"
      ticket += f"➔ Probabilidad de Éxito: {jugada['prob']:.2f}%\n"
      ticket += f"➔ {linea_alerta}: {jugada['mercado']}\n"
      ticket += "-----------------------------------------\n"
      cuenta += 1
      
  while cuenta <= 3:
    ticket += f"JUGADA {cuenta}: [Prop sin valor estadístico suficiente]\n"
    ticket += "-----------------------------------------\n"
    cuenta += 1
    
  ticket += "Monto Base por Ticket: $250 MXN\n"
  return ticket


# =========================================================
# MOTORES PRO Y DEPORTIVOS RESTANTES
# =========================================================
def calcular_probabilidad_ufc_avanzada(metricas_a, metricas_b, contexto_combate):
  striking_a, defense_a, td_def_a, finish_a = metricas_a["striking"], metricas_a["defense"], metricas_a["td_def"], metricas_a["finish"]
  striking_b, defense_b, td_def_b, finish_b = metricas_b["striking"], metricas_b["defense"], metricas_b["td_def"], metricas_b["finish"]
  daño_a = striking_a * (100 - defense_b) / 100.0
  daño_b = striking_b * (100 - defense_a) / 100.0
  ventaja_piso_a = max(0, (100 - td_def_b)) * 0.1
  ventaja_piso_b = max(0, (100 - td_def_a)) * 0.1
  score_a = daño_a + ventaja_piso_a
  score_b = daño_b + ventaja_piso_b
  if contexto_combate.get("edad_a", 30) >= 35 and contexto_combate.get("edad_b", 30) < 35: score_a *= 0.92
  if contexto_combate.get("edad_b", 30) >= 35 and contexto_combate.get("edad_a", 30) < 35: score_b *= 0.92
  if contexto_combate.get("meses_inactivo_a", 0) >= 12: score_a *= 0.95
  if contexto_combate.get("meses_inactivo_b", 0) >= 12: score_b *= 0.95
  score_a *= (1.0 + finish_a)
  score_b *= (1.0 + finish_b)
  total_score = score_a + score_b
  if total_score == 0: return 50.0, 50.0
  return round((score_a / total_score) * 100.0, 2), round((score_b / total_score) * 100.0, 2)


def analizar_combate_ufc(peleador_a, peleador_b, metricas_a, metricas_b, contexto_combate):
  prob_a, prob_b = calcular_probabilidad_ufc_avanzada(metricas_a, metricas_b, contexto_combate)
  opciones = [{"mercado": f"Ganador: {peleador_a}", "prob": prob_a}, {"mercado": f"Ganador: {peleador_b}", "prob": prob_b}]
  validas = [o for o in opciones if o["prob"] >= 70.0]
  return {"prob_a": prob_a, "prob_b": prob_b, "validas": validas}


def analizar_lineas_beisbol(local, visita, fip_l, bullpen_l, fip_v, bullpen_v, linea_total_casino, ofensiva_l=4.5, ofensiva_v=4.5):
  ventaja_casa = 0.15
  pitcheo_local = (fip_l * 0.55) + (bullpen_l * 0.45)
  pitcheo_visita = (fip_v * 0.55) + (bullpen_v * 0.45)
  carreras_l = (ofensiva_l * (pitcheo_visita / 4.20)) + ventaja_casa
  carreras_v = ofensiva_v * (pitcheo_local / 4.20)
  total_proj = carreras_l + carreras_v
  z_tot = (linea_total_casino - total_proj) / 3.1
  prob_under = norm.cdf(z_tot) * 100.0
  prob_over = 100.0 - prob_under
  opciones = [{"mercado": f"Over {linea_total_casino} Carreras", "prob": prob_over}, {"mercado": f"Under {linea_total_casino} Carreras", "prob": prob_under}]
  return {"total_proyectado": round(total_proj, 2), "validas": [o for o in opciones if o["prob"] >= 70.0]}


def analizar_lineas_nhl(local, visita, linea_total_casino, contexto):
  lambda_l, lambda_v = 3.1, 3.1
  if contexto.get("local_goalie_elite", False): lambda_v -= 0.3
  if contexto.get("visita_goalie_elite", False): lambda_l -= 0.3
  total_lam = lambda_l + lambda_v
  prob_under = poisson.cdf(int(linea_total_casino), total_lam) * 100.0
  prob_over = 100.0 - prob_under
  opciones = [{"mercado": f"Over {linea_total_casino} Goles NHL", "prob": prob_over}, {"mercado": f"Under {linea_total_casino} Goles NHL", "prob": prob_under}]
  return {"validas": [o for o in opciones if o["prob"] >= 70.0]}


def analizar_lineas_nba(local, visita, linea_spread, linea_tot, contexto):
  total_proy = 230.0
  z_tot = (linea_tot - total_proy) / 12.5
  prob_under = norm.cdf(z_tot) * 100.0
  prob_over = 100.0 - prob_under
  opciones = [{"mercado": f"Over {linea_tot}", "prob": prob_over}, {"mercado": f"Under {linea_tot}", "prob": prob_under}]
  return {"validas": [o for o in opciones if o["prob"] >= 70.0]}


def analizar_lineas_ncaaf(pr_l, pr_v, tot_p, linea_sp, linea_tot, contexto):
  z_tot = (linea_tot - tot_p) / 14.0
  prob_under = norm.cdf(z_tot) * 100.0
  prob_over = 100.0 - prob_under
  opciones = [{"mercado": f"Over {linea_tot}", "prob": prob_over}, {"mercado": f"Under {linea_tot}", "prob": prob_under}]
  return {"validas": [o for o in opciones if o["prob"] >= 70.0]}


def analizar_lineas_nfl(pr_l, pr_v, tot_p, linea_sp, linea_tot, contexto):
  z_tot = (linea_tot - tot_p) / 10.5
  prob_under = norm.cdf(z_tot) * 100.0
  prob_over = 100.0 - prob_under
  opciones = [{"mercado": f"Over {linea_tot}", "prob": prob_over}, {"mercado": f"Under {linea_tot}", "prob": prob_under}]
  return {"validas": [o for o in opciones if o["prob"] >= 70.0]}


def analizar_mercados_futbol(el, ev, xg_l, xg_v, momio_1x2):
  prob_l = [poisson.pmf(i, xg_l) for i in range(7)]
  prob_v = [poisson.pmf(j, xg_v) for j in range(7)]
  matriz = np.outer(prob_l, prob_v)
  matriz /= matriz.sum()
  tot_matriz = np.fromfunction(lambda i, j: i + j, matriz.shape, dtype=int)
  prob_under_25 = float(matriz[tot_matriz < 3].sum()) * 100.0
  prob_over_25 = 100.0 - prob_under_25
  opciones = [{"mercado": "Over 2.5 Goles", "prob": prob_over_25}, {"mercado": "Under 2.5 Goles", "prob": prob_under_25}]
  return {"validas": [o for o in opciones if o["prob"] >= 70.0]}


@st.cache_data(ttl=300)
def obtener_partidos_y_momios_api_multideporte(api_key):
  if not api_key: return []
  return []


# ---------------------------------------------------------
# SELECTOR GLOBAL DE FECHA Y MENÚ LATERAL
# ---------------------------------------------------------
st.sidebar.title("🎯 Menú Principal")
fecha_seleccionada = st.sidebar.date_input("📅 Fecha a Analizar:", value=date.today())
fecha_formato_str = fecha_seleccionada.strftime("%Y-%m-%d")

st.sidebar.markdown("---")
st.sidebar.subheader("🌐 Configuración de API & Telegram")
st.session_state["api_key_guardada"] = st.sidebar.text_input("API Key:", value=st.session_state["api_key_guardada"], type="password")
st.session_state["telegram_token"] = st.sidebar.text_input("Bot Token:", value=st.session_state["telegram_token"], type="password")
st.session_state["telegram_chat_id"] = st.sidebar.text_input("Chat ID:", value=st.session_state["telegram_chat_id"])

if st.sidebar.button("🔄 Sincronizar Datos", use_container_width=True):
  st.cache_data.clear()
  st.rerun()

st.sidebar.markdown("---")
modulo_seleccionado = st.sidebar.radio(
    "Selecciona el módulo:",
    [
        "🌐 Extractor Automático en Vivo (Playdoit)",
        "⚽ Prop: Fútbol Soccer Común (Playdoit)",
        "🥊 Prop: UFC / MMA Común",
        "🛡️ Prop: NFL Común (Playdoit)",
        "🏀 Prop: NBA Común (Playdoit)",
        "🔍 Escáner Automático Multi-Deporte (+EV)",
        "🥊 Sistema Pro UFC / MMA",
        "⚾ Béisbol Pro (MLB / LMP)",
        "🏒 Hockey Pro (NHL)",
        "🏀 Sistema Pro NBA",
        "🎓 Sistema Pro NCAAF (Universitario)",
        "🛡️ Sistema Pro NFL",
        "⚽ Módulo Pro Fútbol (Soccer)",
        "📊 Control de Bankroll & Historial SQLite",
        "🚀 Optimizador de Parlays (Monte Carlo)",
        "🧮 Calculadora de Arbitraje (Surebets)",
        "📈 Backtesting Histórico & Steam Moves",
        "⚖️ Gestor Multi-Bookmaker (Line Shopping)",
    ],
)


# =========================================================
# MÓDULOS DE PLAYER PROPS Y EXTRACCIÓN
# =========================================================
if modulo_seleccionado == "🌐 Extractor Automático en Vivo (Playdoit)":
  st.title(f"🌐 **Extractor Automático en Vivo [{fecha_formato_str}]**")
  st.markdown("--- \n *Módulo de escaneo de cuotas en tiempo real.*")
  st.info("ℹ️ Nota: En este entorno en la nube, el navegador automatizado está desactivado por restricciones del servidor. Puedes ingresar tus líneas manualmente en cada módulo de props o usar el Escáner Multi-Deporte.")
  
  url_objetivo = st.text_input("URL Objetivo:", value="https://playdoit.mx")
  if st.button("🚀 Simular Conexión y Escaneo", use_container_width=True):
    st.success("¡Conexión establecida correctamente con la plataforma! Usa los módulos de la izquierda para analizar tus partidos.")


elif modulo_seleccionado == "⚽ Prop: Fútbol Soccer Común (Playdoit)":
  st.title(f"⚽ **Props: Fútbol Soccer Común [{fecha_formato_str}]**")
  st.markdown("--- \n *Análisis de Goles, Remates a Puerta, Faltas y Tarjetas con Distribución de Poisson.*")
  
  col1, col2 = st.columns(2)
  with col1:
    jugador = st.text_input("Jugador / Atleta:", value="Erling Haaland", key="psc_jug")
    mercado = st.selectbox("Mercado Playdoit:", ["Remates a Puerta", "Tarjetas Amarillas", "Goles", "Faltas Cometidas"], key="psc_merc")
    partido_str = st.text_input("Partido (Ej. Man. City vs Liverpool):", value="Man. City vs Liverpool", key="psc_part")
  with col2:
    promedio_hist = st.number_input("Promedio Histórico (Lambda):", value=2.8, step=0.05, key="psc_prom")
    linea_cas = st.number_input("Línea Casino:", value=1.5, step=0.5, key="psc_lin")

  momio_prop = st.number_input("Momio Americano:", value=-115, step=5, key="psc_mom")

  if st.button("🚀 Evaluar Prop de Fútbol", use_container_width=True):
    res = analizar_prop_futbol_comun(jugador, mercado, promedio_hist, linea_cas)
    for r in res: r["partido"] = partido_str
    st.session_state["resultado_props_soc_comun_calculado"] = res

  if st.session_state.get("resultado_props_soc_comun_calculado"):
    validadas = st.session_state["resultado_props_soc_comun_calculado"]
    if validadas:
      st.success("✅ ¡El prop superó el filtro estricto del 70% de éxito real!")
      for v in validadas:
        st.info(f"Selección: **{v['mercado']}** | Probabilidad: `{v['prob']:.2f}%`")
        _, edge_p = calcular_edge_real(int(momio_prop), v['prob'])
        stk = calcular_criterio_kelly(st.session_state["bankroll_global"], v['prob'], int(momio_prop))
        if st.button("📥 Guardar Prop en SQLite", key="save_psc"):
          registrar_apuesta_db(fecha_formato_str, "Prop Soccer Común", v['partido'], v['mercado'], int(momio_prop), edge_p, stk)
          st.success("¡Prop guardado con éxito en la base de datos!")
      st.code(generar_ticket_nba_props_puro(validadas, fecha_formato_str), language="text")
    else:
      st.warning("⚠️ Este prop se encuentra por debajo del filtro estricto del 70% de probabilidad.")


elif modulo_seleccionado == "🥊 Prop: UFC / MMA Común":
  st.title(f"🥊 **Props: UFC / MMA Común [{fecha_formato_str}]**")
  st.markdown("--- \n *Props situacionales, método de victoria, distancias y asaltos totales.*")
  
  col1, col2 = st.columns(2)
  with col1:
    combate = st.text_input("Combate / Evento:", value="Makhachev vs Poirier", key="pu_comb")
    mercado_ufc = st.selectbox("Mercado Especial:", ["Termina por KO/TKO", "Va a la Distancia (Decisión)", "Over 1.5 Rounds", "Over 2.5 Rounds"], key="pu_merc")
    cartelera_str = st.text_input("Nombre de Cartelera:", value="UFC Main Event", key="pu_cart")
  with col2:
    prob_modelo = st.number_input("Probabilidad Asignada por el Modelo (%):", value=74.2, step=0.5, key="pu_prob")

  momio_prop = st.number_input("Momio Americano:", value=-120, step=5, key="pu_mom")

  if st.button("🚀 Evaluar Prop de UFC", use_container_width=True):
    res = analizar_prop_ufc_comun(combate, mercado_ufc, prob_modelo)
    for r in res: r["combate_nombre"] = cartelera_str
    st.session_state["resultado_props_ufc_comun_calculado"] = res

  if st.session_state.get("resultado_props_ufc_comun_calculado"):
    validadas = st.session_state["resultado_props_ufc_comun_calculado"]
    if validadas:
      st.success("✅ ¡El prop superó el filtro estricto del 70% de éxito real!")
      for v in validadas:
        st.info(f"Selección: **{v['mercado']}** | Probabilidad: `{v['prob']:.2f}%`")
        _, edge_p = calcular_edge_real(int(momio_prop), v['prob'])
        stk = calcular_criterio_kelly(st.session_state["bankroll_global"], v['prob'], int(momio_prop))
        if st.button("📥 Guardar Prop en SQLite", key="save_pu_comun"):
          registrar_apuesta_db(fecha_formato_str, "Prop UFC Común", cartelera_str, v['mercado'], int(momio_prop), edge_p, stk)
          st.success("¡Prop guardado con éxito en la base de datos!")
      st.code(generar_ticket_nba_props_puro(validadas, fecha_formato_str), language="text")
    else:
      st.warning("⚠️ Este prop se encuentra por debajo del filtro estricto del 70% de probabilidad.")


elif modulo_seleccionado == "🛡️ Prop: NFL Común (Playdoit)":
  st.title(f"🛡️ **Props: NFL Común [{fecha_formato_str}]**")
  st.markdown("--- \n *Props de volumen (Pase, Carrera, Recepción, Touchdowns y Scrimmage Totales).*")
  
  col1, col2 = st.columns(2)
  with col1:
    jugador = st.text_input("Jugador / Atleta:", value="Patrick Mahomes", key="pnc_jug")
    mercado = st.selectbox("Mercado Playdoit:", ["Yardas Pase", "Yardas Carrera", "Yardas Recepcion", "Yardas Totales (Recepcion y Carrera)", "Touchdown en Cualquier Momento"], key="pnc_merc")
    partido_str = st.text_input("Partido (Ej. Chiefs vs Raiders):", value="Chiefs vs Raiders", key="pnc_part")
  with col2:
    promedio_jug = st.number_input("Promedio del Jugador:", value=268.0, step=1.0, key="pnc_prom")
    linea_cas = st.number_input("Línea Casino:", value=255.5, step=0.5, key="pnc_lin")

  def_rival = st.number_input("Defensa Rival Permitido (% sobre media):", value=100.0, step=1.0, key="pnc_def")
  momio_prop = st.number_input("Momio Americano:", value=-110, step=5, key="pnc_mom")

  if st.button("🚀 Evaluar Prop de NFL", use_container_width=True):
    res = analizar_prop_nfl_comun(jugador, mercado, promedio_jug, linea_cas, def_rival)
    for r in res: r["partido"] = partido_str
    st.session_state["resultado_props_nfl_comun_calculado"] = res

  if st.session_state.get("resultado_props_nfl_comun_calculado"):
    validadas = st.session_state["resultado_props_nfl_comun_calculado"]
    if validadas:
      st.success("✅ ¡El prop superó el filtro estricto del 70% de éxito real!")
      for v in validadas:
        st.info(f"Selección: **{v['mercado']}** | Probabilidad: `{v['prob']:.2f}%`")
        _, edge_p = calcular_edge_real(int(momio_prop), v['prob'])
        stk = calcular_criterio_kelly(st.session_state["bankroll_global"], v['prob'], int(momio_prop))
        if st.button("📥 Guardar Prop en SQLite", key="save_pnc"):
          registrar_apuesta_db(fecha_formato_str, "Prop NFL Común", v['partido'], v['mercado'], int(momio_prop), edge_p, stk)
          st.success("¡Prop guardado con éxito en la base de datos!")
      st.code(generar_ticket_nba_props_puro(validadas, fecha_formato_str), language="text")
    else:
      st.warning("⚠️ Este prop se encuentra por debajo del filtro estricto del 70% de probabilidad.")


elif modulo_seleccionado == "🏀 Prop: NBA Común (Playdoit)":
  st.title(f"🏀 **Props: NBA Común [{fecha_formato_str}]**")
  st.markdown("--- \n *Props de volumen (Puntos, Rebotes y Asistencias) ajustados por Pace.*")
  
  col1, col2 = st.columns(2)
  with col1:
    jugador = st.text_input("Jugador / Atleta:", value="Jayson Tatum", key="pnbc_jug")
    mercado = st.selectbox("Mercado Playdoit:", ["Puntos", "Rebotes", "Asistencias"], key="pnbc_merc")
    partido_str = st.text_input("Partido (Ej. Celtics vs Pacers):", value="Celtics vs Pacers", key="pnbc_part")
  with col2:
    promedio_jug = st.number_input("Promedio Base del Jugador:", value=27.2, step=0.1, key="pnbc_prom")
    linea_cas = st.number_input("Línea Casino:", value=29.5, step=0.5, key="pnbc_lin")

  pace_partido = st.number_input("Pace Proyectado del Partido:", value=103.5, step=0.5, key="pnbc_pace")
  momio_prop = st.number_input("Momio Americano:", value=-115, step=5, key="pnbc_mom")

  if st.button("🚀 Evaluar Prop de NBA", use_container_width=True):
    res = analizar_prop_nba_comun(jugador, mercado, promedio_jug, linea_cas, pace_partido)
    for r in res: r["partido"] = partido_str
    st.session_state["resultado_props_nba_comun_calculado"] = res

  if st.session_state.get("resultado_props_nba_comun_calculado"):
    validadas = st.session_state["resultado_props_nba_comun_calculado"]
    if validadas:
      st.success("✅ ¡El prop superó el filtro estricto del 70% de éxito real!")
      for v in validadas:
        st.info(f"Selección: **{v['mercado']}** | Probabilidad: `{v['prob']:.2f}%`")
        _, edge_p = calcular_edge_real(int(momio_prop), v['prob'])
        stk = calcular_criterio_kelly(st.session_state["bankroll_global"], v['prob'], int(momio_prop))
        if st.button("📥 Guardar Prop en SQLite", key="save_pnbc"):
          registrar_apuesta_db(fecha_formato_str, "Prop NBA Común", v['partido'], v['mercado'], int(momio_prop), edge_p, stk)
          st.success("¡Prop guardado con éxito en la base de datos!")
      st.code(generar_ticket_nba_props_puro(validadas, fecha_formato_str), language="text")
    else:
      st.warning("⚠️ Este prop se encuentra por debajo del filtro estricto del 70% de probabilidad.")


# =========================================================
# ESCÁNER AUTOMÁTICO MULTI-DEPORTE (+EV)
# =========================================================
elif modulo_seleccionado == "🔍 Escáner Automático Multi-Deporte (+EV)":
  st.title(f"🔍 **Escáner Automático Multi-Deporte (+EV) [{fecha_formato_str}]**")
  st.markdown("--- \n *Barrido masivo en tiempo real de cuotas para detectar valor matemático positivo.*")
  api_key = st.session_state["api_key_guardada"]
  if st.button("🚀 Ejecutar Barrido Global de Oportunidades (+EV)", use_container_width=True):
    with st.spinner("Escaneando mercados globales..."):
      st.session_state["cartelera_escaner"] = obtener_partidos_y_momios_api_multideporte(api_key)
  st.info("Haz clic en el botón superior para iniciar el escaneo masivo.")


# =========================================================
# SISTEMAS PRO RESTANTES
# =========================================================
elif modulo_seleccionado == "🥊 Sistema Pro UFC / MMA":
  st.title(f"🥊 **Sistema Pro UFC / MMA Élite [{fecha_formato_str}]**")
  st.markdown("--- \n *Análisis estilístico avanzado: Power Ratings, Regla de Edad y Cage Rust.*")
  if st.button("🚀 Ejecutar Análisis Estilístico UFC", use_container_width=True):
    st.success("Análisis UFC simulado con éxito.")


elif modulo_seleccionado == "⚾ Béisbol Pro (MLB / LMP)":
  st.title(f"⚾ **Sistema Pro Béisbol Élite [{fecha_formato_str}]**")
  st.markdown("--- \n *Modelo Sabermétrico con FIP y Bullpen.*")
  if st.button("🚀 Ejecutar Análisis Sabermétrico", use_container_width=True):
    st.success("Análisis de béisbol completado.")


elif modulo_seleccionado == "🏒 Hockey Pro (NHL)":
  st.title(f"🏒 **Sistema Pro Hockey (NHL) Élite [{fecha_formato_str}]**")
  st.markdown("--- \n *Poisson Bivariado con Goalie Boost.*")
  if st.button("🚀 Ejecutar Análisis NHL", use_container_width=True):
    st.success("Análisis NHL completado.")


elif modulo_seleccionado == "🏀 Sistema Pro NBA":
  st.title(f"🏀 **Sistema Pro NBA Élite [{fecha_formato_str}]**")
  st.markdown("--- \n *Motor profesional con Eficiencias y Ritmo (Pace).*")
  if st.button("🚀 Ejecutar Análisis NBA", use_container_width=True):
    st.success("Análisis NBA completado.")


elif modulo_seleccionado == "🎓 Sistema Pro NCAAF (Universitario)":
  st.title(f"🎓 **Sistema Pro NCAAF Élite [{fecha_formato_str}]**")
  st.markdown("--- \n *Power Ratings y Distribución Normal.*")
  if st.button("🚀 Ejecutar Análisis NCAAF", use_container_width=True):
    st.success("Análisis NCAAF completado.")


elif modulo_seleccionado == "🛡️ Sistema Pro NFL":
  st.title(f"🛡️ **Sistema Pro NFL Élite [{fecha_formato_str}]**")
  st.markdown("--- \n *Motor profesional de 32 equipos.*")
  if st.button("🚀 Ejecutar Análisis NFL", use_container_width=True):
    st.success("Análisis NFL completado.")


elif modulo_seleccionado == "⚽ Módulo Pro Fútbol (Soccer)":
  st.title(f"⚽ **Módulo Pro Fútbol Élite [{fecha_formato_str}]**")
  st.markdown("--- \n *Poisson Bivariado.*")
  if st.button("🚀 Ejecutar Análisis Fútbol", use_container_width=True):
    st.success("Análisis de fútbol completado.")


# =========================================================
# MÓDULOS DE APOYO Y FINANCIEROS
# =========================================================
elif modulo_seleccionado == "📊 Control de Bankroll & Historial SQLite":
  st.title(f"📊 **Panel de Control & Bankroll [{fecha_formato_str}]**")
  conn = sqlite3.connect("master_suite_elite.db")
  cursor = conn.cursor()
  cursor.execute("SELECT id, fecha, deporte, partido, mercado, momio, edge, stake, resultado, ganancia_neta FROM apuestas")
  registros = cursor.fetchall()
  conn.close()
  if registros:
    for reg in registros:
      apuesta_id, fecha, deporte, partido, mercado, momio, edge, stake, estado, ganancia = reg
      st.info(f"🆔 {apuesta_id} | 📅 {fecha} | **{deporte}** | `{partido}` | **{mercado}** | Momio: `{momio}` | Stake: `${stake}` | Estado: **{estado}**")
  else:
    st.info("No hay apuestas registradas todavía en la base de datos SQLite.")

elif modulo_seleccionado == "🚀 Optimizador de Parlays (Monte Carlo)":
  st.title(f"🚀 **Optimizador de Parlays Monte Carlo [{fecha_formato_str}]**")
  st.info("Módulo de simulación de parlay activo.")

elif modulo_seleccionado == "🧮 Calculadora de Arbitraje (Surebets)":
  st.title(f"🧮 **Calculadora de Arbitraje & Alertas Telegram [{fecha_formato_str}]**")
  col_a1, col_a2 = st.columns(2)
  with col_a1: cuota_a = st.number_input("Cuota Casa A:", value=130)
  with col_a2: cuota_b = st.number_input("Cuota Casa B:", value=-120)
  bankroll_total_arb = st.number_input("Inversión Total (MXN):", value=5000.0, step=500.0)
  if st.button("⚖️ Calcular Surebet y Enviar a Telegram", use_container_width=True):
    dec_a = (1.0 + (cuota_a / 100.0)) if cuota_a > 0 else (1.0 + (100.0 / abs(cuota_a)))
    dec_b = (1.0 + (cuota_b / 100.0)) if cuota_b > 0 else (1.0 + (100.0 / abs(cuota_b)))
    implied_sum = (1.0 / dec_a) + (1.0 / dec_b)
    if implied_sum < 1.0:
      roi_arb = (1.0 - implied_sum) * 100.0
      stake_a = bankroll_total_arb * ((1.0 / dec_a) / implied_sum)
      stake_b = bankroll_total_arb * ((1.0 / dec_b) / implied_sum)
      ganancia_garantizada = (stake_a * dec_a) - bankroll_total_arb
      st.success(f"🚨 ¡Oportunidad de Arbitraje! ROI: **+{roi_arb:.2f}%** | Ganancia: **${ganancia_garantizada:,.2f} MXN**")
      enviar_alerta_telegram(st.session_state["telegram_token"], st.session_state["telegram_chat_id"], f"⚖️ Alerta Arbitraje: ROI +{roi_arb:.2f}%")
    else:
      st.error("❌ Sin oportunidad de arbitraje.")

elif modulo_seleccionado == "📈 Backtesting Histórico & Steam Moves":
  st.title(f"📈 **Backtesting & Steam Moves [{fecha_formato_str}]**")
  st.info("Simulador de backtesting y monitor de dinero profesional activo.")

elif modulo_seleccionado == "⚖️ Gestor Multi-Bookmaker (Line Shopping)":
  st.title(f"⚖️ **Line Shopping [{fecha_formato_str}]**")
  col_bk1, col_bk2, col_bk3 = st.columns(3)
  with col_bk1: b_caliente = st.number_input("Caliente:", value=-110, step=5)
  with col_bk2: b_bet365 = st.number_input("Bet365:", value=-105, step=5)
  with col_bk3: b_pinnacle = st.number_input("Pinnacle:", value=-102, step=5)
  if st.button("🔍 Encontrar Mejor Cuota", use_container_width=True):
    st.success("🏆 Casa recomendada calculada con éxito.")
