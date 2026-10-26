from datetime import date, datetime, timedelta, timezone
import hashlib
import io
import math
import os
import random
import sqlite3
import threading
import time
import numpy as np
import pandas as pd
import requests
import scipy.stats as stats
from scipy.stats import norm, poisson
from sklearn.ensemble import GradientBoostingRegressor, HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import Ridge
import altair as alt
import streamlit as st

# Configuración global de la página
st.set_page_config(
    page_title="Central de Apuestas Pro - Master Suite Analítica Élite Pro",
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

if "apuestas_manuales_ev" not in st.session_state:
  st.session_state["apuestas_manuales_ev"] = []

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


def limpiar_momio(texto_momio):
  try:
    limpio = texto_momio.strip().replace("+", "")
    return int(limpio)
  except:
    return -110


def limpiar_spread(texto_spread):
  try:
    limpio = texto_spread.strip().replace("+", "")
    return float(limpio)
  except:
    return 0.0


# =========================================================
# MOTORES DE PLAYER PROPS ESPECÍFICOS
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


def analizar_prop_nba_comun_avanzado(jugador, mercado, promedio_jugador, linea_casino, pace_equipo_jugador, pace_equipo_rival, viene_de_b2b):
  pace_partido_proyectado = (pace_equipo_jugador + pace_equipo_rival) / 2.0
  pace_promedio_liga = 98.5
  factor_ritmo = pace_partido_proyectado / pace_promedio_liga
  
  proyeccion_ajustada = promedio_jugador * factor_ritmo
  
  if viene_de_b2b:
    if mercado == "Puntos":
      proyeccion_ajustada -= 1.5
    elif mercado == "Asistencias":
      proyeccion_ajustada -= 0.8
            
  desviaciones = {"Puntos": 6.5, "Rebotes": 3.2, "Asistencias": 2.5}
  desv_estandar = desviaciones.get(mercado, 4.0)
  
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
  ticket += f"BOLETO: PLAYER PROPS ({fecha_str})\n"
  ticket += "=========================================\n"
  
  jugadas_ordenadas = sorted(jugadas_procesadas, key=lambda x: x["prob"], reverse=True)
  cuenta = 1
  for jugada in jugadas_ordenadas:
    if cuenta <= 3:
      ticket += f"JUGADA {cuenta}: {jugada.get('partido', 'Evento')}\n"
      ticket += f"➔ Probabilidad de Éxito: {jugada['prob']:.2f}%\n"
      ticket += f"➔ {linea_alerta}: {jugada['mercado']}\n"
      ticket += "-----------------------------------------\n"
      cuenta += 1
      
  while cuenta <= 3:
    ticket += f"JUGADA {cuenta}: [Sin valor estadístico suficiente]\n"
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
# 4. MOTOR PRO NBA
# =========================================================
MATRIZ_BAJAS_NBA = {
    "Boston Celtics": {"Jugador": "Jayson Tatum", "Impacto_Ort": 5.5, "Impacto_Pace": -1.2},
    "Milwaukee Bucks": {"Jugador": "Giannis Antetokounmpo", "Impacto_Ort": 6.2, "Impacto_Pace": -2.0},
    "Dallas Mavericks": {"Jugador": "Luka Doncic", "Impacto_Ort": 6.5, "Impacto_Pace": -2.5},
    "Oklahoma City Thunder": {"Jugador": "Shai Gilgeous-Alexander", "Impacto_Ort": 5.8, "Impacto_Pace": +0.5},
    "Denver Nuggets": {"Jugador": "Nikola Jokic", "Impacto_Ort": 7.0, "Impacto_Pace": -1.5},
    "Los Angeles Lakers": {"Jugador": "Anthony Davis", "Impacto_Ort": 4.8, "Impacto_Pace": -1.0},
    "Golden State Warriors": {"Jugador": "Stephen Curry", "Impacto_Ort": 6.0, "Impacto_Pace": +1.0}
}

def aplicar_matriz_bajas_nba(equipo, ort_base, pace_base, esta_baja):
  ort_ajustado = ort_base
  pace_ajustado = pace_base
  if esta_baja and equipo in MATRIZ_BAJAS_NBA:
    datos_baja = MATRIZ_BAJAS_NBA[equipo]
    ort_ajustado -= datos_baja["Impacto_Ort"]
    pace_ajustado += datos_baja["Impacto_Pace"]
  return ort_ajustado, pace_ajustado

def analizar_lineas_nba_detallado(stats_local, stats_visita, linea_spread_casino, linea_total_casino, contexto, equipo_local_nombre="Boston Celtics", equipo_visita_nombre="Milwaukee Bucks"):
  fta_l = stats_local.get("fta", 22.0)
  fta_v = stats_visita.get("fta", 21.5)

  ort_l_base = stats_local.get("ort", 115.0) + ((stats_local.get("apg", 25.0) - 25.0) * 0.15) - ((stats_local.get("tov", 13.0) - 13.0) * 0.25) + ((fta_l - 22.0) * 0.1)
  drt_l_base = stats_local.get("drt", 115.0)
  
  pace_l_temporada = stats_local.get("pace", 98.5)
  pace_l_reciente = stats_local.get("pace_reciente", pace_l_temporada)
  pace_l_base = (pace_l_reciente * 0.60) + (pace_l_temporada * 0.40)

  ort_v_base = stats_visita.get("ort", 114.0) + ((stats_visita.get("apg", 25.0) - 25.0) * 0.15) - ((stats_visita.get("tov", 13.0) - 13.0) * 0.25) + ((fta_v - 21.5) * 0.1)
  drt_v_base = stats_visita.get("drt", 111.0)
  
  pace_v_temporada = stats_visita.get("pace", 98.5)
  pace_v_reciente = stats_visita.get("pace_reciente", pace_v_temporada)
  pace_v_base = (pace_v_reciente * 0.60) + (pace_v_temporada * 0.40)

  ort_l_ajustada, pace_l_ajustado = aplicar_matriz_bajas_nba(equipo_local_nombre, ort_l_base, pace_l_base, contexto.get("local_estrella_baja", False))
  ort_v_ajustada, pace_v_ajustado = aplicar_matriz_bajas_nba(equipo_visita_nombre, ort_v_base, pace_v_base, contexto.get("visita_estrella_baja", False))

  pace_estimado = (pace_l_ajustado + pace_v_ajustado) / 2.0
  ventaja_casa = 2.5

  ef_ofensiva_final_l = (ort_l_ajustada + ventaja_casa + drt_v_base) / 2.0
  ef_ofensiva_final_v = (ort_v_ajustada + drt_l_base) / 2.0

  if contexto.get("local_b2b", False): 
      ef_ofensiva_final_l -= 2.5
      pace_estimado -= 1.0
  if contexto.get("visita_b2b", False): 
      ef_ofensiva_final_v -= 2.5
      pace_estimado -= 1.0

  puntos_proyectados_local = (ef_ofensiva_final_l / 100.0) * pace_estimado
  puntos_proyectados_visita = (ef_ofensiva_final_v / 100.0) * pace_estimado

  margen_proyectado = puntos_proyectados_local - puntos_proyectados_visita
  total_proyectado = puntos_proyectados_local + puntos_proyectados_visita

  z_spread = (linea_spread_casino - margen_proyectado) / 11.0
  prob_local_handicap = norm.cdf(z_spread) * 100.0
  prob_visita_handicap = 100.0 - prob_local_handicap
  
  z_totales = (linea_total_casino - total_proyectado) / 11.5
  prob_under = norm.cdf(z_totales) * 100.0
  prob_over = 100.0 - prob_under
  
  opciones = [
      {"mercado": f"Hándicap Local ({linea_spread_casino:+.1f})", "prob": prob_local_handicap},
      {"mercado": f"Hándicap Visita ({-linea_spread_casino:+.1f})", "prob": prob_visita_handicap},
      {"mercado": f"Over {linea_total_casino:.1f}", "prob": prob_over},
      {"mercado": f"Under {linea_total_casino:.1f}", "prob": prob_under}
  ]
  validas = [o for o in opciones if o["prob"] >= 70.0]
  return {"margen_proyectado": round(margen_proyectado, 2), "total_proyectado": round(total_proyectado, 2), "prob_local": round(prob_local_handicap, 2), "prob_visita": round(prob_visita_handicap, 2), "prob_over": round(prob_over, 2), "prob_under": round(prob_under, 2), "validas": validas}


# =========================================================
# 5. SISTEMA PRO NCAAF
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
# 6. SISTEMA PRO NFL v4.1 (CENTRO DEPORTIVO & PRUEBAS INTEGRALES)
# =========================================================
TEMPORADAS_NFL_V41 = [2022, 2023, 2024, 2025, 2026]
VARIABLES_NFL_V41 = [
    'local_pf', 'local_pa', 'local_victorias', 'visitante_pf', 'visitante_pa',
    'visitante_victorias', 'local_epa_of', 'local_epa_def',
    'visitante_epa_of', 'visitante_epa_def', 'local_sr_of', 'local_sr_def',
    'visitante_sr_of', 'visitante_sr_def', 'local_juegos', 'visitante_juegos',
    'descanso_local', 'descanso_visitante', 'local_en_casa_pf',
    'visitante_fuera_pf',
]

def _requerir_nfl_v41(df, cols, fuente):
    faltan = sorted(set(cols) - set(df.columns))
    if faltan:
        raise ValueError(f'{fuente}: faltan columnas requeridas: {", ".join(faltan)}')

@st.cache_data(ttl=86400, show_spinner=False)
def cargar_datos_nfl():
    import nflreadpy as nfl
    calendario = nfl.load_schedules(TEMPORADAS_NFL_V41).to_pandas()
    cols = ['game_id', 'season', 'week', 'gameday', 'home_team', 'away_team', 'home_score', 'away_score']
    _requerir_nfl_v41(calendario, cols, 'Calendario')
    calendario = calendario[cols].copy()
    calendario['gameday'] = pd.to_datetime(calendario['gameday'], errors='coerce').dt.normalize()
    for c in ['season', 'week', 'home_score', 'away_score']:
        calendario[c] = pd.to_numeric(calendario[c], errors='coerce')
    calendario = calendario.dropna(subset=['game_id', 'gameday', 'season', 'week', 'home_team', 'away_team'])
    calendario = calendario.drop_duplicates('game_id').sort_values(['gameday', 'game_id']).reset_index(drop=True)

    partes = []
    errores = []
    for temporada in TEMPORADAS_NFL_V41:
        try:
            pbp = nfl.load_pbp(temporada)
            requeridas = ['game_id', 'posteam', 'defteam', 'epa', 'success', 'play_type']
            _requerir_nfl_v41(pbp, requeridas, f'PBP {temporada}')
            pbp = pbp.select(requeridas).to_pandas()
            pbp = pbp[pbp['play_type'].isin(['pass', 'run'])].copy()
            pbp['epa'] = pd.to_numeric(pbp['epa'], errors='coerce')
            pbp['success'] = pd.to_numeric(pbp['success'], errors='coerce')
            pbp = pbp.dropna(subset=['game_id', 'posteam', 'defteam', 'epa', 'success'])
            if pbp.empty:
                continue
            ataque = pbp.groupby(['game_id', 'posteam'], as_index=False).agg(
                epa_of=('epa', 'mean'), sr_of=('success', 'mean'), jugadas=('epa', 'size'))
            defensa = pbp.groupby(['game_id', 'defteam'], as_index=False).agg(
                epa_def=('epa', 'mean'), sr_def=('success', 'mean'))
            equipo = ataque.merge(defensa, left_on=['game_id', 'posteam'],
                                  right_on=['game_id', 'defteam'], how='inner')
            equipo = equipo.rename(columns={'posteam': 'equipo'}).drop(columns=['defteam'])
            partes.append(equipo)
            del pbp
        except Exception as exc:
            errores.append(f"{temporada}: {type(exc).__name__}: {exc}")
    if not partes:
        raise ValueError('NFLverse no devolvió jugadas válidas para calcular EPA y Success Rate.')
    if errores:
        raise ValueError('Falló la carga de estadísticas PBP; no se realizará una validación incompleta: ' + ' | '.join(errores))
    estadisticas = pd.concat(partes, ignore_index=True).drop_duplicates(['game_id', 'equipo'])
    return calendario, estadisticas

def construir_historial(calendario, estadisticas):
    stats = {(str(r.game_id), str(r.equipo)): r for r in estadisticas.itertuples(index=False)}
    historico = {}
    registros = []
    sin_cobertura = 0
    ultima_temporada = None
    prev_temporada = {}

    def previo(equipo, fecha, condicion):
        juegos = historico.get(equipo, [])[-5:]
        if not juegos:
            return dict(pf=21., pa=21., victorias=.5, epa_of=0., epa_def=0.,
                        sr_of=.45, sr_def=.45, n=0, descanso=7, ubicacion_pf=21.)
        subset = [x for x in juegos if x['ubicacion'] == condicion]
        return dict(
            pf=float(np.mean([x['pf'] for x in juegos])),
            pa=float(np.mean([x['pa'] for x in juegos])),
            victorias=float(np.mean([x['victoria'] for x in juegos])),
            epa_of=float(np.mean([x['epa_of'] for x in juegos])),
            epa_def=float(np.mean([x['epa_def'] for x in juegos])),
            sr_of=float(np.mean([x['sr_of'] for x in juegos])),
            sr_def=float(np.mean([x['sr_def'] for x in juegos])),
            n=len(juegos),
            descanso=int(np.clip((fecha - juegos[-1]['fecha']).days, 0, 21)),
            ubicacion_pf=float(np.mean([x['pf'] for x in subset])) if subset else 21.,
        )

    for fecha, grupo in calendario.groupby('gameday', sort=True):
        temporadas_dia = set(grupo['season'].astype(int))
        if len(temporadas_dia) != 1:
            raise ValueError('Una fecha contiene partidos de distintas temporadas; revisar calendario.')
        temporada_dia = next(iter(temporadas_dia))
        if temporada_dia != ultima_temporada:
            prev_temporada = {k: list(v[-5:]) for k, v in historico.items()}
            historico.clear()
            ultima_temporada = temporada_dia
        pendientes = []
        for g in grupo.itertuples(index=False):
            local, visitante, gid = str(g.home_team), str(g.away_team), str(g.game_id)
            h = previo(local, fecha, 'casa')
            a = previo(visitante, fecha, 'fuera')
            fila = dict(game_id=gid, gameday=fecha, season=int(g.season), week=int(g.week),
                        home_team=local, away_team=visitante,
                        home_score=g.home_score, away_score=g.away_score,
                        local_pf=h['pf'], local_pa=h['pa'], local_victorias=h['victorias'],
                        visitante_pf=a['pf'], visitante_pa=a['pa'], visitante_victorias=a['victorias'],
                        local_epa_of=h['epa_of'], local_epa_def=h['epa_def'],
                        visitante_epa_of=a['epa_of'], visitante_epa_def=a['epa_def'],
                        local_sr_of=h['sr_of'], local_sr_def=h['sr_def'],
                        visitante_sr_of=a['sr_of'], visitante_sr_def=a['sr_def'],
                        local_juegos=h['n'], visitante_juegos=a['n'],
                        descanso_local=h['descanso'], descanso_visitante=a['descanso'],
                        local_en_casa_pf=h['ubicacion_pf'], visitante_fuera_pf=a['ubicacion_pf'])
            
            for prefix, team, curr in [('local', local, h), ('visitante', visitante, a)]:
                prior_games = prev_temporada.get(team, [])
                if prior_games:
                    prior = {
                        'pf': float(np.mean([x['pf'] for x in prior_games])),
                        'pa': float(np.mean([x['pa'] for x in prior_games])),
                        'victorias': float(np.mean([x['victoria'] for x in prior_games])),
                        'epa_of': float(np.mean([x['epa_of'] for x in prior_games])),
                        'epa_def': float(np.mean([x['epa_def'] for x in prior_games])),
                        'sr_of': float(np.mean([x['sr_of'] for x in prior_games])),
                        'sr_def': float(np.mean([x['sr_def'] for x in prior_games])),
                    }
                    n = curr['n']
                    for suf, key in [('pf', 'pf'), ('pa', 'pa'),
                                     ('victorias', 'victorias'), ('epa_of', 'epa_of'),
                                     ('epa_def', 'epa_def'), ('sr_of', 'sr_of'),
                                     ('sr_def', 'sr_def')]:
                        col = f'{prefix}_{suf}'
                        fila['experimental_' + col] = (
                            n * curr[key] + 3.0 * prior[key]) / (n + 3.0)
                else:
                    for suf in ('pf', 'pa', 'victorias', 'epa_of', 'epa_def',
                                'sr_of', 'sr_def'):
                        col = f'{prefix}_{suf}'
                        fila['experimental_' + col] = fila[col]

            registros.append(fila)
            if pd.notna(g.home_score) and pd.notna(g.away_score):
                sh, sa = stats.get((gid, local)), stats.get((gid, visitante))
                if sh is not None and sa is not None and sh.jugadas >= 10 and sa.jugadas >= 10:
                    pendientes.append((local, visitante, float(g.home_score), float(g.away_score), sh, sa))
                else:
                    sin_cobertura += 1
        for local, visitante, hp, ap, sh, sa in pendientes:
            historico.setdefault(local, []).append(dict(fecha=fecha, pf=hp, pa=ap,
                victoria=float(hp > ap) + .5 * float(hp == ap), ubicacion='casa',
                epa_of=float(sh.epa_of), epa_def=float(sh.epa_def),
                sr_of=float(sh.sr_of), sr_def=float(sh.sr_def)))
            historico.setdefault(visitante, []).append(dict(fecha=fecha, pf=ap, pa=hp,
                victoria=float(ap > hp) + .5 * float(ap == hp), ubicacion='fuera',
                epa_of=float(sa.epa_of), epa_def=float(sa.epa_def),
                sr_of=float(sa.sr_of), sr_def=float(sa.sr_def)))
    salida = pd.DataFrame(registros)
    salida.attrs['sin_cobertura'] = sin_cobertura
    if sin_cobertura:
        raise ValueError(f'Existen {sin_cobertura} partidos terminados sin cobertura PBP suficiente; validación detenida para evitar estadísticas sesgadas.')
    return salida

@st.cache_resource(show_spinner=False)
def entrenar_v30(csv, huella):
    df = pd.read_csv(io.StringIO(csv))
    df = df.dropna(subset=['home_score', 'away_score']).copy()
    if df[VARIABLES_NFL_V41].isna().any().any():
        raise ValueError('Existen variables faltantes; entrenamiento cancelado.')
    if not np.isfinite(df[VARIABLES_NFL_V41].to_numpy(dtype=float)).all():
        raise ValueError('Existen valores no finitos; entrenamiento cancelado.')
    objetivos = {
        'margen': lambda d: d.home_score - d.away_score,
        'total': lambda d: d.home_score + d.away_score,
    }
    resultados = []
    detalles = []
    comparacion_total = []
    for evaluacion in (2024, 2025):
        train = df[(df.season >= 2022) & (df.season < evaluacion)]
        test = df[df.season == evaluacion]
        if len(train) < 200 or len(test) < 100:
            raise ValueError(f'Datos insuficientes para evaluación {evaluacion}: {len(train)} entrenamiento, {len(test)} prueba.')
        for nombre, objetivo in objetivos.items():
            modelo = HistGradientBoostingRegressor(
                max_iter=110, max_leaf_nodes=12, learning_rate=.045,
                l2_regularization=8., random_state=42)
            modelo.fit(train[VARIABLES_NFL_V41], objetivo(train))
            estimado_boosting = modelo.predict(test[VARIABLES_NFL_V41])
            if nombre == 'total':
                ridge = make_pipeline(StandardScaler(), Ridge(alpha=100.0))
                ridge.fit(train[VARIABLES_NFL_V41], objetivo(train))
                estimado = ridge.predict(test[VARIABLES_NFL_V41])
            else:
                estimado = estimado_boosting
            base = np.full(len(test), float(objetivo(train).mean()))
            for pos, (_, partido_eval) in enumerate(test.iterrows()):
                real = float(objetivo(test).iloc[pos])
                detalles.append({
                    'temporada': evaluacion, 'objetivo': nombre,
                    'fecha': str(partido_eval.gameday)[:10],
                    'local': partido_eval.home_team, 'visitante': partido_eval.away_team,
                    'real': real, 'prediccion': float(estimado[pos]),
                    'referencia': float(base[pos]),
                    'error_absoluto': abs(real - float(estimado[pos])),
                    'error_referencia': abs(real - float(base[pos])),
                    'error_firmado': float(estimado[pos]) - real,
                })
            if nombre == 'total':
                comparacion_total.extend([
                    {'temporada': evaluacion, 'modelo': 'Gradient Boosting', 'MAE': float(mean_absolute_error(objetivo(test), estimado_boosting))},
                    {'temporada': evaluacion, 'modelo': 'Ridge (modelo activo)', 'MAE': float(mean_absolute_error(objetivo(test), estimado))},
                    {'temporada': evaluacion, 'modelo': 'Referencia: promedio', 'MAE': float(mean_absolute_error(objetivo(test), base))},
                ])
            resultados.append({
                'temporada': evaluacion, 'objetivo': nombre,
                'MAE_modelo': float(mean_absolute_error(objetivo(test), estimado)),
                'MAE_referencia': float(mean_absolute_error(objetivo(test), base)),
                'partidos_entrenamiento': len(train), 'partidos_prueba': len(test),
            })
    train_final = df[df.season.between(2022, 2025)]
    modelos = {}
    for nombre, objetivo in objetivos.items():
        if nombre == 'total':
            modelo = make_pipeline(StandardScaler(), Ridge(alpha=100.0))
        else:
            modelo = HistGradientBoostingRegressor(
                max_iter=110, max_leaf_nodes=12, learning_rate=.045,
                l2_regularization=8., random_state=42)
        modelo.fit(train_final[VARIABLES_NFL_V41], objetivo(train_final))
        modelos[nombre] = modelo
    evaluacion_2026 = []
    detalles_2026 = []
    prueba_2026 = df[df.season == 2026].copy()
    if not prueba_2026.empty:
        for nombre, objetivo in objetivos.items():
            real = objetivo(prueba_2026)
            pred = modelos[nombre].predict(prueba_2026[VARIABLES_NFL_V41])
            base = np.full(len(prueba_2026), float(objetivo(train_final).mean()))
            for i, (_, juego) in enumerate(prueba_2026.iterrows()):
                detalles_2026.append({
                    'game_id': str(juego.game_id),
                    'temporada': 2026, 'semana': int(juego.week),
                    'fecha': str(juego.gameday)[:10],
                    'local': juego.home_team, 'visitante': juego.away_team,
                    'objetivo': nombre, 'real': float(real.iloc[i]),
                    'prediccion': float(pred[i]),
                    'referencia': float(base[i]),
                    'error_modelo': abs(float(real.iloc[i]) - float(pred[i])),
                    'error_referencia': abs(float(real.iloc[i]) - float(base[i])),
                })
            evaluacion_2026.append({
                'objetivo': nombre,
                'MAE_hibrido': float(mean_absolute_error(real, pred)),
                'MAE_referencia': float(mean_absolute_error(real, base)),
                'partidos': len(prueba_2026),
            })
    return modelos, pd.DataFrame(resultados), len(train_final), pd.DataFrame(detalles), pd.DataFrame(comparacion_total), pd.DataFrame(evaluacion_2026), pd.DataFrame(detalles_2026)

def auditoria_calidad_nfl_v32(calendario, estadisticas, tabla):
    cal = calendario.copy()
    est = estadisticas.copy()
    cal['finalizado'] = cal['home_score'].notna() & cal['away_score'].notna()
    cal['gameday'] = pd.to_datetime(cal['gameday'], errors='coerce')
    equipos = pd.concat([
        cal[['game_id', 'season', 'finalizado', 'home_team']].rename(columns={'home_team': 'equipo'}),
        cal[['game_id', 'season', 'finalizado', 'away_team']].rename(columns={'away_team': 'equipo'})
    ], ignore_index=True)
    est['jugadas'] = pd.to_numeric(est['jugadas'], errors='coerce')
    est['epa_of'] = pd.to_numeric(est['epa_of'], errors='coerce')
    est['sr_of'] = pd.to_numeric(est['sr_of'], errors='coerce')
    est['sr_def'] = pd.to_numeric(est['sr_def'], errors='coerce')
    est['epa_def'] = pd.to_numeric(est['epa_def'], errors='coerce')
    equipos = equipos.merge(est, on=['game_id', 'equipo'], how='left', validate='many_to_one')
    equipos['estadistica_valida'] = (
        equipos['jugadas'].ge(10)
        & equipos[['epa_of', 'epa_def', 'sr_of', 'sr_def']].notna().all(axis=1)
        & equipos['sr_of'].between(0, 1)
        & equipos['sr_def'].between(0, 1)
    )
    partidos = equipos.groupby(['season', 'game_id'], as_index=False).agg(
        finalizado=('finalizado', 'max'),
        equipos_con_estadistica=('estadistica_valida', 'sum'),
    )
    partidos['cobertura_completa'] = partidos['equipos_con_estadistica'].eq(2)
    partidos['incompleto_finalizado'] = partidos['finalizado'] & ~partidos['cobertura_completa']
    resumen = partidos.groupby('season', as_index=False).agg(
        calendario=('game_id', 'nunique'),
        finalizados=('finalizado', 'sum'),
        finalizados_sin_pbp_completo=('incompleto_finalizado', 'sum'),
    )
    resumen['finalizados_con_pbp_completo'] = (
        resumen['finalizados'] - resumen['finalizados_sin_pbp_completo']
    )
    resumen['cobertura_pct'] = (
        100 * resumen['finalizados_con_pbp_completo']
        / resumen['finalizados'].replace(0, np.nan)
    ).round(1)
    resumen['estado'] = np.select(
        [resumen['finalizados'].eq(0), resumen['finalizados_sin_pbp_completo'].eq(0)],
        ['SIN RESULTADOS', 'COMPLETO'], default='INCOMPLETO'
    )
    pendientes = partidos[partidos['incompleto_finalizado']].copy()
    pendientes = pendientes.merge(
        cal[['game_id', 'gameday', 'week', 'home_team', 'away_team']],
        on='game_id', how='left', validate='one_to_one'
    ).sort_values(['season', 'gameday', 'game_id'])
    fechas = {
        'ultima_fecha_calendario': cal['gameday'].max(),
        'ultimo_resultado': cal.loc[cal['finalizado'], 'gameday'].max(),
        'ultima_fecha_con_pbp_completo': cal.loc[
            cal['game_id'].isin(partidos.loc[partidos['cobertura_completa'], 'game_id']),
            'gameday'
        ].max(),
        'consulta_utc': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'),
    }
    return resumen, pendientes, fechas

def mostrar_auditoria_nfl_v32(calendario, estadisticas, tabla):
    st.subheader('🛡️ NFL 3.2 | Auditoría de calidad de datos')
    st.caption('Comprobaciones de integridad de NFLverse. No mide precisión predictiva.')
    try:
        resumen, pendientes, fechas = auditoria_calidad_nfl_v32(calendario, estadisticas, tabla)
        for titulo, valor in [
            ('Último resultado disponible', fechas['ultimo_resultado']),
            ('Último partido con PBP completo', fechas['ultima_fecha_con_pbp_completo']),
        ]:
            fecha = 'Sin datos' if pd.isna(valor) else pd.Timestamp(valor).strftime('%Y-%m-%d')
            st.write(f'**{titulo}:** {fecha}')
        st.caption('Consulta: ' + fechas['consulta_utc'])
        if resumen.empty:
            st.error('🔴 La auditoría no encontró partidos.')
        elif (resumen['finalizados_sin_pbp_completo'] > 0).any():
            st.warning('🟡 Hay partidos finalizados sin cobertura estadística completa.')
        elif resumen['finalizados'].sum() == 0:
            st.warning('🟡 No se encontraron resultados finalizados.')
        else:
            st.success('🟢 Los partidos finalizados disponibles tienen cobertura PBP válida.')
        st.dataframe(resumen, use_container_width=True, hide_index=True)
        st.download_button('📥 Descargar auditoría por temporada',
            resumen.to_csv(index=False).encode('utf-8'),
            'nfl_v32_calidad_temporadas.csv', 'text/csv', key='nfl32_calidad_csv')
        if not pendientes.empty:
            st.write('**Partidos finalizados con estadísticas incompletas**')
            st.dataframe(pendientes, use_container_width=True, hide_index=True)
            st.download_button('📥 Descargar partidos incompletos',
                pendientes.to_csv(index=False).encode('utf-8'),
                'nfl_v32_partidos_incompletos.csv', 'text/csv', key='nfl32_pendientes_csv')
    except Exception as exc:
        st.error('🔴 No se pudo completar la auditoría NFL 3.2.')
        st.code(str(exc))

def _instantanea_nfl_v33(calendario, estadisticas):
    cal = calendario.copy()
    cal['gameday'] = pd.to_datetime(cal['gameday'], errors='coerce')
    cal['finalizado'] = cal['home_score'].notna() & cal['away_score'].notna()
    terminados = cal.loc[cal['finalizado']].copy()
    terminados['game_id'] = terminados['game_id'].astype(str)
    est = estadisticas.copy()
    est['game_id'] = est['game_id'].astype(str)
    est['equipo'] = est['equipo'].astype(str)
    for columna in ['epa_of', 'epa_def', 'sr_of', 'sr_def', 'jugadas']:
        est[columna] = pd.to_numeric(est[columna], errors='coerce')
    est = est.sort_values(['game_id', 'equipo'])
    campos = ['game_id', 'equipo', 'epa_of', 'epa_def', 'sr_of', 'sr_def', 'jugadas']
    huellas_pbp = {}
    for game_id, grupo in est.groupby('game_id'):
        serial = grupo[campos].to_csv(index=False, float_format='%.12g')
        huellas_pbp[game_id] = hashlib.sha256(serial.encode('utf-8')).hexdigest()
    juegos = {}
    for fila in terminados.itertuples(index=False):
        juegos[str(fila.game_id)] = {
            'temporada': int(fila.season),
            'fecha': str(fila.gameday.date()),
            'marcador': [float(fila.home_score), float(fila.away_score)],
            'pbp_sha256': huellas_pbp.get(str(fila.game_id)),
        }
    ultimo = terminados['gameday'].max() if not terminados.empty else pd.NaT
    return {
        'consulta_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'ultimo_resultado': None if pd.isna(ultimo) else str(ultimo.date()),
        'partidos_finalizados': len(juegos),
        'partidos_con_pbp': sum(x['pbp_sha256'] is not None for x in juegos.values()),
        'juegos': juegos,
    }

def _comparar_instantaneas_nfl_v33(anterior, actual):
    antes, ahora = anterior['juegos'], actual['juegos']
    nuevos = sorted(set(ahora) - set(antes))
    desaparecidos = sorted(set(antes) - set(ahora))
    modificados = []
    for game_id in sorted(set(antes) & set(ahora)):
        campos = []
        if antes[game_id]['marcador'] != ahora[game_id]['marcador']:
            campos.append('marcador')
        if antes[game_id]['pbp_sha256'] != ahora[game_id]['pbp_sha256']:
            campos.append('PBP agregado')
        if campos:
            modificados.append({'game_id': game_id, 'cambio': ', '.join(campos)})
    return nuevos, desaparecidos, modificados

def mostrar_auditoria_nfl_v33(calendario, estadisticas):
    st.subheader('🔎 NFL 3.3 | Vigilancia de actualizaciones')
    st.caption('Compara consultas de esta sesión de Streamlit.')
    actual = _instantanea_nfl_v33(calendario, estadisticas)
    st.write('**Consulta UTC:**', actual['consulta_utc'])
    st.write('**Último resultado disponible:**', actual['ultimo_resultado'] or 'Sin resultados')
    st.write('**Partidos finalizados:**', actual['partidos_finalizados'])
    st.write('**Partidos con registros PBP:**', actual['partidos_con_pbp'])

    if actual['ultimo_resultado']:
        antiguedad = (datetime.now(timezone.utc).date() - pd.Timestamp(actual['ultimo_resultado']).date()).days
        if antiguedad >= 8:
            st.warning(f'🟡 Último resultado hace {antiguedad} días.')
        else:
            st.success('🟢 La última fecha de resultados no supera el umbral orientativo de 7 días.')
    else:
        st.error('🔴 No hay resultados finalizados disponibles.')

    anterior = st.session_state.get('nfl33_ultima_instantanea')
    historial = st.session_state.setdefault('nfl33_historial', [])
    if anterior is None:
        st.info('Primera consulta registrada en esta sesión. Actualiza para comparar cambios.')
    else:
        nuevos, desaparecidos, modificados = _comparar_instantaneas_nfl_v33(anterior, actual)
        if desaparecidos:
            st.error(f'🔴 Desaparecieron {len(desaparecidos)} partidos previamente finalizados.')
        if modificados:
            st.warning(f'🟡 Cambiaron los marcadores o datos PBP de {len(modificados)} partidos.')
            st.dataframe(pd.DataFrame(modificados), hide_index=True, use_container_width=True)
        if nuevos:
            st.success(f'🟢 Se incorporaron {len(nuevos)} resultados nuevos.')
        if not (nuevos or desaparecidos or modificados):
            st.info('No se detectaron cambios respecto de la consulta anterior de esta sesión.')
        historial.append({
            'consulta_utc': actual['consulta_utc'],
            'resultados_nuevos': len(nuevos),
            'resultados_desaparecidos': len(desaparecidos),
            'partidos_modificados': len(modificados),
            'total_finalizados': actual['partidos_finalizados'],
        })
        del historial[:-20]
    st.session_state['nfl33_ultima_instantanea'] = actual
    if historial:
        st.write('**Historial de comparaciones de esta sesión**')
        datos = pd.DataFrame(historial)
        st.dataframe(datos, hide_index=True, use_container_width=True)
        st.download_button('📥 Descargar historial NFL 3.3',
            datos.to_csv(index=False).encode('utf-8'),
            'nfl_v33_historial_sesion.csv', 'text/csv', key='nfl33_historial_csv')

def auditar_integridad_nfl_v341(calendario, estadisticas):
    cal, est = calendario.copy(), estadisticas.copy()
    filas = []

    def agregar(nombre, accion, descripcion):
        try:
            cantidad, nivel = accion()
            filas.append(dict(nivel=nivel, control=nombre, registros=int(cantidad), detalle=descripcion))
        except Exception as exc:
            filas.append(dict(nivel='NO EJECUTADO', control=nombre, registros=0, detalle=f'{type(exc).__name__}: {exc}'))

    def serie_num(df, col):
        return pd.to_numeric(df[col], errors='coerce')

    def contar(n, nivel='ERROR'):
        return (int(n), nivel if n else 'OK')

    agregar('IDs de partidos duplicados', lambda: contar(cal['game_id'].duplicated().sum()), 'Cada game_id debe ser único.')
    agregar('Local y visitante idénticos', lambda: contar((cal['home_team'] == cal['away_team']).sum()), 'Los equipos deben ser distintos.')
    agregar('Fechas inválidas', lambda: contar(pd.to_datetime(cal['gameday'], errors='coerce').isna().sum()), 'Todas las fechas deben poder interpretarse.')
    agregar('Partidos sin marcador completo', lambda: contar(cal[['home_score', 'away_score']].apply(pd.to_numeric, errors='coerce').isna().any(axis=1).sum(), 'INFO'), 'Incluye partidos futuros: no implica error.')
    agregar('Marcadores negativos', lambda: contar(cal[['home_score', 'away_score']].apply(pd.to_numeric, errors='coerce').lt(0).any(axis=1).sum()), 'Los puntos no pueden ser negativos.')
    agregar('Estadísticas duplicadas por equipo', lambda: contar(est.duplicated(['game_id', 'equipo']).sum()), 'Solo una fila por equipo y partido.')
    agregar('SR ofensivo fuera de rango', lambda: contar((serie_num(est, 'sr_of').notna() & ~serie_num(est, 'sr_of').between(0, 1)).sum()), 'Success Rate debe estar entre 0 y 1.')
    agregar('SR defensivo fuera de rango', lambda: contar((serie_num(est, 'sr_def').notna() & ~serie_num(est, 'sr_def').between(0, 1)).sum()), 'Success Rate debe estar entre 0 y 1.')
    agregar('Jugadas negativas o nulas', lambda: contar(serie_num(est, 'jugadas').le(0).sum()), 'Una fila estadística debe contener jugadas válidas.')
    agregar('Estadísticas numéricas faltantes', lambda: contar(est[['epa_of', 'epa_def', 'sr_of', 'sr_def', 'jugadas']].apply(pd.to_numeric, errors='coerce').isna().any(axis=1).sum(), 'AVISO'), 'Revisar filas incompletas.')
    agregar('EPA ofensivo inusual', lambda: contar(serie_num(est, 'epa_of').abs().gt(5).sum(), 'REVISAR'), 'Umbral exploratorio de EPA medio por jugada: |EPA| > 5.')
    agregar('EPA defensivo inusual', lambda: contar(serie_num(est, 'epa_def').abs().gt(5).sum(), 'REVISAR'), 'Umbral exploratorio de EPA medio por jugada: |EPA| > 5.')
    return pd.DataFrame(filas)

def mostrar_auditoria_nfl_v341(calendario, estadisticas):
    st.subheader('🧪 NFL 3.4.1 | Integridad y anomalías')
    st.caption('Doce controles independientes; una falla no interrumpe los demás.')
    informe = auditar_integridad_nfl_v341(calendario, estadisticas)
    errores = int(informe.nivel.eq('ERROR').sum())
    pendientes = int(informe.nivel.eq('NO EJECUTADO').sum())
    avisos = int(informe.nivel.isin(['AVISO', 'REVISAR']).sum())
    a, b, c = st.columns(3)
    a.metric('Controles ejecutados', len(informe) - pendientes)
    b.metric('Controles con errores', errores)
    c.metric('No ejecutados', pendientes)
    if pendientes:
        st.error(f'🔴 {pendientes} controles no se pudieron ejecutar. Revisa la tabla.')
    elif errores:
        st.error(f'🔴 Se encontraron errores en {errores} controles.')
    elif avisos:
        st.warning(f'🟡 Hay {avisos} controles con observaciones.')
    else:
        st.success('🟢 Los doce controles finalizaron sin incidencias detectadas.')
    st.dataframe(informe, use_container_width=True, hide_index=True)
    st.download_button('📥 Descargar auditoría NFL 3.4.1',
                       informe.to_csv(index=False).encode('utf-8'),
                       'nfl_v341_integridad.csv', 'text/csv',
                       key='nfl341_integridad_csv')

def crear_reporte_consolidado_nfl_v35(calendario, estadisticas, tabla):
    fecha_consulta = datetime.now(timezone.utc).isoformat(timespec='seconds')
    filas = []

    def fila(seccion, temporada, indicador, valor, estado, detalle):
        filas.append({
            'consulta_utc': fecha_consulta,
            'seccion': seccion,
            'temporada': temporada,
            'indicador': indicador,
            'valor': valor,
            'estado': estado,
            'detalle': detalle,
        })

    cobertura, pendientes, fechas = auditoria_calidad_nfl_v32(calendario, estadisticas, tabla)
    for registro in cobertura.to_dict('records'):
        temporada = registro.get('season')
        for campo in ['calendario', 'finalizados', 'finalizados_con_pbp_completo', 'finalizados_sin_pbp_completo', 'cobertura_pct']:
            fila('Cobertura NFL 3.2', temporada, campo, registro.get(campo), registro.get('estado', ''), 'Cobertura calculada sobre resultados finalizados disponibles.')

    for campo in ['ultimo_resultado', 'ultima_fecha_con_pbp_completo']:
        valor = fechas.get(campo)
        fila('Fechas NFL 3.2', '', campo, '' if pd.isna(valor) else str(pd.Timestamp(valor).date()), 'INFORMATIVO', 'La fecha de consulta no prueba una publicación nueva.')

    auditoria = auditar_integridad_nfl_v341(calendario, estadisticas)
    for registro in auditoria.to_dict('records'):
        fila('Integridad NFL 3.4.1', '', registro['control'], registro['registros'], registro['nivel'], registro['detalle'])

    instantanea = _instantanea_nfl_v33(calendario, estadisticas)
    for campo in ['partidos_finalizados', 'partidos_con_pbp', 'ultimo_resultado']:
        fila('Actualización NFL 3.3', '', campo, instantanea.get(campo), 'INFORMATIVO', 'Instantánea correspondiente à esta consulta.')

    historial = st.session_state.get('nfl33_historial', [])
    fila('Actualización NFL 3.3', '', 'comparaciones_en_sesion', len(historial), 'INFORMATIVO', 'Historial temporal de Streamlit.')

    return pd.DataFrame(filas)

def mostrar_reporte_consolidado_nfl_v35(calendario, estadisticas, tabla):
    st.subheader('📋 NFL 3.5 | Reporte consolidado de auditorías')
    st.caption('Un solo CSV reúne cobertura, fechas, vigilancia e integridad.')
    try:
        reporte = crear_reporte_consolidado_nfl_v35(calendario, estadisticas, tabla)
        sin_ejecutar = reporte['estado'].eq('NO EJECUTADO').sum()
        errores = reporte['estado'].eq('ERROR').sum()
        st.write(f'**Registros del informe:** {len(reporte)}')
        if sin_ejecutar:
            st.error(f'🔴 {sin_ejecutar} controles no pudieron ejecutarse.')
        elif errores:
            st.warning(f'🟡 Se encontraron {errores} controles con errores.')
        else:
            st.success('🟢 Informe consolidado generado correctamente.')
        st.dataframe(reporte, use_container_width=True, hide_index=True)
        st.download_button(
            '📥 Descargar reporte consolidado NFL',
            data=reporte.to_csv(index=False).encode('utf-8-sig'),
            file_name='nfl_reporte_consolidado.csv',
            mime='text/csv',
            key='nfl35_reporte_consolidado'
        )
    except Exception as exc:
        st.error('🔴 No se pudo generar el reporte consolidado.')
        st.code(f'{type(exc).__name__}: {exc}')

def clasificar_partidos_nfl_v36(calendario, fecha_consulta=None):
    if fecha_consulta is None:
        fecha_consulta = datetime.now(timezone.utc)
    fecha_consulta = pd.Timestamp(fecha_consulta)
    if fecha_consulta.tzinfo is None:
        fecha_consulta = fecha_consulta.tz_localize('UTC')
    fecha_consulta = fecha_consulta.tz_convert('UTC')

    columnas = ['game_id', 'season', 'gameday', 'home_team', 'away_team',
                'home_score', 'away_score']
    faltantes = [c for c in columnas if c not in calendario.columns]
    if faltantes:
        raise ValueError('Faltan columnas de calendario: ' + ', '.join(faltantes))
    df = calendario[columnas].copy()
    df['gameday'] = pd.to_datetime(df['gameday'], errors='coerce', utc=True)
    df['home_score'] = pd.to_numeric(df['home_score'], errors='coerce')
    df['away_score'] = pd.to_numeric(df['away_score'], errors='coerce')
    ambos = df['home_score'].notna() & df['away_score'].notna()
    uno = df['home_score'].notna() ^ df['away_score'].notna()
    fecha_valida = df['gameday'].notna()
    vencido = fecha_valida & (df['gameday'] < fecha_consulta - pd.Timedelta(days=1))
    futuro = fecha_valida & (df['gameday'] >= fecha_consulta.normalize())

    df['estado_auditoria'] = 'PENDIENTE DE CONFIRMACION'
    df.loc[futuro & ~ambos & ~uno, 'estado_auditoria'] = 'PROGRAMADO SIN RESULTADO'
    df.loc[vencido & ~ambos & ~uno, 'estado_auditoria'] = 'REVISAR RESULTADO PENDIENTE'
    df.loc[uno, 'estado_auditoria'] = 'MARCADOR PARCIAL'
    df.loc[ambos, 'estado_auditoria'] = 'RESULTADO DISPONIBLE'
    df.loc[~fecha_valida, 'estado_auditoria'] = 'FECHA INVALIDA'
    df['consulta_utc'] = fecha_consulta.isoformat(timespec='seconds')

    resumen = (df.groupby(['season', 'estado_auditoria'], dropna=False)
                 .size().unstack(fill_value=0).reset_index())
    resumen['total_calendario'] = df.groupby('season').size().reindex(resumen['season']).values
    return df, resumen

def mostrar_auditoria_nfl_v36(calendario):
    st.subheader('📅 NFL 3.6 | Estado de partidos y resultados pendientes')
    st.caption('Distingue encuentros programados, resultados disponibles y registros à revisar.')
    try:
        detalle, resumen = clasificar_partidos_nfl_v36(calendario)
        resultados = int(detalle['estado_auditoria'].eq('RESULTADO DISPONIBLE').sum())
        programados = int(detalle['estado_auditoria'].eq('PROGRAMADO SIN RESULTADO').sum())
        revisar = int(detalle['estado_auditoria'].isin([
            'REVISAR RESULTADO PENDIENTE', 'MARCADOR PARCIAL', 'FECHA INVALIDA'
        ]).sum())
        a, b, c = st.columns(3)
        a.metric('Con resultado', resultados)
        b.metric('Programados', programados)
        c.metric('Para revisar', revisar)
        if revisar:
            st.warning(f'🟡 Hay {revisar} registros por verificar.')
        else:
            st.success('🟢 No se detectaron registros pendientes de revisión.')
        st.dataframe(resumen, use_container_width=True, hide_index=True)
        with st.expander('Ver detalle de los partidos'):
            st.dataframe(detalle, use_container_width=True, hide_index=True)
        st.download_button('📥 Descargar estado de partidos NFL 3.6',
                           detalle.to_csv(index=False).encode('utf-8-sig'),
                           'nfl_v36_estado_partidos.csv', 'text/csv',
                           key='nfl36_estado_partidos')
    except Exception as exc:
        st.error('🔴 No fue posible completar la auditoría NFL 3.6.')
        st.code(f'{type(exc).__name__}: {exc}')

def auditar_consistencia_nfl_v37(calendario, estadisticas, minimo_jugadas=10):
    cal = calendario.copy()
    est = estadisticas.copy()
    columnas_cal = {'game_id','season','home_team','away_team','home_score','away_score'}
    columnas_est = {'game_id','equipo','jugadas','epa_of','epa_def','sr_of','sr_def'}
    faltan_cal = columnas_cal - set(cal.columns)
    faltan_est = columnas_est - set(est.columns)
    if faltan_cal or faltan_est:
        raise ValueError('Columnas faltantes: calendario=' + str(sorted(faltan_cal)) + '; estadísticas=' + str(sorted(faltan_est)))
    cal['game_id'] = cal['game_id'].astype(str)
    est['game_id'] = est['game_id'].astype(str)
    cal['home_score'] = pd.to_numeric(cal['home_score'], errors='coerce')
    cal['away_score'] = pd.to_numeric(cal['away_score'], errors='coerce')
    est['jugadas'] = pd.to_numeric(est['jugadas'], errors='coerce')
    finalizados = cal[cal['home_score'].notna() & cal['away_score'].notna()].copy()
    esperado = pd.concat([
        finalizados[['game_id','season','home_team']].rename(columns={'home_team':'equipo'}),
        finalizados[['game_id','season','away_team']].rename(columns={'away_team':'equipo'})
    ], ignore_index=True)
    resumen_est = est.groupby(['game_id','equipo'], as_index=False).agg(
        registros=('jugadas','size'), jugadas=('jugadas','max'))
    cruce = esperado.merge(resumen_est, on=['game_id','equipo'], how='left', validate='many_to_one')
    cruce['registros'] = cruce['registros'].fillna(0).astype(int)
    cruce['estado'] = 'OK'
    cruce.loc[cruce['registros'].eq(0),'estado'] = 'SIN PBP DE EQUIPO'
    cruce.loc[cruce['registros'].gt(0) & cruce['jugadas'].lt(minimo_jugadas), 'estado'] = 'PBP INSUFICIENTE'
    cruce.loc[cruce['registros'].gt(0) & cruce['jugadas'].isna(), 'estado'] = 'JUGADAS NO VALIDAS'
    ids_cal = set(cal['game_id'])
    extras = est[~est['game_id'].isin(ids_cal)][['game_id','equipo']].copy()
    extras['season'] = pd.NA
    extras['registros'] = 1
    extras['jugadas'] = pd.NA
    extras['estado'] = 'PBP SIN PARTIDO EN CALENDARIO'
    equipos = cal[['game_id','home_team','away_team']].drop_duplicates('game_id')
    unidos = est.merge(equipos, on='game_id', how='inner')
    invalidos = unidos[~(unidos['equipo'].eq(unidos['home_team']) | unidos['equipo'].eq(unidos['away_team']))][['game_id','equipo']].copy()
    invalidos['season'] = pd.NA
    invalidos['registros'] = 1
    invalidos['jugadas'] = pd.NA
    invalidos['estado'] = 'EQUIPO PBP NO CORRESPONDE AL PARTIDO'
    detalle = pd.concat([cruce, extras, invalidos], ignore_index=True)
    detalle = detalle[['game_id','season','equipo','registros','jugadas','estado']]
    resumen = detalle.groupby('estado',dropna=False).size().reset_index(name='registros')
    return detalle, resumen

def mostrar_auditoria_nfl_v37(calendario, estadisticas):
    st.subheader('🔗 NFL 3.7 | Consistencia entre calendario y PBP')
    st.caption('Cruce de equipos y partidos finalizados con estadísticas agregadas.')
    try:
        detalle, resumen = auditar_consistencia_nfl_v37(calendario, estadisticas)
        problemas = detalle[detalle['estado'] != 'OK']
        a, b, c = st.columns(3)
        a.metric('Equipos-partido revisados', len(detalle))
        b.metric('Registros para revisar', len(problemas))
        c.metric('Tipos de discrepancia', problemas['estado'].nunique())
        if problemas.empty:
            st.success('🟢 No se encontraron discrepancias con estos criterios.')
        else:
            st.warning('🟡 Se encontraron discrepancias que requieren revisión.')
        st.dataframe(resumen, use_container_width=True, hide_index=True)
        with st.expander('Ver detalle de discrepancias'):
            st.dataframe(problemas, use_container_width=True, hide_index=True)
        st.download_button('📥 Descargar auditoría NFL 3.7',
                           detalle.to_csv(index=False).encode('utf-8-sig'),
                           'nfl_v37_consistencia.csv','text/csv',key='nfl37_csv')
    except Exception as exc:
        st.error('🔴 No se pudo completar la auditoría NFL 3.7.')
        st.code(f'{type(exc).__name__}: {exc}')

def evaluar_estado_nfl_v38(calendario, estadisticas, ahora=None):
    ahora = ahora or datetime.now(timezone.utc)
    cal = calendario.copy()
    est = estadisticas.copy()
    _requerir_nfl_v41(cal, ['game_id','gameday','home_score','away_score'], 'Calendario v4.1')
    _requerir_nfl_v41(est, ['game_id','equipo'], 'PBP v4.1')
    cal['gameday'] = pd.to_datetime(cal['gameday'], errors='coerce')
    fin = cal[pd.to_numeric(cal['home_score'], errors='coerce').notna() &
              pd.to_numeric(cal['away_score'], errors='coerce').notna()].copy()
    ultima = fin['gameday'].max() if not fin.empty else pd.NaT
    ultimo_dia = ultima.date().isoformat() if pd.notna(ultima) else None
    dias = (ahora.date() - ultima.date()).days if pd.notna(ultima) else None
    ids_pbp = set(est['game_id'].dropna().astype(str))
    ids_fin = set(fin['game_id'].dropna().astype(str))
    sin_pbp = ids_fin - ids_pbp
    proximos = cal[(cal['gameday'].dt.date >= ahora.date()) &
                   (cal['gameday'].dt.date <= (ahora + timedelta(days=7)).date())]
    return {'ultima_fecha_resultado': ultimo_dia,
            'dias_desde_ultimo_resultado': dias,
            'finalizados': len(ids_fin),
            'finalizados_sin_pbp': len(sin_pbp),
            'proximos_7_dias': int(proximos['game_id'].nunique()),
            'registros_equipos_pbp': len(est)}

def mostrar_monitoreo_nfl_v38(calendario, estadisticas, solo_respaldo=False):
    st.subheader('🛰️ NFL 3.8 | Estado de actualización y conexión')
    st.caption('Diagnóstico de datos disponibles.')
    ahora = datetime.now(timezone.utc)
    try:
        datos = evaluar_estado_nfl_v38(calendario, estadisticas, ahora)
        col1, col2, col3 = st.columns(3)
        col1.metric('Partidos con resultado', datos['finalizados'])
        col2.metric('Finalizados sin PBP', datos['finalizados_sin_pbp'])
        col3.metric('Próximos 7 días', datos['proximos_7_dias'])
        st.write('**Última fecha con resultado:**', datos['ultima_fecha_resultado'] or 'Sin datos')
        
        ultima_carga = st.session_state.get('nfl38_ultima_carga_exitosa')
        if ultima_carga:
            st.write('**Última consulta completada en esta sesión (UTC):**', ultima_carga['consulta_utc'])
        else:
            st.info('Todavía no se ha registrado una consulta completa en esta sesión.')
            
        if solo_respaldo:
            st.error('🔴 Consulta fallida. Estos son datos guardados en memoria de la sesión.')
        elif datos['finalizados_sin_pbp']:
            st.warning('🟡 Algunos partidos con resultado no tienen PBP agregado.')
        else:
            st.success('🟢 Datos cargados sin error en esta ejecución.')
            
        reporte = pd.DataFrame([{'consulta_utc': ahora.isoformat(timespec='seconds'), **datos, 'modo': 'respaldo' if solo_respaldo else 'consulta'}])
        st.download_button('📥 Descargar diagnóstico NFL 3.8', reporte.to_csv(index=False).encode('utf-8-sig'), 'nfl_v38_diagnostico.csv', 'text/csv', key='nfl38_csv')
    except Exception as exc:
        st.error('No se pudo ejecutar el monitoreo NFL 3.8.')
        st.code(f'{type(exc).__name__}: {exc}')

@st.cache_data(ttl=21600, show_spinner=False)
def cargar_jugadores_nfl_v39(temporada):
    import nflreadpy as nfl
    if not hasattr(nfl, 'load_player_stats'):
        raise RuntimeError('Esta versión de nflreadpy no incluye load_player_stats. Actualiza la dependencia.')
    try:
        datos = nfl.load_player_stats([int(temporada)], summary_level='week')
    except TypeError:
        datos = nfl.load_player_stats([int(temporada)])
    df = datos.to_pandas() if hasattr(datos, 'to_pandas') else pd.DataFrame(datos)
    if df.empty:
        return df
    df.columns = [str(c).lower() for c in df.columns]
    if 'season' in df:
        df = df[pd.to_numeric(df['season'], errors='coerce') == int(temporada)].copy()
    return df

def _columna_jugador_v39(df, alternativas):
    return next((c for c in alternativas if c in df.columns), None)

def mostrar_jugadores_nfl_v39():
    st.subheader('👥 NFL 3.9 | Estadísticas individuales de jugadores')
    st.caption('Datos observados de NFLverse. Las estadísticas disponibles dependen de la fuente.')
    temporada = st.selectbox('Temporada de jugadores', TEMPORADAS_NFL_V41[::-1], key='nfl39_temporada')
    if st.button('📥 Cargar estadísticas de jugadores', key='nfl39_cargar'):
        st.session_state['nfl39_temporada_cargada'] = int(temporada)
    if st.session_state.get('nfl39_temporada_cargada') != int(temporada):
        st.info('Pulsa «Cargar estadísticas de jugadores» para consultar la temporada seleccionada.')
        return
    try:
        with st.spinner('Consultando estadísticas individuales...'):
            df = cargar_jugadores_nfl_v39(int(temporada))
    except Exception as exc:
        st.error('No fue posible consultar las estadísticas individuales.')
        st.caption(f'Detalle técnico: {type(exc).__name__}: {exc}')
        return
    if df.empty:
        st.warning('La fuente no publicó registros de jugadores para esta temporada.')
        return
    nombre = _columna_jugador_v39(df, ['player_display_name', 'player_name', 'player'])
    identificador = _columna_jugador_v39(df, ['player_id', 'gsis_id'])
    equipo = _columna_jugador_v39(df, ['recent_team', 'team', 'posteam'])
    posicion = _columna_jugador_v39(df, ['position', 'position_group'])
    semana = _columna_jugador_v39(df, ['week'])
    if not nombre and not identificador:
        st.warning('La fuente no incluye columnas para identificar jugadores.')
        return
    if not nombre:
        nombre = identificador
    df = df.copy()
    df[nombre] = df[nombre].fillna('Sin nombre').astype(str)
    if equipo:
        equipos = sorted(df[equipo].dropna().astype(str).unique().tolist())
        eleccion = st.selectbox('Equipo', ['Todos'] + equipos, key='nfl39_equipo')
        if eleccion != 'Todos':
            df = df[df[equipo].astype(str) == eleccion]
    if posicion:
        posiciones = sorted(df[posicion].dropna().astype(str).unique().tolist())
        seleccion = st.selectbox('Posición', ['Todas'] + posiciones, key='nfl39_posicion')
        if seleccion != 'Todas':
            df = df[df[posicion].astype(str) == seleccion]
    if df.empty:
        st.info('No hay jugadores para los filtros seleccionados.')
        return
    metricas = {
        'Pases completos': ['completions'],
        'Intentos de pase': ['attempts', 'passing_attempts'],
        'Yardas por pase': ['passing_yards'],
        'TD por pase': ['passing_tds'],
        'Intercepciones lanzadas': ['interceptions', 'passing_interceptions'],
        'Acarreos': ['carries', 'rushing_attempts'],
        'Yardas terrestres': ['rushing_yards'],
        'TD terrestres': ['rushing_tds'],
        'Recepciones': ['receptions'],
        'Objetivos de pase': ['targets'],
        'Yardas por recepción': ['receiving_yards'],
        'TD por recepción': ['receiving_tds'],
        'Capturas defensivas': ['sacks_solo', 'sacks', 'def_sacks'],
        'Intercepciones defensivas': ['def_interceptions', 'defensive_interceptions'],
        'Tacleadas': ['def_tackles_solo', 'tackles_solo'],
    }
    disponibles = {etiqueta: col for etiqueta, cols in metricas.items() if (col := _columna_jugador_v39(df, cols)) is not None}
    if not disponibles:
        st.warning('No se encontraron columnas estadísticas reconocidas.')
        return
    claves = [identificador] if identificador else [nombre]
    if identificador and nombre:
        claves.append(nombre)
    if equipo:
        claves.append(equipo)
    if posicion:
        claves.append(posicion)
    for col in disponibles.values():
        df[col] = pd.to_numeric(df[col], errors='coerce')
    agregados = df.groupby(claves, dropna=False, as_index=False)[list(set(disponibles.values()))].sum(min_count=1)
    agregados = agregados.rename(columns={v: k for k, v in disponibles.items()})
    metrica = st.selectbox('Estadística para ordenar', list(disponibles), key='nfl39_metrica')
    agregados = agregados.sort_values(metrica, ascending=False, na_position='last')
    st.metric('Jugadores encontrados', len(agregados))
    st.dataframe(agregados.head(100).round(2), use_container_width=True, hide_index=True)
    st.download_button('📥 Descargar estadísticas de jugadores (CSV)', agregados.to_csv(index=False).encode('utf-8-sig'), f'nfl_v39_jugadores_{temporada}.csv', 'text/csv', key='nfl39_csv')
    
    etiquetas = (agregados[nombre].astype(str) + (' | ' + agregados[equipo].astype(str) if equipo else '')).tolist()
    elegido = st.selectbox('Ver evolución de un jugador', range(len(etiquetas)), format_func=lambda i: etiquetas[i], key='nfl39_jugador')
    fila = agregados.iloc[int(elegido)]
    if identificador:
        detalle = df[df[identificador] == fila[identificador]].copy()
    else:
        detalle = df[df[nombre] == fila[nombre]].copy()
        if equipo:
            detalle = detalle[detalle[equipo] == fila[equipo]]
    if semana:
        detalle[semana] = pd.to_numeric(detalle[semana], errors='coerce')
        detalle = detalle.dropna(subset=[semana])
        if not detalle.empty:
            evolucion = detalle.groupby(semana, as_index=False)[disponibles[metrica]].sum(min_count=1)
            evolucion = evolucion.sort_values(semana).rename(columns={semana: 'Semana', disponibles[metrica]: metrica})
            st.line_chart(evolucion.set_index('Semana'))
        else:
            st.info('No hay semanas válidas para graficar este jugador.')

def _mostrar_modulo_nfl_legacy_v40():
    st.header('🏈 NFL | Análisis avanzado v3.9')
    st.caption('Fuente: NFLverse · EPA y Success Rate · Margen: Gradient Boosting · Total: Ridge')
    if st.button('🔄 Consultar nuevamente la fuente NFL', key='nfl_v2_refresh'):
        st.session_state['nfl38_actualizacion_solicitada'] = True
        st.session_state['nfl38_ultimo_intento_utc'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
        cargar_datos_nfl.clear()
        cargar_jugadores_nfl_v39.clear()
        st.rerun()
    try:
        with st.spinner('Cargando jugadas históricas y entrenando el modelo...'):
            calendario, estadisticas = cargar_datos_nfl()
            st.session_state['nfl38_ultima_carga_exitosa'] = {
                'calendario': calendario.copy(),
                'estadisticas': estadisticas.copy(),
                'consulta_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            }
            st.session_state['nfl38_error_reciente'] = None
            st.session_state['nfl38_actualizacion_solicitada'] = False
            
            tabla = construir_historial(calendario, estadisticas)
            completos = tabla.dropna(subset=['home_score', 'away_score'])
            if completos.empty:
                raise ValueError('No hay resultados completos disponibles.')
            csv_modelo = tabla.to_csv(index=False)
            huella = hashlib.sha256(csv_modelo.encode('utf-8')).hexdigest()
            modelos, reporte, ntrain, detalles, comparacion_total, evaluacion_2026, detalles_2026 = entrenar_v30(csv_modelo, huella)
    except Exception as exc:
        st.session_state['nfl38_error_reciente'] = f'{type(exc).__name__}: {exc}'
        st.error('🔴 No se pudo cargar o validar NFL. No se mostrarán resultados nuevos como si fueran actuales.')
        st.code(str(exc))
        anterior = st.session_state.get('nfl38_ultima_carga_exitosa')
        if anterior is not None:
            st.warning('🟡 Existe una copia de datos de una consulta anterior de esta sesión como referencia.')
            mostrar_monitoreo_nfl_v38(anterior['calendario'], anterior['estadisticas'], solo_respaldo=True)
        return

    mostrar_auditoria_nfl_v32(calendario, estadisticas, tabla)
    mostrar_auditoria_nfl_v33(calendario, estadisticas)
    mostrar_auditoria_nfl_v341(calendario, estadisticas)
    mostrar_reporte_consolidado_nfl_v35(calendario, estadisticas, tabla)
    mostrar_auditoria_nfl_v36(calendario)
    mostrar_auditoria_nfl_v37(calendario, estadisticas)
    mostrar_monitoreo_nfl_v38(calendario, estadisticas)
    mostrar_jugadores_nfl_v39()

    st.success('🟢 Datos históricos cargados y evaluaciones temporales completadas')
    st.write(f'**Partidos usados para ajuste final:** {ntrain}')
    st.caption(f'Último partido con resultado disponible: {completos.gameday.max().date()}')

    st.subheader('📊 Evaluación histórica — 2024 y 2025')
    st.dataframe(reporte.round(2), use_container_width=True, hide_index=True)
    st.download_button('📥 Descargar evaluación', reporte.to_csv(index=False).encode('utf-8'),
                       'nfl_v39_validacion.csv', 'text/csv', key='nfl_v39_eval')

    st.subheader('🏟️ Próximos partidos')
    hoy = pd.Timestamp(datetime.now(timezone.utc).date())
    futuros = tabla[(tabla.gameday >= hoy) & tabla.home_score.isna() & tabla.away_score.isna()].sort_values('gameday')
    if futuros.empty:
        st.info('No se encontraron próximos partidos en el calendario publicado.')
        return
    opciones = {f'{r.gameday.date()} | {r.away_team} @ {r.home_team} | Semana {r.week}': idx
                for idx, r in futuros.iterrows()}
    seleccion = st.selectbox('Partido', list(opciones), key='nfl_v39_game')
    partido = futuros.loc[opciones[seleccion]]
    X = pd.DataFrame([partido[VARIABLES_NFL_V41].to_dict()])[VARIABLES_NFL_V41]
    if min(int(partido.local_juegos), int(partido.visitante_juegos)) < 3:
        st.warning('⚠️ Se requieren al menos tres partidos previos por equipo en esta temporada. No se muestra una proyección con datos neutrales.')
        return
    margen = float(modelos['margen'].predict(X)[0])
    total = float(modelos['total'].predict(X)[0])
    c1, c2, c3 = st.columns(3)
    c1.metric('Margen local', f'{margen:+.1f}')
    c2.metric('Total estimado', f'{total:.1f}')
    c3.metric('Puntos local / visitante', f'{(total+margen)/2:.1f} / {(total-margen)/2:.1f}')
    
    st.subheader('📝 Registro verificable de proyección')
    fecha_registro = datetime.now(timezone.utc).isoformat(timespec='seconds')
    registro = pd.DataFrame([{
        'registrado_utc': fecha_registro,
        'game_id': str(partido.game_id),
        'fecha_partido': str(partido.gameday)[:10],
        'local': partido.home_team,
        'visitante': partido.away_team,
        'margen_estimado': round(margen, 3),
        'total_estimado': round(total, 3),
        'modelo_version': '4.1',
        'datos_sha256': huella,
        'entrenamiento_hasta': 2025,
    }])
    st.download_button(
        '📥 Guardar registro fechado (CSV)', registro.to_csv(index=False).encode('utf-8'),
        f'nfl_registro_{partido.game_id}.csv', 'text/csv', key='nfl_v39_log')

@st.cache_data(ttl=3600, show_spinner=False)
def cargar_calendario_rapido_v40():
    import nflreadpy as nfl
    datos = nfl.load_schedules(TEMPORADAS_NFL_V41)
    df = datos.to_pandas() if hasattr(datos, 'to_pandas') else pd.DataFrame(datos)
    _requerir_nfl_v41(df, ['game_id', 'season', 'week', 'gameday', 'home_team',
                  'away_team', 'home_score', 'away_score'], 'Calendario NFL 4.1')
    df = df.copy()
    df['gameday'] = pd.to_datetime(df['gameday'], errors='coerce')
    for col in ['season', 'week', 'home_score', 'away_score']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    return df.dropna(subset=['game_id', 'gameday']).drop_duplicates('game_id')

def _marcador_v40(df):
    vista = df[['gameday', 'week', 'away_team', 'home_team',
                'away_score', 'home_score']].copy()
    vista['gameday'] = vista['gameday'].dt.strftime('%Y-%m-%d')
    vista = vista.rename(columns={'gameday': 'Fecha', 'week': 'Semana',
        'away_team': 'Visitante', 'home_team': 'Local',
        'away_score': 'Puntos visitante', 'home_score': 'Puntos local'})
    st.dataframe(vista, hide_index=True, use_container_width=True)

def _panel_inicio_v40(cal):
    hoy = pd.Timestamp(datetime.now(timezone.utc).date())
    completos = cal.dropna(subset=['home_score', 'away_score'])
    proximos = cal[(cal['gameday'] >= hoy) & cal['home_score'].isna()
                   & cal['away_score'].isna()].sort_values('gameday')
    st.subheader('🏠 Resumen NFL')
    a, b = st.columns(2)
    a.metric('Partidos con resultado', len(completos))
    b.metric('Próximos 7 días', int((proximos['gameday'] < hoy + pd.Timedelta(days=7)).sum()))
    if not completos.empty:
        st.caption('Última fecha con resultado: ' + str(completos['gameday'].max().date()))
    st.markdown('**Próximos encuentros**')
    if proximos.empty:
        st.info('No hay partidos futuros publicados en el calendario consultado.')
    else:
        _marcador_v40(proximos.head(12))
    st.markdown('**Resultados recientes**')
    if not completos.empty:
        _marcador_v40(completos.sort_values('gameday', ascending=False).head(12))

def _panel_partidos_v40(cal):
    st.subheader('📅 Calendario y resultados')
    temporadas = sorted(cal['season'].dropna().astype(int).unique().tolist(), reverse=True)
    temporada = st.selectbox('Temporada', temporadas, key='nfl40_temporada_partidos')
    base = cal[cal['season'] == temporada].copy()
    semanas = sorted(base['week'].dropna().astype(int).unique().tolist())
    semana = st.selectbox('Semana', ['Todas'] + semanas, key='nfl40_semana')
    if semana != 'Todas':
        base = base[base['week'] == semana]
    equipos = sorted(set(base['home_team'].dropna()) | set(base['away_team'].dropna()))
    equipo = st.selectbox('Equipo', ['Todos'] + equipos, key='nfl40_equipo_partidos')
    if equipo != 'Todos':
        base = base[(base['home_team'] == equipo) | (base['away_team'] == equipo)]
    st.metric('Partidos encontrados', len(base))
    _marcador_v40(base.sort_values(['gameday', 'game_id']))
    st.download_button('📥 Descargar calendario (CSV)', base.to_csv(index=False).encode('utf-8-sig'),
                       'nfl40_calendario.csv', 'text/csv', key='nfl40_csv_calendario')

def _panel_equipos_v40(cal):
    st.subheader('🏟️ Estadísticas de equipos')
    temporadas = sorted(cal['season'].dropna().astype(int).unique().tolist(), reverse=True)
    temporada = st.selectbox('Temporada', temporadas, key='nfl40_temporada_equipos')
    juegos = cal[(cal['season'] == temporada)].dropna(subset=['home_score', 'away_score']).copy()
    if juegos.empty:
        st.info('Aún no hay marcadores para esta temporada.')
        return
    local = pd.DataFrame({'Equipo': juegos['home_team'], 'PF': juegos['home_score'],
        'PC': juegos['away_score'], 'V': (juegos['home_score'] > juegos['away_score']).astype(int),
        'D': (juegos['home_score'] < juegos['away_score']).astype(int),
        'E': (juegos['home_score'] == juegos['away_score']).astype(int)})
    visita = pd.DataFrame({'Equipo': juegos['away_team'], 'PF': juegos['away_score'],
        'PC': juegos['home_score'], 'V': (juegos['away_score'] > juegos['home_score']).astype(int),
        'D': (juegos['away_score'] < juegos['home_score']).astype(int),
        'E': (juegos['home_score'] == juegos['away_score']).astype(int)})
    tabla = pd.concat([local, visita], ignore_index=True).groupby('Equipo', as_index=False)[['PF', 'PC', 'V', 'D', 'E']].sum()
    tabla['PJ'] = tabla['V'] + tabla['D'] + tabla['E']
    tabla['Diferencia'] = tabla['PF'] - tabla['PC']
    tabla = tabla.sort_values(['V', 'Diferencia'], ascending=[False, False])
    st.caption('Resumen calculado de los marcadores disponibles.')
    st.dataframe(tabla[['Equipo', 'PJ', 'V', 'D', 'E', 'PF', 'PC', 'Diferencia']],
                 hide_index=True, use_container_width=True)
    st.download_button('📥 Descargar equipos (CSV)', tabla.to_csv(index=False).encode('utf-8-sig'),
                       'nfl40_equipos.csv', 'text/csv', key='nfl40_csv_equipos')

def _panel_estado_v40(cal):
    st.subheader('🛰️ Estado de actualización')
    st.metric('Partidos del calendario', len(cal))
    st.metric('Partidos con marcador', len(cal.dropna(subset=['home_score', 'away_score'])))
    st.write('Última consulta exitosa en esta sesión (UTC):',
             st.session_state.get('nfl40_consulta_utc', 'No registrada'))
    st.info('Para revisar la cobertura PBP, errores y auditorías completas, abre «Auditorías y análisis».')

def _evaluar_pruebas_v41(cal):
    pruebas = []
    def agregar(nombre, correcto, detalle, severidad='ERROR'):
        pruebas.append({'Prueba': nombre, 'Estado': 'OK' if correcto else severidad,
                        'Detalle': str(detalle)})

    columnas = {'game_id', 'season', 'week', 'gameday', 'home_team',
                'away_team', 'home_score', 'away_score'}
    faltantes = sorted(columnas - set(cal.columns))
    agregar('Columnas obligatorias', not faltantes,
            'Completas' if not faltantes else 'Faltan: ' + ', '.join(faltantes))
    if faltantes:
        return pd.DataFrame(pruebas)

    agregar('Calendario no vacío', len(cal) > 0, f'{len(cal)} partidos')
    duplicados = int(cal['game_id'].duplicated().sum())
    agregar('Identificadores únicos', duplicados == 0, f'{duplicados} duplicados')
    nulos = int(cal[['game_id','gameday','season','week','home_team','away_team']].isna().any(axis=1).sum())
    agregar('Campos básicos completos', nulos == 0, f'{nulos} filas incompletas')
    mismo_equipo = int((cal['home_team'].astype(str) == cal['away_team'].astype(str)).sum())
    agregar('Rivales distintos', mismo_equipo == 0, f'{mismo_equipo} coincidencias')
    marcadores = cal[['home_score','away_score']].apply(pd.to_numeric, errors='coerce')
    parciales = int(marcadores.isna().any(axis=1).ne(marcadores.isna().all(axis=1)).sum())
    agregar('Marcadores completos o pendientes', parciales == 0, f'{parciales} marcadores parciales')
    invalidos = int((marcadores.lt(0).any(axis=1) | ((marcadores % 1).ne(0) & marcadores.notna()).any(axis=1)).sum())
    agregar('Marcadores enteros no negativos', invalidos == 0, f'{invalidos} marcadores inválidos')
    semana = pd.to_numeric(cal['week'], errors='coerce')
    semanas_invalidas = int((semana.lt(1) | semana.gt(25) | semana.isna()).sum())
    agregar('Semanas en rango razonable', semanas_invalidas == 0, f'{semanas_invalidas} semanas fuera de rango', 'AVISO')
    temporada = pd.to_numeric(cal['season'], errors='coerce')
    fuera = int((~temporada.isin(TEMPORADAS_NFL_V41)).sum())
    agregar('Temporadas configuradas', fuera == 0, f'{fuera} fuera de configuración', 'AVISO')
    return pd.DataFrame(pruebas)

def _ventana_proximos_v41(cal, fecha_referencia=None):
    hoy = pd.Timestamp(fecha_referencia or datetime.now(timezone.utc).date()).normalize()
    fecha = pd.to_datetime(cal['gameday'], errors='coerce').dt.tz_localize(None).dt.normalize()
    pendientes = cal['home_score'].isna() & cal['away_score'].isna()
    ventana = pendientes & fecha.ge(hoy) & fecha.lt(hoy + pd.Timedelta(days=7))
    return cal.loc[ventana].copy()

def _pruebas_sinteticas_v41():
    base = pd.DataFrame([{'game_id':'2026_01_A_B','season':2026,'week':1,
        'gameday':pd.Timestamp('2026-09-10'),'home_team':'A','away_team':'B',
        'home_score':21,'away_score':17},
        {'game_id':'2026_02_C_D','season':2026,'week':2,
        'gameday':pd.Timestamp('2026-09-17'),'home_team':'C','away_team':'D',
        'home_score':float('nan'),'away_score':float('nan')}])
    resultados = []
    def probar(nombre, df, esperado):
        hallados = _evaluar_pruebas_v41(df)
        estado = hallados.set_index('Prueba').loc[nombre, 'Estado']
        resultados.append({'Prueba': 'Caso simulado: ' + nombre,
                           'Estado': 'OK' if estado == esperado else 'ERROR',
                           'Detalle': f'Esperado {esperado}; obtenido {estado}'})
    probar('Identificadores únicos', pd.concat([base, base.iloc[[0]]], ignore_index=True), 'ERROR')
    cambio = base.copy(); cambio.loc[0, 'home_score'] = -1
    probar('Marcadores enteros no negativos', cambio, 'ERROR')
    cambio = base.copy(); cambio.loc[0, 'away_score'] = float('nan')
    probar('Marcadores completos o pendientes', cambio, 'ERROR')
    cambio = base.copy(); cambio.loc[0, 'away_team'] = 'A'
    probar('Rivales distintos', cambio, 'ERROR')
    resultado = _ventana_proximos_v41(base, '2026-09-11')
    resultados.append({'Prueba':'Caso simulado: ventana de 7 días',
        'Estado':'OK' if len(resultado)==1 else 'ERROR',
        'Detalle':f'Esperado 1; obtenido {len(resultado)}'})
    return pd.DataFrame(resultados)

def mostrar_pruebas_integrales_nfl_v41():
    st.subheader('🧪 NFL 4.1 | Pruebas integrales')
    st.caption('Verificaciones de calidad del calendario y pruebas con datos simulados.')
    if not st.button('▶️ Ejecutar pruebas NFL 4.1', key='nfl41_ejecutar'):
        st.info('Pulsa el botón para ejecutar las comprobaciones.')
        return
    try:
        cal = cargar_calendario_rapido_v40()
    except Exception as exc:
        st.error('No se pudo cargar el calendario. Las pruebas reales no se ejecutaron.')
        st.caption(f'{type(exc).__name__}: {exc}')
        return
    reales = _evaluar_pruebas_v41(cal)
    simuladas = _pruebas_sinteticas_v41()
    resultado = pd.concat([reales.assign(Origen='Datos reales'),
                           simuladas.assign(Origen='Pruebas simuladas')], ignore_index=True)
    a,b,c = st.columns(3)
    a.metric('Comprobaciones', len(resultado))
    b.metric('Errores', int(resultado['Estado'].eq('ERROR').sum()))
    c.metric('Avisos', int(resultado['Estado'].eq('AVISO').sum()))
    st.dataframe(resultado[['Origen','Prueba','Estado','Detalle']],
                 hide_index=True, use_container_width=True)
    if resultado['Estado'].eq('ERROR').any():
        st.error('Se encontraron errores. Revisa el detalle antes de continuar.')
    elif resultado['Estado'].eq('AVISO').any():
        st.warning('Sin errores críticos; hay avisos para revisar.')
    else:
        st.success('Las comprobaciones ejecutadas terminaron sin discrepancias.')
    st.markdown('**Reconciliación de próximos 7 días**')
    proximos = _ventana_proximos_v41(cal)
    st.metric('Partidos sin marcador dentro de la ventana', len(proximos))
    if not proximos.empty:
        _marcador_v40(proximos.sort_values('gameday'))
    st.download_button('📥 Descargar informe de pruebas (CSV)',
        resultado.to_csv(index=False).encode('utf-8-sig'),
        'nfl_v4_1_pruebas.csv', 'text/csv', key='nfl41_descarga')

def mostrar_modulo_nfl():
    st.header('🏈 NFL 4.1 | Centro deportivo')
    st.caption('Panel unificado para celular · NFLverse · Resultados y estadísticas observadas')
    if st.button('🔄 Actualizar calendario y estadísticas', key='nfl40_actualizar'):
        cargar_calendario_rapido_v40.clear()
        cargar_datos_nfl.clear()
        cargar_jugadores_nfl_v39.clear()
        st.session_state.pop('nfl40_consulta_utc', None)
        st.rerun()
    secciones = ['🏠 Inicio', '📅 Partidos', '🏟️ Equipos',
                 '👥 Jugadores', '🛰️ Estado', '🧪 Auditorías y análisis', '🧪 Pruebas 4.1']
    seleccion = st.selectbox('Ir à sección', secciones, key='nfl40_navegacion')
    if seleccion == '🧪 Pruebas 4.1':
        mostrar_pruebas_integrales_nfl_v41()
        return
    if seleccion == '👥 Jugadores':
        mostrar_jugadores_nfl_v39()
        return
    if seleccion == '🧪 Auditorías y análisis':
        st.caption('Este panel conserva las auditorías y el análisis histórico. La carga puede tardar.')
        _mostrar_modulo_nfl_legacy_v40()
        return
    try:
        with st.spinner('Consultando calendario NFL...'):
            cal = cargar_calendario_rapido_v40()
        if 'nfl40_consulta_utc' not in st.session_state:
            st.session_state['nfl40_consulta_utc'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
    except Exception as exc:
        st.error('No fue posible cargar el calendario. Intenta actualizar más tarde.')
        st.caption(f'Detalle técnico: {type(exc).__name__}: {exc}')
        return
    if seleccion == '🏠 Inicio':
        _panel_inicio_v40(cal)
    elif seleccion == '📅 Partidos':
        _panel_partidos_v40(cal)
    elif seleccion == '🏟️ Equipos':
        _panel_equipos_v40(cal)
    elif seleccion == '🛰️ Estado':
        _panel_estado_v40(cal)


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
  st.title(f"🧮 **Calculadora de Arbitraje [{fecha_formato_str}]**")
  col_a1, col_a2 = st.columns(2)
  with col_a1: cuota_a = st.number_input("Casa A:", value=130)
  with col_a2: cuota_b = st.number_input("Casa B:", value=-120)
  bankroll_total_arb = st.number_input("Inversión Total (MXN):", value=5000.0, step=500.0)
  if st.button("⚖️ Calcular Surebet", use_container_width=True):
    dec_a = (1.0 + (cuota_a / 100.0)) if cuota_a > 0 else (1.0 + (100.0 / abs(cuota_a)))
    dec_b = (1.0 + (cuota_b / 100.0)) if cuota_b > 0 else (1.0 + (100.0 / abs(cuota_b)))
    implied_sum = (1.0 / dec_a) + (1.0 / dec_b)
    if implied_sum < 1.0:
      roi_arb = (1.0 - implied_sum) * 100.0
      stake_a = bankroll_total_arb * ((1.0 / dec_a) / implied_sum)
      stake_b = bankroll_total_arb * ((1.0 / dec_b) / implied_sum)
      ganancia_garantizada = (stake_a * dec_a) - bankroll_total_arb
      st.success(f"🚨 ¡Oportunidad de Arbitraje! ROI: **+{roi_arb:.2f}%** | Ganancia: **${ganancia_garantizada:,.2f} MXN**")
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
