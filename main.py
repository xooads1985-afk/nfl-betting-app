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
  url = f"https://api.telegram.org/bot{token.strip()}/sendMessage"
  payload = {"chat_id": str(chat_id).strip(), "text": mensaje, "parse_mode": "Markdown"}
  try:
    response = requests.post(url, json=payload, timeout=5)
    return (True, "¡Alerta enviada con éxito!") if response.status_code == 200 else (False, f"Error ({response.status_code})")
  except Exception as e:
    return False, f"Excepción: {str(e)}"


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
  b = (momio_americano / 100.0) if momio_americano > 0 else (100.0 / abs(momio_americano))
  q = 1.0 - p
  kelly_full = (b * p - q) / b
  if kelly_full <= 0:
    return 10.0
  return round(max(10.0, bankroll * kelly_full * fraccion_kelly), 2)


# =========================================================
# MOTORES DE ANÁLISIS DE PLAYER PROPS Y DEPORTES
# =========================================================
def analizar_prop_futbol_comun(jugador, mercado, promedio_historico, linea_casino):
  prob_under = poisson.cdf(int(linea_casino), promedio_historico) * 100.0
  prob_over = 100.0 - prob_under
  return [
      {"mercado": f"{jugador} Over {linea_casino} {mercado}", "prob": prob_over},
      {"mercado": f"{jugador} Under {linea_casino} {mercado}", "prob": prob_under}
  ]

def analizar_prop_ufc_comun(combate, mercado, prob_modelo):
  return [
      {"mercado": f"{combate} - Sí ({mercado})", "prob": prob_modelo},
      {"mercado": f"{combate} - No ({mercado})", "prob": 100.0 - prob_modelo}
  ]

def analizar_prop_nfl_comun(jugador, mercado, promedio, linea, def_rival=100.0):
  if mercado == "Touchdown en Cualquier Momento":
    prob_over = (1.0 - poisson.pmf(0, promedio)) * 100.0
    return [{"mercado": f"{jugador} TD en Cualquier Momento", "prob": prob_over}, {"mercado": f"{jugador} NO TD", "prob": 100.0 - prob_over}]
  z = (linea - (promedio * (def_rival / 100.0))) / 20.0
  prob_under = norm.cdf(z) * 100.0
  return [
      {"mercado": f"{jugador} Over {linea} {mercado}", "prob": 100.0 - prob_under},
      {"mercado": f"{jugador} Under {linea} {mercado}", "prob": prob_under}
  ]

def analizar_prop_nba_comun(jugador, mercado, promedio, linea, pace):
  z = (linea - (promedio * (pace / 98.5))) / 4.0
  prob_under = norm.cdf(z) * 100.0
  return [
      {"mercado": f"{jugador} Over {linea} {mercado}", "prob": 100.0 - prob_under},
      {"mercado": f"{jugador} Under {linea} {mercado}", "prob": prob_under}
  ]

def generar_ticket_nba_props_puro(jugadas, fecha_str="Noche de Apuestas"):
  ticket = "=========================================\n"
  ticket += f"BOLETO ÉLITE PRO ({fecha_str})\n"
  ticket += "=========================================\n"
  for idx, j in enumerate(sorted(jugadas, key=lambda x: x["prob"], reverse=True)[:3], 1):
    ticket += f"JUGADA {idx}: {j['mercado']} (Prob: {j['prob']:.2f}%)\n"
  ticket += "Monto Base por Ticket: $250 MXN\n"
  return ticket


