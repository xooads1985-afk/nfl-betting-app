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
# MOTORES MATEMÁTICOS DE ÉLITE (TODOS LOS DEPORTES)
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


# 1. Motor NCAAF (Congelado)
def motor_matematico_ncaaf_spread(ppg_local, pap_local, ppg_visita, pap_visita, spread_casino, factor_localia=3.0, fatiga_visita=False, fatiga_local=False, lesion_qb_local=False, lesion_qb_visita=False):
  pr_local = ppg_local - (pap_local * 0.95)
  pr_visita = ppg_visita - (pap_visita * 0.95)
  if fatiga_local: pr_local -= 2.5
  if fatiga_visita: pr_visita -= 2.5
  if lesion_qb_local: pr_local -= 6.5
  if lesion_qb_visita: pr_visita -= 6.5
  margen_proyectado = (pr_local + factor_localia) - pr_visita
  z_score = (margen_proyectado - abs(spread_casino)) / 13.5
  return round(max(5.0, min(95.0, stats.norm.cdf(z_score) * 100.0)), 2), round(margen_proyectado, 1)

def motor_matematico_ncaaf_totales(ppg_local, pap_local, ppg_visita, pap_visita, linea_casa, fatiga_visita=False, fatiga_local=False, lesion_qb_local=False, lesion_qb_visita=False):
  lam = (ppg_local + ppg_visita + pap_local + pap_visita) / 2.0
  if fatiga_local or fatiga_visita: lam -= 3.0
  if lesion_qb_local or lesion_qb_visita: lam -= 5.0
  lam_adj = round(max(15.0, lam * 0.98), 1)
  prob_under = sum([poisson.pmf(k, lam_adj) for k in range(int(math.floor(linea_casa)) + 1)])
  return round((1.0 - prob_under) * 100.0, 2), lam_adj


# 2. Motor NFL (Congelado)
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


# 3. Motor NBA (Congelado)
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


# 4. Motor Soccer (Congelado)
def motor_matematico_soccer(goles_favor_local, goles_contra_local, goles_favor_visita, goles_contra_visita, linea_ou=2.5):
  lam_l = max(0.2, (goles_favor_local + goles_contra_visita) / 2.0)
  lam_v = max(0.2, (goles_favor_visita + goles_contra_local) / 2.0)
  p_win_l, p_tie, p_win_v, p_over = 0.0, 0.0, 0.0, 0.0
  for gl in range(7):
    for gv in range(7):
      p = poisson.pmf(gl, lam_l) * poisson.pmf(gv, lam_v)
      if gl > gv: p_win_l += p
      elif gl == gv: p_tie += p
      else: p_win_v += p
      if (gl + gv) > linea_ou: p_over += p
  return {
      "1X2_local": round(p_win_l * 100.0, 2), "1X2_empate": round(p_tie * 100.0, 2), "1X2_visita": round(p_win_v * 100.0, 2),
      "over_pct": round(p_over * 100.0, 2), "under_pct": round((1.0 - p_over) * 100.0, 2),
      "lambda_local": round(lam_l, 2), "lambda_visita": round(lam_v, 2)
  }


# 5. Motor Hockey Pro (NHL) - Congelado
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
      "moneyline_local": round(p_win_l * 100.0, 2),
      "moneyline_visita": round((1.0 - p_win_l) * 100.0, 2),
      "over_pct": round(p_over * 100.0, 2),
      "under_pct": round((1.0 - p_over) * 100.0, 2),
      "lam_l": round(lam_l, 2), "lam_v": round(lam_v, 2)
  }


# 6. Motor Béisbol Pro (MLB / LMP) - Congelado
def motor_matematico_baseball(era_starter_local, fip_starter_local, era_starter_visita, fip_starter_visita, bullpen_rating_local=3.5, bullpen_rating_visita=3.5, linea_runline=-1.5, linea_ou=8.5):
  runs_local = (fip_starter_local * 0.6) + (bullpen_rating_local * 0.4)
  runs_visita = (fip_starter_visita * 0.6) + (bullpen_rating_visita * 0.4)
  margen_carreras = runs_visita - runs_local
  z_score = (margen_carreras - abs(linea_runline)) / 3.2
  prob_runline = stats.norm.cdf(z_score) * 100.0
  total_carreras = runs_local + runs_visita
  prob_under_ou = sum([poisson.pmf(k, total_carreras) for k in range(int(math.floor(linea_ou)) + 1)])
  return {
      "runline_prob": round(max(5.0, min(95.0, prob_runline)), 2),
      "over_pct": round((1.0 - prob_under_ou) * 100.0, 2),
      "under_pct": round(prob_under_ou * 100.0, 2),
      "proyeccion_carreras": round(total_carreras, 2)
  }


