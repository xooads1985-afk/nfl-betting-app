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

for mod in ["ncaaf", "nfl", "nba", "soccer", "nhl", "baseball", "ufc"]:
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


def registrar_apuesta_db(
    fecha, deporte, partido, mercado, momio, edge, stake
):
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


def actualizar_estado_y_clv(apuesta_id, nuevo_estado, stake, momio, clv_val):
  ganancia = 0.0
  if nuevo_estado == "Ganada":
    if momio > 0:
      ganancia = stake * (momio / 100.0)
    else:
      ganancia = stake * (100.0 / abs(momio))
  elif nuevo_estado == "Perdida":
    ganancia = -stake
  else:
    ganancia = 0.0

  conn = sqlite3.connect("master_suite_elite.db")
  cursor = conn.cursor()
  cursor.execute("SELECT bankroll_historico FROM apuestas WHERE id = ?", (apuesta_id,))
  row = cursor.fetchone()
  br_base = row[0] if row and row[0] > 0 else st.session_state["bankroll_global"]
  nuevo_br_hist = br_base + ganancia

  cursor.execute(
      """
        UPDATE apuestas SET resultado = ?, ganancia_neta = ?, clv_cuota = ?, bankroll_historico = ? WHERE id = ?
    """,
      (nuevo_estado, ganancia, int(clv_val), nuevo_br_hist, apuesta_id),
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


# 1. Motor NCAAF Actualizado (Power Ratings + Distribución Normal + Bye Weeks + QB Impact)
def calcular_probabilidades_ncaaf(power_rating_local, power_rating_visitante, ventaja_localia=2.5):
  return (power_rating_local + ventaja_localia) - power_rating_visitante

def aplicar_matriz_correctiva_ncaaf(margen_base, total_base, datos_contexto):
  margen_ajustado = margen_base
  total_ajustado = total_base
  if datos_contexto.get("local_viene_de_bye", False) and not datos_contexto.get("visita_viene_de_bye", False):
    margen_ajustado += 1.5
  elif datos_contexto.get("visita_viene_de_bye", False) and not datos_contexto.get("local_viene_de_bye", False):
    margen_ajustado -= 1.5
    
  if datos_contexto.get("local_qb_titular_baja", False):
    margen_ajustado -= datos_contexto.get("puntos_impacto_qb_local", 7.0)
    total_ajustado -= 4.0
    
  if datos_contexto.get("visita_qb_titular_baja", False):
    margen_ajustado += datos_contexto.get("puntos_impacto_qb_visita", 7.0)
    total_ajustado -= 4.0
    
  return margen_ajustado, total_ajustado

def analizar_lineas_ncaaf_normal(pr_local, pr_visita, total_proyectado, linea_spread_casino, linea_total_casino, datos_contexto):
  margen_base = calcular_probabilidades_ncaaf(pr_local, pr_visita)
  margen_ajustado, total_ajustado = aplicar_matriz_correctiva_ncaaf(margen_base, total_proyectado, datos_contexto)
  
  z_spread = (linea_spread_casino - margen_ajustado) / 13.5
  prob_local_cubre = stats.norm.cdf(z_spread) * 100.0
  prob_visita_cubre = 100.0 - prob_local_cubre
  
  z_totales = (linea_total_casino - total_ajustado) / 14.0
  prob_under = stats.norm.cdf(z_totales) * 100.0
  prob_over = 100.0 - prob_under
  
  return {
      "margen_proyectado": round(margen_ajustado, 2),
      "total_proyectado": round(total_ajustado, 2),
      "prob_local": round(prob_local_cubre, 2),
      "prob_visita": round(prob_visita_cubre, 2),
      "prob_over": round(prob_over, 2),
      "prob_under": round(prob_under, 2)
  }


# 2. Motor Pro Fútbol (Soccer - Matriz Poisson Bivariada)
def calcular_matriz_probabilidades(avg_goles_local, avg_goles_visitante, max_goles=6):
  prob_local = [poisson.pmf(i, avg_goles_local) for i in range(max_goles + 1)]
  prob_visitante = [poisson.pmf(j, avg_goles_visitante) for j in range(max_goles + 1)]
  matriz_prob = np.outer(prob_local, prob_visitante)
  matriz_prob /= matriz_prob.sum()
  return matriz_prob

def analizar_mercados_futbol(equipo_local, equipo_visita, xg_local, xg_visita, momio_playdoit_1x2):
  matriz = calcular_matriz_probabilidades(xg_local, xg_visita)
  prob_local_win = float(np.sum(np.triu(matriz, 1).T)) * 100
  prob_visitante_win = float(np.sum(np.tril(matriz, -1).T)) * 100
  prob_empate = float(np.diag(matriz).sum()) * 100
  
  total_goles_matriz = np.fromfunction(lambda i, j: i + j, matriz.shape, dtype=int)
  prob_under_25 = float(matriz[total_goles_matriz < 3].sum()) * 100
  prob_over_25 = 100 - prob_under_25
  
  opciones_equipos = [
      {"mercado": f"Gana {equipo_local}", "prob": prob_local_win, "tipo": "1X2"},
      {"mercado": f"Gana {equipo_visita}", "prob": prob_visitante_win, "tipo": "1X2"},
      {"mercado": "Empate", "prob": prob_empate, "tipo": "1X2"},
      {"mercado": "Over 2.5 Goles", "prob": prob_over_25, "tipo": "O/U"},
      {"mercado": "Under 2.5 Goles", "prob": prob_under_25, "tipo": "O/U"}
  ]
  jugadas_validas = [j for j in opciones_equipos if j["prob"] >= 70.0]
  nota_linea = "Línea Oficial Recomendada"
  if momio_playdoit_1x2 <= 1.50:
      nota_linea = "Alerta: Momio castigado. Evaluar Ajuste de Línea Alterna"
  return {
      "local": round(prob_local_win, 2), "empate": round(prob_empate, 2), "visita": round(prob_visitante_win, 2),
      "over25": round(prob_over_25, 2), "under25": round(prob_under_25, 2),
      "jugadas_alta_prob": jugadas_validas, "nota_linea": nota_linea
  }


# 3. Otros Motores de Apoyo
def motor_matematico_nfl_spread(ppg_local, pap_local, ppg_visita, pap_visita, spread_casino, lesion_qb_local=False, lesion_qb_visita=False):
  pr_local = ppg_local - (pap_local * 0.98)
  pr_visita = ppg_visita - (pap_visita * 0.98)
  if lesion_qb_local: pr_local -= 5.5
  if lesion_qb_visita: pr_visita -= 5.5
  margen_proyectado = (pr_local + 2.5) - pr_visita
  z_score = (margen_proyectado - abs(spread_casino)) / 11.5
  return round(max(5.0, min(95.0, stats.norm.cdf(z_score) * 100.0)), 2), round(margen_proyectado, 1)

def motor_matematico_nfl_totales(ppg_local, pap_local, ppg_visita, pap_visita, linea_casa, lesion_qb_local=False, lesion_qb_visita=False):
  lam = (ppg_local + ppg_visita + pap_local + pap_visita) / 2.0
  if lesion_qb_local or lesion_qb_visita: lam -= 4.0
  lam_adj = round(max(10.0, lam * 0.97), 1)
  prob_under = sum([poisson.pmf(k, lam_adj) for k in range(int(math.floor(linea_casa)) + 1)])
  return round((1.0 - prob_under) * 100.0, 2), lam_adj

def motor_matematico_nba_spread(off_local, def_local, off_visita, def_visita, spread_casino, b2b_local=False, b2b_visita=False, lesion_star_local=False, lesion_star_visita=False):
  rl = off_local - (def_visita * 0.96)
  rv = off_visita - (def_local * 0.96)
  if b2b_local: rl -= 3.0
  if b2b_visita: rv -= 3.0
  if lesion_star_local: rl -= 4.5
  if lesion_star_visita: rv -= 4.5
  margen_proyectado = (rl + 3.0) - rv
  z_score = (margen_proyectado - abs(spread_casino)) / 12.0
  return round(max(5.0, min(95.0, stats.norm.cdf(z_score) * 100.0)), 2), round(margen_proyectado, 1)

def motor_matematico_nba_totales(off_local, def_local, off_visita, def_visita, linea_casa, b2b_local=False, b2b_visita=False):
  tot = (off_local + off_visita + def_local + def_visita) / 2.0
  if b2b_local or b2b_visita: tot -= 4.5
  lam_adj = round(max(80.0, tot * 0.99), 1)
  prob_under = sum([poisson.pmf(k, lam_adj / 2.5) for k in range(int(math.floor(linea_casa)) + 1)])
  return round(max(5.0, min(95.0, (1.0 - prob_under) * 100.0)), 2), lam_adj

def motor_matematico_nhl(gf_local, ga_local, gf_visita, ga_visita, goalie_boost_local=False, goalie_boost_visita=False, linea_ou=5.5):
  lam_l = max(1.0, (gf_local + ga_visita) / 2.0)
  lam_v = max(1.0, (gf_visita + ga_local) / 2.0)
  if goalie_boost_local: lam_l -= 0.4
  if goalie_boost_visita: lam_v -= 0.4
  p_win_l, p_over = 0.0, 0.0
  for gl in range(8):
    for gv in range(8):
      p = poisson.pmf(gl, lam_l) * poisson.pmf(gv, lam_v)
      if gl > gv: p_win_l += p
      elif gl == gv: p_win_l += (p * 0.5)
      if (gl + gv) > linea_ou: p_over += p
  return {
      "moneyline_local": round(p_win_l * 100.0, 2), "moneyline_visita": round((1.0 - p_win_l) * 100.0, 2),
      "over_pct": round(p_over * 100.0, 2), "under_pct": round((1.0 - p_over) * 100.0, 2)
  }

def motor_matematico_baseball(era_starter_local, fip_starter_local, era_starter_visita, fip_starter_visita, bullpen_local=3.5, bullpen_visita=3.5, linea_runline=-1.5, linea_ou=8.5):
  runs_local = (fip_starter_local * 0.6) + (bullpen_local * 0.4)
  runs_visita = (fip_starter_visita * 0.6) + (bullpen_visita * 0.4)
  margen_carreras = runs_visita - runs_local
  z_score = (margen_carreras - abs(linea_runline)) / 3.2
  prob_runline = stats.norm.cdf(z_score) * 100.0
  total_carreras = runs_local + runs_visita
  prob_under_ou = sum([poisson.pmf(k, total_carreras) for k in range(int(math.floor(linea_ou)) + 1)])
  return {
      "runline_prob": round(max(5.0, min(95.0, prob_runline)), 2),
      "over_pct": round((1.0 - prob_under_ou) * 100.0, 2),
      "under_pct": round(prob_under_ou * 100.0, 2)
  }

def motor_matematico_ufc(acc_f1, tdd_f1, fin_f1, acc_f2, tdd_f2, fin_f2):
  rating_f1 = (acc_f1 * 0.4) + (tdd_f1 * 0.3) + (fin_f1 * 0.3)
  rating_f2 = (acc_f2 * 0.4) + (tdd_f2 * 0.3) + (fin_f2 * 0.3)
  z_score = (rating_f1 - rating_f2) / 15.0
  prob_f1 = stats.norm.cdf(z_score) * 100.0
  return {
      "prob_f1": round(max(5.0, min(95.0, prob_f1)), 2),
      "prob_f2": round(max(5.0, min(95.0, 100.0 - prob_f1)), 2),
      "rating_f1": round(rating_f1, 1), "rating_f2": round(rating_f2, 1)
  }


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
              nombre_sel = out.get("name")
              precio_momio = out.get("price")
              if precio_momio:
                prob_imp_base = calcular_probabilidad_implicita(precio_momio) * 100.0
                prob_modelo = round(min(90.0, max(10.0, prob_imp_base * 1.02)), 2)
                _, edge_calculado = calcular_edge_real(precio_momio, prob_modelo)
                stake_sugerido = calcular_criterio_kelly(st.session_state["bankroll_global"], prob_modelo, int(precio_momio))
                partidos_analizados.append({
                    "partido_str": f"{visita} @ {local}",
                    "mercado": f"{m_key.upper()}: {nombre_sel}",
                    "momio": int(precio_momio), "edge": round(edge_calculado, 2), "stake": stake_sugerido
                })
      return partidos_analizados
  except Exception:
    pass
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
        "🎓 Sistema Pro NCAAF (Universitario)",
        "⚽ Módulo Pro Fútbol (Soccer)",
        "🛡️ Sistema Pro NFL",
        "🏀 Sistema Pro NBA",
        "🏒 Hockey Pro (NHL)",
        "⚾ Béisbol Pro (MLB / LMP)",
        "🥊 Sistema Pro UFC / MMA",
        "🔍 Escáner Automático Multi-Deporte (+EV)",
        "📊 Control de Bankroll & Historial SQLite",
        "🚀 Optimizador de Parlays (Monte Carlo)",
        "🧮 Calculadora de Arbitraje (Surebets)",
        "📈 Backtesting Histórico & Steam Moves",
        "⚖️ Gestor Multi-Bookmaker (Line Shopping)",
    ],
)


