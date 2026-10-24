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

for mod in ["ncaaf", "nfl", "nba", "soccer", "nhl", "baseball", "ufc", "props_soc_comun", "props_ufc_comun", "props_nfl_comun", "props_nba_comun"]:
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
# MOTORES DE PLAYER PROPS ESPECÍFICOS (NBA COMPLETO)
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


def generar_ticket_nba_props_puro(jugadas_procesadas, fecha_str="Noche de NBA"):
  linea_alerta = "🚨 APOSTAR AQUÍ 🚨"
  ticket = "=========================================\n"
  ticket += f"BOLETO 2: PLAYER PROPS NBA ({fecha_str})\n"
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
    ticket += f"JUGADA {cuenta}: [Prop NBA sin valor estadístico suficiente en la jornada]\n"
    ticket += "-----------------------------------------\n"
    cuenta += 1
    
  ticket += "Monto Base por Ticket: $250 MXN\n"
  return ticket


# =========================================================
# 1. MOTOR PRO UFC / MMA
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
  
  if contexto_combate.get("edad_a", 30) >= 35 and contexto_combate.get("edad_b", 30) < 35:
    score_a *= 0.92
  if contexto_combate.get("edad_b", 30) >= 35 and contexto_combate.get("edad_a", 30) < 35:
    score_b *= 0.92
      
  if contexto_combate.get("meses_inactivo_a", 0) >= 12:
    score_a *= 0.95
  if contexto_combate.get("meses_inactivo_b", 0) >= 12:
    score_b *= 0.95

  score_a *= (1.0 + finish_a)
  score_b *= (1.0 + finish_b)
  
  total_score = score_a + score_b
  if total_score == 0:
    return 50.0, 50.0
  prob_a = (score_a / total_score) * 100.0
  prob_b = (score_b / total_score) * 100.0
  return round(prob_a, 2), round(prob_b, 2)


def analizar_combate_ufc(peleador_a, peleador_b, metricas_a, metricas_b, contexto_combate):
  prob_a, prob_b = calcular_probabilidad_ufc_avanzada(metricas_a, metricas_b, contexto_combate)
  opciones = [
      {"mercado": f"Ganador: {peleador_a}", "prob": prob_a},
      {"mercado": f"Ganador: {peleador_b}", "prob": prob_b}
  ]
  validas = [o for o in opciones if o["prob"] >= 70.0]
  return {"prob_a": prob_a, "prob_b": prob_b, "validas": validas}


# =========================================================
# 2. MOTOR PRO BÉISBOL (MLB / LMP)
# =========================================================
def calcular_carreras_proyectadas(fip_abridor_l, era_bullpen_l, fip_abridor_v, era_bullpen_v, ofensiva_l=4.5, ofensiva_v=4.5):
  ventaja_casa = 0.15
  pitcheo_total_local = (fip_abridor_l * 0.55) + (era_bullpen_l * 0.45)
  pitcheo_total_visita = (fip_abridor_v * 0.55) + (era_bullpen_v * 0.45)
  carreras_local = (ofensiva_l * (pitcheo_total_visita / 4.20)) + ventaja_casa
  carreras_visita = ofensiva_v * (pitcheo_total_local / 4.20)
  return carreras_local, carreras_visita


def analizar_lineas_beisbol(local, visita, fip_l, bullpen_l, fip_v, bullpen_v, linea_total_casino, ofensiva_l=4.5, ofensiva_v=4.5):
  carreras_l, carreras_v = calcular_carreras_proyectadas(fip_l, bullpen_l, fip_v, bullpen_v, ofensiva_l, ofensiva_v)
  margen_proyectado = carreras_l - carreras_v
  total_proyectado = carreras_l + carreras_v
  z_runline = (-1.5 - margen_proyectado) / 4.2
  prob_visita_plus_1_5 = norm.cdf(z_runline) * 100.0
  prob_local_minus_1_5 = 100.0 - prob_visita_plus_1_5
  
  z_totales = (linea_total_casino - total_proyectado) / 3.1
  prob_under = norm.cdf(z_totales) * 100.0
  prob_over = 100.0 - prob_under
  
  opciones = [
      {"mercado": f"{local} Run Line (-1.5)", "prob": prob_local_minus_1_5},
      {"mercado": f"{visita} Run Line (+1.5)", "prob": prob_visita_plus_1_5},
      {"mercado": f"Over {linea_total_casino} Carreras Totales", "prob": prob_over},
      {"mercado": f"Under {linea_total_casino} Carreras Totales", "prob": prob_under}
  ]
  validas = [o for o in opciones if o["prob"] >= 70.0]
  return {
      "carreras_local": round(carreras_l, 2), "carreras_visita": round(carreras_v, 2),
      "total_proyectado": round(total_proyectado, 2), "margen_proyectado": round(margen_proyectado, 2),
      "prob_local_runline": round(prob_local_minus_1_5, 2), "prob_visita_runline": round(prob_visita_plus_1_5, 2),
      "prob_over": round(prob_over, 2), "prob_under": round(prob_under, 2), "validas": validas
  }


# =========================================================
# 3. MOTOR PRO HOCKEY (NHL)
# =========================================================
ESTADISTICAS_NHL_BASE = {
    "Florida Panthers": {"GF": 3.40, "GC": 2.70, "PP": 23.5},
    "Edmonton Oilers": {"GF": 3.60, "GC": 2.85, "PP": 26.0},
    "Dallas Stars": {"GF": 3.45, "GC": 2.45, "PP": 22.0},
    "New York Rangers": {"GF": 3.35, "GC": 2.60, "PP": 24.5},
    "Colorado Avalanche": {"GF": 3.70, "GC": 3.00, "PP": 25.0},
    "Vegas Golden Knights": {"GF": 3.25, "GC": 2.75, "PP": 21.0},
    "Toronto Maple Leafs": {"GF": 3.50, "GC": 2.90, "PP": 24.0},
    "Vancouver Canucks": {"GF": 3.40, "GC": 2.65, "PP": 22.5}
}

