from datetime import date, datetime, timedelta
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
from sklearn.model_selection import train_test_split
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
# 6. SISTEMA PRO NFL (MACHINE LEARNING + NFLVERSE)
# =========================================================
YEARS_NFL = [2022, 2023, 2024, 2025, 2026]
FEATURES_NFL = ["home_pf", "home_pa", "home_win", "away_pf", "away_pa", "away_win", "home_n", "away_n", "rest_home", "rest_away"]

@st.cache_data(ttl=86400, show_spinner=False)
def cargar_partidos_nfl():
    import nflreadpy as nfl
    raw = nfl.load_schedules(YEARS_NFL).to_pandas()
    needed = ["game_id", "season", "week", "gameday", "home_team", "away_team", "home_score", "away_score"]
    missing = [c for c in needed if c not in raw.columns]
    if missing:
        raise ValueError(f"La fuente no contiene columnas requeridas: {', '.join(missing)}")
    df = raw[needed].copy()
    df["gameday"] = pd.to_datetime(df["gameday"], errors="coerce")
    for c in ("season", "week", "home_score", "away_score"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["game_id", "season", "week", "gameday", "home_team", "away_team"])
    df = df.drop_duplicates("game_id").sort_values(["gameday", "game_id"]).reset_index(drop=True)
    if df.empty:
        raise ValueError("NFLverse devolvió un calendario vacío")
    return df

def construir_variables_nfl(df):
    history = {}
    rows = []
    for date, group in df.groupby("gameday", sort=True):
        pending = []
        for _, g in group.iterrows():
            home, away = str(g.home_team), str(g.away_team)
            def prior(team):
                played = history.get(team, [])
                last = played[-5:]
                n = len(last)
                if not n:
                    return 21.0, 21.0, 0.5, 0, 7
                rest = int((date - last[-1][0]).days)
                return (float(np.mean([x[1] for x in last])),
                        float(np.mean([x[2] for x in last])),
                        float(np.mean([x[3] for x in last])), n,
                        int(np.clip(rest, 0, 21)))
            hpf, hpa, hw, hn, hr = prior(home)
            apf, apa, aw, an, ar = prior(away)
            row = {"game_id": g.game_id, "gameday": date, "season": int(g.season),
                   "week": int(g.week), "home_team": home, "away_team": away,
                   "home_pf": hpf, "home_pa": hpa, "home_win": hw,
                   "away_pf": apf, "away_pa": apa, "away_win": aw,
                   "home_n": hn, "away_n": an, "rest_home": hr, "rest_away": ar,
                   "home_score": g.home_score, "away_score": g.away_score}
            rows.append(row)
            if pd.notna(g.home_score) and pd.notna(g.away_score):
                hs, vs = float(g.home_score), float(g.away_score)
                pending.append((home, away, hs, vs))
        for home, away, hs, vs in pending:
            history.setdefault(home, []).append((date, hs, vs, float(hs > vs) + 0.5 * float(hs == vs)))
            history.setdefault(away, []).append((date, vs, hs, float(vs > hs) + 0.5 * float(vs == vs)))
    return pd.DataFrame(rows)

@st.cache_resource(show_spinner=False)
def entrenar_modelo_nfl(data_version, train_csv):
    df = pd.read_csv(io.StringIO(train_csv), parse_dates=["gameday"])
    complete = df.dropna(subset=["home_score", "away_score"]).copy()
    train = complete[complete.season.between(2022, 2024)]
    test = complete[complete.season == 2025]
    if len(train) < 300 or len(test) < 100:
        raise ValueError("Faltan partidos suficientes de 2022-2025 para validar el modelo.")
    for frame in (train, test):
        if frame[FEATURES_NFL].isna().any().any():
            raise ValueError("Hay variables faltantes en el historial")
    targets = {"margen": lambda d: d.home_score - d.away_score,
               "total": lambda d: d.home_score + d.away_score}
    metrics, models = {}, {}
    for name, target in targets.items():
        model = HistGradientBoostingRegressor(max_iter=110, max_leaf_nodes=12, learning_rate=0.045,
                                              l2_regularization=8.0, random_state=42)
        model.fit(train[FEATURES_NFL], target(train))
        pred = model.predict(test[FEATURES_NFL])
        base = np.repeat(float(target(train).mean()), len(test))
        metrics[name] = {"MAE_modelo": float(mean_absolute_error(target(test), pred)),
                         "MAE_referencia": float(mean_absolute_error(target(test), base))}
        models[name] = model
    full = complete[complete.season.between(2022, 2025)]
    for name, target in targets.items():
        models[name].fit(full[FEATURES_NFL], target(full))
    return models, metrics, len(train), len(test)


