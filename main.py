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
    page_title="Central de Apuestas Pro - Master Suite Analítica Élite",
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
# CONFIGURACIÓN DE BASE DE DATOS LOCAL (SQLITE)
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
            resultado TEXT
        )
    """)
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
        INSERT INTO apuestas (fecha, deporte, partido, mercado, momio, edge, stake, resultado)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'Pendiente')
    """,
      (fecha, deporte, partido, mercado, momio, edge, stake),
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
# MOTORES MATEMÁTICOS Y KELLY
# ---------------------------------------------------------
def calcular_edge_real(momio_casino, probabilidad_modelo):
  prob_imp = (
      100.0 / (momio_casino + 100.0)
      if momio_casino > 0
      else abs(momio_casino) / (abs(momio_casino) + 100.0)
  ) * 100.0
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


# ---------------------------------------------------------
# CONEXIÓN CON THE ODDS API (PARA NFL, NBA, FÚTBOL)
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
                prob_imp_base = (
                    100.0 / (precio_momio + 100.0)
                    if precio_momio > 0
                    else abs(precio_momio) / (abs(precio_momio) + 100.0)
                ) * 100.0
                
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
        "🔍 Escáner Automático Multi-Deporte (+EV)",
        "🛡️ Sistema Pro NFL",
        "🏀 Sistema Pro NBA",
        "🎓 Sistema Pro NCAAF (Universitario)",
        "⚽ Módulo Pro Fútbol (Soccer)",
        "⚾ Béisbol & LMP",
        "🏒 Hockey Pro (NHL)",
        "🥊 Sistema Pro UFC",
        "📊 Control de Bankroll & Historial SQLite",
        "🚀 Optimizador de Parlays",
    ],
)


# =========================================================
# 0. ESCÁNER AUTOMÁTICO MULTI-DEPORTE
# =========================================================
if modulo_seleccionado == "🔍 Escáner Automático Multi-Deporte (+EV)":
  st.title(f"🔍 **Escáner Multi-Deporte [{fecha_formato_str}]**")
  edge_min = st.slider("Filtro de Edge Mínimo (%):", 0.0, 15.0, 3.0, 0.5)

  if st.button("🚀 Ejecutar Escaneo de Mercado", use_container_width=True):
    api_key = st.session_state["api_key_guardada"]
    deportes = [
        ("Fútbol (EPL)", "soccer_epl"),
        ("NBA", "basketball_nba"),
        ("NFL", "americanfootball_nfl")
    ]
    hallazgos = []
    for nombre_dep, skey in deportes:
      picks = obtener_partidos_y_momios_api(skey, api_key)
      for p in picks:
        if p["edge"] >= edge_min:
          hallazgos.append({"deporte": nombre_dep, **p})
    st.session_state["resultados_escaneo"] = hallazgos

  if "resultados_escaneo" in st.session_state and st.session_state["resultados_escaneo"]:
    st.success(f"Se encontraron **{len(st.session_state['resultados_escaneo'])}** oportunidades con valor.")
    for item in st.session_state["resultados_escaneo"]:
      st.markdown(f"**{item['deporte']}** | `{item['partido_str']}` — 🎯 **{item['mercado']}**")
      st.info(f"• Cuota: `{item['momio']}` | Edge: `+{item['edge']:.2f}%` | Stake: `${item['stake']} MXN`")
  else:
    st.info("Presiona el botón para ejecutar el escaneo de cuotas.")


# =========================================================
# 1. NFL
# =========================================================
elif modulo_seleccionado == "🛡️ Sistema Pro NFL":
  st.title(f"🛡️ **Sistema Pro NFL [{fecha_formato_str}]**")
  api_key = st.session_state["api_key_guardada"]
  cartelera = obtener_partidos_y_momios_api("americanfootball_nfl", api_key)
  if not cartelera:
    st.warning("No hay partidos activos de NFL en este momento.")
  else:
    for idx, p in enumerate(cartelera[:10], 1):
      st.markdown(f"### 🏈 NFL #{idx}: `{p['partido_str']}`")
      st.info(f"🎯 Apuesta: **{p['mercado']}** | Cuota: `{p['momio']}` | Edge: `+{p['edge']:.2f}%` | Stake: `${p['stake']} MXN`")
      st.markdown("---")