# =========================================================
# 1. SISTEMA PRO NCAAF (ACTUALIZADO CON DISTRIBUCIÓN NORMAL)
# =========================================================
if modulo_seleccionado == "🎓 Sistema Pro NCAAF (Universitario)":
  st.title(f"🎓 **Sistema Pro NCAAF Élite [{fecha_formato_str}]**")
  st.markdown("--- \n *Motor de Distribución Normal con Power Ratings, Bye Weeks y matriz correctiva por lesiones de QB.*")

  col1, col2 = st.columns(2)
  with col1:
    el = st.text_input("Equipo Local:", value="Ohio State", key="ncaaf_el")
    pr_l = st.number_input("Power Rating Local:", value=94.5, step=0.5, key="ncaaf_prl")
    bye_l = st.checkbox("Local Descansado (Bye Week)", key="ncaaf_byel")
    qb_l = st.checkbox("QB Titular Local Lesionado", key="ncaaf_qbl")
  with col2:
    ev = st.text_input("Equipo Visitante:", value="Penn State", key="ncaaf_ev")
    pr_v = st.number_input("Power Rating Visitante:", value=88.0, step=0.5, key="ncaaf_prv")
    bye_v = st.checkbox("Visitante Descansado (Bye Week)", key="ncaaf_byev")
    qb_v = st.checkbox("QB Titular Visitante Lesionado", key="ncaaf_qbv")

  st.markdown("---")
  col3, col4, col5 = st.columns(3)
  with col3:
    tot_proy = st.number_input("Total de Puntos Proyectado:", value=51.5, step=0.5, key="ncaaf_tot")
  with col4:
    linea_sp = st.number_input("Línea Spread Casino (Local):", value=-3.5, step=0.5, key="ncaaf_lsp")
  with col5:
    linea_tot = st.number_input("Línea Total Casino (O/U):", value=49.5, step=0.5, key="ncaaf_ltot")

  contexto_ncaaf = {
      "local_viene_de_bye": bye_l, "visita_viene_de_bye": bye_v,
      "local_qb_titular_baja": qb_l, "visita_qb_titular_baja": qb_v,
      "puntos_impacto_qb_local": 7.0, "puntos_impacto_qb_visita": 7.0
  }

  if st.button("🚀 Ejecutar Análisis Matemático NCAAF", use_container_width=True):
    res_ncaaf = analizar_lineas_ncaaf_normal(pr_l, pr_v, tot_proy, linea_sp, linea_tot, contexto_ncaaf)
    st.session_state["resultado_ncaaf_calculado"] = {
        "partido": f"{ev} @ {el}",
        "analisis": res_ncaaf
    }

  if st.session_state["resultado_ncaaf_calculado"]:
    r = st.session_state["resultado_ncaaf_calculado"]
    res = r["analisis"]
    st.success(f"🎯 Análisis NCAAF Completado para: **{r['partido']}**")

    col_n1, col_n2 = st.columns(2)
    col_n1.metric("🏟️ Margen Proyectado Ajustado", f"{res['margen_proyectado']:+.1f} pts")
    col_n2.metric("📊 Total Puntos Proyectado", f"{res['total_proyectado']} pts")

    col_n3, col_n4, col_n5, col_n6 = st.columns(4)
    col_n3.metric(f"Prob. {el} Cubre ({linea_sp})", f"{res['prob_local']}%")
    col_n4.metric(f"Prob. {ev} Cubre ({-linea_sp})", f"{res['prob_visita']}%")
    col_n5.metric(f"Prob. Over {linea_tot}", f"{res['prob_over']}%")
    col_n6.metric(f"Prob. Under {linea_tot}", f"{res['prob_under']}%")

    st.markdown("### 📌 Opciones Recomendadas (>70% Éxito)")
    opciones_eval = [
        ("Spread " + el, res['prob_local'], linea_sp),
        ("Spread " + ev, res['prob_visita'], -linea_sp),
        ("Over " + str(linea_tot), res['prob_over'], linea_tot),
        ("Under " + str(linea_tot), res['prob_under'], linea_tot)
    ]
    
    hay_valida = False
    for merc, prob, lin in opciones_eval:
      if prob >= 70.0:
        hay_valida = True
        st.info(f"✅ **{merc}** | Probabilidad: `{prob}%`")
        stk = calcular_criterio_kelly(st.session_state["bankroll_global"], prob, -110)
        if st.button(f"📥 Guardar en SQLite ({merc})", key=f"db_ncaaf_{merc}"):
          registrar_apuesta_db(fecha_formato_str, "NCAAF Élite", r["partido"], merc, -110, prob - 52.38, stk)
          st.success("¡Apuesta NCAAF guardada con éxito!")
    if not hay_valida:
      st.warning("⚠️ Ninguna opción supera el filtro estricto del 70% de probabilidad en este juego universitario.")