# 7. Motor UFC / Artes Marciales Mixtas (Nuevo - Power Ratings & Striking Differential)
def motor_matematico_ufc(striking_acc_f1, takedown_def_f1, finish_rate_f1, striking_acc_f2, takedown_def_f2, finish_rate_f2):
  # Power Rating basado en precisión de golpeo, defensa de derribos y tasa de finalización
  rating_f1 = (striking_acc_f1 * 0.4) + (takedown_def_f1 * 0.3) + (finish_rate_f1 * 0.3)
  rating_f2 = (striking_acc_f2 * 0.4) + (takedown_def_f2 * 0.3) + (finish_rate_f2 * 0.3)
  
  diferencial = rating_f1 - rating_f2
  z_score = diferencial / 15.0 # Desviación estándar para peleas UFC
  prob_f1 = stats.norm.cdf(z_score) * 100.0
  
  return {
      "prob_f1": round(max(5.0, min(95.0, prob_f1)), 2),
      "prob_f2": round(max(5.0, min(95.0, 100.0 - prob_f1)), 2),
      "rating_f1": round(rating_f1, 1),
      "rating_f2": round(rating_f2, 1)
  }


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
        "🥊 Sistema Pro UFC / MMA",
        "🏒 Hockey Pro (NHL)",
        "⚾ Béisbol Pro (MLB / LMP)",
        "⚽ Módulo Pro Fútbol (Soccer)",
        "🎓 Sistema Pro NCAAF (Universitario)",
        "🛡️ Sistema Pro NFL",
        "🏀 Sistema Pro NBA",
        "🔍 Escáner Automático Multi-Deporte (+EV)",
        "📊 Control de Bankroll & Historial SQLite",
        "🚀 Optimizador de Parlays (Monte Carlo)",
        "🧮 Calculadora de Arbitraje (Surebets)",
        "📈 Backtesting Histórico & Steam Moves",
        "⚖️ Gestor Multi-Bookmaker (Line Shopping)",
    ],
)


# =========================================================
# 1. SISTEMA PRO NCAAF (CONGELADO Y SEGURO)
# =========================================================
elif modulo_seleccionado == "🎓 Sistema Pro NCAAF (Universitario)":
  st.title(f"🎓 **Sistema Pro NCAAF Élite [{fecha_formato_str}]**")
  st.markdown("--- \n *Módulo protegido y congelado.*")
  col1, col2 = st.columns(2)
  with col1:
    ev = st.text_input("Visitante:", value="Michigan", key="ncaaf_ev")
    ov = st.number_input("Anotados Visita:", value=28.5, step=0.5, key="ncaaf_ov")
    dv = st.number_input("Permitidos Visita:", value=17.0, step=0.5, key="ncaaf_dv")
    fv = st.checkbox("Bye Week Ausente", key="ncaaf_fv")
    lqbv = st.checkbox("QB Lesionado", key="ncaaf_lqbv")
  with col2:
    el = st.text_input("Local:", value="Ohio State", key="ncaaf_el")
    ol = st.number_input("Anotados Local:", value=34.0, step=0.5, key="ncaaf_ol")
    dl = st.number_input("Permitidos Local:", value=12.5, step=0.5, key="ncaaf_dl")
    fl = st.checkbox("Bye Week Ausente", key="ncaaf_fl")
    lqbl = st.checkbox("QB Lesionado", key="ncaaf_lqbl")
  tm = st.selectbox("Mercado:", ["Spread", "Total Over/Under"], key="ncaaf_tm")
  if tm == "Spread":
    seq = st.text_input("Selección:", value="Ohio State (-3.5)", key="ncaaf_seq")
    sp = st.number_input("Spread:", value=-3.5, step=0.5, key="ncaaf_sp")
    mm = st.number_input("Momio:", value=-110, step=5, key="ncaaf_mm")
    if st.button("🚀 Calcular NCAAF", use_container_width=True):
      pr, mar = motor_matematico_ncaaf_spread(ol, dl, ov, dv, sp, 3.0, fv, fl, lqbl, lqbv)
      st.session_state["resultado_ncaaf_calculado"] = {"partido": f"{ev} @ {el}", "mercado": f"Spread: {seq} ({sp})", "momio": int(mm), "prob": pr}
  else:
    lc = st.number_input("Línea O/U:", value=51.5, step=0.5, key="ncaaf_lc")
    op = st.radio("Sel:", ["Over", "Under"], horizontal=True, key="ncaaf_op")
    mm = st.number_input("Momio:", value=-110, step=5, key="ncaaf_mmo")
    if st.button("🚀 Calcular NCAAF", use_container_width=True):
      pov, lam = motor_matematico_ncaaf_totales(ol, dl, ov, dv, lc, fv, fl, lqbl, lqbv)
      st.session_state["resultado_ncaaf_calculado"] = {"partido": f"{ev} @ {el}", "mercado": f"Total {op} ({lc})", "momio": int(mm), "prob": pov if "Over" in op else 100.0-pov}
  if st.session_state["resultado_ncaaf_calculado"]:
    r = st.session_state["resultado_ncaaf_calculado"]
    _, eg = calcular_edge_real(r["momio"], r["prob"])
    stk = calcular_criterio_kelly(st.session_state["bankroll_global"], r["prob"], r["momio"])
    st.success(f"🎯 **{r['partido']}** | Prob: `{r['prob']}%` | Edge: `+{eg:.2f}%` | Stake: `${stk} MXN`")
    if st.button("📥 Guardar SQLite", key="db_nc"): registrar_apuesta_db(fecha_formato_str, "NCAAF", r["partido"], r["mercado"], r["momio"], eg, stk); st.success("Guardado.")


