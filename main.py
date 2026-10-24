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


# 1. Motor NCAAF
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


# 2. Motor NFL
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


# 3. Motor NBA
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


# 4. Motor Soccer
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


# 5. Motor Hockey Pro (NHL)
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


# 6. Motor Béisbol Pro (MLB / LMP)
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


# 7. Motor UFC / MMA
def motor_matematico_ufc(striking_acc_f1, takedown_def_f1, finish_rate_f1, striking_acc_f2, takedown_def_f2, finish_rate_f2):
  rating_f1 = (striking_acc_f1 * 0.4) + (takedown_def_f1 * 0.3) + (finish_rate_f1 * 0.3)
  rating_f2 = (striking_acc_f2 * 0.4) + (takedown_def_f2 * 0.3) + (finish_rate_f2 * 0.3)
  diferencial = rating_f1 - rating_f2
  z_score = diferencial / 15.0
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
# 1. SISTEMA PRO NCAAF
# =========================================================
if modulo_seleccionado == "🎓 Sistema Pro NCAAF (Universitario)":
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
# 2. SISTEMA PRO NFL
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
# 3. SISTEMA PRO NBA
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
# 4. FÚTBOL SOCCER
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
# 5. HOCKEY PRO (NHL)
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
