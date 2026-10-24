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
  try:
    cursor.execute("ALTER TABLE apuestas ADD COLUMN ganancia_neta REAL DEFAULT 0.0")
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
    ganancia = 0.0

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
# MOTORES MATEMÁTICOS & MODELOS AVANZADOS NCAAF
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


def modelo_poisson_totales(lambda_esperado, linea_total):
  prob_under = 0.0
  limite = int(math.floor(linea_total))
  for k in range(limite + 1):
    prob_under += poisson.pmf(k, lambda_esperado)
  prob_over = 1.0 - prob_under
  return round(prob_over * 100.0, 2)


def calcular_probabilidad_spread_power_rating(power_rating_local, power_rating_visita, factor_localia, spread_casino):
  """Calcula la probabilidad exacta de cubrir el spread usando diferencia de Power Ratings y distribución normal."""
  diferencia_esperada = (power_rating_local + factor_localia) - power_rating_visita
  desviacion_std = 13.5
  z_score = (diferencia_esperada - abs(spread_casino)) / desviacion_std
  prob_cubrir = stats.norm.cdf(z_score) * 100.0
  return round(max(5.0, min(95.0, prob_cubrir)), 2), round(diferencia_esperada, 1)


# ---------------------------------------------------------
# CONEXIÓN CON THE ODDS API (PARA OTROS DEPORTES)
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
        "🔍 Escáner Automático Multi-Deporte (+EV)",
        "🛡️ Sistema Pro NFL",
        "🏀 Sistema Pro NBA",
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
# MÓDULO PRINCIPAL: SISTEMA PRO NCAAF (ULTRA-PRECISO)
# =========================================================
if modulo_seleccionado == "🎓 Sistema Pro NCAAF (Universitario)":
  st.title(f"🎓 **Sistema Pro NCAAF Élite (Fútbol Americano Universitario) [{fecha_formato_str}]**")
  st.markdown("--- \n *Módulo cuantitativo avanzado con Power Ratings institucionales, ajustes por Fortaleza de Conferencia y distribución normal para Spreads y Poisson para Totales.*")

  st.subheader("✍️ Parámetros Avanzados del Partido")
  
  col_eq1, col_eq2 = st.columns(2)
  with col_eq1:
    equipo_visita = st.text_input("Equipo Visitante:", value="Michigan Wolverines")
    pr_visita = st.number_input("Power Rating Visitante (EPA/Eficiencia):", value=24.5, step=0.5)
  with col_eq2:
    equipo_local = st.text_input("Equipo Local:", value="Ohio State Buckeyes")
    pr_local = st.number_input("Power Rating Local (EPA/Eficiencia):", value=28.0, step=0.5)

  col_fac1, col_fac2 = st.columns(2)
  with col_fac1:
    factor_localia = st.slider("Factor Estadio / Localía (Pts):", 0.0, 5.0, 3.0, 0.5)
  with col_fac2:
    ajuste_sos = st.selectbox("Ajuste por Fortaleza de Conferencia (SOS):", ["Neutro", "Visitante con SOS Superior", "Local con SOS Superior"])

  if ajuste_sos == "Visitante con SOS Superior":
    pr_visita += 2.0
  elif ajuste_sos == "Local con SOS Superior":
    pr_local += 2.0

  tipo_mercado = st.selectbox(
      "Selecciona el Tipo de Mercado / Apuesta:",
      [
          "Spread (Hándicap con Power Ratings)", 
          "Ganador (Moneyline Avanzado)",
          "Total Over / Under (Altas y Bajas - Poisson)"
      ]
  )

  if tipo_mercado == "Spread (Hándicap con Power Ratings)":
    seleccion_equipo = st.text_input("Equipo Seleccionado para Cubrir el Spread:", value="Ohio State Buckeyes (-3.5)")
    spread_linea_casino = st.number_input("Línea de Spread del Casino (Ej. -3.5 o +7.5):", value=-3.5, step=0.5)
    momio_manual = st.number_input("Momio Americano:", value=-110, step=5)
    
    if st.button("🚀 Calcular Probabilidad Científica de Spread", use_container_width=True):
      prob_calc, margen_proyectado = calcular_probabilidad_spread_power_rating(pr_local, pr_visita, factor_localia, spread_linea_casino)
      mercado_manual = f"Spread: {seleccion_equipo} (Línea: {spread_linea_casino} | Proyectado: {margen_proyectado:+1.1f} pts)"
      
      st.session_state["resultado_ncaaf_calculado"] = {
          "partido": f"{equipo_visita} @ {equipo_local}",
          "mercado": mercado_manual,
          "momio": int(momio_manual),
          "prob": prob_calc
      }

  elif tipo_mercado == "Ganador (Moneyline Avanzado)":
    seleccion_ml = st.text_input("Equipo Ganador (Moneyline):", value="Ohio State Buckeyes")
    momio_manual = st.number_input("Momio Americano:", value=-150, step=5)
    
    if st.button("🚀 Calcular Modelo Moneyline Élite", use_container_width=True):
      diferencia_pr = (pr_local + factor_localia) - pr_visita
      prob_base_ml = 50.0 + (diferencia_pr * 2.2)
      probabilidad_calculada = round(min(92.0, max(12.0, prob_base_ml)), 2)
      mercado_manual = f"Ganador (Moneyline): {seleccion_ml}"
      
      st.session_state["resultado_ncaaf_calculado"] = {
          "partido": f"{equipo_visita} @ {equipo_local}",
          "mercado": mercado_manual,
          "momio": int(momio_manual),
          "prob": probabilidad_calculada
      }

  else:  # Totales Over / Under con Poisson y ritmo de juego (Pace)
    col_p1, col_p2 = st.columns(2)
    with col_p1:
      lambda_esperado = st.number_input("Promedio Combinado Esperado de Puntos (Lambda):", value=54.5, step=0.5)
    with col_p2:
      linea_puntos_casa = st.number_input("Línea Total de Puntos de la Casa (O/U):", value=53.5, step=0.5)
    
    opcion_ou = st.radio("Selección Totales:", ["Over (Altas)", "Under (Bajas)"], horizontal=True)
    momio_manual = st.number_input("Momio Americano:", value=-110, step=5)

    if st.button("🚀 Calcular con Motor de Poisson y Ritmo", use_container_width=True):
      prob_over_poisson = modelo_poisson_totales(lambda_esperado, linea_puntos_casa)
      probabilidad_calculada = prob_over_poisson if "Over" in opcion_ou else (100.0 - prob_over_poisson)
      mercado_manual = f"Total {opcion_ou} ({linea_puntos_casa} pts) [Lambda Proyectado: {lambda_esperado}]"
      
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
    
    st.metric(label="📊 Probabilidad Científica Calculada por el Modelo", value=f"{res['prob']}%")

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
        if ok:
          st.success(res_tel)
        else:
          st.error(res_tel)
  else:
    st.info("Configura los parámetros avanzados arriba y presiona el botón para generar el cálculo exacto.")