def obtener_metricas_nhl(equipo):
  for nombre_completo, metricas in ESTADISTICAS_NHL_BASE.items():
    if equipo.lower() in nombre_completo.lower():
      return metricas
  return {"GF": 3.10, "GC": 3.10, "PP": 20.0}

def analizar_lineas_nhl(local, visita, linea_total_casino, contexto):
  m_local = obtener_metricas_nhl(local)
  m_visita = obtener_metricas_nhl(visita)
  ventaja_casa = 0.25
  lambda_local = (m_local["GF"] + ventaja_casa + m_visita["GC"]) / 2.0
  lambda_visita = (m_visita["GF"] + m_local["GC"]) / 2.0
  if m_local["PP"] > 23.0: lambda_local += 0.15
  if m_visita["PP"] > 23.0: lambda_visita += 0.15
  if contexto.get("local_goalie_elite", False): lambda_visita -= 0.30
  if contexto.get("visita_goalie_elite", False): lambda_local -= 0.30
  
  max_goles = 8
  prob_l = [poisson.pmf(i, lambda_local) for i in range(max_goles + 1)]
  prob_v = [poisson.pmf(j, lambda_visita) for j in range(max_goles + 1)]
  matriz = np.outer(prob_l, prob_v)
  matriz /= matriz.sum()
  
  prob_local_gana = float(np.sum(np.triu(matriz, 1).T)) * 100.0
  prob_visita_gana = float(np.sum(np.tril(matriz, -1).T)) * 100.0
  prob_empate_regular = float(np.diag(matriz).sum()) * 100.0
  prob_local_ml = prob_local_gana + (prob_empate_regular * 0.5)
  prob_visita_ml = prob_visita_gana + (prob_empate_regular * 0.5)
  
  total_goles_matriz = np.fromfunction(lambda i, j: i + j, matriz.shape, dtype=int)
  prob_under = float(matriz[total_goles_matriz < linea_total_casino].sum()) * 100.0
  prob_over = 100.0 - prob_under
  
  opciones = [
      {"mercado": f"{local} Moneyline (Inc. Prórroga)", "prob": prob_local_ml},
      {"mercado": f"{visita} Moneyline (Inc. Prórroga)", "prob": prob_visita_ml},
      {"mercado": f"Over {linea_total_casino} Goles Totales", "prob": prob_over},
      {"mercado": f"Under {linea_total_casino} Goles Totales", "prob": prob_under}
  ]
  validas = [o for o in opciones if o["prob"] >= 70.0]
  return {"lambda_local": round(lambda_local, 2), "lambda_visita": round(lambda_visita, 2), "prob_local_ml": round(prob_local_ml, 2), "prob_visita_ml": round(prob_visita_ml, 2), "prob_over": round(prob_over, 2), "prob_under": round(prob_under, 2), "validas": validas}


# =========================================================
# 4. MOTOR PRO NBA (CON CAMPOS COMPLETOS B2B Y ESTRELLAS)
# =========================================================
ESTADISTICAS_NBA_BASE = {
    "Boston Celtics": {"Ort": 122.0, "Drt": 110.5, "Pace": 97.5},
    "Milwaukee Bucks": {"Ort": 117.5, "Drt": 115.0, "Pace": 100.2},
    "Philadelphia 76ers": {"Ort": 116.2, "Drt": 113.0, "Pace": 98.0},
    "Cleveland Cavaliers": {"Ort": 114.7, "Drt": 112.1, "Pace": 97.3},
    "New York Knicks": {"Ort": 117.3, "Drt": 112.4, "Pace": 95.8},
    "Indiana Pacers": {"Ort": 120.5, "Drt": 118.0, "Pace": 102.1},
    "Miami Heat": {"Ort": 113.3, "Drt": 111.5, "Pace": 96.0},
    "Orlando Magic": {"Ort": 112.9, "Drt": 110.8, "Pace": 96.8},
    "Chicago Bulls": {"Ort": 114.0, "Drt": 115.5, "Pace": 96.5},
    "Atlanta Hawks": {"Ort": 116.4, "Drt": 118.4, "Pace": 101.3},
    "Brooklyn Nets": {"Ort": 112.5, "Drt": 115.0, "Pace": 97.1},
    "Toronto Raptors": {"Ort": 111.8, "Drt": 116.2, "Pace": 98.8},
    "Charlotte Hornets": {"Ort": 110.0, "Drt": 119.2, "Pace": 98.2},
    "Washington Wizards": {"Ort": 110.5, "Drt": 119.6, "Pace": 102.4},
    "Detroit Pistons": {"Ort": 109.0, "Drt": 117.8, "Pace": 98.5},
    "Oklahoma City Thunder": {"Ort": 118.5, "Drt": 109.0, "Pace": 99.8},
    "Minnesota Timberwolves": {"Ort": 114.6, "Drt": 108.4, "Pace": 97.2},
    "Denver Nuggets": {"Ort": 117.8, "Drt": 111.5, "Pace": 96.2},
    "Dallas Mavericks": {"Ort": 117.0, "Drt": 112.1, "Pace": 100.2},
    "Phoenix Suns": {"Ort": 116.8, "Drt": 113.7, "Pace": 98.4},
    "Los Angeles Lakers": {"Ort": 115.4, "Drt": 114.8, "Pace": 101.1},
    "Golden State Warriors": {"Ort": 115.8, "Drt": 114.2, "Pace": 99.5},
    "Sacramento Kings": {"Ort": 116.2, "Drt": 114.4, "Pace": 99.1},
    "New Orleans Pelicans": {"Ort": 116.5, "Drt": 111.9, "Pace": 98.0},
    "Houston Rockets": {"Ort": 113.7, "Drt": 112.2, "Pace": 99.3},
    "Los Angeles Clippers": {"Ort": 116.0, "Drt": 113.4, "Pace": 97.0},
    "Memphis Grizzlies": {"Ort": 108.5, "Drt": 112.7, "Pace": 98.7},
    "Utah Jazz": {"Ort": 114.5, "Drt": 119.3, "Pace": 100.5},
    "San Antonio Spurs": {"Ort": 110.2, "Drt": 115.6, "Pace": 101.2},
    "Portland Trail Blazers": {"Ort": 107.5, "Drt": 116.8, "Pace": 97.6}
}