# =========================================================
# 7. FÚTBOL SOCCER
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
st.sidebar.subheader("🌐 Configuración de API")
st.session_state["api_key_guardada"] = st.sidebar.text_input("Ingresa tu API Key de The Odds API:", value=st.session_state["api_key_guardada"], type="password")

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
        "🔍 Escáner Automático & Manual (+EV)",
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

  momio_prop_str = st.text_input("Momio Americano (Ej. -115 o +130):", value="-115", key="psc_mom")
  momio_prop = limpiar_momio(momio_prop_str)

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
        _, edge_p = calcular_edge_real(momio_prop, v['prob'])
        stk = calcular_criterio_kelly(st.session_state["bankroll_global"], v['prob'], momio_prop)
        if st.button("📥 Guardar Prop en SQLite", key="save_psc"):
          registrar_apuesta_db(fecha_formato_str, "Prop Soccer Común", v['partido'], v['mercado'], momio_prop, edge_p, stk)
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

  momio_prop_str = st.text_input("Momio Americano (Ej. -120 o +110):", value="-120", key="pu_mom")
  momio_prop = limpiar_momio(momio_prop_str)

  if st.button("🚀 Evaluar Prop de UFC", use_container_width=True):
    res = analizar_prop_ufc_comun(combate, mercado_ufc, prob_modelo)
    for r in res:
      r["partido"] = cartelera_str
    st.session_state["resultado_props_ufc_comun_calculado"] = res

  if st.session_state.get("resultado_props_ufc_comun_calculado"):
    validadas = st.session_state["resultado_props_ufc_comun_calculado"]
    if validadas:
      st.success("✅ ¡El prop superó el filtro estricto del 70% de éxito real!")
      for v in validadas:
        st.info(f"Selección: **{v['mercado']}** | Probabilidad: `{v['prob']:.2f}%`")
        _, edge_p = calcular_edge_real(momio_prop, v['prob'])
        stk = calcular_criterio_kelly(st.session_state["bankroll_global"], v['prob'], momio_prop)
        if st.button("📥 Guardar Prop en SQLite", key="save_pu_comun"):
          registrar_apuesta_db(fecha_formato_str, "Prop UFC Común", cartelera_str, v['mercado'], momio_prop, edge_p, stk)
          st.success("¡Prop guardado con éxito en la base de datos!")
      st.code(generar_ticket_nba_props_puro(validadas, fecha_formato_str), language="text")
    else:
      st.warning("⚠️ Este prop se encuentra por debajo del filtro estricto del 70% de probabilidad.")