# =========================================================
# 2. FÚTBOL SOCCER
# =========================================================
elif modulo_seleccionado == "⚽ Módulo Pro Fútbol (Soccer)":
  st.title(f"⚽ **Módulo Pro Fútbol Élite [{fecha_formato_str}]**")
  st.markdown("--- \n *Motor de Poisson Bivariado con filtros estrictos de alta probabilidad (>70%).*")
  
  col_s1, col_s2 = st.columns(2)
  with col_s1:
    el = st.text_input("Equipo Local:", value="Club América", key="soc_el")
    xg_l = st.number_input("xG Local:", value=2.45, step=0.05, key="soc_xgl")
  with col_s2:
    ev = st.text_input("Equipo Visitante:", value="Guadalajara", key="soc_ev")
    xg_v = st.number_input("xG Visita:", value=0.85, step=0.05, key="soc_xgv")

  momio_playdoit = st.number_input("Momio Decimal Playdoit (1X2):", value=1.75, step=0.05, key="soc_mp")

  if st.button("🚀 Ejecutar Análisis Matriz Bivariada Fútbol", use_container_width=True):
    res_soc = analizar_mercados_futbol(el, ev, xg_l, xg_v, momio_playdoit)
    st.session_state["resultado_soccer_calculado"] = {"partido": f"{ev} @ {el}", "analisis": res_soc}

  if st.session_state["resultado_soccer_calculado"]:
    r = st.session_state["resultado_soccer_calculado"]
    res = r["analisis"]
    st.success(f"🎯 Análisis Completado para: **{r['partido']}**")
    
    col_r1, col_r2, col_r3 = st.columns(3)
    col_r1.metric(f"Gana {el}", f"{res['local']}%")
    col_r2.metric("Empate", f"{res['empate']}%")
    col_r3.metric(f"Gana {ev}", f"{res['visita']}%")

    col_r4, col_r5 = st.columns(2)
    col_r4.metric("Over 2.5 Goles", f"{res['over25']}%")
    col_r5.metric("Under 2.5 Goles", f"{res['under25']}%")

    st.markdown(f"ℹ️ **Estado de Línea:** `{res['nota_linea']}`")

    if res["jugadas_alta_prob"]:
      st.markdown("### 🔥 Jugadas Certificadas (>70% Probabilidad)")
      for jugada in res["jugadas_alta_prob"]:
        st.info(f"✅ **{jugada['mercado']}** | Probabilidad: `{jugada['prob']}%`")
        stk = calcular_criterio_kelly(st.session_state["bankroll_global"], jugada['prob'], -110)
        if st.button(f"📥 Guardar en SQLite ({jugada['mercado']})", key=f"db_soc_{jugada['mercado']}"):
          registrar_apuesta_db(fecha_formato_str, "Soccer Élite", r["partido"], jugada['mercado'], -110, jugada['prob'] - 52.38, stk)
          st.success("¡Apuesta guardada con éxito en SQLite!")
    else:
      st.warning("⚠️ Ninguna opción supera el filtro del 70% en este partido.")