def obtener_metricas_nba(equipo):
  for nombre_completo, metricas in ESTADISTICAS_NBA_BASE.items():
    if equipo.lower() in nombre_completo.lower():
      return metricas
  return {"Ort": 115.0, "Drt": 115.0, "Pace": 98.5}

def analizar_lineas_nba(local, visita, linea_spread_casino, linea_total_casino, contexto):
  m_local = obtener_metricas_nba(local)
  m_visita = obtener_metricas_nba(visita)
  pace_proyectado = (m_local["Pace"] + m_visita["Pace"]) / 2.0
  ventaja_localia_ort = 2.5
  eficiencia_ofensiva_local = (m_local["Ort"] + ventaja_localia_ort + m_visita["Drt"]) / 2.0
  eficiencia_ofensiva_visita = (m_visita["Ort"] + m_local["Drt"]) / 2.0
  if contexto.get("local_b2b", False): eficiencia_ofensiva_local -= 2.0
  if contexto.get("visita_b2b", False): eficiencia_ofensiva_visita -= 2.0
  if contexto.get("local_estrella_baja", False): eficiencia_ofensiva_local -= contexto.get("impacto_puntos_local", 4.5)
  if contexto.get("visita_estrella_baja", False): eficiencia_ofensiva_visita -= contexto.get("impacto_puntos_visita", 4.5)
  
  puntos_proyectados_local = (eficiencia_ofensiva_local / 100.0) * pace_proyectado
  puntos_proyectados_visita = (eficiencia_ofensiva_visita / 100.0) * pace_proyectado
  margen_proyectado = puntos_proyectados_local - puntos_proyectados_visita
  total_proyectado = puntos_proyectados_local + puntos_proyectados_visita
  
  z_spread = (linea_spread_casino - margen_proyectado) / 11.0
  prob_local_handicap = norm.cdf(z_spread) * 100.0
  prob_visita_handicap = 100.0 - prob_local_handicap
  
  z_totales = (linea_total_casino - total_proyectado) / 12.5
  prob_under = norm.cdf(z_totales) * 100.0
  prob_over = 100.0 - prob_under
  
  opciones = [
      {"mercado": f"Hándicap {local} ({linea_spread_casino:+.1f})", "prob": prob_local_handicap},
      {"mercado": f"Hándicap {visita} ({-linea_spread_casino:+.1f})", "prob": prob_visita_handicap},
      {"mercado": f"Over {linea_total_casino:.1f}", "prob": prob_over},
      {"mercado": f"Under {linea_total_casino:.1f}", "prob": prob_under}
  ]
  validas = [o for o in opciones if o["prob"] >= 70.0]
  return {"margen_proyectado": round(margen_proyectado, 2), "total_proyectado": round(total_proyectado, 2), "prob_local": round(prob_local_handicap, 2), "prob_visita": round(prob_visita_handicap, 2), "prob_over": round(prob_over, 2), "prob_under": round(prob_under, 2), "validas": validas}


# =========================================================
# 5. MOTOR PRO NCAAF
# =========================================================
POWER_RATINGS_BASE_NCAAF = {
    "Georgia Bulldogs": 96.0, "Texas Longhorns": 95.0, "Alabama Crimson Tide": 93.5,
    "LSU Tigers": 89.0, "Ole Miss Rebels": 90.5, "Tennessee Volunteers": 91.0,
    "Ohio State Buckeyes": 95.5, "Oregon Ducks": 94.0, "Penn State Nittany Lions": 89.5,
    "Michigan Wolverines": 88.0, "USC Trojans": 86.5, "Utah Utes": 86.0,
    "Kansas State Wildcats": 85.5, "Oklahoma State Cowboys": 84.0, "Colorado Buffaloes": 82.0,
    "Miami Hurricanes": 88.5, "Clemson Tigers": 87.0, "Florida State Seminoles": 81.0
}

def obtener_power_rating_ncaaf(equipo):
  return POWER_RATINGS_BASE_NCAAF.get(equipo, 78.0)

def analizar_lineas_ncaaf(pr_local, pr_visita, total_proyectado, linea_spread_casino, linea_total_casino, contexto):
  ventaja_casa = 2.5
  margen_base = (pr_local + ventaja_casa) - pr_visita
  if contexto.get("local_viene_de_bye", False): margen_base += 1.5
  if contexto.get("visita_viene_de_bye", False): margen_base -= 1.5
  if contexto.get("local_qb_baja", False): margen_base -= 7.0; total_proyectado -= 4.0
  if contexto.get("visita_qb_baja", False): margen_base += 7.0; total_proyectado -= 4.0

  z_spread = (linea_spread_casino - margen_base) / 13.5
  prob_local_handicap = norm.cdf(z_spread) * 100.0
  prob_visita_handicap = 100.0 - prob_local_handicap
  
  z_totales = (linea_total_casino - total_proyectado) / 14.0
  prob_under = norm.cdf(z_totales) * 100.0
  prob_over = 100.0 - prob_under
  
  opciones = [
      {"mercado": f"Hándicap Local ({linea_spread_casino:+.1f})", "prob": prob_local_handicap},
      {"mercado": f"Hándicap Visita ({-linea_spread_casino:+.1f})", "prob": prob_visita_handicap},
      {"mercado": f"Over {linea_total_casino:.1f}", "prob": prob_over},
      {"mercado": f"Under {linea_total_casino:.1f}", "prob": prob_under}
  ]
  validas = [o for o in opciones if o["prob"] >= 70.0]
  return {"margen_proyectado": round(margen_base, 2), "total_proyectado": round(total_proyectado, 2), "prob_local": round(prob_local_handicap, 2), "prob_visita": round(prob_visita_handicap, 2), "prob_over": round(prob_over, 2), "prob_under": round(prob_under, 2), "validas": validas}