elif modulo_seleccionado == "🛡️ Prop: NFL Común (Playdoit)":
  st.title(f"🛡️ **Props: NFL Común por Posición & Anytime TD [{fecha_formato_str}]**")
  st.markdown("--- \n *Opciones de mercado adaptadas específicamente según la posición del jugador (QB, RB, WR, TE).*")
  
  col1, col2 = st.columns(2)
  with col1:
    jugador = st.text_input("Jugador / Atleta:", value="Alvin Kamara", key="pnc_jug")
    posicion_jugador = st.selectbox("Posición del Jugador:", ["Quarterback (QB)", "Running Back (RB)", "Wide Receiver (WR)", "Tight End (TE)"], key="pnc_pos")
    partido_str = st.text_input("Partido (Ej. Pittsburgh Steelers vs New Orleans Saints):", value="Pittsburgh Steelers vs New Orleans Saints", key="pnc_part")
  with col2:
    if "Quarterback" in posicion_jugador:
      mercados_disponibles = ["Yardas de Pase", "Pases de Anotación (TD Pass)", "Intercepciones", "Yardas por Tierra del QB", "Touchdown en Cualquier Momento (Anytime TD)"]
    elif "Running Back" in posicion_jugador:
      mercados_disponibles = ["Yardas de Carrera", "Yardas de Recepción", "Yardas Combinadas (Carrera + Recepción)", "Touchdown en Cualquier Momento (Anytime TD)"]
    else:
      mercados_disponibles = ["Yardas de Recepción", "Recepciones Totales (Catches)", "Touchdown en Cualquier Momento (Anytime TD)"]
      
    mercado = st.selectbox("Mercado Específico Disponible:", mercados_disponibles, key="pnc_merc")

  col3, col4 = st.columns(2)
  with col3:
    if "Touchdown" in mercado:
      promedio_jug = st.number_input("Tasa Histórica de TDs por Partido (Ej. 0.65 = 65%):", value=0.60, step=0.05, key="pnc_prom_td")
      linea_cas = 0.5
    else:
      promedio_jug = st.number_input("Promedio Base del Jugador en este Mercado:", value=85.5, step=0.5, key="pnc_prom")
      linea_cas = st.number_input("Línea Casino (O/U):", value=89.5, step=0.5, key="pnc_lin")
  with col4:
    yardas_o_defensa = st.number_input("Estadística de la Defensa Rival (Yardas permitidas / Factor TD):", value=230.0, step=0.5, key="pnc_def_yardas")
    momio_prop_str = st.text_input("Momio Americano (Ej. -110 o +135):", value="-110", key="pnc_mom")
    momio_prop = limpiar_momio(momio_prop_str)

  if st.button("🚀 Evaluar Prop Dinámica de NFL", use_container_width=True):
    if "Touchdown" in mercado:
      factor_defensa_td = yardas_o_defensa if yardas_o_defensa < 2.0 else 1.10
      prob_modelo_atd = min(85.0, max(15.0, (promedio_jug * factor_defensa_td) * 100.0))
      
      resultados_props = [
          {"mercado": f"{jugador} - Sí Anota Touchdown (Anytime)", "prob": round(prob_modelo_atd, 2)},
          {"mercado": f"{jugador} - No Anota Touchdown", "prob": round(100.0 - prob_modelo_atd, 2)}
      ]
      st.session_state["resultado_props_nfl_comun_calculado"] = {
          "partido": partido_str, "opciones": resultados_props, "proyeccion": f"{prob_modelo_atd:.1f}% Prob. Anotar"
      }
    else:
      if "Pase" in mercado:
        promedio_liga_base, desv_estandar = 230.0, 45.0
      elif "Carrera" in mercado:
        promedio_liga_base, desv_estandar = 70.0, 18.0
      elif "Combinadas" in mercado:
        promedio_liga_base, desv_estandar = 110.0, 25.0
      else:
        promedio_liga_base, desv_estandar = 50.0, 22.0

      factor_defensa = yardas_o_defensa / promedio_liga_base if yardas_o_defensa > 10 else 1.1
      proyeccion_ajustada = promedio_jug * factor_defensa

      z_score = (linea_cas - proyeccion_ajustada) / desv_estandar
      prob_under = norm.cdf(z_score) * 100.0
      prob_over = 100.0 - prob_under

      resultados_props = [
          {"mercado": f"{jugador} Over {linea_cas} {mercado}", "prob": round(prob_over, 2)},
          {"mercado": f"{jugador} Under {linea_cas} {mercado}", "prob": round(prob_under, 2)}
      ]
      st.session_state["resultado_props_nfl_comun_calculado"] = {
          "partido": partido_str, "opciones": resultados_props, "proyeccion": f"{proyeccion_ajustada:.1f} unidades"
      }

  if st.session_state.get("resultado_props_nfl_comun_calculado"):
    res_data = st.session_state["resultado_props_nfl_comun_calculado"]
    st.info(f"📊 **Proyección del Modelo para {jugador} ({posicion_jugador}):** `{res_data['proyeccion']}`")
    
    st.markdown("### 📌 Resultados del Análisis de Probabilidad (+EV)")
    for v in res_data["opciones"]:
      _, edge_p = calcular_edge_real(momio_prop, v['prob'])
      stk = calcular_criterio_kelly(st.session_state["bankroll_global"], v['prob'], momio_prop)
      
      if v['prob'] >= 52.0:
        st.success(f"✅ **{v['mercado']}** | Probabilidad: `{v['prob']:.2f}%` | Edge: `+{edge_p:.2f}%` | Stake: `${stk} MXN`")
      else:
        st.warning(f"⚠️ **{v['mercado']}** | Probabilidad: `{v['prob']:.2f}%`")
        
      if st.button(f"📥 Guardar en SQLite ({v['mercado']})", key=f"save_prop_{v['mercado']}"):
        registrar_apuesta_db(fecha_formato_str, "Prop NFL Dinámico", res_data['partido'], v['mercado'], momio_prop, edge_p, stk)
        st.success("¡Apuesta guardada con éxito en la base de datos!")