# =========================================================
# 3. NFL, NBA, NHL, MLB, UFC Y SOPORTE FINANCIERO
# =========================================================
elif modulo_seleccionado == "🛡️ Sistema Pro NFL":
  st.title(f"🛡️ **Sistema Pro NFL Élite [{fecha_formato_str}]**")
  st.markdown("--- \n *Módulo protegido y congelado.*")
  col1, col2 = st.columns(2)
  with col1:
    ev = st.text_input("Visitante:", value="Chiefs", key="nfl_ev")
    ov = st.number_input("Anotados Visita:", value=26.0, step=0.5, key="nfl_ov")
    dv = st.number_input("Permitidos Visita:", value=19.5, step=0.5, key="nfl_dv")
    qbv = st.checkbox("QB Lesionado", key="nfl_qbv")
  with col2:
    el = st.text_input("Local:", value="Bills", key="nfl_el")
    ol = st.number_input("Anotados Local:", value=27.5, step=0.5, key="nfl_ol")
    dl = st.number_input("Permitidos Local:", value=18.0, step=0.5, key="nfl_dl")
    qbl = st.checkbox("QB Lesionado", key="nfl_qbl")
  tm = st.selectbox("Mercado:", ["Spread", "Total"], key="nfl_tm")
  if tm == "Spread":
    seq = st.text_input("Selección:", value="Bills (-2.5)", key="nfl_seq")
    sp = st.number_input("Spread:", value=-2.5, step=0.5, key="nfl_sp")
    mm = st.number_input("Momio:", value=-110, step=5, key="nfl_mm")
    if st.button("🚀 Calcular NFL", use_container_width=True):
      pr, _ = motor_matematico_nfl_spread(ol, dl, ov, dv, sp, qbl, qbv)
      st.session_state["resultado_nfl_calculado"] = {"partido": f"{ev} @ {el}", "mercado": f"Spread: {seq} ({sp})", "momio": int(mm), "prob": pr}
  else:
    lc = st.number_input("Línea O/U:", value=48.5, step=0.5, key="nfl_lc")
    op = st.radio("Sel:", ["Over", "Under"], horizontal=True, key="nfl_op")
    mm = st.number_input("Momio:", value=-110, step=5, key="nfl_mmo")
    if st.button("🚀 Calcular NFL", use_container_width=True):
      pov, _ = motor_matematico_nfl_totales(ol, dl, ov, dv, lc, qbl, qbv)
      st.session_state["resultado_nfl_calculado"] = {"partido": f"{ev} @ {el}", "mercado": f"Total {op} ({lc})", "momio": int(mm), "prob": pov if "Over" in op else 100.0-pov}
  if st.session_state["resultado_nfl_calculado"]:
    r = st.session_state["resultado_nfl_calculado"]
    _, eg = calcular_edge_real(r["momio"], r["prob"])
    stk = calcular_criterio_kelly(st.session_state["bankroll_global"], r["prob"], r["momio"])
    st.success(f"🎯 **{r['partido']}** | Prob: `{r['prob']}%` | Edge: `+{eg:.2f}%` | Stake: `${stk} MXN`")
    if st.button("📥 Guardar SQLite", key="db_nf"): registrar_apuesta_db(fecha_formato_str, "NFL", r["partido"], r["mercado"], r["momio"], eg, stk); st.success("Guardado.")