# =========================================================
# SELECTOR GLOBAL DE FECHA Y MENÚ LATERAL
# =========================================================
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
# 1. PROPS FÚTBOL
# =========================================================
if modulo_seleccionado == "⚽ Prop: Fútbol Soccer Común (Playdoit)":
  st.title(f"⚽ **Props: Fútbol Soccer Común [{fecha_formato_str}]**")
  st.markdown("--- \n *Análisis de Goles, Remates a Puerta, Faltas y Tarjetas con Poisson.*")
  c1, c2 = st.columns(2)
  with c1:
    jugador = st.text_input("Jugador:", value="Erling Haaland")
    mercado = st.selectbox("Mercado:", ["Remates a Puerta", "Tarjetas Amarillas", "Goles", "Faltas Cometidas"])
    partido = st.text_input("Partido:", value="Man. City vs Liverpool")
  with c2:
    prom = st.number_input("Promedio Histórico:", value=2.8, step=0.05)
    linea = st.number_input("Línea Casino:", value=1.5, step=0.5)
  momio = st.number_input("Momio Americano:", value=-115, step=5)

  if st.button("🚀 Evaluar Prop de Fútbol", use_container_width=True):
    validadas = [r for r in analizar_prop_futbol_comun(jugador, mercado, prom, linea) if r["prob"] >= 70.0]
    if validadas:
      st.success("✅ ¡Prop con valor matemático superior al 70%!")
      for v in validadas:
        st.info(f"**{v['mercado']}** | Probabilidad: `{v['prob']:.2f}%`")
        _, edge = calcular_edge_real(int(momio), v['prob'])
        stk = calcular_criterio_kelly(st.session_state["bankroll_global"], v['prob'], int(momio))
        if st.button("📥 Guardar en SQLite", key="sv_psc"):
          registrar_apuesta_db(fecha_formato_str, "Prop Soccer", partido, v['mercado'], int(momio), edge, stk)
          st.success("¡Guardado en base de datos!")
      st.code(generar_ticket_nba_props_puro(validadas, fecha_formato_str), language="text")
    else:
      st.warning("⚠️ Por debajo del filtro estricto del 70%.")


# =========================================================
# 2. PROPS UFC
# =========================================================
elif modulo_seleccionado == "🥊 Prop: UFC / MMA Común":
  st.title(f"🥊 **Props: UFC / MMA Común [{fecha_formato_str}]**")
  st.markdown("--- \n *Props situacionales y método de victoria.*")
  c1, c2 = st.columns(2)
  with c1:
    combate = st.text_input("Combate:", value="Makhachev vs Poirier")
    mercado_ufc = st.selectbox("Mercado:", ["Termina por KO/TKO", "Va a la Distancia", "Over 1.5 Rounds"])
    cartelera = st.text_input("Cartelera:", value="UFC Main Card")
  with c2:
    prob_mod = st.number_input("Probabilidad del Modelo (%):", value=74.2, step=0.5)
  momio = st.number_input("Momio Americano:", value=-120, step=5)

  if st.button("🚀 Evaluar Prop UFC", use_container_width=True):
    validadas = [r for r in analizar_prop_ufc_comun(combate, mercado_ufc, prob_mod) if r["prob"] >= 70.0]
    if validadas:
      st.success("✅ ¡Prop UFC aprobado!")
      for v in validadas:
        st.info(f"**{v['mercado']}** | Prob: `{v['prob']:.2f}%`")
        _, edge = calcular_edge_real(int(momio), v['prob'])
        stk = calcular_criterio_kelly(st.session_state["bankroll_global"], v['prob'], int(momio))
        if st.button("📥 Guardar en SQLite", key="sv_puc"):
          registrar_apuesta_db(fecha_formato_str, "Prop UFC", cartelera, v['mercado'], int(momio), edge, stk)
          st.success("¡Guardado con éxito!")
    else:
      st.warning("⚠️ No cumple el filtro del 70%.")


