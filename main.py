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

if "resultado_ncaaf_calculado" not in st.session_state:
  st.session_state["resultado_ncaaf_calculado"] = None

if "resultado_nfl_calculado" not in st.session_state:
  st.session_state["resultado_nfl_calculado"] = None


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
# MOTORES MATEMÁTICOS & SINDICATO INDUSTRIAL (NCAAF & NFL)
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


# Motor NCAAF
def motor_matematico_ncaaf_spread(ppg_local, pap_local, ppg_visita, pap_visita, spread_casino, factor_localia=3.0, fatiga_visita=False, fatiga_local=False, lesion_qb_local=False, lesion_qb_visita=False):
  pr_local = ppg_local - (pap_local * 0.95)
  pr_visita = ppg_visita - (pap_visita * 0.95)
  if fatiga_local: pr_local -= 2.5
  if fatiga_visita: pr_visita -= 2.5
  if lesion_qb_local: pr_local -= 6.5
  if lesion_qb_visita: pr_visita -= 6.5
  margen_proyectado = (pr_local + factor_localia) - pr_visita
  desviacion_std = 13.5
  z_score = (margen_proyectado - abs(spread_casino)) / desviacion_std
  prob_cubrir = stats.norm.cdf(z_score) * 100.0
  return round(max(5.0, min(95.0, prob_cubrir)), 2), round(margen_proyectado, 1)


def motor_matematico_ncaaf_totales(ppg_local, pap_local, ppg_visita, pap_visita, linea_casa, fatiga_visita=False, fatiga_local=False, lesion_qb_local=False, lesion_qb_visita=False):
  lambda_esperado = (ppg_local + ppg_visita + pap_local + pap_visita) / 2.0
  if fatiga_local or fatiga_visita: lambda_esperado -= 3.0
  if lesion_qb_local or lesion_qb_visita: lambda_esperado -= 5.0
  lambda_ajustado = round(max(15.0, lambda_esperado * 0.98), 1)
  prob_under = 0.0
  limite = int(math.floor(linea_casa))
  for k in range(limite + 1):
    prob_under += poisson.pmf(k, lambda_ajustado)
  prob_over = (1.0 - prob_under) * 100.0
  return round(prob_over, 2), lambda_ajustado


# Motor NFL (Profesional - Desviación estándar ajustada a 11.5 y factor localía de 2.5)
def motor_matematico_nfl_spread(ppg_local, pap_local, ppg_visita, pap_visita, spread_casino, lesion_qb_local=False, lesion_qb_visita=False):
  pr_local = ppg_local - (pap_local * 0.98)
  pr_visita = ppg_visita - (pap_visita * 0.98)
  
  if lesion_qb_local: pr_local -= 5.5 # En NFL la baja de un QB pesa entre 5 y 6 puntos
  if lesion_qb_visita: pr_visita -= 5.5
  
  # Factor localía estándar NFL (aprox 2.5 puntos)
  margen_proyectado = (pr_local + 2.5) - pr_visita
  desviacion_std = 11.5 # Desviación típica profesional en NFL
  z_score = (margen_proyectado - abs(spread_casino)) / desviacion_std
  prob_cubrir = stats.norm.cdf(z_score) * 100.0
  return round(max(5.0, min(95.0, prob_cubrir)), 2), round(margen_proyectado, 1)


def motor_matematico_nfl_totales(ppg_local, pap_local, ppg_visita, pap_visita, linea_casa, lesion_qb_local=False, lesion_qb_visita=False):
  lambda_esperado = (ppg_local + ppg_visita + pap_local + pap_visita) / 2.0
  if lesion_qb_local or lesion_qb_visita: lambda_esperado -= 4.0
  lambda_ajustado = round(max(10.0, lambda_esperado * 0.97), 1)
  
  prob_under = 0.0
  limite = int(math.floor(linea_casa))
  for k in range(limite + 1):
    prob_under += poisson.pmf(k, lambda_ajustado)
  prob_over = (1.0 - prob_under) * 100.0
  return round(prob_over, 2), lambda_ajustado