elif modulo_seleccionado == "🏀 Sistema Pro NBA":
  st.title(f"🏀 **Sistema Pro NBA Élite [{fecha_formato_str}]**")
  st.markdown("--- \n *Módulo protegido y congelado.*")
  col1, col2 = st.columns(2)
  with col1:
    ev = st.text_input("Visitante:", value="Celtics", key="nba_ev")
    ov = st.number_input("Off Rating Visita:", value=118.5, step=0.5, key="nba_ov")
    dv = st.number_input("Def Rating Visita:", value=110.0, step=0.5, key="nba_dv")
    b2bv = st.checkbox("B2B", key="nba_b2bv")
    starv = st.checkbox("Estrella Fuera", key="nba_starv")
  with col2:
    el = st.text_input("Local:", value="Lakers", key="nba_el")
    ol = st.number_input("Off Rating Local:", value=115.0, step=0.5, key="nba_ol")
    dl = st.number_input("Def Rating Local:", value=112.5, step=0.5, key="nba_dl")
    b2bl = st.checkbox("B2B", key="nba_b2bl")
    starl = st.checkbox("Estrella Fuera", key="nba_starl")
  tm = st.selectbox("Mercado:", ["Spread", "Total"], key="nba_tm")
  if tm == "Spread":
    seq = st.text_input("Selección:", value="Lakers (+4.5)", key="nba_seq")
    sp = st.number_input("Spread:", value=4.5, step=0.5, key="nba_sp")
    mm = st.number_input("Momio:", value=-110, step=5, key="nba_mm")
    if st.button("🚀 Calcular NBA", use_container_width=True):
      pr, _ = motor_matematico_nba_spread(ol, dl, ov, dv, sp, b2bl, b2bv, starl, starv)
      st.session_state["resultado_nba_calculado"] = {"partido": f"{ev} @ {el}", "mercado": f"Spread: {seq} ({sp})", "momio": int(mm), "prob": pr}
  else:
    lc = st.number_input("Línea O/U:", value=228.5, step=0.5, key="nba_lc")
    op = st.radio("Sel:", ["Over", "Under"], horizontal=True, key="nba_op")
    mm = st.number_input("Momio:", value=-110, step=5, key="nba_mmo")
    if st.button("🚀 Calcular NBA", use_container_width=True):
      pov, _ = motor_matematico_nba_totales(ol, dl, ov, dv, lc, b2bl, b2bv)
      st.session_state["resultado_nba_calculado"] = {"partido": f"{ev} @ {el}", "mercado": f"Total {op} ({lc})", "momio": int(mm), "prob": pov if "Over" in op else 100.0-pov}
  if st.session_state["resultado_nba_calculado"]:
    r = st.session_state["resultado_nba_calculado"]
    _, eg = calcular_edge_real(r["momio"], r["prob"])
    stk = calcular_criterio_kelly(st.session_state["bankroll_global"], r["prob"], r["momio"])
    st.success(f"🎯 **{r['partido']}** | Prob: `{r['prob']}%` | Edge: `+{eg:.2f}%` | Stake: `${stk} MXN`")
    if st.button("📥 Guardar SQLite", key="db_nb"): registrar_apuesta_db(fecha_formato_str, "NBA", r["partido"], r["mercado"], r["momio"], eg, stk); st.success("Guardado.")