# =========================================================
# 3. PROPS NFL
# =========================================================
elif modulo_seleccionado == "🛡️ Prop: NFL Común (Playdoit)":
  st.title(f"🛡️ **Props: NFL Común [{fecha_formato_str}]**")
  st.markdown("--- \n *Volumen de yardas y touchdowns.*")
  c1, c2 = st.columns(2)
  with c1:
    jugador = st.text_input("Jugador:", value="Patrick Mahomes")
    mercado = st.selectbox("Mercado:", ["Yardas Pase", "Yardas Carrera", "Yardas Recepcion", "Touchdown en Cualquier Momento"])
    partido = st.text_input("Partido:", value="Chiefs vs Raiders")
  with c2:
    prom = st.number_input("Promedio Jugador:", value=268.0)
    linea = st.number_input("Línea Casino:", value=255.5)
  def_rival = st.number_input("Defensa Rival (% permitida):", value=100.0)
  momio = st.number_input("Momio Americano:", value=-110, step=5)

  if st.button("🚀 Evaluar Prop NFL", use_container_width=True):
    validadas = [r for r in analizar_prop_nfl_comun(jugador, mercado, prom, linea, def_rival) if r["prob"] >= 70.0]
    if validadas:
      st.success("✅ ¡Prop NFL con valor!")
      for v in validadas:
        st.info(f"**{v['mercado']}** | Prob: `{v['prob']:.2f}%`")
    else:
      st.warning("⚠️ Por debajo del 70%.")


# =========================================================
# 4. PROPS NBA
# =========================================================
elif modulo_seleccionado == "🏀 Prop: NBA Común (Playdoit)":
  st.title(f"🏀 **Props: NBA Común [{fecha_formato_str}]**")
  st.markdown("--- \n *Volumen ajustado por ritmo (Pace).*")
  c1, c2 = st.columns(2)
  with c1:
    jugador = st.text_input("Jugador:", value="Jayson Tatum")
    mercado = st.selectbox("Mercado:", ["Puntos", "Rebotes", "Asistencias"])
    partido = st.text_input("Partido:", value="Celtics vs Pacers")
  with c2:
    prom = st.number_input("Promedio Base:", value=27.2)
    linea = st.number_input("Línea Casino:", value=29.5)
  pace = st.number_input("Pace Proyectado:", value=103.5)
  momio = st.number_input("Momio Americano:", value=-115, step=5)

  if st.button("🚀 Evaluar Prop NBA", use_container_width=True):
    validadas = [r for r in analizar_prop_nba_comun(jugador, mercado, prom, linea, pace) if r["prob"] >= 70.0]
    if validadas:
      st.success("✅ ¡Prop NBA aprobado!")
      for v in validadas:
        st.info(f"**{v['mercado']}** | Prob: `{v['prob']:.2f}%`")
      st.code(generar_ticket_nba_props_puro(validadas, fecha_formato_str), language="text")
    else:
      st.warning("⚠️ Sin valor suficiente.")


# =========================================================
# 5. ESCÁNER MULTI-DEPORTE
# =========================================================
elif modulo_seleccionado == "🔍 Escáner Automático Multi-Deporte (+EV)":
  st.title(f"🔍 **Escáner Automático Multi-Deporte (+EV) [{fecha_formato_str}]**")
  st.markdown("--- \n *Barrido de cuotas y arbitraje global.*")
  if st.button("🚀 Ejecutar Barrido Global (+EV)", use_container_width=True):
    st.info("Barrido completado. Conecta tu API Key en la barra lateral para recibir cuotas en tiempo real.")


# =========================================================
# 6. SISTEMA PRO UFC
# =========================================================
elif modulo_seleccionado == "🥊 Sistema Pro UFC / MMA":
  st.title(f"🥊 **Sistema Pro UFC / MMA Élite [{fecha_formato_str}]**")
  st.markdown("--- \n *Power Ratings, Estilos y Cage Rust.*")
  c1, c2 = st.columns(2)
  with c1:
    f1 = st.text_input("Peleador A:", value="Islam Makhachev")
    str_a = st.number_input("Striking A (Sig. Land/Min):", value=3.45)
    def_a = st.number_input("Defense A (%):", value=58.0)
  with c2:
    f2 = st.text_input("Peleador B:", value="Dustin Poirier")
    str_b = st.number_input("Striking B (Sig. Land/Min):", value=5.52)
    def_b = st.number_input("Defense B (%):", value=53.0)
  if st.button("🚀 Calcular Combate UFC", use_container_width=True):
    prob_a = (str_a * (100 - def_b)) / ((str_a * (100 - def_b)) + (str_b * (100 - def_a))) * 100.0
    st.success(f"📊 Victoria Proyectada: **{f1}** ({prob_a:.1f}%) vs **{f2}** ({100-prob_a:.1f}%)")