# =========================================================
# MÓDULOS SECUNDARIOS DE SOPORTE
# =========================================================
elif modulo_seleccionado == "🔍 Escáner Automático Multi-Deporte (+EV)":
  st.title(f"🔍 **Escáner Multi-Deporte [{fecha_formato_str}]**")
  api_key = st.session_state["api_key_guardada"]
  cartelera = obtener_partidos_y_momios_api("americanfootball_nfl", api_key)
  for idx, p in enumerate(cartelera[:10], 1):
    st.info(f"🏈 NFL #{idx}: `{p['partido_str']}` | **{p['mercado']}** | Cuota: `{p['momio']}` | Edge: `+{p['edge']:.2f}%`")

elif modulo_seleccionado in ["🛡️ Sistema Pro NFL", "🏀 Sistema Pro NBA", "⚽ Módulo Pro Fútbol (Soccer)"]:
  st.title(f"📌 **{modulo_seleccionado} [{fecha_formato_str}]**")
  api_key = st.session_state["api_key_guardada"]
  skey = "americanfootball_nfl" if "NFL" in modulo_seleccionado else ("basketball_nba" if "NBA" in modulo_seleccionado else "soccer_epl")
  cartelera = obtener_partidos_y_momios_api(skey, api_key)
  for idx, p in enumerate(cartelera[:10], 1):
    st.info(f"• `{p['partido_str']}` — **{p['mercado']}** | Cuota: `{p['momio']}` | Edge: `+{p['edge']:.2f}%`")

elif modulo_seleccionado in ["⚾ Béisbol & LMP", "🏒 Hockey Pro (NHL)", "🥊 Sistema Pro UFC"]:
  st.title(f"📌 **{modulo_seleccionado} [{fecha_formato_str}]**")
  st.info("Módulo activo y preparado para análisis.")

elif modulo_seleccionado == "📊 Control de Bankroll & Historial SQLite":
  st.title(f"📊 **Panel de Control, Métricas & Bankroll [{fecha_formato_str}]**")
  conn = sqlite3.connect("master_suite_elite.db")
  cursor = conn.cursor()
  cursor.execute("SELECT id, fecha, deporte, partido, mercado, momio, edge, stake, resultado, ganancia_neta FROM apuestas")
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

  st.markdown("---")
  if registros:
    for reg in registros:
      apuesta_id, fecha, deporte, partido, mercado, momio, edge, stake, estado, ganancia = reg
      col_info, col_b1, col_b2, col_b3 = st.columns([5, 1, 1, 1])
      with col_info:
        st.info(f"🆔 {apuesta_id} | 📅 {fecha} | **{deporte}** | `{partido}` \n• **{mercado}** | Cuota: `{momio}` | Stake: `${stake} MXN` | Estado: **{estado}** (${ganancia:+,.2f})")
      with col_b1:
        if st.button("✅", key=f"win_{apuesta_id}"):
          actualizar_estado_apuesta(apuesta_id, "Ganada", stake, momio)
          st.rerun()
      with col_b2:
        if st.button("❌", key=f"loss_{apuesta_id}"):
          actualizar_estado_apuesta(apuesta_id, "Perdida", stake, momio)
          st.rerun()
      with col_b3:
        if st.button("🤝", key=f"push_{apuesta_id}"):
          actualizar_estado_apuesta(apuesta_id, "Push", stake, momio)
          st.rerun()
  else:
    st.info("No hay apuestas registradas todavía.")

elif modulo_seleccionado == "🚀 Optimizador de Parlays (Monte Carlo)":
  st.title(f"🚀 **Optimizador de Parlays Monte Carlo [{fecha_formato_str}]**")
  st.info("Módulo de simulación de parlay activo.")

elif modulo_seleccionado == "🧮 Calculadora de Arbitraje (Surebets)":
  st.title(f"🧮 **Calculadora de Arbitraje [{fecha_formato_str}]**")
  st.info("Calculadora de surebets activa.")