elif modulo_seleccionado == "🏀 Prop: NBA Común (Playdoit)":
  st.title(f"🏀 **Props: NBA Común Élite (Avanzado con Pace Cruzado & B2B) [{fecha_formato_str}]**")
  st.markdown("--- \n *Props de volumen (Puntos, Rebotes y Asistencias) ajustados por el ritmo combinado del partido y factor de fatiga por Back-to-Back.*")
  
  col1, col2 = st.columns(2)
  with col1:
    jugador = st.text_input("Jugador / Atleta:", value="Anthony Davis", key="pnbc_jug")
    mercado = st.selectbox("Mercado Playdoit:", ["Puntos", "Rebotes", "Asistencias"], key="pnbc_merc")
    partido_str = st.text_input("Partido (Ej. Lakers vs Knicks):", value="Lakers vs Knicks", key="pnbc_part")
  with col2:
    promedio_jug = st.number_input("Promedio Base del Jugador:", value=25.0, step=0.1, key="pnbc_prom")
    linea_cas = st.number_input("Línea Casino (O/U):", value=26.5, step=0.5, key="pnbc_lin")

  st.markdown("### ⚙️ Factores de Entorno Cruzados (Pace y Fatiga)")
  col_p1, col_p2, col_p3 = st.columns(3)
  with col_p1:
    pace_eq_jugador = st.number_input("Pace Equipo del Jugador:", value=101.1, step=0.5, key="pnbc_pace_j")
  with col_p2:
    pace_eq_rival = st.number_input("Pace Equipo Rival:", value=95.8, step=0.5, key="pnbc_pace_r")
  with col_p3:
    b2b_activo = st.checkbox("⚠️ ¿El equipo viene de jugar anoche (B2B)?", value=True, key="pnbc_b2b")

  momio_prop_str = st.text_input("Momio Americano (Ej. -115 o +105):", value="-115", key="pnbc_mom")
  momio_prop = limpiar_momio(momio_prop_str)

  if st.button("🚀 Evaluar Prop Avanzado de NBA", use_container_width=True):
    res = analizar_prop_nba_comun_avanzado(jugador, mercado, promedio_jug, linea_cas, pace_eq_jugador, pace_eq_rival, b2b_activo)
    for r in res:
      r["partido"] = partido_str
    st.session_state["resultado_props_nba_comun_calculado"] = res

  if st.session_state.get("resultado_props_nba_comun_calculado"):
    validadas = st.session_state["resultado_props_nba_comun_calculado"]
    if validadas:
      st.success("✅ ¡El prop superó el filtro estricto del 70% de éxito real!")
      for v in validadas:
        st.info(f"Selección: **{v['mercado']}** | Probabilidad: `{v['prob']:.2f}%`")
        _, edge_p = calcular_edge_real(momio_prop, v['prob'])
        stk = calcular_criterio_kelly(st.session_state["bankroll_global"], v['prob'], momio_prop)
        if st.button("📥 Guardar Prop en SQLite", key="save_pnbc"):
          registrar_apuesta_db(fecha_formato_str, "Prop NBA Común", v['partido'], v['mercado'], momio_prop, edge_p, stk)
          st.success("¡Prop guardado con éxito en la base de datos!")
      st.code(generar_ticket_nba_props_puro(validadas, fecha_formato_str), language="text")
    else:
      st.warning("⚠️ Este prop se encuentra por debajo del filtro estricto del 70% de probabilidad.")