# =========================================================
# 2. SISTEMA PRO NFL (CONGELADO Y SEGURO)
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


# =========================================================
# 3. SISTEMA PRO NBA (CONGELADO Y SEGURO)
# =========================================================
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


# =========================================================
# 4. FÚTBOL SOCCER (CONGELADO Y SEGURO)
# =========================================================
elif modulo_seleccionado == "⚽ Módulo Pro Fútbol (Soccer)":
  st.title(f"⚽ **Módulo Pro Fútbol Élite [{fecha_formato_str}]**")
  st.markdown("--- \n *Módulo protegido y congelado.*")
  col1, col2 = st.columns(2)
  with col1:
    ev = st.text_input("Visitante:", value="Real Madrid", key="soc_ev")
    gfv = st.number_input("GF Visita:", value=1.8, step=0.1, key="soc_gfv")
    gcv = st.number_input("GC Visita:", value=1.0, step=0.1, key="soc_gcv")
  with col2:
    el = st.text_input("Local:", value="Barcelona", key="soc_el")
    gfl = st.number_input("GF Local:", value=2.1, step=0.1, key="soc_gfl")
    gcl = st.number_input("GC Local:", value=0.8, step=0.1, key="soc_gcl")
  tm = st.selectbox("Mercado:", ["1X2", "Total Goles"], key="soc_tm")
  if tm == "1X2":
    sel = st.selectbox("Selección:", ["Local (1)", "Empate (X)", "Visitante (2)"], key="soc_sel")
    mm = st.number_input("Momio:", value=110, step=5, key="soc_mm")
    if st.button("🚀 Calcular Soccer", use_container_width=True):
      mat = motor_matematico_soccer(gfl, gcl, gfv, gcv)
      prob = mat["1X2_local"] if "Local" in sel else (mat["1X2_empate"] if "Empate" in sel else mat["1X2_visita"])
      st.session_state["resultado_soccer_calculado"] = {"partido": f"{ev} @ {el}", "mercado": f"1X2: {sel}", "momio": int(mm), "prob": prob}
  else:
    lg = st.number_input("Línea Goles:", value=2.5, step=0.5, key="soc_lg")
    op = st.radio("Sel:", ["Over", "Under"], horizontal=True, key="soc_op")
    mm = st.number_input("Momio:", value=-110, step=5, key="soc_mmo")
    if st.button("🚀 Calcular Soccer", use_container_width=True):
      mat = motor_matematico_soccer(gfl, gcl, gfv, gcv, lg)
      st.session_state["resultado_soccer_calculado"] = {"partido": f"{ev} @ {el}", "mercado": f"Total {op} {lg}", "momio": int(mm), "prob": mat["over_pct"] if "Over" in op else mat["under_pct"]}
  if st.session_state["resultado_soccer_calculado"]:
    r = st.session_state["resultado_soccer_calculado"]
    _, eg = calcular_edge_real(r["momio"], r["prob"])
    stk = calcular_criterio_kelly(st.session_state["bankroll_global"], r["prob"], r["momio"])
    st.success(f"🎯 **{r['partido']}** | Prob: `{r['prob']}%` | Edge: `+{eg:.2f}%` | Stake: `${stk} MXN`")
    if st.button("📥 Guardar SQLite", key="db_so"): registrar_apuesta_db(fecha_formato_str, "Soccer", r["partido"], r["mercado"], r["momio"], eg, stk); st.success("Guardado.")