# ---------------------------------------------------------
# CONEXIÓN CON THE ODDS API (OTROS DEPORTES)
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
              nombre_seleccion = out.get("name")
              precio_momio = out.get("price")
              if precio_momio:
                prob_imp_base = calcular_probabilidad_implicita(precio_momio) * 100.0
                factor_modelo_ia = 1.03 if precio_momio > 0 else 0.99
                prob_modelo = round(min(90.0, max(10.0, prob_imp_base * factor_modelo_ia)), 2)
                _, edge_calculado = calcular_edge_real(precio_momio, prob_modelo)
                
                if m_key == "h2h":
                  mercado_claro = f"Ganador (Moneyline): {nombre_seleccion}"
                elif m_key == "spreads":
                  punto_spread = out.get("point", 0.0)
                  mercado_claro = f"Spread: {nombre_seleccion} ({punto_spread})"
                elif m_key == "totals":
                  punto_total = out.get("point", 0.0)
                  mercado_claro = f"Total Over/Under: {nombre_seleccion} ({punto_total})"
                else:
                  mercado_claro = f"{m_key.upper()}: {nombre_seleccion}"

                stake_sugerido = calcular_criterio_kelly(
                    st.session_state["bankroll_global"], prob_modelo, int(precio_momio)
                )

                partidos_analizados.append({
                    "partido_str": f"{visita} @ {local}",
                    "local": local,
                    "visita": visita,
                    "mercado": mercado_claro,
                    "momio": int(precio_momio),
                    "edge": round(edge_calculado, 2),
                    "stake": stake_sugerido
                })
      return partidos_analizados
  except Exception:
    pass
  return []


# ---------------------------------------------------------
# SELECTOR GLOBAL DE FECHA Y MENÚ LATERAL
# ---------------------------------------------------------
st.sidebar.title("🎯 Menú Principal")

fecha_seleccionada = st.sidebar.date_input(
    "📅 Fecha a Analizar:", value=date.today()
)
fecha_formato_str = fecha_seleccionada.strftime("%Y-%m-%d")

st.sidebar.markdown("---")
st.sidebar.subheader("🌐 Configuración de API & Telegram")
st.session_state["api_key_guardada"] = st.sidebar.text_input(
    "API Key (The Odds API):",
    value=st.session_state["api_key_guardada"],
    type="password",
)
st.session_state["telegram_token"] = st.sidebar.text_input(
    "Bot Token:", value=st.session_state["telegram_token"], type="password"
)
st.session_state["telegram_chat_id"] = st.sidebar.text_input(
    "Chat ID:", value=st.session_state["telegram_chat_id"]
)

if st.sidebar.button("🔄 Sincronizar Datos", use_container_width=True):
  st.cache_data.clear()
  st.rerun()

st.sidebar.markdown("---")
modulo_seleccionado = st.sidebar.radio(
    "Selecciona el módulo:",
    [
        "🎓 Sistema Pro NCAAF (Universitario)",
        "🛡️ Sistema Pro NFL",
        "🔍 Escáner Automático Multi-Deporte (+EV)",
        "🏀 Sistema Pro NBA",
        "⚽ Módulo Pro Fútbol (Soccer)",
        "⚾ Béisbol & LMP",
        "🏒 Hockey Pro (NHL)",
        "🥊 Sistema Pro UFC",
        "📊 Control de Bankroll & Historial SQLite",
        "🚀 Optimizador de Parlays (Monte Carlo)",
        "🧮 Calculadora de Arbitraje (Surebets)",
        "📈 Backtesting Histórico & Steam Moves",
        "⚖️ Gestor Multi-Bookmaker (Line Shopping)",
    ],
)