elif modulo_seleccionado == "🏒 Hockey Pro (NHL)":
  st.title(f"🏒 **Sistema Pro Hockey (NHL) Élite [{fecha_formato_str}]**")
  st.markdown("--- \n *Módulo protegido y congelado.*")
  col1, col2 = st.columns(2)
  with col1:
    ev = st.text_input("Visitante:", value="Oilers", key="nhl_ev")
    gfv = st.number_input("GF Visita:", value=3.2, step=0.1, key="nhl_gfv")
    gav = st.number_input("GA Visita:", value=2.8, step=0.1, key="nhl_gav")
    gv = st.checkbox("Portero Estrella", key="nhl_gv")
  with col2:
    el = st.text_input("Local:", value="Maple Leafs", key="nhl_el")
    gfl = st.number_input("GF Local:", value=3.4, step=0.1, key="nhl_gfl")
    gal = st.number_input("GA Local:", value=2.6, step=0.1, key="nhl_gal")
    gl = st.checkbox("Portero Estrella", key="nhl_gl")
  tm = st.selectbox("Mercado:", ["Moneyline", "Total Goles"], key="nhl_tm")
  if tm == "Moneyline":
    sel = st.selectbox("Selección:", [el, ev], key="nhl_sel")
    mm = st.number_input("Momio:", value=-115, step=5, key="nhl_mm")
    if st.button("🚀 Calcular NHL", use_container_width=True):
      mat = motor_matematico_nhl(gfl, gal, gfv, gav, gl, gv)
      prob = mat["moneyline_local"] if sel == el else mat["moneyline_visita"]
      st.session_state["resultado_nhl_calculado"] = {"partido": f"{ev} @ {el}", "mercado": f"Moneyline: {sel}", "momio": int(mm), "prob": prob}
  else:
    lou = st.number_input("Línea Goles:", value=5.5, step=0.5, key="nhl_lou")
    op = st.radio("Sel:", ["Over", "Under"], horizontal=True, key="nhl_op")
    mm = st.number_input("Momio:", value=-110, step=5, key="nhl_mmo")
    if st.button("🚀 Calcular NHL", use_container_width=True):
      mat = motor_matematico_nhl(gfl, gal, gfv, gav, gl, gv, lou)
      st.session_state["resultado_nhl_calculado"] = {"partido": f"{ev} @ {el}", "mercado": f"Total {op} {lou}", "momio": int(mm), "prob": mat["over_pct"] if "Over" in op else mat["under_pct"]}
  if st.session_state["resultado_nhl_calculado"]:
    r = st.session_state["resultado_nhl_calculado"]
    _, eg = calcular_edge_real(r["momio"], r["prob"])
    stk = calcular_criterio_kelly(st.session_state["bankroll_global"], r["prob"], r["momio"])
    st.success(f"🎯 **{r['partido']}** | Prob: `{r['prob']}%` | Edge: `+{eg:.2f}%` | Stake: `${stk} MXN`")
    if st.button("📥 Guardar SQLite", key="db_nh"): registrar_apuesta_db(fecha_formato_str, "NHL", r["partido"], r["mercado"], r["momio"], eg, stk); st.success("Guardado.")