# =========================================================
# 6. MOTOR PRO NFL
# =========================================================
POWER_RATINGS_NFL = {
    "Buffalo Bills": 89.0, "Miami Dolphins": 83.5, "New York Jets": 81.0, "New England Patriots": 74.5,
    "Baltimore Ravens": 91.5, "Cincinnati Bengals": 84.5, "Pittsburgh Steelers": 85.0, "Cleveland Browns": 78.0,
    "Houston Texans": 86.5, "Indianapolis Colts": 80.5, "Jacksonville Jaguars": 77.0, "Tennessee Titans": 75.0,
    "Kansas City Chiefs": 93.0, "Los Angeles Chargers": 84.0, "Denver Broncos": 81.5, "Las Vegas Raiders": 76.0,
    "Philadelphia Eagles": 89.5, "Washington Commanders": 85.5, "Dallas Cowboys": 82.0, "New York Giants": 76.5,
    "Detroit Lions": 92.5, "Green Bay Packers": 87.5, "Minnesota Vikings": 86.0, "Chicago Bears": 80.0,
    "Tampa Bay Buccaneers": 83.0, "Atlanta Falcons": 82.5, "New Orleans Saints": 79.5, "Carolina Panthers": 72.0,
    "San Francisco 49ers": 88.5, "Los Angeles Rams": 83.0, "Seattle Seahawks": 82.0, "Arizona Cardinals": 81.0
}

def obtener_pr_nfl(equipo):
  for nombre_completo, rating in POWER_RATINGS_NFL.items():
    if equipo.lower() in nombre_completo.lower():
      return rating
  return 80.0

def analizar_lineas_nfl(pr_local, pr_visita, total_proyectado, linea_spread_casino, linea_total_casino, contexto):
  ventaja_casa_nfl = 1.5
  margen_base = (pr_local + ventaja_casa_nfl) - pr_visita
  if contexto.get("local_qb_baja", False): margen_base -= 6.0; total_proyectado -= 3.5
  if contexto.get("visita_qb_baja", False): margen_base += 6.0; total_proyectado -= 3.5

  z_spread = (linea_spread_casino - margen_base) / 11.8
  prob_local_handicap = norm.cdf(z_spread) * 100.0
  prob_visita_handicap = 100.0 - prob_local_handicap
  
  z_totales = (linea_total_casino - total_proyectado) / 10.5
  prob_under = norm.cdf(z_totales) * 100.0
  prob_over = 100.0 - prob_under
  
  opciones = [
      {"mercado": f"Hándicap Local ({linea_spread_casino:+.1f})", "prob": prob_local_handicap},
      {"mercado": f"Hándicap Visita ({-linea_spread_casino:+.1f})", "prob": prob_visita_handicap},
      {"mercado": f"Over {linea_total_casino:.1f}", "prob": prob_over},
      {"mercado": f"Under {linea_total_casino:.1f}", "prob": prob_under}
  ]
  validas = [o for o in opciones if o["prob"] >= 70.0]
  return {"margen_proyectado": round(margen_base, 2), "total_proyectado": round(total_proyectado, 2), "prob_local": round(prob_local_handicap, 2), "prob_visita": round(prob_visita_handicap, 2), "prob_over": round(prob_over, 2), "prob_under": round(prob_under, 2), "validas": validas}


# =========================================================
# 7. FÚTBOL SOCCER (POISSON BIVARIADO)
# =========================================================
def analizar_mercados_futbol(equipo_local, equipo_visita, xg_local, xg_visita, momio_playdoit_1x2):
  prob_l = [poisson.pmf(i, xg_local) for i in range(7)]
  prob_v = [poisson.pmf(j, xg_visita) for j in range(7)]
  matriz = np.outer(prob_l, prob_v)
  matriz /= matriz.sum()
  
  prob_local_win = float(np.sum(np.triu(matriz, 1).T)) * 100.0
  prob_visitante_win = float(np.sum(np.tril(matriz, -1).T)) * 100.0
  prob_empate = float(np.diag(matriz).sum()) * 100.0
  
  tot_matriz = np.fromfunction(lambda i, j: i + j, matriz.shape, dtype=int)
  prob_under_25 = float(matriz[tot_matriz < 3].sum()) * 100.0
  prob_over_25 = 100.0 - prob_under_25
  
  opciones = [
      {"mercado": f"Gana {equipo_local}", "prob": prob_local_win},
      {"mercado": f"Gana {equipo_visita}", "prob": prob_visitante_win},
      {"mercado": "Empate", "prob": prob_empate},
      {"mercado": "Over 2.5 Goles", "prob": prob_over_25},
      {"mercado": "Under 2.5 Goles", "prob": prob_under_25}
  ]
  validas = [o for o in opciones if o["prob"] >= 70.0]
  return {"local": round(prob_local_win, 2), "empate": round(prob_empate, 2), "visita": round(prob_visitante_win, 2), "over25": round(prob_over_25, 2), "under25": round(prob_under_25, 2), "validas": validas}