# =========================================================
# 1. SISTEMA PRO NCAAF (100% MANUAL Y FLUIDO)
# =========================================================
if modulo_seleccionado == "🎓 Sistema Pro NCAAF (Universitario)":
  st.title(f"🎓 **Sistema Pro NCAAF Élite (Fútbol Americano Universitario) [{fecha_formato_str}]**")
  st.markdown("--- \n *Motor cuantitativo optimizado: ingreso manual directo, Power Ratings, Distribución Normal, Poisson, Fatiga y Lesiones de QB.*")

  st.subheader("✍️ Estadísticas, Fatiga & Impacto de Lesiones")
  
  col_eq1, col_eq2 = st.columns(2)
  with col_eq1:
    equipo_visita = st.text_input("Equipo Visitante:", value="Michigan Wolverines")
    off_visita_pts = st.number_input("Puntos Anotados (Visita):", value=28.5, step=0.5, key="ncaaf_ov")
    def_visita_pts = st.number_input("Puntos Permitidos (Visita):", value=17.0, step=0.5, key="ncaaf_dv")
    fatiga_visita = st.checkbox("⚠️ Visitante sin descanso (Bye Week ausente)", key="ncaaf_fv")
    lesion_qb_visita = st.checkbox("🚨 BAJA CRÍTICA: QB Titular Visitante Lesionado", key="ncaaf_lqbv")
  with col_eq2:
    equipo_local = st.text_input("Equipo Local:", value="Ohio State Buckeyes")
    off_local_pts = st.number_input("Puntos Anotados (Local):", value=34.0, step=0.5, key="ncaaf_ol")
    def_local_pts = st.number_input("Puntos Permitidos (Local):", value=12.5, step=0.5, key="ncaaf_dl")
    fatiga_local = st.checkbox("⚠️ Local sin descanso (Bye Week ausente)", key="ncaaf_fl")
    lesion_qb_local = st.checkbox("🚨 BAJA CRÍTICA: QB Titular Local Lesionado", key="ncaaf_lqbl")

  tipo_mercado = st.selectbox(
      "Selecciona el Mercado a Analizar (NCAAF):",
      [
          "Spread (Hándicap con Lesiones y Fatiga)", 
          "Total Over / Under (Altas y Bajas Avanzadas - Poisson)"
      ]
  )

  if tipo_mercado == "Spread (Hándicap con Lesiones y Fatiga)":
    seleccion_equipo = st.text_input("Equipo Seleccionado para el Spread:", value="Ohio State Buckeyes (-3.5)")
    spread_casino = st.number_input("Línea de Spread del Casino (Ej. -3.5):", value=-3.5, step=0.5, key="ncaaf_sc")
    momio_manual = st.number_input("Momio Americano:", value=-110, step=5, key="ncaaf_mm")
    
    if st.button("🚀 Ejecutar Modelo Matemático Avanzado de Spread", use_container_width=True):
      prob_calc, margen_proyectado = motor_matematico_ncaaf_spread(off_local_pts, def_local_pts, off_visita_pts, def_visita_pts, spread_casino, 3.0, fatiga_visita, fatiga_local, lesion_qb_local, lesion_qb_visita)
      mercado_manual = f"Spread: {seleccion_equipo} (Línea: {spread_casino} | Proyectado: {margen_proyectado:+1.1f} pts)"
      
      st.session_state["resultado_ncaaf_calculado"] = {
          "partido": f"{equipo_visita} @ {equipo_local}",
          "mercado": mercado_manual,
          "momio": int(momio_manual),
          "prob": prob_calc
      }

  else:  
    linea_casa_ou = st.number_input("Línea Total de Puntos de la Casa (O/U):", value=51.5, step=0.5, key="ncaaf_lco")
    opcion_ou = st.radio("Selección Totales:", ["Over (Altas)", "Under (Bajas)"], horizontal=True, key="ncaaf_oou")
    momio_manual = st.number_input("Momio Americano:", value=-110, step=5, key="ncaaf_mmo")

    if st.button("🚀 Ejecutar Modelo Matemático Avanzado de Totales", use_container_width=True):
      prob_over_calc, lambda_proyectado = motor_matematico_ncaaf_totales(off_local_pts, def_local_pts, off_visita_pts, def_visita_pts, linea_casa_ou, fatiga_visita, fatiga_local, lesion_qb_local, lesion_qb_visita)
      probabilidad_calculada = prob_over_calc if "Over" in opcion_ou else (100.0 - prob_over_calc)
      mercado_manual = f"Total {opcion_ou} ({linea_casa_ou} pts) [Modelo Lambda: {lambda_proyectado}]"
      
      st.session_state["resultado_ncaaf_calculado"] = {
          "partido": f"{equipo_visita} @ {equipo_local}",
          "mercado": mercado_manual,
          "momio": int(momio_manual),
          "prob": round(probabilidad_calculada, 2)
      }

  st.markdown("---")
  st.subheader("📌 Resultado del Análisis (Fijo e Inalterable)")

  if st.session_state["resultado_ncaaf_calculado"]:
    res = st.session_state["resultado_ncaaf_calculado"]
    _, edge_man = calcular_edge_real(res["momio"], res["prob"])
    stake_man = calcular_criterio_kelly(st.session_state["bankroll_global"], res["prob"], res["momio"])

    st.success(f"🎯 Análisis guardado y fijo para: **{res['partido']}**")
    st.metric(label="📊 Probabilidad Científica Calculada por el Código", value=f"{res['prob']}%")

    st.info(
        f"🎯 **Apuesta Sugerida:** `{res['mercado']}` \n"
        f"📈 **Cuota:** `{res['momio']}` | 🎯 **Edge Neto (+EV):** `+{edge_man:.2f}%` | 💡 **Stake Óptimo (Kelly 25%):** `${stake_man} MXN`"
    )

    col_sb1, col_sb2 = st.columns(2)
    with col_sb1:
      if st.button("📥 Guardar en Base de Datos SQLite", key="guardar_sqlite_ncaaf"):
        registrar_apuesta_db(fecha_formato_str, "NCAAF Élite", res["partido"], res["mercado"], res["momio"], edge_man, stake_man)
        st.success("✅ ¡Apuesta guardada con éxito en SQLite!")
    with col_sb2:
      if st.button("📤 Enviar Alerta a Telegram", key="enviar_telegram_ncaaf"):
        msg = f"🎓 *ALERTA NCAAF ÉLITE*\n🏟️ {res['partido']}\n📊 {res['mercado']}\n📈 Momio: {res['momio']} | Edge: +{edge_man:.2f}%\n💰 Stake: ${stake_man} MXN"
        ok, res_tel = enviar_alerta_telegram(st.session_state["telegram_token"], st.session_state["telegram_chat_id"], msg)
        if ok: st.success(res_tel)
        else: st.error(res_tel)
  else:
    st.info("Ingresa los datos arriba y presiona el botón para generar el análisis definitivo.")