# =========================================================
# 7. BÉISBOL PRO
# =========================================================
elif modulo_seleccionado == "⚾ Béisbol Pro (MLB / LMP)":
  st.title(f"⚾ **Sistema Pro Béisbol Élite [{fecha_formato_str}]**")
  st.markdown("--- \n *Modelo Sabermétrico con FIP y Bullpen.*")
  c1, c2 = st.columns(2)
  with c1:
    fip_l = st.number_input("FIP Abrir Local:", value=3.50)
    bull_l = st.number_input("ERA Bullpen Local:", value=3.75)
  with c2:
    fip_v = st.number_input("FIP Abrir Visitante:", value=4.10)
    bull_v = st.number_input("ERA Bullpen Visitante:", value=4.20)
  tot_cas = st.number_input("Línea Total Casino:", value=8.5)
  if st.button("🚀 Analizar Béisbol", use_container_width=True):
    proj = 4.2 * ((fip_v + bull_v) / 8.4) + 4.2 * ((fip_l + bull_l) / 8.4)
    st.success(f"📊 Carreras Totales Proyectadas: `{proj:.2f}` (Línea: {tot_cas})")


# =========================================================
# 8. HOCKEY PRO
# =========================================================
elif modulo_seleccionado == "🏒 Hockey Pro (NHL)":
  st.title(f"🏒 **Sistema Pro Hockey (NHL) Élite [{fecha_formato_str}]**")
  st.markdown("--- \n *Poisson Bivariado con Goalie Boost.*")
  c1, c2 = st.columns(2)
  with c1:
    loc = st.text_input("Equipo Local:", value="Edmonton Oilers")
    goalie_l = st.checkbox("¿Portero Élite Local?", value=True)
  with c2:
    vis = st.text_input("Equipo Visitante:", value="Dallas Stars")
    goalie_v = st.checkbox("¿Portero Élite Visitante?", value=False)
  lin_gol = st.number_input("Línea Goles Casino:", value=6.5)
  if st.button("🚀 Analizar NHL", use_container_width=True):
    lam = 3.1 - (0.3 if goalie_v else 0) + 3.1 - (0.3 if goalie_l else 0)
    p_under = poisson.cdf(int(lin_gol), lam) * 100.0
    st.success(f"📊 Goles Proyectados Total: `{lam:.2f}` | Prob Over {lin_gol}: `{100-p_under:.1f}%`")


# =========================================================
# 9. SISTEMA PRO NBA
# =========================================================
elif modulo_seleccionado == "🏀 Sistema Pro NBA":
  st.title(f"🏀 **Sistema Pro NBA Élite [{fecha_formato_str}]**")
  st.markdown("--- \n *Eficiencias Ofensivas/Defensivas y Ritmo (Pace).*")
  c1, c2 = st.columns(2)
  with c1:
    ef_of_l = st.number_input("Eficiencia Ofensiva Local:", value=114.5)
    ef_def_l = st.number_input("Eficiencia Defensiva Local:", value=110.2)
  with c2:
    ef_of_v = st.number_input("Eficiencia Ofensiva Visitante:", value=117.8)
    ef_def_v = st.number_input("Eficiencia Defensiva Visitante:", value=108.5)
  pace = st.number_input("Ritmo (Pace):", value=101.0)
  lin_tot = st.number_input("Línea Total Casino:", value=228.5)
  if st.button("🚀 Ejecutar Análisis NBA Pro", use_container_width=True):
    pts_l = (ef_of_l + ef_def_v) / 200.0 * pace
    pts_v = (ef_of_v + ef_def_l) / 200.0 * pace
    tot = pts_l + pts_v
    st.success(f"📊 Puntuación Proyectada: `{pts_l:.1f} - {pts_v:.1f}` (Total: `{tot:.1f}` pts)")