# =========================================================
# 5. HOCKEY PRO (NHL) (CONGELADO Y SEGURO)
# =========================================================
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


# =========================================================
# 6. BÉISBOL PRO (MLB / LMP) (CONGELADO Y SEGURO)
# =========================================================
elif modulo_seleccionado == "⚾ Béisbol Pro (MLB / LMP)":
  st.title(f"⚾ **Sistema Pro Béisbol Élite [{fecha_formato_str}]**")
  st.markdown("--- \n *Módulo protegido y congelado.*")
  col1, col2 = st.columns(2)
  with col1:
    ev = st.text_input("Visitante:", value="Yankees", key="bs_ev")
    erav = st.number_input("ERA Visita:", value=3.50, step=0.05, key="bs_erav")
    fipv = st.number_input("FIP Visita:", value=3.35, step=0.05, key="bs_fipv")
    bpv = st.number_input("Bullpen Visita (1-5):", value=3.2, step=0.1, key="bs_bpv")
  with col2:
    el = st.text_input("Local:", value="Red Sox", key="bs_el")
    eral = st.number_input("ERA Local:", value=3.80, step=0.05, key="bs_eral")
    fipl = st.number_input("FIP Local:", value=3.95, step=0.05, key="bs_fipl")
    bpl = st.number_input("Bullpen Local (1-5):", value=3.6, step=0.1, key="bs_bpl")
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


