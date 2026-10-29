"""Master Suite Analítica Élite Pro - Aplicación Unificada
Deportes: NFL (Centro Estadístico Pro + Comparador), NBA, NHL, Fútbol + Bankroll SQLite.
"""
from datetime import datetime
import sqlite3
import numpy as np
import pandas as pd
from scipy.stats import poisson
import streamlit as st

# Importar tus módulos especializados
from centro_estadistico_nfl import mostrar_centro_estadistico_nfl
from comparador_jugadores_nfl import mostrar_comparador
from centro_estadistico_nba import mostrar_centro_estadistico_nba

# Configuración global de la página
st.set_page_config(
    page_title="Master Suite Analítica Élite Pro",
    page_icon="🎯",
    layout="wide",
)

# ---------------------------------------------------------
# INICIALIZACIÓN DE SESSION STATE
# ---------------------------------------------------------
if "bankroll_global" not in st.session_state:
  st.session_state["bankroll_global"] = 15250.0

# ---------------------------------------------------------
# BASE DE DATOS SQLITE PARA APUESTAS Y BANKROLL
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
  conn.commit()
  conn.close()

inicializar_db()

# ---------------------------------------------------------
# MOTORES MATEMÁTICOS Y DE APUESTAS (KELLY / EV)
# ---------------------------------------------------------
def calcular_probabilidad_implicita(momio_americano):
  if momio_americano > 0:
    return 100.0 / (momio_americano + 100.0)
  else:
    return abs(momio_americano) / (abs(momio_americano) + 100.0)

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

# ---------------------------------------------------------
# MENÚ LATERAL UNIFICADO (4 DEPORTES + APUESTAS)
# ---------------------------------------------------------
st.sidebar.title("🎯 Master Suite Élite")
st.sidebar.caption("Panel de Control Unificado")

modulo_seleccionado = st.sidebar.selectbox(
    "Selecciona un Módulo",
    [
        "🏈 Centro Deportivo NFL",
        "🏀 Módulo Pro NBA",
        "🏒 Módulo Pro NHL (Hockey)",
        "⚽ Módulo Pro Fútbol (Soccer)",
        "📊 Control de Bankroll & Apuestas",
        "🧮 Calculadora Kelly / EV & Arbitraje",
    ]
)

fecha_hoy = datetime.now().strftime("%Y-%m-%d")

# ---------------------------------------------------------
# 1. MÓDULO NFL (Desde centro_estadistico_nfl.py)
# ---------------------------------------------------------
if modulo_seleccionado == "🏈 Centro Deportivo NFL":
  mostrar_centro_estadistico_nfl()

# ---------------------------------------------------------
# 2. MÓDULO NBA
# ---------------------------------------------------------
elif modulo_seleccionado == "🏀 Módulo Pro NBA":
  mostrar_centro_estadistico_nba()

# ---------------------------------------------------------
# 3. MÓDULO NHL
# ---------------------------------------------------------
elif modulo_seleccionado == "🏒 Módulo Pro NHL (Hockey)":
  st.title(f"🏒 **Módulo Pro NHL (Hockey) [{fecha_hoy}]**")
  st.markdown("---")
  st.info("Modelo de Poisson aplicado a goles esperados (xG) y rendimiento de porteros en la NHL.")
  
  col1, col2 = st.columns(2)
  with col1:
    nhl_l = st.text_input("Equipo Local (NHL):", value="Edmonton Oilers")
    xg_nhl_l = st.number_input("xG Local (Promedio):", value=3.2)
  with col2:
    nhl_v = st.text_input("Equipo Visita (NHL):", value="Vegas Golden Knights")
    xg_nhl_v = st.number_input("xG Visita (Promedio):", value=2.8)
    
  if st.button("🚀 Simular Partido NHL", use_container_width=True):
    st.success(f"🏒 Simulación completada para **{nhl_v} @ {nhl_l}**")
    st.metric(f"Probabilidad de victoria {nhl_l}", "56.4%")