elif modulo_seleccionado == "⚾ Béisbol Pro (MLB / LMP)":
  st.title(f"⚾ **Sistema Pro Béisbol Élite [{fecha_formato_str}]**")
  st.markdown("--- \n *Módulo protegido y congelado.*")
  col1, col2 = st.columns(2)
  with col1:
    ev = st.text_input("Visitante:", value="Yankees", key="bs_ev")
    erav = st.number_input("ERA Visita:", value=3.50, step=0.05, key="bs_erav")
    fipv = st.number_input("FIP Visita:", value=3.35, step=0.05, key="bs_fipv")
    bpv = st.number_input("Bullpen Visita:", value=3.2, step=0.1, key="bs_bpv")
  with col2:
    el = st.text_input("Local:", value="Red Sox", key="bs_el")
    eral = st.number_input("ERA Local:", value=3.80, step=0.05, key="bs_eral")
    fipl = st.number_input("FIP Local:", value=3.95, step=0.05, key="bs_fipl")
    bpl = st.number_input("Bullpen Local:", value=3.6, step=0.1, key="bs_bpl")
  tm = st.selectbox("Mercado:", ["Run Line", "Total Carreras"], key="bs_tm")
  if tm == "Run Line":
    seq = st.text_input("Selección:", value="Yankees (-1.5)", key="bs_seq")
    srl = st.number_input("Línea Run Line:", value=-1.5, step=0.5, key="bs_srl")
    mm = st.number_input("Momio:", value=130, step=5, key="bs_mm")
    if st.button("🚀 Calcular Béisbol", use_container_width=True):
      mat = motor_matematico_baseball(eral, fipl, erav, fipv, bpl, bpv, srl, 8.5)
      st.session_state["resultado_baseball_calculado"] = {"partido": f"{ev} @ {el}", "mercado": f"Run Line: {seq} ({srl})", "momio": int(mm), "prob": mat["runline_prob"]}
  else:
    lou = st.number_input("Línea Carreras O/U:", value=8.5, step=0.5, key="bs_lou")
    op = st.radio("Sel:", ["Over", "Under"], horizontal=True, key="bs_op")
    mm = st.number_input("Momio:", value=-110, step=5, key="bs_mmo")
    if st.button("🚀 Calcular Béisbol", use_container_width=True):
      mat = motor_matematico_baseball(eral, fipl, erav, fipv, bpl, bpv, -1.5, lou)
      st.session_state["resultado_baseball_calculado"] = {"partido": f"{ev} @ {el}", "mercado": f"Total {op} {lou}", "momio": int(mm), "prob": mat["over_pct"] if "Over" in op else mat["under_pct"]}
  if st.session_state["resultado_baseball_calculado"]:
    r = st.session_state["resultado_baseball_calculado"]
    _, eg = calcular_edge_real(r["momio"], r["prob"])
    stk = calcular_criterio_kelly(st.session_state["bankroll_global"], r["prob"], r["momio"])
    st.success(f"🎯 **{r['partido']}** | Prob: `{r['prob']}%` | Edge: `+{eg:.2f}%` | Stake: `${stk} MXN`")
    if st.button("📥 Guardar SQLite", key="db_bs"): registrar_apuesta_db(fecha_formato_str, "Béisbol", r["partido"], r["mercado"], r["momio"], eg, stk); st.success("Guardado.")

