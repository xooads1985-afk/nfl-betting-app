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
# 1. MOTOR PRO UFC / MMA (AVANZADO: EDAD & CAGE RUST)
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
# 2. MOTOR PRO BÉISBOL (MLB / LMP - SABERMETRÍA & FIP)
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
        "🥊 Sistema Pro UFC / MMA",
        "⚾ Béisbol Pro (MLB / LMP)",
        "📊 Control de Bankroll & Historial SQLite",
        "🧮 Calculadora de Arbitraje (Surebets)",
    ],
)


# =========================================================
# 1. INTERFAZ MÓDULO UFC / MMA AVANZADO
# =========================================================
if modulo_seleccionado == "🥊 Sistema Pro UFC / MMA":
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
# 3. CONTROL DE BANKROLL & HISTORIAL SQLITE
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


# =========================================================
# 4. RESTO DE MÓDULOS ACTIVOS
# =========================================================
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
else:
  st.title(f"⚙️ **Módulo en Órbita [{fecha_formato_str}]**")
  st.info("Seleccione un módulo principal en el menú lateral para operar.")