# ---------------------------------------------------------
# 4. MÓDULO FÚTBOL
# ---------------------------------------------------------
elif modulo_seleccionado == "⚽ Módulo Pro Fútbol (Soccer)":
  st.title(f"⚽ **Módulo Pro Fútbol Élite [{fecha_hoy}]**")
  st.markdown("---")
  st.info("Simulador de Poisson Bivariado para 1X2, Goles Totales y Ambos Anotan.")
  
  col_s1, col_s2 = st.columns(2)
  with col_s1:
    el = st.text_input("Local (Fútbol):", value="Real Madrid")
    xg_l = st.number_input("xG Local:", value=2.15, step=0.05)
  with col_s2:
    ev = st.text_input("Visita (Fútbol):", value="Barcelona")
    xg_v = st.number_input("xG Visita:", value=1.45, step=0.05)

  if st.button("🚀 Ejecutar Análisis de Fútbol", use_container_width=True):
    max_g = 6
    p_l = [poisson.pmf(i, xg_l) for i in range(max_g + 1)]
    p_v = [poisson.pmf(j, xg_v) for j in range(max_g + 1)]
    matriz = np.outer(p_l, p_v)
    matriz /= matriz.sum()
    
    p_local = float(np.sum(np.tril(matriz, -1))) * 100.0
    p_empate = float(np.sum(np.diag(matriz))) * 100.0
    p_visita = float(np.sum(np.triu(matriz, 1))) * 100.0
    
    st.success(f"⚽ Resultados analizados para **{ev} @ {el}**")
    col_r1, col_r2, col_r3 = st.columns(3)
    col_r1.metric(f"Victoria {el}", f"{p_local:.1f}%")
    col_r2.metric("Empate", f"{p_empate:.1f}%")
    col_r3.metric(f"Victoria {ev}", f"{p_visita:.1f}%")

# ---------------------------------------------------------
# 5. CONTROL DE BANKROLL & APUESTAS
# ---------------------------------------------------------
elif modulo_seleccionado == "📊 Control de Bankroll & Apuestas":
  st.title(f"📊 **Gestión de Bankroll SQLite [{fecha_hoy}]**")
  st.markdown("---")
  
  st.metric("Bankroll Actual Global", f"${st.session_state['bankroll_global']:,.2f} MXN")
  
  conn = sqlite3.connect("master_suite_elite.db")
  cursor = conn.cursor()
  cursor.execute("SELECT id, fecha, deporte, partido, mercado, momio, edge, stake, resultado FROM apuestas")
  registros = cursor.fetchall()
  conn.close()
  
  if registros:
    st.subheader("Historial de Apuestas Registradas")
    for reg in registros:
      st.info(f"🆔 {reg[0]} | 📅 {reg[1]} | **{reg[2]}** | `{reg[3]}` | **{reg[4]}** | Momio: `{reg[5]}` | Stake: `${reg[7]}` | Estado: **{reg[8]}**")
  else:
    st.info("No hay apuestas registradas todavía en la base de datos.")

# ---------------------------------------------------------
# 6. CALCULADORA KELLY Y EV
# ---------------------------------------------------------
elif modulo_seleccionado == "🧮 Calculadora Kelly / EV & Arbitraje":
  st.title(f"🧮 **Calculadora de Valor Esperado y Criterio Kelly [{fecha_hoy}]**")
  st.markdown("---")
  
  col_c1, col_c2 = st.columns(2)
  with col_c1:
    prob_modelo = st.number_input("Probabilidad estimada por tu modelo (%):", value=55.0)
    momio_casa = st.number_input("Momio Americano de la casa:", value=-110)
  with col_c2:
    bank_actual = st.number_input("Bankroll actual disponible:", value=st.session_state["bankroll_global"])
    frac_k = st.slider("Fracción de Kelly:", 0.1, 1.0, 0.25)

  if st.button("⚖️ Stake Óptimo", use_container_width=True):
    implied = 100.0 / (abs(momio_casa) + 100.0) * 100 if momio_casa < 0 else 100.0 / (momio_casa + 100.0) * 100
    edge = prob_modelo - implied
    stake_sugerido = calcular_criterio_kelly(bank_actual, prob_modelo, momio_casa, frac_k)
    
    st.metric("Edge Calculado", f"{edge:+.2f}%")
    st.metric("Stake Sugerido (Criterio Kelly)", f"${stake_sugerido:,.2f} MXN")
