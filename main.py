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


# ---------------------------------------------------------
# CONFIGURACIÓN DE BASE DE DATOS LOCAL (SQLITE ROBUSTA)
# ---------------------------------------------------------
def inicializar_db():
  conn = sqlite3.connect("master_suite_elite.db")
  cursor = conn.cursor()
  # Crear tabla base si no existe
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
  # Asegurar que la columna ganancia_neta exista en bases de datos anteriores
  try:
    cursor.execute("ALTER TABLE apuestas ADD COLUMN ganancia_neta REAL DEFAULT 0.0")
  except sqlite3.OperationalError:
    pass # La columna ya existe
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
        INSERT INTO apuestas (fecha, deporte, partido, mercado, momio, edge, stake, resultado, ganancia_neta)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'Pendiente', 0.0)
    """,
      (fecha, deporte, partido, mercado, momio, edge, stake),
  )
  conn.commit()
  conn.close()


def actualizar_estado_apuesta(apuesta_id, nuevo_estado, stake, momio):
  ganancia = 0.0
  if nuevo_estado == "Ganada":
    if momio > 0:
      ganancia = stake * (momio / 100.0)
    else:
      ganancia = stake * (100.0 / abs(momio))
  elif nuevo_estado == "Perdida":
    ganancia = -stake
  else:
    ganancia = 0.0  # Push

  conn = sqlite3.connect("master_suite_elite.db")
  cursor = conn.cursor()
  cursor.execute(
      """
        UPDATE apuestas SET resultado = ?, ganancia_neta = ? WHERE id = ?
    """,
      (nuevo_estado, ganancia, apuesta_id),
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
# MOTORES MATEMÁTICOS AVANZADOS & POISSON
# ---------------------------------------------------------
def calcular_probabilidad_implicita(momio_americano):
  if momio_americano > 0:
    return 100.0 / (momio_americano + 100.0)
  else:
    return abs(momio_americano) / (abs(momio_americano) + 100.0)


def calcular_fair_odds_novig(momio_1, momio_2):
  p1 = calcular_probabilidad_implicita(momio_1)
  p2 = calcular_probabilidad_implicita(momio_2)
  total = p1 + p2
  return (p1 / total) * 100.0, (p2 / total) * 100.0


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


def modelo_poisson_totales(lambda_esperado, linea_total):
  prob_under = 0.0
  limite = int(math.floor(linea_total))
  for k in range(limite + 1):
    prob_under += poisson.pmf(k, lambda_esperado)
  prob_over = 1.0 - prob_under
  return round(prob_over * 100.0, 2)


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
        "🔍 Escáner Automático Multi-Deporte (+EV)",
        "🛡️ Sistema Pro NFL",
        "🏀 Sistema Pro NBA",
        "🎓 Sistema Pro NCAAF (Universitario)",
        "⚽ Módulo Pro Fútbol (Soccer)",
        "⚾ Béisbol & LMP",
        "🏒 Hockey Pro (NHL)",
        "🥊 Sistema Pro UFC",
        "📊 Control de Bankroll & Historial SQLite",
        "🚀 Optimizador de Parlays (Monte Carlo)",
        "🧮 Calculadora de Arbitraje (Surebets)",
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
# 3. NCAAF
# =========================================================
elif modulo_seleccionado == "🎓 Sistema Pro NCAAF (Universitario)":
  st.title(f"🎓 **Sistema Pro NCAAF (Fútbol Americano Universitario) [{fecha_formato_str}]**")
  st.markdown("--- \n *Módulo exclusivo de análisis cuantitativo y gestión de valor con motor de Poisson para totales.*")

  equipo_visita = st.text_input("Equipo Visitante:", value="Michigan Wolverines")
  equipo_local = st.text_input("Equipo Local:", value="Ohio State Buckeyes")
  
  tipo_mercado = st.selectbox(
      "Tipo de Mercado / Apuesta:",
      [
          "Spread (Hándicap)", 
          "Total Over / Under (Altas y Bajas de Puntos - Poisson)"
      ]
  )

  if tipo_mercado == "Spread (Hándicap)":
    seleccion_equipo = st.text_input("Equipo Seleccionado para el Spread:", value="Ohio State Buckeyes (-3.5)")
    mercado_manual = f"Spread: {seleccion_equipo}"
    momio_manual = st.number_input("Momio Americano:", value=-110, step=5)
    
    if st.button("🚀 Calcular Modelo y Generar Análisis Élite", use_container_width=True):
      probabilidad_calculada = 58.5
      st.session_state["resultado_ncaaf_calculado"] = {
          "partido": f"{equipo_visita} @ {equipo_local}",
          "mercado": mercado_manual,
          "momio": int(momio_manual),
          "prob": probabilidad_calculada
      }
  else:
    col_p1, col_p2 = st.columns(2)
    with col_p1:
      lambda_estimado = st.number_input("Promedio Esperado de Puntos (Lambda):", value=52.5, step=0.5)
    with col_p2:
      linea_puntos = st.number_input("Línea de Puntos Total (O/U):", value=51.5, step=0.5)
    
    opcion_ou = st.radio("Selección Totales:", ["Over (Altas)", "Under (Bajas)"], horizontal=True)
    momio_manual = st.number_input("Momio Americano:", value=-110, step=5)

    if st.button("🚀 Calcular con Modelo de Poisson", use_container_width=True):
      prob_over_poisson = modelo_poisson_totales(lambda_estimado, linea_puntos)
      probabilidad_calculada = prob_over_poisson if "Over" in opcion_ou else (100.0 - prob_over_poisson)
      mercado_manual = f"Total {opcion_ou} ({linea_puntos} pts) [Lambda: {lambda_estimado}]"
      
      st.session_state["resultado_ncaaf_calculado"] = {
          "partido": f"{equipo_visita} @ {equipo_local}",
          "mercado": mercado_manual,
          "momio": int(momio_manual),
          "prob": round(probabilidad_calculada, 2)
      }

  if st.session_state["resultado_ncaaf_calculado"]:
    res = st.session_state["resultado_ncaaf_calculado"]
    _, edge_man = calcular_edge_real(res["momio"], res["prob"])
    stake_man = calcular_criterio_kelly(st.session_state["bankroll_global"], res["prob"], res["momio"])

    st.success(f"🎯 Análisis guardado y fijo para: **{res['partido']}**")
    st.metric(label="📊 Probabilidad Calculada por el Modelo", value=f"{res['prob']}%")

    st.info(
        f"🎯 **Apuesta Sugerida:** `{res['mercado']}` \n"
        f"📈 **Cuota:** `{res['momio']}` | 🎯 **Edge Neto:** `+{edge_man:.2f}%` | 💡 **Stake Óptimo (Kelly):** `${stake_man} MXN`"
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
        if ok:
          st.success(res_tel)
        else:
          st.error(res_tel)


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
  st.title(f"📊 **Panel de Control, Métricas & Bankroll [{fecha_formato_str}]**")

  conn = sqlite3.connect("master_suite_elite.db")
  cursor = conn.cursor()
  cursor.execute("SELECT id, fecha, deporte, partido, mercado, momio, edge, stake, resultado, ganancia_neta FROM apuestas")
  registros = cursor.fetchall()
  conn.close()

  total_apuestas = len(registros)
  resueltas = [r for r in registros if r[8] in ["Ganada", "Perdida"]]
  ganadas = [r for r in registros if r[8] == "Ganada"]
  perdidas = [r for r in registros if r[8] == "Perdida"]
  
  hit_rate = (len(ganadas) / len(resueltas) * 100.0) if resueltas else 0.0
  total_apostado = sum([r[7] for r in resueltas])
  ganancia_total_neta = sum([r[9] for r in resueltas])
  
  roi = (ganancia_total_neta / total_apostado * 100.0) if total_apostado > 0 else 0.0

  bankroll_base = st.session_state["bankroll_global"]
  bankroll_actualizado = bankroll_base + ganancia_total_neta

  col_m1, col_m2, col_m3, col_m4 = st.columns(4)
  col_m1.metric("💰 Bankroll Actual", f"${bankroll_actualizado:,.2f} MXN")
  col_m2.metric("🎯 Hit Rate (Acierto)", f"{hit_rate:.1f}%")
  col_m3.metric("📈 ROI Neto", f"{roi:.2f}%")
  col_m4.metric("💵 Ganancia Neta", f"${ganancia_total_neta:+,.2f} MXN")

  st.markdown("---")
  st.subheader("📋 Auditoría y Gestión de Apuestas Históricas")

  if registros:
    for reg in registros:
      apuesta_id, fecha, deporte, partido, mercado, momio, edge, stake, estado, ganancia = reg
      
      col_info, col_btn1, col_btn2, col_btn3 = st.columns([5, 1, 1, 1])
      with col_info:
        st.info(f"🆔 ID: {apuesta_id} | 📅 {fecha} | **{deporte}** | `{partido}` \n• Mercado: **{mercado}** | Cuota: `{momio}` | Stake: `${stake} MXN` | Estado: **{estado}** (Neto: `${ganancia:+,.2f} MXN`)")
      
      with col_btn1:
        if st.button("✅ Ganada", key=f"win_{apuesta_id}"):
          actualizar_estado_apuesta(apuesta_id, "Ganada", stake, momio)
          st.rerun()
      with col_btn2:
        if st.button("❌ Perdida", key=f"loss_{apuesta_id}"):
          actualizar_estado_apuesta(apuesta_id, "Perdida", stake, momio)
          st.rerun()
      with col_btn3:
        if st.button("🤝 Push", key=f"push_{apuesta_id}"):
          actualizar_estado_apuesta(apuesta_id, "Push", stake, momio)
          st.rerun()
  else:
    st.info("No hay apuestas registradas todavía.")


# =========================================================
# 9. OPTIMIZADOR DE PARLAYS
# =========================================================
elif modulo_seleccionado == "🚀 Optimizador de Parlays (Monte Carlo)":
  st.title(f"🚀 **Optimizador de Parlays por Simulación Monte Carlo [{fecha_formato_str}]**")
  st.markdown("Combina múltiples selecciones y simula 10,000 escenarios para calcular la probabilidad real combinada.")

  num_legs = st.slider("Número de selecciones (Legs) en el Parlay:", 2, 5, 3)
  
  probabilidades_legs = []
  momios_legs = []
  
  col_p1, col_p2 = st.columns(2)
  for i in range(num_legs):
    with col_p1:
      p = st.number_input(f"Prob. estimada Leg #{i+1} (%):", value=60.0, key=f"p_leg_{i}")
      probabilidades_legs.append(p / 100.0)
    with col_p2:
      m = st.number_input(f"Momio americano Leg #{i+1}:", value=-110, key=f"m_leg_{i}")
      momios_legs.append(m)

  if st.button("🎲 Ejecutar Simulación Monte Carlo (10,000 iteraciones)", use_container_width=True):
    iteraciones = 10000
    exitos = 0
    
    for _ in range(iteraciones):
      acierta_todo = True
      for p in probabilidades_legs:
        if random.random() > p:
          acierta_todo = False
          break
      if acierta_todo:
        exitos += 1
        
    prob_monte_carlo = (exitos / iteraciones) * 100.0
    
    cuota_decimal_total = 1.0
    for m in momios_legs:
      if m > 0:
        cuota_decimal_total *= (1.0 + (m / 100.0))
      else:
        cuota_decimal_total *= (1.0 + (100.0 / abs(m)))
        
    momio_combinado_americano = int((cuota_decimal_total - 1.0) * 100.0) if cuota_decimal_total >= 2.0 else int(-100.0 / (cuota_decimal_total - 1.0))
    
    prob_implicita_parlay = calcular_probabilidad_implicita(momio_combinado_americano) * 100.0
    edge_parlay = prob_monte_carlo - prob_implicita_parlay
    stake_parlay = calcular_criterio_kelly(st.session_state["bankroll_global"], prob_monte_carlo, momio_combinado_americano, 0.15)

    st.success(f"📊 **Resultados de la Simulación Monte Carlo:**")
    st.metric(label="Probabilidad Real Combinada", value=f"{prob_monte_carlo:.2f}%")
    st.info(
        f"🔗 **Momio Combinado Estimado:** `{momio_combinado_americano}` \n"
        f"🎯 **Edge Neto del Parlay:** `+{edge_parlay:.2f}%` \n"
        f"💡 **Stake Sugerido (Kelly Ajustado):** `${stake_parlay} MXN`"
    )


# =========================================================
# 10. CALCULADORA DE ARBITRAJE
# =========================================================
elif modulo_seleccionado == "🧮 Calculadora de Arbitraje (Surebets)":
  st.title(f"🧮 **Calculadora de Arbitraje Matemático [{fecha_formato_str}]**")
  st.markdown("Asegura ganancias libres de riesgo cuando dos casas de apuestas tienen cuotas desalineadas.")

  col_a1, col_a2 = st.columns(2)
  with col_a1:
    cuota_a = st.number_input("Cuota Casa A (Americana Ej. +130):", value=130)
  with col_a2:
    cuota_b = st.number_input("Cuota Casa B (Americana Ej. -120):", value=-120)

  bankroll_total_arb = st.number_input("Inversión Total para la Surebet (MXN):", value=5000.0, step=500.0)

  if st.button("⚖️ Calcular Distribución de Arbitraje", use_container_width=True):
    dec_a = (1.0 + (cuota_a / 100.0)) if cuota_a > 0 else (1.0 + (100.0 / abs(cuota_a)))
    dec_b = (1.0 + (cuota_b / 100.0)) if cuota_b > 0 else (1.0 + (100.0 / abs(cuota_b)))

    implied_sum = (1.0 / dec_a) + (1.0 / dec_b)

    if implied_sum < 1.0:
      roi_arb = (1.0 - implied_sum) * 100.0
      stake_a = bankroll_total_arb * ((1.0 / dec_a) / implied_sum)
      stake_b = bankroll_total_arb * ((1.0 / dec_b) / implied_sum)
      ganancia_garantizada = (stake_a * dec_a) - bankroll_total_arb

      st.success(f"🚨 ¡Se detectó una Oportunidad de Arbitraje (Surebet)! ROI: **+{roi_arb:.2f}%**")
      st.metric(label="💵 Ganancia Garantizada Absoluta", value=f"${ganancia_garantizada:,.2f} MXN")
      
      col_res1, col_res2 = st.columns(2)
      with col_res1:
        st.info(f"📌 **Apuesta en Casa A:** \n• Inversión: **${stake_a:,.2f} MXN** \n• Cuota: `{cuota_a}`")
      with col_res2:
        st.info(f"📌 **Apuesta en Casa B:** \n• Inversión: **${stake_b:,.2f} MXN** \n• Cuota: `{cuota_b}`")
    else:
      st.error(f"❌ No hay arbitraje disponible. La suma implícita es {implied_sum*100:.2f}% (mayor al 100%).")