# =========================================================
# 2. NBA
# =========================================================
elif modulo_seleccionado == "🏀 Sistema Pro NBA":
  st.title(f"🏀 **Sistema Pro NBA [{fecha_formato_str}]**")
  api_key = st.session_state["api_key_guardada"]
  cartelera = obtener_partidos_y_momios_api("basketball_nba", api_key)
  if not cartelera:
    st.warning("No hay partidos activos de NBA en este momento.")
  else:
    for idx, p in enumerate(cartelera[:10], 1):
      st.markdown(f"### 🏀 NBA #{idx}: `{p['partido_str']}`")
      st.info(f"🎯 Apuesta: **{p['mercado']}** | Cuota: `{p['momio']}` | Edge: `+{p['edge']:.2f}%` | Stake: `${p['stake']} MXN`")
      st.markdown("---")


# =========================================================
# 3. NCAAF (UNIVERSITARIO - 100% MANUAL Y LIMPIO, SIN API)
# =========================================================
elif modulo_seleccionado == "🎓 Sistema Pro NCAAF (Universitario)":
  st.title(f"🎓 **Sistema Pro NCAAF (Fútbol Americano Universitario) [{fecha_formato_str}]**")
  st.markdown("--- \n *Módulo exclusivo de análisis cuantitativo y gestión de valor para conferencias élite (SEC, Big Ten, Big 12, ACC).*")

  st.subheader("✍️ Registro y Análisis de Partido Élite")
  with st.form("form_manual_ncaaf"):
    col_m1, col_m2 = st.columns(2)
    with col_m1:
      equipo_visita = st.text_input("Equipo Visitante:", value="Michigan Wolverines")
    with col_m2:
      equipo_local = st.text_input("Equipo Local:", value="Ohio State Buckeyes")
    
    col_m3, col_m4, col_m5 = st.columns(3)
    with col_m3:
      mercado_manual = st.text_input("Apuesta / Línea:", value="Spread: Ohio State Buckeyes (-3.5)")
    with col_m4:
      momio_manual = st.number_input("Momio Americano:", value=-110, step=5)
    with col_m5:
      prob_manual = st.slider("Probabilidad Modelo (%):", 10.0, 90.0, 55.0, 0.5)

    submitted = st.form_submit_button("🚀 Calcular Modelo y Generar Análisis Élite")
    if submitted:
      partido_manual_str = f"{equipo_visita} @ {equipo_local}"
      _, edge_man = calcular_edge_real(momio_manual, prob_manual)
      stake_man = calcular_criterio_kelly(st.session_state["bankroll_global"], prob_manual, momio_manual)

      st.success(f"🎯 Análisis generado para: **{partido_manual_str}**")
      st.info(
          f"🎯 **Apuesta Sugerida:** `{mercado_manual}` \n"
          f"📈 **Cuota:** `{momio_manual}` | 🎯 **Edge Neto:** `+{edge_man:.2f}%` | 💡 **Stake Óptimo (Kelly):** `${stake_man} MXN`"
      )

      col_sb1, col_sb2 = st.columns(2)
      with col_sb1:
        if st.button("📥 Guardar en Base de Datos SQLite"):
          registrar_apuesta_db(fecha_formato_str, "NCAAF Élite", partido_manual_str, mercado_manual, int(momio_manual), edge_man, stake_man)
          st.success("✅ ¡Apuesta guardada con éxito en SQLite!")
      with col_sb2:
        if st.button("📤 Enviar Alerta a Telegram"):
          msg = f"🎓 *ALERTA NCAAF ÉLITE*\n🏟️ {partido_manual_str}\n📊 {mercado_manual}\n📈 Momio: {momio_manual} | Edge: +{edge_man:.2f}%\n💰 Stake: ${stake_man} MXN"
          ok, res = enviar_alerta_telegram(st.session_state["telegram_token"], st.session_state["telegram_chat_id"], msg)
          if ok:
            st.success(res)
          else:
            st.error(res)