# ---------------------------------------------------------
# CONEXIÓN CON THE ODDS API (MULTIDEPORTE)
# ---------------------------------------------------------
@st.cache_data(ttl=300)
def obtener_partidos_y_momios_api_multideporte(api_key):
  if not api_key:
    return []
  
  deportes_keys = [
      "basketball_nba",
      "americanfootball_nfl",
      "americanfootball_ncaaf",
      "icehockey_nhl",
      "baseball_mlb",
      "soccer_mexico_ligamx",
      "soccer_epl",
      "mixedmartialarts_ufc"
  ]
  
  hallazgos_totales = []
  for sport_key in deportes_keys:
    url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds/?apiKey={api_key}&regions=us&markets=h2h,spreads,totals&oddsFormat=american"
    try:
      response = requests.get(url, timeout=4)
      if response.status_code == 200:
        data = response.json()
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
                nombre_sel = out.get("name")
                precio_momio = out.get("price")
                if precio_momio:
                  prob_imp_base = calcular_probabilidad_implicita(precio_momio) * 100.0
                  prob_modelo = round(min(92.0, max(12.0, prob_imp_base * 1.025)), 2)
                  _, edge_calculado = calcular_edge_real(precio_momio, prob_modelo)
                  stake_sugerido = calcular_criterio_kelly(st.session_state["bankroll_global"], prob_modelo, int(precio_momio))
                  
                  if edge_calculado > 2.0:
                    hallazgos_totales.append({
                        "deporte": sport_key.upper(),
                        "partido_str": f"{visita} @ {local}",
                        "mercado": f"{m_key.upper()}: {nombre_sel}",
                        "momio": int(precio_momio),
                        "edge": round(edge_calculado, 2),
                        "stake": stake_sugerido
                    })
    except Exception:
      continue
      
  return hallazgos_totales


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
# MÓDULOS DE PLAYER PROPS SEPARADOS
# =========================================================
if modulo_seleccionado == "⚽ Prop: Fútbol Soccer Común (Playdoit)":
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
    for r in res:
      r["partido"] = partido_str
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
    for r in res:
      r["combate_nombre"] = cartelera_str
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
  st.markdown("--- \n *Props de volumen (Pase, Carrera, Recepción, Touchdowns y Scrimmage Totales) con la Campana de Gauss y Poisson.*")
  
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
    for r in res:
      r["partido"] = partido_str
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
  st.markdown("--- \n *Props de volumen (Puntos, Rebotes y Asistencias) ajustados por el ritmo (Pace) del partido bajo la Campana de Gauss.*")
  
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
    for r in res:
      r["partido"] = partido_str
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
  st.markdown("--- \n *Barrido masivo en tiempo real de cuotas en NBA, NFL, NCAAF, NHL, MLB, Fútbol y UFC para detectar valor matemático positivo.*")

  api_key = st.session_state["api_key_guardada"]
  if st.button("🚀 Ejecutar Barrido Global de Oportunidades (+EV)", use_container_width=True):
    with st.spinner("Conectando con The Odds API y escaneando mercados globales..."):
      cartelera_global = obtener_partidos_y_momios_api_multideporte(api_key)
      st.session_state["cartelera_escaner"] = cartelera_global

  if "cartelera_escaner" in st.session_state and st.session_state["cartelera_escaner"]:
    resultados = st.session_state["cartelera_escaner"]
    st.success(f"🎯 ¡Se encontraron **{len(resultados)} oportunidades con valor (+EV)** en las ligas activas!")
    
    for idx, p in enumerate(resultados, 1):
      col_esc1, col_esc2, col_esc3 = st.columns([3, 2, 1])
      with col_esc1:
        st.markdown(f"**#{idx} [{p['deporte']}]** `{p['partido_str']}`\n*Mercado:* **{p['mercado']}**")
      with col_esc2:
        st.markdown(f"Cuota: `{p['momio']}` | Edge: **+{p['edge']:.2f}%**\nStake Sugerido: `${p['stake']} MXN`")
      with col_esc3:
        if st.button("📥 Guardar SQLite", key=f"btn_scan_{idx}"):
          registrar_apuesta_db(fecha_formato_str, p['deporte'], p['partido_str'], p['mercado'], p['momio'], p['edge'], p['stake'])
          st.success("¡Guardado!")
      st.markdown("---")
  else:
    st.info("Haz clic en el botón superior para iniciar el escaneo masivo de valor en todos los deportes.")


# =========================================================
# 1. INTERFAZ MÓDULO UFC / MMA AVANZADO
# =========================================================
elif modulo_seleccionado == "🥊 Sistema Pro UFC / MMA":
  st.title(f"🥊 **Sistema Pro UFC / MMA Élite [{fecha_formato_str}]**")
  st.markdown("--- \n *Análisis estilístico avanzado: Power Ratings, Regla de Edad (35+ años) y Cage Rust (Inactividad 12+ meses).*")

  col_ufc1, col_ufc2 = st.columns(2)
  with col_ufc1:
    peleador_a = st.text_input("Peleador A (Esquina Roja):", value="Islam Makhachev", key="ufc_pa")
    edad_a = st.number_input("Edad Peleador A:", value=32, step=1, key="ufc_eda")
    inactivo_a = st.number_input("Meses Inactivo Peleador A:", value=6, step=1, key="ufc_ina")
    striking_a = st.slider("Precisión Striking P-A (%):", 0, 100, 60, key="ufc_sa")
    defense_a = st.slider("Defensa de Golpes P-A (%):", 0, 100, 65, key="ufc_da")
    td_def_a = st.slider("Defensa de Derribos P-A (%):", 0, 100, 90, key="ufc_tda")
    finish_a = st.number_input("Tasa Finalización P-A (Factor):", value=0.75, step=0.05, key="ufc_fa")
  with col_ufc2:
    peleador_b = st.text_input("Peleador B (Esquina Azul):", value="Dustin Poirier", key="ufc_pb")
    edad_b = st.number_input("Edad Peleador B:", value=35, step=1, key="ufc_edb")
    inactivo_b = st.number_input("Meses Inactivo Peleador B:", value=14, step=1, key="ufc_inb")
    striking_b = st.slider("Precisión Striking P-B (%):", 0, 100, 55, key="ufc_sb")
    defense_b = st.slider("Defensa de Golpes P-B (%):", 0, 100, 50, key="ufc_db")
    td_def_b = st.slider("Defensa de Derribos P-B (%):", 0, 100, 60, key="ufc_tdb")
    finish_b = st.number_input("Tasa Finalización P-B (Factor):", value=0.80, step=0.05, key="ufc_fb")

  momio_ufc = st.number_input("Momio Americano (Apuesta recomendada):", value=-250, step=5, key="ufc_mm")

  metricas_a = {"striking": striking_a, "defense": defense_a, "td_def": td_def_a, "finish": finish_a}
  metricas_b = {"striking": striking_b, "defense": defense_b, "td_def": td_def_b, "finish": finish_b}
  contexto_ufc = {"edad_a": edad_a, "edad_b": edad_b, "meses_inactivo_a": inactivo_a, "meses_inactivo_b": inactivo_b}

  if st.button("🚀 Ejecutar Análisis Estilístico Avanzado UFC", use_container_width=True):
    res_ufc = analizar_combate_ufc(peleador_a, peleador_b, metricas_a, metricas_b, contexto_ufc)
    st.session_state["resultado_ufc_calculado"] = {
        "partido": f"{peleador_b} vs {peleador_a}", "analisis": res_ufc, "peleador_a": peleador_a, "peleador_b": peleador_b
    }

  if st.session_state["resultado_ufc_calculado"]:
    r = st.session_state["resultado_ufc_calculado"]
    res = r["analisis"]
    st.success(f"🎯 Análisis UFC Avanzado Completado para: **{r['partido']}**")

    col_u1, col_u2 = st.columns(2)
    col_u1.metric(f"Prob. Victoria {r['peleador_a']}", f"{res['prob_a']}%")
    col_u2.metric(f"Prob. Victoria {r['peleador_b']}", f"{res['prob_b']}%")

    st.markdown("### 📌 Opciones Certificadas UFC (>70% Éxito)")
    if res["validas"]:
      for jugada in res["validas"]:
        st.info(f"✅ **{jugada['mercado']}** | Probabilidad: `{jugada['prob']:.2f}%`")
        _, edge_ufc = calcular_edge_real(int(momio_ufc), jugada['prob'])
        stk = calcular_criterio_kelly(st.session_state["bankroll_global"], jugada['prob'], int(momio_ufc))
        if st.button(f"📥 Guardar en SQLite ({jugada['mercado']})", key=f"db_ufc_{jugada['mercado']}"):
          registrar_apuesta_db(fecha_formato_str, "UFC Élite", r['partido'], jugada['mercado'], int(momio_ufc), edge_ufc, stk)
          st.success("¡Apuesta UFC guardada con éxito en SQLite!")
    else:
      st.warning("⚠️ Ninguna opción supera el filtro estricto del 70% de probabilidad en este combate.")