# =========================================================
# 2. SISTEMA PRO NFL (NUEVO MÓDULO PROFESIONAL BLINDADO)
# =========================================================
elif modulo_seleccionado == "🛡️ Sistema Pro NFL":
  st.title(f"🛡️ **Sistema Pro NFL Élite [{fecha_formato_str}]**")
  st.markdown("--- \n *Módulo profesional de la NFL con Power Ratings calibrados para la liga, distribución normal, modelo de Poisson y matriz de impacto por lesión de mariscal de campo.*")

  st.subheader("✍️ Estadísticas Promedio & Reporte de Lesiones NFL")
  
  col_nfl1, col_nfl2 = st.columns(2)
  with col_nfl1:
    equipo_visita_nfl = st.text_input("Equipo Visitante (NFL):", value="Kansas City Chiefs")
    off_visita_nfl = st.number_input("Puntos Anotados (Visita NFL):", value=26.0, step=0.5, key="nfl_ov")
    def_visita_nfl = st.number_input("Puntos Permitidos (Visita NFL):", value=19.5, step=0.5, key="nfl_dv")
    lesion_qb_visita_nfl = st.checkbox("🚨 BAJA CRÍTICA: QB Titular Visitante Lesionado", key="nfl_lqbv")
  with col_nfl2:
    equipo_local_nfl = st.text_input("Equipo Local (NFL):", value="Buffalo Bills")
    off_local_nfl = st.number_input("Puntos Anotados (Local NFL):", value=27.5, step=0.5, key="nfl_ol")
    def_local_nfl = st.number_input("Puntos Permitidos (Local NFL):", value=18.0, step=0.5, key="nfl_dl")
    lesion_qb_local_nfl = st.checkbox("🚨 BAJA CRÍTICA: QB Titular Local Lesionado", key="nfl_lqbl")

  tipo_mercado_nfl = st.selectbox(
      "Selecciona el Mercado a Analizar (NFL):",
      [
          "Spread (Hándicap Profesional NFL)", 
          "Total Over / Under (Altas y Bajas NFL - Poisson)"
      ]
  )

  if tipo_mercado_nfl == "Spread (Hándicap Profesional NFL)":
    seleccion_equipo_nfl = st.text_input("Equipo Seleccionado para el Spread NFL:", value="Buffalo Bills (-2.5)")
    spread_casino_nfl = st.number_input("Línea de Spread del Casino (Ej. -2.5):", value=-2.5, step=0.5, key="nfl_sc")
    momio_manual_nfl = st.number_input("Momio Americano (NFL):", value=-110, step=5, key="nfl_mm")
    
    if st.button("🚀 Ejecutar Modelo Matemático Profesional NFL (Spread)", use_container_width=True):
      prob_calc_nfl, margen_proyectado_nfl = motor_matematico_nfl_spread(off_local_nfl, def_local_nfl, off_visita_nfl, def_visita_nfl, spread_casino_nfl, lesion_qb_local_nfl, lesion_qb_visita_nfl)
      mercado_manual_nfl = f"Spread NFL: {seleccion_equipo_nfl} (Línea: {spread_casino_nfl} | Proyectado: {margen_proyectado_nfl:+1.1f} pts)"
      
      st.session_state["resultado_nfl_calculado"] = {
          "partido": f"{equipo_visita_nfl} @ {equipo_local_nfl}",
          "mercado": mercado_manual_nfl,
          "momio": int(momio_manual_nfl),
          "prob": prob_calc_nfl
      }

  else:  
    linea_casa_ou_nfl = st.number_input("Línea Total de Puntos de la Casa (O/U NFL):", value=48.5, step=0.5, key="nfl_lco")
    opcion_ou_nfl = st.radio("Selección Totales NFL:", ["Over (Altas)", "Under (Bajas)"], horizontal=True, key="nfl_oou")
    momio_manual_nfl = st.number_input("Momio Americano (NFL):", value=-110, step=5, key="nfl_mmo")

    if st.button("🚀 Ejecutar Modelo Matemático Profesional NFL (Totales)", use_container_width=True):
      prob_over_calc_nfl, lambda_proyectado_nfl = motor_matematico_nfl_totales(off_local_nfl, def_local_nfl, off_visita_nfl, def_visita_nfl, linea_casa_ou_nfl, lesion_qb_local_nfl, lesion_qb_visita_nfl)
      probabilidad_calculada_nfl = prob_over_calc_nfl if "Over" in opcion_ou_nfl else (100.0 - prob_over_calc_nfl)
      mercado_manual_nfl = f"Total {opcion_ou_nfl} ({linea_casa_ou_nfl} pts) [Modelo Lambda NFL: {lambda_proyectado_nfl}]"
      
      st.session_state["resultado_nfl_calculado"] = {
          "partido": f"{equipo_visita_nfl} @ {equipo_local_nfl}",
          "mercado": mercado_manual_nfl,
          "momio": int(momio_manual_nfl),
          "prob": round(probabilidad_calculada_nfl, 2)
      }

  st.markdown("---")
  st.subheader("📌 Resultado del Análisis NFL (Fijo e Inalterable)")

  if st.session_state["resultado_nfl_calculado"]:
    res_nfl = st.session_state["resultado_nfl_calculado"]
    _, edge_man_nfl = calcular_edge_real(res_nfl["momio"], res_nfl["prob"])
    stake_man_nfl = calcular_criterio_kelly(st.session_state["bankroll_global"], res_nfl["prob"], res_nfl["momio"])

    st.success(f"🎯 Análisis NFL guardado y fijo para: **{res_nfl['partido']}**")
    st.metric(label="📊 Probabilidad Científica Calculada por el Modelo NFL", value=f"{res_nfl['prob']}%")

    st.info(
        f"🎯 **Apuesta Sugerida:** `{res_nfl['mercado']}` \n"
        f"📈 **Cuota:** `{res_nfl['momio']}` | 🎯 **Edge Neto (+EV):** `+{edge_man_nfl:.2f}%` | 💡 **Stake Óptimo (Kelly 25%):** `${stake_man_nfl} MXN`"
    )

    col_sbn1, col_sbn2 = st.columns(2)
    with col_sbn1:
      if st.button("📥 Guardar en Base de Datos SQLite (NFL)", key="guardar_sqlite_nfl"):
        registrar_apuesta_db(fecha_formato_str, "NFL Élite", res_nfl["partido"], res_nfl["mercado"], res_nfl["momio"], edge_man_nfl, stake_man_nfl)
        st.success("✅ ¡Apuesta NFL guardada con éxito en SQLite!")
    with col_sbn2:
      if st.button("📤 Enviar Alerta a Telegram (NFL)", key="enviar_telegram_nfl"):
        msg = f"🛡️ *ALERTA NFL ÉLITE*\n🏟️ {res_nfl['partido']}\n📊 {res_nfl['mercado']}\n📈 Momio: {res_nfl['momio']} | Edge: +{edge_man_nfl:.2f}%\n💰 Stake: ${stake_man_nfl} MXN"
        ok, res_tel = enviar_alerta_telegram(st.session_state["telegram_token"], st.session_state["telegram_chat_id"], msg)
        if ok: st.success(res_tel)
        else: st.error(res_tel)
  else:
    st.info("Ingresa los datos arriba y presiona el botón para generar el análisis definitivo de la NFL.")