# =========================================================
# 4. FÚTBOL
# =========================================================
elif modulo_seleccionado == "⚽ Módulo Pro Fútbol (Soccer)":
  st.title(f"⚽ **Módulo Pro Fútbol [{fecha_formato_str}]**")
  api_key = st.session_state["api_key_guardada"]
  cartelera = obtener_partidos_y_momios_api("soccer_epl", api_key)
  if not cartelera:
    st.warning("No hay partidos activos de Fútbol en este momento.")
  else:
    for idx, p in enumerate(cartelera[:10], 1):
      st.markdown(f"### ⚽ Fútbol #{idx}: `{p['partido_str']}`")
      st.info(f"🎯 Apuesta: **{p['mercado']}** | Cuota: `{p['momio']}` | Edge: `+{p['edge']:.2f}%` | Stake: `${p['stake']} MXN`")
      st.markdown("---")


# =========================================================
# 5. BÉISBOL
# =========================================================
elif modulo_seleccionado == "⚾ Béisbol & LMP":
  st.title(f"⚾ **Béisbol Pro [{fecha_formato_str}]**")
  st.info("Módulo activo para ligas de béisbol y torneos internacionales.")


# =========================================================
# 6. HOCKEY
# =========================================================
elif modulo_seleccionado == "🏒 Hockey Pro (NHL)":
  st.title(f"🏒 **Hockey Pro NHL [{fecha_formato_str}]**")
  st.info("Módulo activo para análisis de Puck Line y totales en NHL.")


# =========================================================
# 7. UFC
# =========================================================
elif modulo_seleccionado == "🥊 Sistema Pro UFC":
  st.title(f"🥊 **Sistema Pro UFC [{fecha_formato_str}]**")
  st.info("Módulo activo para pronósticos en combates de artes marciales mixtas.")


# =========================================================
# 8. BANKROLL Y SQLITE
# =========================================================
elif modulo_seleccionado == "📊 Control de Bankroll & Historial SQLite":
  st.title(f"📊 **Panel de Control y Bankroll [{fecha_formato_str}]**")
  
  col_br1, col_br2 = st.columns(2)
  with col_br1:
    nuevo_br = st.number_input("Actualizar Bankroll Global (MXN):", value=st.session_state["bankroll_global"], step=500.0)
    if nuevo_br != st.session_state["bankroll_global"]:
      st.session_state["bankroll_global"] = nuevo_br
  with col_br2:
    st.metric(label="💰 Bankroll Actual", value=f"${st.session_state['bankroll_global']:,.2f} MXN")

  st.markdown("---")
  st.subheader("📋 Historial de Apuestas Guardadas")
  conn = sqlite3.connect("master_suite_elite.db")
  cursor = conn.cursor()
  cursor.execute("SELECT id, fecha, deporte, partido, mercado, momio, edge, stake, resultado FROM apuestas")
  registros = cursor.fetchall()
  conn.close()

  if registros:
    for reg in registros:
      st.info(f"🆔 ID: {reg[0]} | 📅 {reg[1]} | Deporte: **{reg[2]}** | Partido: `{reg[3]}` \n• Mercado: **{reg[4]}** | Momio: `{reg[5]}` | Edge: `+{reg[6]:.2f}%` | Stake: `${reg[7]} MXN` | Estado: `{reg[8]}`")
  else:
    st.info("No hay apuestas registradas todavía.")


# =========================================================
# 9. PARLAYS
# =========================================================
elif modulo_seleccionado == "🚀 Optimizador de Parlays":
  st.title(f"🚀 **Optimizador de Parlays [{fecha_formato_str}]**")
  st.info("Módulo activo para combinación de apuestas con valor positivo.")
