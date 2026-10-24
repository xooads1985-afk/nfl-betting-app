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

if "api_key_guardada" not in st.session_state:
  st.session_state["api_key_guardada"] = API_KEY_PREDEFINIDA

if "telegram_token" not in st.session_state:
  st.session_state["telegram_token"] = TELEGRAM_TOKEN_PREDEFINIDO

if "telegram_chat_id" not in st.session_state:
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
# SELECTOR GLOBAL DE FECHA Y MENÚ
# ---------------------------------------------------------
st.sidebar.title("🎯 Menú Principal")

fecha_seleccionada = st.sidebar.date_input(
    "📅 Fecha a Analizar:", value=date.today()
)
fecha_formato_str = fecha_seleccionada.strftime("%Y-%m-%d")

st.sidebar.markdown("---")
modulo_seleccionado = st.sidebar.radio(
    "Selecciona el módulo:",
    [
        "🔍 Escáner Automático Inteligente Multi-Deporte (+EV)",
        "🎓 NCAA (Fútbol Americano Universitario & Hándicap)",
        "📊 Analítica, Control de Bankroll & Registro CLV",
    ],
)


# =========================================================
# 0. ESCÁNER AUTOMÁTICO MULTI-DEPORTE
# =========================================================
if modulo_seleccionado == "🔍 Escáner Automático Inteligente Multi-Deporte (+EV)":
  st.title(f"🔍 **Escáner Multi-Deporte [{fecha_formato_str}]**")
  
  edge_min = st.slider("Filtro de Edge Mínimo (%):", 0.0, 15.0, 3.0, 0.5)

  if st.button("🚀 Ejecutar Escaneo de Mercado", use_container_width=True):
    api_key = st.session_state["api_key_guardada"]
    deportes = [
        ("Fútbol (EPL)", "soccer_epl"),
        ("NBA", "basketball_nba"),
        ("NFL", "americanfootball_nfl"),
        ("NCAAF", "americanfootball_ncaaf")
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
# 7. NCAA (FÚTBOL AMERICANO UNIVERSITARIO - ESCÁNER DIRECTO)
# =========================================================
elif modulo_seleccionado == "🎓 NCAA (Fútbol Americano Universitario & Hándicap)":
  st.title(f"🎓 **Robot NCAAF (Fútbol Americano Universitario) [{fecha_formato_str}]**")
  st.markdown("--- \n *Escáner inteligente de la cartelera colegial conectado a The Odds API.*")

  edge_min_ncaa = st.slider("🎯 Filtro de Edge Mínimo Requerido para NCAAF (%):", 0.0, 15.0, 2.0, 0.5)
  api_key = st.session_state["api_key_guardada"]

  if st.button("🚀 Escanear Mejores Juegos de NCAAF", use_container_width=True):
    with st.spinner("Analizando cartelera masiva de fútbol americano colegial..."):
      cartelera = obtener_partidos_y_momios_api("americanfootball_ncaaf", api_key)
      if cartelera:
        filtrados = [p for p in cartelera if p["edge"] >= edge_min_ncaa]
        st.session_state["ncaaf_picks"] = sorted(filtrados, key=lambda x: x["edge"], reverse=True)
      else:
        st.session_state["ncaaf_picks"] = []

  if "ncaaf_picks" in st.session_state:
    picks_ncaaf = st.session_state["ncaaf_picks"]
    if picks_ncaaf:
      st.success(f"🎯 Se encontraron **{len(picks_ncaaf)}** selecciones con valor en NCAAF.")
      for idx, item in enumerate(picks_ncaaf[:20], 1):
        st.markdown(f"### 🏈 Partido #{idx}: `{item['partido_str']}`")
        st.markdown(f"🎯 **Apuesta Recomendada:** `{item['mercado']}`")
        st.info(f"📈 Cuota: `{item['momio']}` | 🎯 **Edge Neto: `+{item['edge']:.2f}%`** | 💡 **Stake (Kelly): `${item['stake']} MXN`**")

        col1, col2 = st.columns(2)
        with col1:
          if st.button(f"📥 Guardar en SQLite (NCAAF #{idx})", key=f"db_ncaa_{idx}"):
            registrar_apuesta_db(
                fecha_formato_str, "NCAAF", item["partido_str"], item["mercado"], item["momio"], item["edge"], item["stake"]
            )
            st.success("✅ ¡Guardado en base de datos!")
        with col2:
          if st.button(f"📤 Enviar a Telegram (NCAAF #{idx})", key=f"tg_ncaa_{idx}"):
            msg = f"🎓 *NCAAF Pick*\n🏟️ {item['partido_str']}\n📊 Apuesta: {item['mercado']}\n📈 Cuota: {item['momio']} | Edge: +{item['edge']:.2f}%"
            ok, res = enviar_alerta_telegram(st.session_state["telegram_token"], st.session_state["telegram_chat_id"], msg)
            if ok:
              st.success("✅ ¡Enviado!")
            else:
              st.error(res)
        st.markdown("---")
    else:
      st.warning("⚠️ No hay partidos que superen el filtro de Edge actual. Intenta bajar el slider.")
  else:
    st.info("ℹ️ Haz clic en el botón superior para cargar y escanear los mejores juegos de la NCAAF.")


# =========================================================
# 13. BANKROLL Y REGISTRO
# =========================================================
elif modulo_seleccionado == "📊 Analítica, Control de Bankroll & Registro CLV":
  st.title(f"📊 **Panel de Bankroll y Apuestas [{fecha_formato_str}]**")
  
  nuevo_br = st.number_input("Actualizar Bankroll (MXN):", value=st.session_state["bankroll_global"], step=500.0)
  if nuevo_br != st.session_state["bankroll_global"]:
    st.session_state["bankroll_global"] = nuevo_br

  st.markdown("---")
  st.subheader("📋 Historial de Apuestas Guardadas")
  
  conn = sqlite3.connect("master_suite_elite.db")
  cursor = conn.cursor()
  cursor.execute("SELECT id, fecha, deporte, partido, mercado, momio, edge, stake, resultado FROM apuestas")
  registros = cursor.fetchall()
  conn.close()

  if registros:
    for reg in registros:
      st.info(f"🆔 ID: {reg[0]} | 📅 {reg[1]} | Deporte: **{reg[2]}** | Partido: `{reg[3]}` \n• Mercado: **{reg[4]}** | Momio: `{reg[5]}` | Edge: `+{reg[6]:.2f}%` | Stake: `${reg[7]} MXN`")
  else:
    st.info("No hay apuestas registradas todavía.")