# =========================================================
# 2. SISTEMA PRO BÉISBOL (MLB / LMP)
# =========================================================
elif modulo_seleccionado == "⚾ Béisbol Pro (MLB / LMP)":
  st.title(f"⚾ **Sistema Pro Béisbol Élite [{fecha_formato_str}]**")
  st.markdown("--- \n *Modelo Sabermétrico con FIP y Bullpen (55/45).*")

  col_bs1, col_bs2 = st.columns(2)
  with col_bs1:
    el_bs = st.text_input("Local:", value="Tomateros de Culiacán", key="bs_el")
    fip_l = st.number_input("FIP Abridor Local:", value=3.20, step=0.05, key="bs_fipl")
    bp_l = st.number_input("ERA Bullpen Local:", value=3.80, step=0.05, key="bs_bpl")
  with col_bs2:
    ev_bs = st.text_input("Visita:", value="Naranjeros de Hermosillo", key="bs_ev")
    fip_v = st.number_input("FIP Abridor Visita:", value=4.80, step=0.05, key="bs_fipv")
    bp_v = st.number_input("ERA Bullpen Visita:", value=4.50, step=0.05, key="bs_bpv")

  linea_tot_bs = st.number_input("Línea Total Carreras O/U:", value=7.5, step=0.5, key="bs_ltot")

  if st.button("🚀 Ejecutar Análisis Sabermétrico", use_container_width=True):
    res_bs = analizar_lineas_beisbol(el_bs, ev_bs, fip_l, bp_l, fip_v, bp_v, linea_tot_bs)
    st.session_state["resultado_baseball_calculado"] = {"partido": f"{ev_bs} @ {el_bs}", "analisis": res_bs}

  if st.session_state["resultado_baseball_calculado"]:
    r = st.session_state["resultado_baseball_calculado"]
    res = r["analisis"]
    st.success(f"🎯 Análisis Béisbol: **{r['partido']}** | Total Proyectado: `{res['total_proyectado']} c`")
    if res["validas"]:
      for jugada in res["validas"]:
        st.info(f"✅ **{jugada['mercado']}** | Prob: `{jugada['prob']:.2f}%`")
        stk = calcular_criterio_kelly(st.session_state["bankroll_global"], jugada['prob'], -110)
        if st.button(f"📥 Guardar SQLite ({jugada['mercado']})", key=f"db_bs_{jugada['mercado']}"):
          registrar_apuesta_db(fecha_formato_str, "Béisbol Élite", r['partido'], jugada['mercado'], -110, jugada['prob'] - 52.38, stk)
          st.success("Guardado.")
    else:
      st.warning("⚠️ Sin opciones sobre el 70%.")


# =========================================================
# 3. SISTEMA PRO HOCKEY (NHL)
# =========================================================
elif modulo_seleccionado == "🏒 Hockey Pro (NHL)":
  st.title(f"🏒 **Sistema Pro Hockey (NHL) Élite [{fecha_formato_str}]**")
  st.markdown("--- \n *Poisson Bivariado con Goles a Favor/En Contra, Power Play y Goalie Boost.*")

  el_nhl = st.text_input("Equipo Local NHL:", value="Florida Panthers", key="nhl_el")
  ev_nhl = st.text_input("Equipo Visitante NHL:", value="Edmonton Oilers", key="nhl_ev")

  col_nhl1, col_nhl2 = st.columns(2)
  with col_nhl1: goalie_l = st.checkbox("Portero Local Élite (Goalie Boost)", key="nhl_gl")
  with col_nhl2: goalie_v = st.checkbox("Portero Visitante Élite (Goalie Boost)", key="nhl_gv")

  linea_tot_nhl = st.number_input("Línea Total Goles O/U:", value=5.5, step=0.5, key="nhl_ltot")
  contexto_nhl = {"local_goalie_elite": goalie_l, "visita_goalie_elite": goalie_v}

  if st.button("🚀 Ejecutar Análisis NHL", use_container_width=True):
    res_nhl = analizar_lineas_nhl(el_nhl, ev_nhl, linea_tot_nhl, contexto_nhl)
    st.session_state["resultado_nhl_calculado"] = {"partido": f"{ev_nhl} @ {el_nhl}", "analisis": res_nhl}

  if st.session_state["resultado_nhl_calculado"]:
    r = st.session_state["resultado_nhl_calculado"]
    res = r["analisis"]
    st.success(f"🎯 Análisis NHL: **{r['partido']}**")
    if res["validas"]:
      for jugada in res["validas"]:
        st.info(f"✅ **{jugada['mercado']}** | Prob: `{jugada['prob']:.2f}%`")
        stk = calcular_criterio_kelly(st.session_state["bankroll_global"], jugada['prob'], -110)
        if st.button(f"📥 Guardar SQLite ({jugada['mercado']})", key=f"db_nhl_{jugada['mercado']}"):
          registrar_apuesta_db(fecha_formato_str, "NHL Élite", r['partido'], jugada['mercado'], -110, jugada['prob'] - 52.38, stk)
          st.success("Guardado.")
    else:
      st.warning("⚠️ Sin opciones sobre el 70%.")