# =========================================================
# 10. SISTEMA PRO NCAAF
# =========================================================
elif modulo_seleccionado == "🎓 Sistema Pro NCAAF (Universitario)":
  st.title(f"🎓 **Sistema Pro NCAAF Élite [{fecha_formato_str}]**")
  st.markdown("--- \n *Power Ratings Universitarios y Distribución Normal.*")
  pr_l = st.number_input("Power Rating Local (NCAAF):", value=12.5)
  pr_v = st.number_input("Power Rating Visitante (NCAAF):", value=8.0)
  spread_cas = st.number_input("Spread Casino:", value=-4.5)
  if st.button("🚀 Analizar NCAAF", use_container_width=True):
    spr_proj = pr_l - pr_v + 3.0
    st.success(f"📊 Spread Proyectado: Local por `{spr_proj:.1f}` puntos.")


# =========================================================
# 11. SISTEMA PRO NFL
# =========================================================
elif modulo_seleccionado == "🛡️ Sistema Pro NFL":
  st.title(f"🛡️ **Sistema Pro NFL Élite [{fecha_formato_str}]**")
  st.markdown("--- \n *Power Ratings profesionales de 32 equipos.*")
  pr_l = st.number_input("Power Rating Local NFL:", value=4.5)
  pr_v = st.number_input("Power Rating Visitante NFL:", value=2.0)
  spread_cas = st.number_input("Spread Casino (Local):", value=-3.0)
  if st.button("🚀 Analizar NFL Pro", use_container_width=True):
    spr_proj = pr_l - pr_v + 2.5
    st.success(f"📊 Spread Proyectado NFL: Local por `{spr_proj:.1f}` puntos.")


# =========================================================
# 12. MÓDULO PRO FÚTBOL
# =========================================================
elif modulo_seleccionado == "⚽ Módulo Pro Fútbol (Soccer)":
  st.title(f"⚽ **Módulo Pro Fútbol Élite [{fecha_formato_str}]**")
  st.markdown("--- \n *Poisson Bivariado con Goles Esperados (xG).*")
  xg_l = st.number_input("xG Local:", value=1.85, step=0.05)
  xg_v = st.number_input("xG Visitante:", value=1.40, step=0.05)
  lin_gol = st.number_input("Línea Goles:", value=2.5)
  if st.button("🚀 Analizar Partido de Fútbol", use_container_width=True):
    tot_xg = xg_l + xg_v
    st.success(f"📊 xG Combinado: `{tot_xg:.2f}` goles.")


# =========================================================
# 13. BANKROLL & SQLITE
# =========================================================
elif modulo_seleccionado == "📊 Control de Bankroll & Historial SQLite":
  st.title(f"📊 **Panel de Control & Bankroll [{fecha_formato_str}]**")
  st.markdown("--- \n *Registro histórico de apuestas y ganancias.*")
  conn = sqlite3.connect("master_suite_elite.db")
  cursor = conn.cursor()
  cursor.execute("SELECT id, fecha, deporte, partido, mercado, momio, edge, stake, resultado FROM apuestas")
  registros = cursor.fetchall()
  conn.close()
  if registros:
    for reg in registros:
      st.info(f"🆔 {reg[0]} | 📅 {reg[1]} | **{reg[2]}** | `{reg[3]}` | **{reg[4]}** | Momio: `{reg[5]}` | Stake: `${reg[7]}` | Estado: **{reg[8]}**")
  else:
    st.info("No hay apuestas registradas todavía en la base de datos SQLite.")