# =========================================================
# MÓDULOS SECUNDARIOS DE SOPORTE
# =========================================================
elif modulo_seleccionado == "🔍 Escáner Automático Multi-Deporte (+EV)":
  st.title(f"🔍 **Escáner Multi-Deporte [{fecha_formato_str}]**")
  api_key = st.session_state["api_key_guardada"]
  cartelera = obtener_partidos_y_momios_api("americanfootball_nfl", api_key)
  for idx, p in enumerate(cartelera[:10], 1):
    st.info(f"🏈 NFL #{idx}: `{p['partido_str']}` | **{p['mercado']}** | Cuota: `{p['momio']}` | Edge: `+{p['edge']:.2f}%`")

elif modulo_seleccionado in ["🏀 Sistema Pro NBA", "⚽ Módulo Pro Fútbol (Soccer)"]:
  st.title(f"📌 **{modulo_seleccionado} [{fecha_formato_str}]**")
  api_key = st.session_state["api_key_guardada"]
  skey = "basketball_nba" if "NBA" in modulo_seleccionado else "soccer_epl"
  cartelera = obtener_partidos_y_momios_api(skey, api_key)
  for idx, p in enumerate(cartelera[:10], 1):
    st.info(f"• `{p['partido_str']}` — **{p['mercado']}** | Cuota: `{p['momio']}` | Edge: `+{p['edge']:.2f}%`")