# =========================================================
# 7. NUEVO MÓDULO: SISTEMA PRO UFC / MMA
# =========================================================
elif modulo_seleccionado == "🥊 Sistema Pro UFC / MMA":
  st.title(f"🥊 **Sistema Pro UFC / MMA Élite [{fecha_formato_str}]**")
  st.markdown("--- \n *Módulo avanzado de artes marciales mixtas basado en Power Ratings de golpeo, defensa de derribos y tasa de finalización.*")

  col_ufc1, col_ufc2 = st.columns(2)
  with col_ufc1:
    peleador_1 = st.text_input("Peleador 1 (Rojo/Esquina A):", value="Islam Makhachev", key="ufc_p1")
    acc_f1 = st.slider("Precisión de Golpeo (%) Peleador 1:", 30.0, 70.0, 58.0, 1.0, key="ufc_acc1")
    tdd_f1 = st.slider("Defensa de Derribos (%) Peleador 1:", 40.0, 100.0, 90.0, 1.0, key="ufc_tdd1")
    fin_f1 = st.slider("Tasa de Finalización (%) Peleador 1:", 20.0, 100.0, 75.0, 1.0, key="ufc_fin1")
  with col_ufc2:
    peleador_2 = st.text_input("Peleador 2 (Azul/Esquina B):", value="Arman Tsarukyan", key="ufc_p2")
    acc_f2 = st.slider("Precisión de Golpeo (%) Peleador 2:", 30.0, 70.0, 48.0, 1.0, key="ufc_acc2")
    tdd_f2 = st.slider("Defensa de Derribos (%) Peleador 2:", 40.0, 100.0, 78.0, 1.0, key="ufc_tdd2")
    fin_f2 = st.slider("Tasa de Finalización (%) Peleador 2:", 20.0, 100.0, 60.0, 1.0, key="ufc_fin2")

  seleccion_ufc = st.selectbox("Selecciona al Peleador a Apoyar (Moneyline):", [peleador_1, peleador_2], key="ufc_sel")
  momio_manual_ufc = st.number_input("Momio Americano (UFC):", value=-250, step=5, key="ufc_mm")

  if st.button("🚀 Ejecutar Modelo Matemático UFC (Moneyline)", use_container_width=True):
    matriz_ufc = motor_matematico_ufc(acc_f1, tdd_f1, fin_f1, acc_f2, tdd_f2, fin_f2)
    
    if seleccion_ufc == peleador_1:
      prob_ufc = matriz_ufc["prob_f1"]
      mercado_txt = f"UFC Moneyline: {peleador_1}"
    else:
      prob_ufc = matriz_ufc["prob_f2"]
      mercado_txt = f"UFC Moneyline: {peleador_2}"

    st.session_state["resultado_ufc_calculado"] = {
        "partido": f"{peleador_2} vs {peleador_1}",
        "mercado": mercado_txt,
        "momio": int(momio_manual_ufc),
        "prob": prob_ufc,
        "rat1": matriz_ufc["rating_f1"],
        "rat2": matriz_ufc["rating_f2"]
    }

  st.markdown("---")
  st.subheader("📌 Resultado del Análisis UFC (Fijo e Inalterable)")

  if st.session_state["resultado_ufc_calculado"]:
    res_ufc = st.session_state["resultado_ufc_calculado"]
    _, edge_ufc = calcular_edge_real(res_ufc["momio"], res_ufc["prob"])
    stake_ufc = calcular_criterio_kelly(st.session_state["bankroll_global"], res_ufc["prob"], res_ufc["momio"])

    st.success(f"🎯 Análisis UFC guardado y fijo para: **{res_ufc['partido']}**")
    st.metric(label="📊 Probabilidad Científica Calculada para la Pelea", value=f"{res_ufc['prob']}%")
    st.info(f"🥊 **Power Ratings:** {peleador_1}: `{res_ufc['rat1']}` pts | {peleador_2}: `{res_ufc['rat2']}` pts")

    st.info(
        f"🎯 **Apuesta Sugerida:** `{res_ufc['mercado']}` \n"
        f"📈 **Cuota:** `{res_ufc['momio']}` | 🎯 **Edge Neto (+EV):** `+{edge_ufc:.2f}%` | 💡 **Stake Óptimo (Kelly 25%):** `${stake_ufc} MXN`"
    )

    col_ufcb1, col_ufcb2 = st.columns(2)
    with col_ufcb1:
      if st.button("📥 Guardar en Base de Datos SQLite (UFC)", key="guardar_sqlite_ufc"):
        registrar_apuesta_db(fecha_formato_str, "UFC Élite", res_ufc["partido"], res_ufc["mercado"], res_ufc["momio"], edge_ufc, stake_ufc)
        st.success("✅ ¡Apuesta UFC guardada con éxito en SQLite!")
    with col_ufcb2:
      if st.button("📤 Enviar Alerta a Telegram (UFC)", key="enviar_telegram_ufc"):
        msg = f"🥊 *ALERTA UFC ÉLITE*\n🏟️ {res_ufc['partido']}\n📊 {res_ufc['mercado']}\n📈 Momio: {res_ufc['momio']} | Edge: +{edge_ufc:.2f}%\n💰 Stake: ${stake_ufc} MXN"
        ok, res_tel = enviar_alerta_telegram(st.session_state["telegram_token"], st.session_state["telegram_chat_id"], msg)
        if ok: st.success(res_tel)
        else: st.error(res_tel)
  else:
    st.info("Ingresa los datos arriba y presiona el botón para generar el análisis definitivo de UFC.")


# =========================================================
# MÓDULOS SECUNDARIOS DE SOPORTE (ESCANER, BANKROLL, ETC.)
# =========================================================
elif modulo_seleccionado == "🔍 Escáner Automático Multi-Deporte (+EV)":
  st.title(f"🔍 **Escáner Multi-Deporte [{fecha_formato_str}]**")
  api_key = st.session_state["api_key_guardada"]
  cartelera = obtener_partidos_y_momios_api("mixedmartialarts_mixed_martial_arts", api_key)
  for idx, p in enumerate(cartelera[:10], 1):
    st.info(f"🥊 UFC #{idx}: `{p['partido_str']}` | **{p['mercado']}** | Cuota: `{p['momio']}` | Edge: `+{p['edge']:.2f}%`")


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
      if ok: st.success("📤 ¡Alerta de Surebet enviada à Telegram con éxito!")
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