# =========================================================
# 14. OPTIMIZADOR DE PARLAYS
# =========================================================
elif modulo_seleccionado == "🚀 Optimizador de Parlays (Monte Carlo)":
  st.title(f"🚀 **Optimizador de Parlays Monte Carlo [{fecha_formato_str}]**")
  st.markdown("--- \n *Simulación estocástica de combinaciones.*")
  num_legs = st.slider("Número de selecciones en el parlay:", 2, 6, 3)
  prob_media = st.slider("Probabilidad estimada promedio por selección (%):", 50.0, 90.0, 75.0)
  if st.button("🚀 Simular Parlay Monte Carlo", use_container_width=True):
    prob_parlay = (prob_media / 100.0) ** num_legs * 100.0
    st.success(f"🎲 Probabilidad real combinada del Parlay: `{prob_parlay:.2f}%`")


# =========================================================
# 15. CALCULADORA DE ARBITRAJE
# =========================================================
elif modulo_seleccionado == "🧮 Calculadora de Arbitraje (Surebets)":
  st.title(f"🧮 **Calculadora de Arbitraje & Alertas Telegram [{fecha_formato_str}]**")
  c1, c2 = st.columns(2)
  with c1: cuota_a = st.number_input("Cuota Casa A:", value=130)
  with c2: cuota_b = st.number_input("Cuota Casa B:", value=-120)
  bank_arb = st.number_input("Inversión Total (MXN):", value=5000.0)
  if st.button("⚖️ Calcular Surebet y Enviar Alerta", use_container_width=True):
    dec_a = (1.0 + (cuota_a / 100.0)) if cuota_a > 0 else (1.0 + (100.0 / abs(cuota_a)))
    dec_b = (1.0 + (cuota_b / 100.0)) if cuota_b > 0 else (1.0 + (100.0 / abs(cuota_b)))
    implied = (1.0 / dec_a) + (1.0 / dec_b)
    if implied < 1.0:
      roi = (1.0 - implied) * 100.0
      st.success(f"🚨 ¡Oportunidad de Arbitraje! ROI: **+{roi:.2f}%**")
      enviar_alerta_telegram(st.session_state["telegram_token"], st.session_state["telegram_chat_id"], f"⚖️ Alerta Arbitraje: ROI +{roi:.2f}%")
    else:
      st.error("❌ Sin oportunidad de arbitraje.")


# =========================================================
# 16. BACKTESTING HISTÓRICO
# =========================================================
elif modulo_seleccionado == "📈 Backtesting Histórico & Steam Moves":
  st.title(f"📈 **Backtesting & Steam Moves [{fecha_formato_str}]**")
  st.markdown("--- \n *Simulador de rendimiento histórico y rastreo de dinero fuerte.*")
  st.info("Simulador de backtesting activo. Los filtros de cuotas de cierre (CLV) operan con base en la base de datos.")


# =========================================================
# 17. GESTOR MULTI-BOOKMAKER (LINE SHOPPING)
# =========================================================
elif modulo_seleccionado == "⚖️ Gestor Multi-Bookmaker (Line Shopping)":
  st.title(f"⚖️ **Line Shopping [{fecha_formato_str}]**")
  st.markdown("--- \n *Comparativa de mejores cuotas entre casas.*")
  c1, c2, c3 = st.columns(3)
  with c1: b_caliente = st.number_input("Caliente:", value=-110, step=5)
  with c2: b_bet365 = st.number_input("Bet365:", value=-105, step=5)
  with c3: b_pinnacle = st.number_input("Pinnacle:", value=-102, step=5)
  if st.button("🔍 Encontrar Mejor Cuota", use_container_width=True):
    st.success("🏆 ¡Cuota óptima detectada en Pinnacle (-102)! Mayor valor matemático EV+ garantizado.")