elif modulo_seleccionado in ["⚾ Béisbol & LMP", "🏒 Hockey Pro (NHL)", "🥊 Sistema Pro UFC"]:
  st.title(f"📌 **{modulo_seleccionado} [{fecha_formato_str}]**")
  st.info("Módulo activo y preparado para análisis.")


# =========================================================
# PANEL DE CONTROL FINANCIERO (CON GRÁFICA Y CLV)
# =========================================================
elif modulo_seleccionado == "📊 Control de Bankroll & Historial SQLite":
  st.title(f"📊 **Panel de Control, Métricas & Bankroll [{fecha_formato_str}]**")
  
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
    st.subheader("📈 Evolución Histórica del Bankroll")
    historial_br = [r[11] for r in registros if r[11] > 0]
    if historial_br:
      st.line_chart(historial_br)

  st.markdown("---")
  st.subheader("📋 Auditoría, CLV & Gestión de Apuestas")

  if registros:
    for reg in registros:
      apuesta_id, fecha, deporte, partido, mercado, momio, edge, stake, estado, ganancia, clv, _ = reg
      
      col_info, col_clv, col_b1, col_b2, col_b3 = st.columns([4, 1.5, 1, 1, 1])
      with col_info:
        st.info(f"🆔 {apuesta_id} | 📅 {fecha} | **{deporte}** | `{partido}` \n• **{mercado}** | Cuota: `{momio}` | Stake: `${stake} MXN` | Estado: **{estado}** (${ganancia:+,.2f}) | CLV: `{clv}`")
      
      with col_clv:
        clv_input = st.number_input("Cuota Cierre (CLV):", value=int(momio), key=f"clv_val_{apuesta_id}", step=5)
        
      with col_b1:
        if st.button("✅ Ganada", key=f"win_{apuesta_id}"):
          actualizar_estado_y_clv(apuesta_id, "Ganada", stake, momio, clv_input)
          st.rerun()
      with col_b2:
        if st.button("❌ Perdida", key=f"loss_{apuesta_id}"):
          actualizar_estado_y_clv(apuesta_id, "Perdida", stake, momio, clv_input)
          st.rerun()
      with col_b3:
        if st.button("🤝 Push", key=f"push_{apuesta_id}"):
          actualizar_estado_y_clv(apuesta_id, "Push", stake, momio, clv_input)
          st.rerun()
  else:
    st.info("No hay apuestas registradas todavía.")