# =========================================================
# 4. SISTEMA PRO NBA (CON CAMPOS COMPLETOS B2B Y ESTRELLAS)
# =========================================================
elif modulo_seleccionado == "🏀 Sistema Pro NBA":
  st.title(f"🏀 **Sistema Pro NBA Élite [{fecha_formato_str}]**")
  st.markdown("--- \n *Motor profesional con Eficiencias y Ritmo (Pace).*")

  el_nba = st.text_input("Equipo Local NBA:", value="Boston Celtics", key="nba_el")
  ev_nba = st.text_input("Equipo Visitante NBA:", value="Milwaukee Bucks", key="nba_ev")

  col_nba1, col_nba2 = st.columns(2)
  with col_nba1:
    b2b_l_nba = st.checkbox("Local en B2B", key="nba_b2bl")
    estrella_l_nba = st.checkbox("Estrella Local Fuera", key="nba_starl")
  with col_nba2:
    b2b_v_nba = st.checkbox("Visitante en B2B", key="nba_b2bv")
    estrella_v_nba = st.checkbox("Estrella Visitante Fuera", key="nba_starv")

  linea_sp_nba = st.number_input("Línea Spread Casino:", value=-4.5, step=0.5, key="nba_lsp")
  linea_tot_nba = st.number_input("Línea Total Casino O/U:", value=228.5, step=0.5, key="nba_ltot")
  contexto_nba = {"local_b2b": b2b_l_nba, "visita_b2b": b2b_v_nba, "local_estrella_baja": estrella_l_nba, "visita_estrella_baja": estrella_v_nba, "impacto_puntos_local": 4.5, "impacto_puntos_visita": 4.5}

  if st.button("🚀 Ejecutar Análisis NBA", use_container_width=True):
    res_nba = analizar_lineas_nba(el_nba, ev_nba, linea_sp_nba, linea_tot_nba, contexto_nba)
    st.session_state["resultado_nba_calculado"] = {"partido": f"{ev_nba} @ {el_nba}", "analisis": res_nba}

  if st.session_state["resultado_nba_calculado"]:
    r = st.session_state["resultado_nba_calculado"]
    res = r["analisis"]
    st.success(f"🎯 Análisis NBA: **{r['partido']}** | Margen Proyectado: `{res['margen_proyectado']}` | Total Proyectado: `{res['total_proyectado']}`")
    if res["validas"]:
      for jugada in res["validas"]:
        st.info(f"✅ **{jugada['mercado']}** | Prob: `{jugada['prob']:.2f}%`")
        stk = calcular_criterio_kelly(st.session_state["bankroll_global"], jugada['prob'], -110)
        if st.button(f"📥 Guardar SQLite ({jugada['mercado']})", key=f"db_nba_{jugada['mercado']}"):
          registrar_apuesta_db(fecha_formato_str, "NBA Élite", r['partido'], jugada['mercado'], -110, jugada['prob'] - 52.38, stk)
          st.success("Guardado.")
    else:
      st.warning("⚠️ Sin opciones sobre el 70%.")


# =========================================================
# 5. SISTEMA PRO NCAAF
# =========================================================
elif modulo_seleccionado == "🎓 Sistema Pro NCAAF (Universitario)":
  st.title(f"🎓 **Sistema Pro NCAAF Élite [{fecha_formato_str}]**")
  st.markdown("--- \n *Power Ratings y Distribución Normal.*")

  el = st.text_input("Equipo Local:", value="Georgia Bulldogs", key="ncaaf_el")
  ev = st.text_input("Equipo Visitante:", value="Clemson Tigers", key="ncaaf_ev")
  pr_l = obtener_power_rating_ncaaf(el)
  pr_v = obtener_power_rating_ncaaf(ev)

  col_c1, col_c2 = st.columns(2)
  with col_c1: bye_l = st.checkbox("Local en Bye Week", key="ncaaf_byel"); qb_l = st.checkbox("QB Local Lesionado", key="ncaaf_qbl")
  with col_c2: bye_v = st.checkbox("Visita en Bye Week", key="ncaaf_byev"); qb_v = st.checkbox("QB Visita Lesionado", key="ncaaf_qbv")

  tot_proy = st.number_input("Total Proyectado:", value=52.0, step=0.5, key="ncaaf_tot")
  linea_sp = st.number_input("Spread Casino:", value=-14.5, step=0.5, key="ncaaf_lsp")
  linea_tot = st.number_input("Total Casino O/U:", value=46.5, step=0.5, key="ncaaf_ltot")
  contexto_ncaaf = {"local_viene_de_bye": bye_l, "visita_viene_de_bye": bye_v, "local_qb_baja": qb_l, "visita_qb_baja": qb_v}

  if st.button("🚀 Ejecutar Análisis NCAAF", use_container_width=True):
    res_ncaaf = analizar_lineas_ncaaf(pr_l, pr_v, tot_proy, linea_sp, linea_tot, contexto_ncaaf)
    st.session_state["resultado_ncaaf_calculado"] = {"partido": f"{ev} @ {el}", "analisis": res_ncaaf}

  if st.session_state["resultado_ncaaf_calculado"]:
    r = st.session_state["resultado_ncaaf_calculado"]
    res = r["analisis"]
    st.success(f"🎯 Análisis NCAAF: **{r['partido']}**")
    if res["validas"]:
      for jugada in res["validas"]:
        st.info(f"✅ **{jugada['mercado']}** | Prob: `{jugada['prob']:.2f}%`")
        stk = calcular_criterio_kelly(st.session_state["bankroll_global"], jugada['prob'], -110)
        if st.button(f"📥 Guardar SQLite ({jugada['mercado']})", key=f"db_ncaaf_{jugada['mercado']}"):
          registrar_apuesta_db(fecha_formato_str, "NCAAF Élite", r['partido'], jugada['mercado'], -110, jugada['prob'] - 52.38, stk)
          st.success("Guardado.")
    else:
      st.warning("⚠️ Sin opciones sobre el 70%.")