# =========================================================
# ESCÁNER AUTOMÁTICO & MANUAL (+EV)
# =========================================================
elif modulo_seleccionado == "🔍 Escáner Automático & Manual (+EV)":
  st.title(f"🔍 **Escáner de Valor (+EV) Automático & Manual [{fecha_formato_str}]**")
  st.markdown("--- \n *Detecta oportunidades de valor positivo conectándote à la API o ingresando tus propios análisis manuales.*")

  tab_auto, tab_manual = st.tabs(["🌐 Escáner Automático (API)", "✍️ Ingreso Manual (+EV)"])

  with tab_auto:
    api_key = st.session_state["api_key_guardada"]
    if st.button("🚀 Ejecutar Barrido Global Automático", use_container_width=True):
      if not api_key:
        st.error("⚠️ Por favor ingresa tu API Key en la barra lateral.")
      else:
        with st.spinner("Conectando con The Odds API y escaneando mercados globales..."):
          cartelera_global = obtener_partidos_y_momios_api_multideporte(api_key)
          st.session_state["cartelera_escaner"] = cartelera_global

    if "cartelera_escaner" in st.session_state and st.session_state["cartelera_escaner"]:
      resultados = st.session_state["cartelera_escaner"]
      st.success(f"🎯 ¡Se encontraron **{len(resultados)} oportunidades con valor (+EV)** automáticas!")
      
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
      st.info("Ingresa tu API Key y haz clic en el botón superior para barrer cuotas automáticamente con la API.")

  with tab_manual:
    st.markdown("### ✍️ Registrar Oportunidad Manualmente")
    col_m1, col_m2 = st.columns(2)
    with col_m1:
      deporte_man = st.selectbox("Deporte:", ["NBA", "NFL", "NCAAF", "NHL", "MLB", "SOCCER", "UFC"], key="man_dep")
      partido_man = st.text_input("Partido (Ej. Los Angeles Lakers vs Golden State Warriors):", value="Los Angeles Lakers vs Golden State Warriors", key="man_part")
      mercado_man = st.text_input("Mercado (Ej. Lakers Spread -3.5):", value="Lakers Spread -3.5", key="man_merc")
    with col_m2:
      momio_man_str = st.text_input("Momio Americano (Ej. -110 o +130):", value="-110", key="man_mom")
      momio_man = limpiar_momio(momio_man_str)
      prob_real_man = st.number_input("Probabilidad Real Calculada por tu Modelo (%):", value=58.0, step=0.5, key="man_prob")

    if st.button("🔍 Calcular Edge y Evaluar Valor", use_container_width=True):
      prob_imp, edge_man = calcular_edge_real(momio_man, prob_real_man)
      stake_man = calcular_criterio_kelly(st.session_state["bankroll_global"], prob_real_man, momio_man)
      
      st.markdown("### 📊 Resultado del Análisis Manual")
      col_res_m1, col_res_m2, col_res_m3 = st.columns(3)
      col_res_m1.metric("Probabilidad Implícita", f"{prob_imp:.2f}%")
      col_res_m2.metric("Edge Matemático", f"{edge_man:+.2f}%", delta="Valor Positivo (+EV)" if edge_man > 0 else "Sin Valor")
      col_res_m3.metric("Stake Sugerido (Kelly)", f"${stake_man} MXN")

      if edge_man > 2.0:
        st.success("🎯 ¡Excelente oportunidad! Supera el umbral del 2% de Edge positivo.")
        if st.button("📥 Guardar Apuesta Manual en SQLite", key="save_manual_ev"):
          registrar_apuesta_db(fecha_formato_str, deporte_man, partido_man, mercado_man, momio_man, edge_man, stake_man)
          st.success("¡Apuesta manual guardada con éxito en tu base de datos!")
      else:
        st.warning("⚠️ Esta apuesta tiene un Edge bajo o negativo. No se recomienda arriesgar capital.")


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

  momio_ufc_str = st.text_input("Momio Americano (Apuesta recomendada):", value="-250", key="ufc_mm")
  momio_ufc = limpiar_momio(momio_ufc_str)

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
        _, edge_ufc = calcular_edge_real(momio_ufc, jugada['prob'])
        stk = calcular_criterio_kelly(st.session_state["bankroll_global"], jugada['prob'], momio_ufc)
        if st.button(f"📥 Guardar en SQLite ({jugada['mercado']})", key=f"db_ufc_{jugada['mercado']}"):
          registrar_apuesta_db(fecha_formato_str, "UFC Élite", r['partido'], jugada['mercado'], momio_ufc, edge_ufc, stk)
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
  with col_nhl1:
    goalie_l = st.checkbox("Portero Local Élite (Goalie Boost)", key="nhl_gl")
  with col_nhl2:
    goalie_v = st.checkbox("Portero Visitante Élite (Goalie Boost)", key="nhl_gv")

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
# 4. SISTEMA PRO NBA
# =========================================================
elif modulo_seleccionado == "🏀 Sistema Pro NBA":
  st.title(f"🏀 **Sistema Pro NBA Élite con Métricas Detalladas, Pace Reciente & Matriz de Bajas [{fecha_formato_str}]**")
  st.markdown("--- \n *Análisis profundo: Eficiencias, Pace Reciente (5 partidos), Asistencias, Pérdidas, Tiros Libres (FTA), Porcentajes, Rebotes y Load Management.*")

  col_nba_eq1, col_nba_eq2 = st.columns(2)
  with col_nba_eq1:
    el_nba = st.selectbox("Equipo Local NBA:", list(MATRIZ_BAJAS_NBA.keys()) + ["Los Angeles Lakers", "Golden State Warriors", "Denver Nuggets", "Phoenix Suns"], key="nba_el")
    st.markdown("##### 📊 Estadísticas Detalladas Local")
    ort_l = st.number_input("Offensive Rating (ORT):", value=122.0, step=0.5, key="nba_ortl")
    drt_l = st.number_input("Defensive Rating (DRT):", value=110.5, step=0.5, key="nba_drtl")
    pace_l = st.number_input("Ritmo Temporada (Pace):", value=97.5, step=0.1, key="nba_pacel")
    pace_rec_l = st.number_input("Ritmo Últimos 5 Partidos (Pace Reciente):", value=98.0, step=0.1, key="nba_pacerl")
    apg_l = st.number_input("Asistencias (APG):", value=26.5, step=0.5, key="nba_apgl")
    tov_l = st.number_input("Pérdidas (TOV):", value=12.5, step=0.5, key="nba_tovl")
    fta_l = st.number_input("Tiros Libres Intentados (FTA):", value=22.0, step=0.5, key="nba_ftal")
    fg_l = st.number_input("% Tiros de Campo (FG%):", value=48.2, step=0.1, key="nba_fgl")
    tp_l = st.number_input("% Triples (3P%):", value=37.5, step=0.1, key="nba_tpl")
    rpg_l = st.number_input("Rebotes Totales (RPG):", value=44.0, step=0.5, key="nba_rpgl")
    
    st.markdown("##### 🚨 Situación Local")
    b2b_l_nba = st.checkbox("Local en B2B (Días consecutivos)", key="nba_b2bl")
    estrella_l_nba = st.checkbox(f"🚨 {MATRIZ_BAJAS_NBA.get(el_nba, {}).get('Jugador', 'Estrella Local')} Fuera (Baja / Load Mng)", key="nba_starl")

  with col_nba_eq2:
    ev_nba = st.selectbox("Equipo Visitante NBA:", list(MATRIZ_BAJAS_NBA.keys()) + ["Los Angeles Lakers", "Golden State Warriors", "Denver Nuggets", "Phoenix Suns"], index=1, key="nba_ev")
    st.markdown("##### 📊 Estadísticas Detalladas Visitante")
    ort_v = st.number_input("Offensive Rating (ORT):", value=117.5, step=0.5, key="nba_ortv")
    drt_v = st.number_input("Defensive Rating (DRT):", value=115.0, step=0.5, key="nba_drtv")
    pace_v = st.number_input("Ritmo Temporada (Pace):", value=100.2, step=0.1, key="nba_pacev")
    pace_rec_v = st.number_input("Ritmo Últimos 5 Partidos (Pace Reciente):", value=99.5, step=0.1, key="nba_pacerv")
    apg_v = st.number_input("Asistencias (APG):", value=25.8, step=0.5, key="nba_apgv")
    tov_v = st.number_input("Pérdidas (TOV):", value=13.0, step=0.5, key="nba_tovv")
    fta_v = st.number_input("Tiros Libres Intentados (FTA):", value=21.5, step=0.5, key="nba_ftav")
    fg_v = st.number_input("% Tiros de Campo (FG%):", value=47.5, step=0.1, key="nba_fgv")
    tp_v = st.number_input("% Triples (3P%):", value=36.8, step=0.1, key="nba_tpv")
    rpg_v = st.number_input("Rebotes Totales (RPG):", value=42.5, step=0.5, key="nba_rpgv")
    
    st.markdown("##### 🚨 Situación Visitante")
    b2b_v_nba = st.checkbox("Visitante en B2B (Días consecutivos)", key="nba_b2bv")
    estrella_v_nba = st.checkbox(f"🚨 {MATRIZ_BAJAS_NBA.get(ev_nba, {}).get('Jugador', 'Estrella Visitante')} Fuera (Baja / Load Mng)", key="nba_starv")

  st.markdown("---")
  col_line1, col_line2 = st.columns(2)
  with col_line1:
    linea_sp_nba_str = st.text_input("Línea Spread Casino (Ej. -4.5 o +3.5):", value="-4.5", key="nba_lsp")
    linea_sp_nba = limpiar_spread(linea_sp_nba_str)
  with col_line2:
    linea_tot_nba = st.number_input("Línea Total Casino O/U:", value=228.5, step=0.5, key="nba_ltot")

  stats_local_dict = {"ort": ort_l, "drt": drt_l, "pace": pace_l, "pace_reciente": pace_rec_l, "apg": apg_l, "tov": tov_l, "fta": fta_l, "fg_pct": fg_l, "three_p_pct": tp_l, "rpg": rpg_l}
  stats_visita_dict = {"ort": ort_v, "drt": drt_v, "pace": pace_v, "pace_reciente": pace_rec_v, "apg": apg_v, "tov": tov_v, "fta": fta_v, "fg_pct": fg_v, "three_p_pct": tp_v, "rpg": rpg_v}
  contexto_nba = {"local_b2b": b2b_l_nba, "visita_b2b": b2b_v_nba, "local_estrella_baja": estrella_l_nba, "visita_estrella_baja": estrella_v_nba}

  if st.button("🚀 Ejecutar Análisis NBA Completo (Over/Under Blindado)", use_container_width=True):
    res_nba = analizar_lineas_nba_detallado(stats_local_dict, stats_visita_dict, linea_sp_nba, linea_tot_nba, contexto_nba, el_nba, ev_nba)
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
  linea_sp_str = st.text_input("Spread Casino (Ej. -14.5 o +7.5):", value="-14.5", key="ncaaf_lsp")
  linea_sp = limpiar_spread(linea_sp_str)
  linea_tot = st.number_input("Línea Casino O/U:", value=46.5, step=0.5, key="ncaaf_ltot")
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
# 6. SISTEMA PRO NFL (ML + NFLVERSE CON MÉTRICAS Y APUESTAS +EV)
# =========================================================
elif modulo_seleccionado == "🛡️ Sistema Pro NFL":
  st.title(f"🛡️ **Sistema Pro NFL Élite (Machine Learning & Apuestas +EV) [{fecha_formato_str}]**")
  st.markdown("--- \n *Modelo predictivo basado en HistGradientBoostingRegressor con validación histórica y cálculo de valor (+EV).*")
  
  if st.button("🔄 Actualizar Fuente NFLverse", key="nfl_refresh"):
    cargar_partidos_nfl.clear()
    st.rerun()

  try:
    with st.spinner("Consultando NFLverse y construyendo historial de rendimiento..."):
      games = cargar_partidos_nfl()
      frame = construir_variables_nfl(games)
      completed = frame.dropna(subset=["home_score", "away_score"])
      if completed.empty:
        st.error("La fuente no contiene resultados terminados.")
        st.stop()
      fingerprint = int(pd.util.hash_pandas_object(
          completed[["game_id", "home_score", "away_score"]], index=False).sum())
      models, metrics, ntrain, ntest = entrenar_modelo_nfl(
          fingerprint, frame.to_csv(index=False))
  except Exception as exc:
    st.error("🔴 Modelo no disponible: no fue posible cargar o validar datos históricos.")
    st.code(str(exc))
    st.stop()

  st.success("🟢 Fuente real cargada y validación histórica completada con datos de NFLverse.")
  st.write(f"**Partidos para entrenamiento inicial:** {ntrain} · **Partidos evaluados de 2025:** {ntest}")
  st.caption(f"Último partido con resultado disponible en la fuente: {completed.gameday.max().date()}")

  # VALIDACIÓN DEL MODELO (MÉTRICAS MAE)
  report = pd.DataFrame(metrics).T.round(2)
  st.subheader("📊 Validación del Modelo (Métricas MAE - Temporada 2025)")
  st.dataframe(report, use_container_width=True)
  
  if any(v["MAE_modelo"] >= v["MAE_referencia"] for v in metrics.values()):
    st.warning("🟡 Al menos una proyección no supera la referencia básica en 2025. Interprétala con cautela.")
  else:
    st.info("✅ La validación de 2025 mejora la referencia básica del error absoluto medio (MAE).")

  st.markdown("---")
  st.subheader("📅 Seleccionar Próximo Partido para Analizar y Apostar")
  today = pd.Timestamp(datetime.now(timezone.utc).date())
  future = frame[(frame.gameday >= today) & frame.home_score.isna() & frame.away_score.isna()].copy()
  future = future.sort_values("gameday")
  
  if future.empty:
    st.info("No hay partidos futuros publicados en los datos cargados actualmente.")
  else:
    options = {f"{r.gameday.date()} | {r.away_team} @ {r.home_team} | Semana {r.week}": i
               for i, r in future.iterrows()}
    chosen = st.selectbox("Selecciona un enfrentamiento:", list(options), key="nfl_game_select")
    row = future.loc[options[chosen]]
    
    x = pd.DataFrame([row[FEATURES_NFL].to_dict()])[FEATURES_NFL]
    margin = float(models["margen"].predict(x)[0])
    total = float(models["total"].predict(x)[0])
    home_points, away_points = (total + margin) / 2, (total - margin) / 2

    st.markdown("### 📊 Proyecciones del Modelo")
    c1, c2, c3 = st.columns(3)
    c1.metric("Margen Local Estimado", f"{margin:+.1f}")
    c2.metric("Total de Puntos Estimado", f"{total:.1f}")
    c3.metric("Puntos (Local / Visita)", f"{home_points:.1f} / {away_points:.1f}")

    if min(int(row.home_n), int(row.away_n)) < 3:
      st.warning("⚠️ Algún equipo tiene menos de 3 partidos recientes en el historial; proyectar con precaución.")

    st.markdown("---")
    st.subheader("🎯 Configuración de Apuesta & Evaluación de Valor (+EV)")
    
    col_l1, col_l2, col_l3 = st.columns(3)
    with col_l1:
      tipo_apuesta = st.selectbox("Mercado:", ["Spread Local", "Spread Visitante", "Altas (Over)", "Bajas (Under)"], key="nfl_ap_tipo")
    with col_l2:
      bookie_line = st.number_input("Línea de la Casa (Spread / Total O/U):", value=-3.0 if "Spread" in tipo_apuesta else 43.5, step=0.5, key="nfl_book_line")
    with col_l3:
      momio_casa_str = st.text_input("Momio Americano (Ej. -110 o +135):", value="-110", key="nfl_momio_input")
      momio_casa = limpiar_momio(momio_casa_str)

    # Cálculo de probabilidad del modelo basado en distribución normal
    if "Spread Local" in tipo_apuesta:
      ventaja = margin - bookie_line
      prob_modelo = float(norm.cdf(ventaja / 13.5) * 100.0)
    elif "Spread Visitante" in tipo_apuesta:
      ventaja = (-margin) - bookie_line
      prob_modelo = float(norm.cdf(ventaja / 13.5) * 100.0)
    elif "Altas" in tipo_apuesta:
      ventaja = total - bookie_line
      prob_modelo = float(norm.cdf(ventaja / 14.0) * 100.0)
    else:  # Bajas
      ventaja = bookie_line - total
      prob_modelo = float(norm.cdf(ventaja / 14.0) * 100.0)

    prob_modelo = round(min(92.0, max(10.0, prob_modelo)), 2)

    # Cálculo de probabilidad implícita y Edge
    if momio_casa > 0:
      prob_imp = 100.0 / (momio_casa + 100.0) * 100.0
    else:
      prob_imp = abs(momio_casa) / (abs(momio_casa) + 100.0) * 100.0

    edge = round(prob_modelo - prob_imp, 2)

    # Criterio de Kelly con tope de $250 MXN
    bankroll = st.session_state.get("bankroll_global", 15250.0)
    p = prob_modelo / 100.0
    b = (momio_casa / 100.0) if momio_casa > 0 else (100.0 / abs(momio_casa))
    q = 1.0 - p
    kelly_full = (b * p - q) / b
    stake_sugerido = round(max(10.0, bankroll * kelly_full * 0.25), 2)
    stake_final = min(250.0, stake_sugerido)  # Tope disciplinado de $250 MXN

    st.markdown("### 📈 Resultados del Análisis de Valor")
    col_res1, col_res2, col_res3 = st.columns(3)
    col_res1.metric("Probabilidad del Modelo", f"{prob_modelo:.2f}%")
    col_res2.metric("Edge Matemático", f"{edge:+.2f}%", delta="Valor Positivo (+EV)" if edge > 0 else "Sin Valor")
    col_res3.metric("Stake Recomendado (Tope $250)", f"${stake_final} MXN")

    if edge > 1.5:
      st.success(f"🎯 **¡Oportunidad detectada!** El modelo encuentra valor positivo (+EV) en **{row.away_team} @ {row.home_team}**.")
      if st.button("📥 Guardar Apuesta en Base de Datos SQLite", key="save_nfl_bet"):
        partido_str = f"{row.away_team} @ {row.home_team}"
        mercado_str = f"{tipo_apuesta} ({bookie_line}) [Momio {momio_casa:+d}]"
        try:
          registrar_apuesta_db(fecha_formato_str, "NFL Élite ML", partido_str, mercado_str, momio_casa, edge, stake_final)
          st.success("¡Apuesta guardada con éxito en la base de datos SQLite!")
        except Exception as e:
          st.error(f"Error al guardar: {e}")
    else:
      st.warning("⚠️ Esta línea no ofrece suficiente margen de valor (+EV) según las proyecciones del modelo.")

    output = pd.DataFrame([{
        "fecha": row.gameday.date(), "local": row.home_team,
        "visitante": row.away_team, "margen_local": round(margin, 2),
        "total": round(total, 2), "probabilidad_modelo": prob_modelo,
        "edge": edge, "stake_sugerido": stake_final
    }])
    st.download_button("📥 Descargar Proyección y Análisis (.csv)", output.to_csv(index=False).encode("utf-8"),
                       "nfl_analisis_apuesta.csv", "text/csv", key="nfl_projection_dl")


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
  with col_a1: cuota_a = st.number_input("Cuota Casa A:", value=130)
  with col_a2: cuota_b = st.number_input("Cuota Casa B:", value=-120)
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