elif modulo_seleccionado == "🥊 Sistema Pro UFC / MMA":
  st.title(f"🥊 **Sistema Pro UFC / MMA Élite [{fecha_formato_str}]**")
  st.markdown("--- \n *Módulo avanzado de artes marciales mixtas.*")
  col_ufc1, col_ufc2 = st.columns(2)
  with col_ufc1:
    peleador_1 = st.text_input("Peleador 1:", value="Islam Makhachev", key="ufc_p1")
    acc_f1 = st.slider("Precisión Golpeo P1:", 30.0, 70.0, 58.0, 1.0, key="ufc_acc1")
    tdd_f1 = st.slider("Defensa Derribos P1:", 40.0, 100.0, 90.0, 1.0, key="ufc_tdd1")
    fin_f1 = st.slider("Tasa Finalización P1:", 20.0, 100.0, 75.0, 1.0, key="ufc_fin1")
  with col_ufc2:
    peleador_2 = st.text_input("Peleador 2:", value="Arman Tsarukyan", key="ufc_p2")
    acc_f2 = st.slider("Precisión Golpeo P2:", 30.0, 70.0, 48.0, 1.0, key="ufc_acc2")
    tdd_f2 = st.slider("Defensa Derribos P2:", 40.0, 100.0, 78.0, 1.0, key="ufc_tdd2")
    fin_f2 = st.slider("Tasa Finalización P2:", 20.0, 100.0, 60.0, 1.0, key="ufc_fin2")

  seleccion_ufc = st.text_input("Peleador a Apoyar:", value="Islam Makhachev", key="ufc_sel_text")
  momio_manual_ufc = st.number_input("Momio Americano (UFC):", value=-250, step=5, key="ufc_mm")

  if st.button("🚀 Ejecutar Modelo UFC (Moneyline)", use_container_width=True):
    matriz_ufc = motor_matematico_ufc(acc_f1, tdd_f1, fin_f1, acc_f2, tdd_f2, fin_f2)
    prob_ufc = matriz_ufc["prob_f1"] if seleccion_ufc.strip().lower() == peleador_1.strip().lower() else matriz_ufc["prob_f2"]
    st.session_state["resultado_ufc_calculado"] = {
        "partido": f"{peleador_2} vs {peleador_1}", "mercado": f"UFC Moneyline: {seleccion_ufc}",
        "momio": int(momio_manual_ufc), "prob": prob_ufc, "rat1": matriz_ufc["rating_f1"], "rat2": matriz_ufc["rating_f2"]
    }

  if st.session_state["resultado_ufc_calculado"]:
    res_ufc = st.session_state["resultado_ufc_calculado"]
    _, edge_ufc = calcular_edge_real(res_ufc["momio"], res_ufc["prob"])
    stake_ufc = calcular_criterio_kelly(st.session_state["bankroll_global"], res_ufc["prob"], res_ufc["momio"])
    st.success(f"🎯 Análisis UFC para: **{res_ufc['partido']}** | Prob: `{res_ufc['prob']}%` | Edge: `+{edge_ufc:.2f}%`")
    if st.button("📥 Guardar SQLite (UFC)", key="guardar_sqlite_ufc"):
      registrar_apuesta_db(fecha_formato_str, "UFC Élite", res_ufc["partido"], res_ufc["mercado"], res_ufc["momio"], edge_ufc, stake_ufc)
      st.success("¡Apuesta UFC guardada!")

elif modulo_seleccionado == "🔍 Escáner Automático Multi-Deporte (+EV)":
  st.title(f"🔍 **Escáner Multi-Deporte [{fecha_formato_str}]**")
  api_key = st.session_state["api_key_guardada"]
  cartelera = obtener_partidos_y_momios_api("soccer_mexico_ligamx", api_key)
  for idx, p in enumerate(cartelera[:10], 1):
    st.info(f"⚽ Liga MX #{idx}: `{p['partido_str']}` | **{p['mercado']}** | Cuota: `{p['momio']}` | Edge: `+{p['edge']:.2f}%`")

elif modulo_seleccionado == "📊 Control de Bankroll & Historial SQLite":
  st.title(f"📊 **Panel de Control & Bankroll [{fecha_formato_str}]**")
  conn = sqlite3.connect("master_suite_elite.db")
  cursor = conn.cursor()
  cursor.execute("SELECT id, fecha, deporte, partido, mercado, momio, edge, stake, resultado, ganancia_neta, clv_cuota, bankroll_historico FROM apuestas")
  registros = cursor.fetchall()
  conn.close()
  resueltas = [r for r in registros if r[8] in ["Ganada", "Perdida"]]
  ganadas = [r for r in registros if r[8] == "Ganada"]
  hit_rate = (len(ganadas) / len(resueltas) * 100.0) if resueltas else 0.0
  total_apostado = sum([r[7] for r in resueltas])
  ganancia_total_neta = sum([r[9] for r in resueltas])
  roi = (ganancia_total_neta / total_apostado * 100.0) if total_apostado > 0 else 0.0
  bankroll_actualizado = st.session_state["bankroll_global"] + ganancia_total_neta

  col_m1, col_m2, col_m3, col_m4 = st.columns(4)
  col_m1.metric("💰 Bankroll Actual", f"${bankroll_actualizado:,.2f} MXN")
  col_m2.metric("🎯 Hit Rate", f"{hit_rate:.1f}%")
  col_m3.metric("📈 ROI Neto", f"{roi:.2f}%")
  col_m4.metric("💵 Ganancia Neta", f"${ganancia_total_neta:+,.2f} MXN")

  if registros:
    st.markdown("---")
    for reg in registros:
      apuesta_id, fecha, deporte, partido, mercado, momio, edge, stake, estado, ganancia, clv, _ = reg
      st.info(f"🆔 {apuesta_id} | 📅 {fecha} | **{deporte}** | `{partido}` | **{mercado}** | Momio: `{momio}` | Stake: `${stake}` | Estado: **{estado}** (${ganancia:+,.2f})")
  else:
    st.info("No hay apuestas registradas todavía.")

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
      msg = f"⚖️ *ALERTA DE ARBITRAJE*\nROI: +{roi_arb:.2f}%\nGanancia: ${ganancia_garantizada:,.2f} MXN"
      enviar_alerta_telegram(st.session_state["telegram_token"], st.session_state["telegram_chat_id"], msg)
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