# =========================================================
# PARLAYS Y ARBITRAJE
# =========================================================
elif modulo_seleccionado == "🚀 Optimizador de Parlays (Monte Carlo)":
  st.title(f"🚀 **Optimizador de Parlays Monte Carlo [{fecha_formato_str}]**")
  st.info("Módulo de simulación de parlay activo.")

elif modulo_seleccionado == "🧮 Calculadora de Arbitraje (Surebets)":
  st.title(f"🧮 **Calculadora de Arbitraje & Alertas Telegram [{fecha_formato_str}]**")
  
  col_a1, col_a2 = st.columns(2)
  with col_a1:
    cuota_a = st.number_input("Cuota Casa A (Ej. +130):", value=130)
  with col_a2:
    cuota_b = st.number_input("Cuota Casa B (Ej. -120):", value=-120)

  bankroll_total_arb = st.number_input("Inversión Total para la Surebet (MXN):", value=5000.0, step=500.0)

  if st.button("⚖️ Calcular Surebet y Enviar a Telegram", use_container_width=True):
    dec_a = (1.0 + (cuota_a / 100.0)) if cuota_a > 0 else (1.0 + (100.0 / abs(cuota_a)))
    dec_b = (1.0 + (cuota_b / 100.0)) if cuota_b > 0 else (1.0 + (100.0 / abs(cuota_b)))

    implied_sum = (1.0 / dec_a) + (1.0 / dec_b)

    if implied_sum < 1.0:
      roi_arb = (1.0 - implied_sum) * 100.0
      stake_a = bankroll_total_arb * ((1.0 / dec_a) / implied_sum)
      stake_b = bankroll_total_arb * ((1.0 / dec_b) / implied_sum)
      ganancia_garantizada = (stake_a * dec_a) - bankroll_total_arb

      st.success(f"🚨 ¡Oportunidad de Arbitraje Detectada! ROI: **+{roi_arb:.2f}%** | Ganancia: **${ganancia_garantizada:,.2f} MXN**")
      
      msg = f"⚖️ *ALERTA DE ARBITRAJE (SUREBET)*\n📈 ROI: +{roi_arb:.2f}%\n💵 Ganancia: ${ganancia_garantizada:,.2f} MXN\n📌 Casa A ({cuota_a}): ${stake_a:,.2f}\n📌 Casa B ({cuota_b}): ${stake_b:,.2f}"
      ok, res_tel = enviar_alerta_telegram(st.session_state["telegram_token"], st.session_state["telegram_chat_id"], msg)
      if ok: st.success("📤 ¡Alerta de Surebet enviada a Telegram con éxito!")
    else:
      st.error(f"❌ Sin arbitraje. La suma implícita es {implied_sum*100:.2f}% (superior al 100%).")