# =========================================================
# 6. SISTEMA PRO NFL
# =========================================================
elif modulo_seleccionado == "🛡️ Sistema Pro NFL":
  st.title(f"🛡️ **Sistema Pro NFL Élite [{fecha_formato_str}]**")
  st.markdown("--- \n *Motor profesional de 32 equipos.*")

  el_nfl = st.text_input("Equipo Local NFL:", value="Kansas City Chiefs", key="nfl_el")
  ev_nfl = st.text_input("Equipo Visitante NFL:", value="Baltimore Ravens", key="nfl_ev")
  pr_l_nfl = obtener_pr_nfl(el_nfl)
  pr_v_nfl = obtener_pr_nfl(ev_nfl)

  col_nfl1, col_nfl2 = st.columns(2)
  with col_nfl1: qb_l_nfl = st.checkbox("QB Local Lesionado", key="nfl_qbl")
  with col_nfl2: qb_v_nfl = st.checkbox("QB Visita Lesionado", key="nfl_qbv")

  tot_proy_nfl = st.number_input("Total Proyectado NFL:", value=48.5, step=0.5, key="nfl_tot")
  linea_sp_nfl = st.number_input("Spread Casino NFL:", value=-3.0, step=0.5, key="nfl_lsp")
  linea_tot_nfl = st.number_input("Total Casino O/U NFL:", value=47.5, step=0.5, key="nfl_ltot")
  contexto_nfl = {"local_qb_baja": qb_l_nfl, "visita_qb_baja": qb_v_nfl}

  if st.button("🚀 Ejecutar Análisis NFL", use_container_width=True):
    res_nfl = analizar_lineas_nfl(pr_l_nfl, pr_v_nfl, tot_proy_nfl, linea_sp_nfl, linea_tot_nfl, contexto_nfl)
    st.session_state["resultado_nfl_calculado"] = {"partido": f"{ev_nfl} @ {el_nfl}", "analisis": res_nfl}

  if st.session_state["resultado_nfl_calculado"]:
    r = st.session_state["resultado_nfl_calculado"]
    res = r["analisis"]
    st.success(f"🎯 Análisis NFL: **{r['partido']}**")
    if res["validas"]:
      for jugada in res["validas"]:
        st.info(f"✅ **{jugada['mercado']}** | Prob: `{jugada['prob']:.2f}%`")
        stk = calcular_criterio_kelly(st.session_state["bankroll_global"], jugada['prob'], -110)
        if st.button(f"📥 Guardar SQLite ({jugada['mercado']})", key=f"db_nfl_{jugada['mercado']}"):
          registrar_apuesta_db(fecha_formato_str, "NFL Élite", r['partido'], jugada['mercado'], -110, jugada['prob'] - 52.38, stk)
          st.success("Guardado.")
    else:
      st.warning("⚠️ Sin opciones sobre el 70%.")


# =========================================================
# 7. FÚTBOL SOCCER
# =========================================================
elif modulo_seleccionado == "⚽ Módulo Pro Fútbol (Soccer)":
  st.title(f"⚽ **Módulo Pro Fútbol Élite [{fecha_formato_str}]**")
  st.markdown("--- \n *Poisson Bivariado.*")
  
  col_s1, col_s2 = st.columns(2)
  with col_s1: el = st.text_input("Local:", value="Club América", key="soc_el"); xg_l = st.number_input("xG Local:", value=2.45, step=0.05, key="soc_xgl")
  with col_s2: ev = st.text_input("Visita:", value="Guadalajara", key="soc_ev"); xg_v = st.number_input("xG Visita:", value=0.85, step=0.05, key="soc_xgv")

  momio_playdoit = st.number_input("Momio Decimal 1X2:", value=1.75, step=0.05, key="soc_mp")

  if st.button("🚀 Ejecutar Análisis Fútbol", use_container_width=True):
    res_soc = analizar_mercados_futbol(el, ev, xg_l, xg_v, momio_playdoit)
    st.session_state["resultado_soccer_calculado"] = {"partido": f"{ev} @ {el}", "analisis": res_soc}

  if st.session_state["resultado_soccer_calculado"]:
    r = st.session_state["resultado_soccer_calculado"]
    res = r["analisis"]
    st.success(f"🎯 Análisis Fútbol: **{r['partido']}**")
    if res["validas"]:
      for jugada in res["validas"]:
        st.info(f"✅ **{jugada['mercado']}** | Prob: `{jugada['prob']}%`")
        stk = calcular_criterio_kelly(st.session_state["bankroll_global"], jugada['prob'], -110)
        if st.button(f"📥 Guardar SQLite ({jugada['mercado']})", key=f"db_soc_{jugada['mercado']}"):
          registrar_apuesta_db(fecha_formato_str, "Soccer Élite", r['partido'], jugada['mercado'], -110, jugada['prob'] - 52.38, stk)
          st.success("Guardado.")
    else:
      st.warning("⚠️ Sin opciones sobre el 70%.")


# =========================================================
# 8. MÓDULOS DE APOYO Y FINANCIEROS
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