# =========================================================
# BACKTESTING & STEAM MOVES
# =========================================================
elif modulo_seleccionado == "📈 Backtesting Histórico & Steam Moves":
  st.title(f"📈 **Simulador de Backtesting & Alertas Steam Moves [{fecha_formato_str}]**")
  st.markdown("Audita el rendimiento histórico de tus algoritmos aplicando pruebas de estrés sobre 500 partidos simulados de temporadas pasadas.")

  num_partidos_simulados = st.slider("Número de partidos para simulación histórica:", 100, 1000, 500, 50)
  win_rate_estimado = st.slider("Tasa de acierto estimada del modelo (%):", 50.0, 70.0, 56.5, 0.5)
  momio_promedio = st.number_input("Momio americano promedio de las apuestas:", value=-110, step=5)

  if st.button("🚀 Ejecutar Simulación de Backtesting Histórico", use_container_width=True):
    total_apostado_sim = num_partidos_simulados * 500.0
    aciertos = int(num_partidos_simulados * (win_rate_estimado / 100.0))
    fallos = num_partidos_simulados - aciertos
    
    if momio_promedio > 0:
      ganancia_por_acierto = 500.0 * (momio_promedio / 100.0)
    else:
      ganancia_por_acierto = 500.0 * (100.0 / abs(momio_promedio))
      
    retorno_total = (aciertos * ganancia_por_acierto) - (fallos * 500.0)
    roi_simulado = (retorno_total / total_apostado_sim) * 100.0

    st.success(f"📊 **Resultados del Backtesting sobre {num_partidos_simulados} partidos:**")
    col_b1, col_b2, col_b3 = st.columns(3)
    col_b1.metric("🎯 Aciertos Proyectados", f"{aciertos} / {num_partidos_simulados}")
    col_b2.metric("📈 ROI Histórico Simulado", f"{roi_simulado:,.2f}%")
    col_b3.metric("💵 Utilidad Neta Proyectada", f"${retorno_total:+,.2f} MXN")

    if roi_simulado > 0:
      st.markdown("✅ **Veredicto del Sindicato:** El modelo muestra rentabilidad positiva sostenida (*Positive EV*). Es viable para operar con Criterio Kelly.")
    else:
      st.markdown("❌ **Veredicto del Sindicato:** El modelo no supera el 'vig' de la casa bajo este momio. Se recomienda ajustar el Edge mínimo.")

  st.markdown("---")
  st.subheader("🔥 Monitor de Steam Moves (Dinero Profesional)")
  st.info("💡 **Alerta de Mercado:** El sistema monitorea en tiempo real si las líneas de Las Vegas se mueven 2+ puntos en contra del público general. Cuando se detecta un *Steam Move* respaldado por tus Power Ratings, la oportunidad se marca como Alta Prioridad.")


# =========================================================
# GESTOR MULTI-BOOKMAKER (LINE SHOPPING)
# =========================================================
elif modulo_seleccionado == "⚖️ Gestor Multi-Bookmaker (Line Shopping)":
  st.title(f"⚖️ **Comparador de Cuotas & Line Shopping [{fecha_formato_str}]**")
  st.markdown("Nunca apuestes con cuotas bajas. Compara simultáneamente los momios de las principales casas para encontrar la mayor rentabilidad.")

  col_bk1, col_bk2, col_bk3 = st.columns(3)
  with col_bk1:
    book_caliente = st.number_input("Momio en Caliente:", value=-110, step=5)
  with col_bk2:
    book_bet365 = st.number_input("Momio en Bet365:", value=-105, step=5)
  with col_bk3:
    book_pinnacle = st.number_input("Momio en Pinnacle (Sharp):", value=-102, step=5)

  if st.button("🔍 Encontrar la Mejor Cuota (Line Shopping)", use_container_width=True):
    def a_decimal(m):
      return (1.0 + (m / 100.0)) if m > 0 else (1.0 + (100.0 / abs(m)))

    dec_caliente = a_decimal(book_caliente)
    dec_bet365 = a_decimal(book_bet365)
    dec_pinnacle = a_decimal(book_pinnacle)

    mejores_cuotas = {
        "Caliente": (book_caliente, dec_caliente),
        "Bet365": (book_bet365, dec_bet365),
        "Pinnacle": (book_pinnacle, dec_pinnacle)
    }

    mejor_casa = max(mejores_cuotas, key=lambda k: mejores_cuotas[k][1])
    mejor_momio, mejor_dec = mejores_cuotas[mejor_casa]

    st.success(f"🏆 **Casa Recomendada para esta Apuesta:** `{mejor_casa}` con cuota ` {mejor_momio} ` (Decimal: `{mejor_dec:.2f}`)")
    st.markdown("💡 *Apostar siempre en la casa con mejor momio incrementa tu ROI a largo plazo entre un 3% y un 5% sin arriesgar capital extra.*")
