"""Módulo de Puente y Automatización Universal con los 32 equipos de NFL y 30 de NBA, más Historial SQLite."""
import streamlit as st
import math
import sqlite3
from datetime import datetime
import pandas as pd

# Listas completas oficiales por liga
EQUIPOS_POR_DEPORTE = {
    "🏈 NFL": [
        "Arizona Cardinals", "Atlanta Falcons", "Baltimore Ravens", "Buffalo Bills", 
        "Carolina Panthers", "Chicago Bears", "Cincinnati Bengals", "Cleveland Browns", 
        "Dallas Cowboys", "Denver Broncos", "Detroit Lions", "Green Bay Packers", 
        "Houston Texans", "Indianapolis Colts", "Jacksonville Jaguars", "Kansas City Chiefs", 
        "Las Vegas Raiders", "Los Angeles Chargers", "Los Angeles Rams", "Miami Dolphins", 
        "Minnesota Vikings", "New England Patriots", "New Orleans Saints", "New York Giants", 
        "New York Jets", "Philadelphia Eagles", "Pittsburgh Steelers", "San Francisco 49ers", 
        "Seattle Seahawks", "Tampa Bay Buccaneers", "Tennessee Titans", "Washington Commanders"
    ],
    "🏀 NBA": [
        "Atlanta Hawks", "Boston Celtics", "Brooklyn Nets", "Charlotte Hornets", 
        "Chicago Bulls", "Cleveland Cavaliers", "Dallas Mavericks", "Denver Nuggets", 
        "Detroit Pistons", "Golden State Warriors", "Houston Rockets", "Indiana Pacers", 
        "Los Angeles Clippers", "Los Angeles Lakers", "Memphis Grizzlies", "Miami Heat", 
        "Milwaukee Bucks", "Minnesota Timberwolves", "New Orleans Pelicans", "New York Knicks", 
        "Oklahoma City Thunder", "Orlando Magic", "Philadelphia 76ers", "Phoenix Suns", 
        "Portland Trail Blazers", "Sacramento Kings", "San Antonio Spurs", "Toronto Raptors", 
        "Utah Jazz", "Washington Wizards"
    ]
}

def inicializar_base_datos():
    """Crea la base de datos y la tabla de historial si no existen."""
    conexion = sqlite3.connect("apuestas_historial.db")
    cursor = conexion.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS historial (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            deporte TEXT,
            partido TEXT,
            mercado TEXT,
            prob_modelo REAL,
            prob_implicita REAL,
            edge REAL,
            momio INTEGER,
            stake REAL,
            estado TEXT
        )
    """)
    conexion.commit()
    conexion.close()

def guardar_en_sqlite(deporte, partido, mercado, prob_modelo, prob_implicita, edge, momio, stake):
    """Inserta una nueva apuesta registrada en la base de datos."""
    inicializar_base_datos()
    conexion = sqlite3.connect("apuestas_historial.db")
    cursor = conexion.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    cursor.execute("""
        INSERT INTO historial (fecha, deporte, partido, mercado, prob_modelo, prob_implicita, edge, momio, stake, estado)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (fecha_actual, deporte, partido, mercado, prob_modelo, prob_implicita, edge, momio, stake, "Pendiente"))
    
    conexion.commit()
    conexion.close()

def cargar_historial_por_deporte(deporte_filtro):
    """Carga el historial de apuestas filtrado por un deporte específico."""
    inicializar_base_datos()
    conexion = sqlite3.connect("apuestas_historial.db")
    try:
        df = pd.read_sql_query("SELECT * FROM historial WHERE deporte = ? ORDER BY id DESC", conexion, params=(deporte_filtro,))
    except Exception:
        df = pd.DataFrame()
    conexion.close()
    return df

def actualizar_estado_apuesta(apuesta_id, nuevo_estado):
    """Actualiza el estado de una apuesta en la base de datos."""
    conexion = sqlite3.connect("apuestas_historial.db")
    cursor = conexion.cursor()
    cursor.execute("UPDATE historial SET estado = ? WHERE id = ?", (nuevo_estado, apuesta_id))
    conexion.commit()
    conexion.close()

def calcular_probabilidad_por_margen(proyeccion_modelo, linea_casa, deporte):
    diferencia = proyeccion_modelo - linea_casa  
    if "NFL" in deporte:
        desviacion_std = 13.5
    else:  # NBA
        desviacion_std = 11.0
        
    z = diferencia / (desviacion_std * math.sqrt(2))
    probabilidad = 0.5 * (1.0 + math.erf(z)) * 100.0
    return max(15.0, min(85.0, round(probabilidad, 2)))

def mostrar_puente_kelly_universal():
    st.header("⚡ Automatización Élite: De Proyección a Criterio Kelly")
    st.caption("Selecciona tu deporte y despliega las listas completas con todas las franquicias oficiales.")
    st.markdown("---")
    
    pestana_calculadora, pestana_historial = st.tabs(["🧮 Calculadora y Registro", "📂 Historial y Calificación"])
    
    with pestana_calculadora:
        deporte_sel = st.selectbox("Selecciona el Deporte:", ["🏈 NFL", "🏀 NBA"], key="dep_calc")
        
        lista_equipos = EQUIPOS_POR_DEPORTE.get(deporte_sel, [])
        
        st.subheader("📊 1. Encuentro y Pronóstico")
        col_eq1, col_eq2 = st.columns(2)
        with col_eq1:
            equipo_local = st.selectbox("Equipo Local:", lista_equipos, key="eq_local")
        with col_eq2:
            idx_default = 1 if len(lista_equipos) > 1 else 0
            equipo_visitante = st.selectbox("Equipo Visitante:", lista_equipos, index=idx_default, key="eq_vis")
            
        partido_str = f"{equipo_local} vs {equipo_visitante}"
                
        modo_calculo = st.radio(
            "¿Cómo deseas ingresar los datos de tu modelo?",
            ["🧮 Automático (Comparar mi proyección vs. Línea de la casa)", "📊 Directo (Ya tengo el porcentaje de probabilidad)"],
            horizontal=True
        )
        
        col1, col2 = st.columns(2)
        
        with col1:
            mercado_sel = st.selectbox("Mercado a Apostar:", [
                "Total Puntos (Over / Under)", 
                f"Spread / Hándicap: {equipo_local}", 
                f"Spread / Hándicap: {equipo_visitante}", 
                "Moneyline (Ganador)"
            ])
            
            if "Automático" in modo_calculo:
                proyeccion_modelo = st.number_input("Lo que proyecta tu modelo (Puntos totales/Margen):", value=48.5, step=0.5)
                linea_casa = st.number_input("La línea de la casa de apuestas:", value=44.5, step=0.5)
                prob_modelo = calcular_probabilidad_por_margen(proyeccion_modelo, linea_casa, deporte_sel)
                st.info(f"🧠 Probabilidad estimada automáticamente: **{prob_modelo}%**")
            else:
                prob_modelo = st.slider("Probabilidad estimada por tu modelo (%)", min_value=20.0, max_value=95.0, value=56.0, step=0.5)
                
        with col2:
            st.subheader("💰 2. Datos de la Casa de Apuestas")
            momio_casa = st.number_input("Momio Americano (Ej. -110, +135):", value=-110, step=5)
            bankroll = st.number_input("Bankroll Disponible ($ MXN):", value=st.session_state.get("bankroll_global", 15250.0), step=100.0)
            fraccion_kelly = st.slider("Fracción de Criterio Kelly (Riesgo):", min_value=0.1, max_value=1.0, value=0.25, step=0.05)
            
        st.markdown("---")
        st.subheader("🎯 3. Diagnóstico Automático de Valor")
        
        if momio_casa > 0:
            prob_implicita = (100.0 / (momio_casa + 100.0)) * 100.0
            decimal_odds = (momio_casa / 100.0) + 1.0
        else:
            prob_implicita = (abs(momio_casa) / (abs(momio_casa) + 100.0)) * 100.0
            decimal_odds = (100.0 / abs(momio_casa)) + 1.0
            
        edge = prob_modelo - prob_implicita
        p = prob_modelo / 100.0
        q = 1.0 - p
        b = decimal_odds - 1.0
        kelly_full = ((b * p) - q) / b if b > 0 else 0.0
        stake_sugerido = max(10.0, bankroll * kelly_full * fraccion_kelly) if kelly_full > 0 else 0.0
        
        r1, r2, r3, r4 = st.columns(4)
        r1.metric("Probabilidad Modelo", f"{prob_modelo:.1f}%")
        r2.metric("Probabilidad Implícita", f"{prob_implicita:.1f}%")
        
        if edge > 0:
            r3.metric("Edge (Ventaja)", f"{edge:+.2f}%", delta="¡Valor Detectado!")
        else:
            r3.metric("Edge (Ventaja)", f"{edge:+.2f}%", delta="Sin Valor", delta_color="inverse")
            
        r4.metric("Stake Sugerido", f"${stake_sugerido:,.2f} MXN")
        
        st.markdown---()
        
        if edge > 0:
            st.success(f"✅ **¡Apuesta Viable para {partido_str}!** Ventaja detectada del **{edge:.2f}%**.")
            
            if st.button("💾 Registrar y Guardar en Base de Datos SQLite", use_container_width=True):
                guardar_en_sqlite(deporte_sel, partido_str, mercado_sel, prob_modelo, prob_implicita, edge, momio_casa, stake_sugerido)
                st.success(f"¡Pronóstico de {deporte_sel} guardado exitosamente en `apuestas_historial.db`!")
        else:
            st.warning("⚠️ **Precaución:** La línea de la casa no ofrece suficiente ventaja matemática. Se recomienda omitir.")

    with pestana_historial:
        st.subheader("📂 Bitácora de Apuestas y Calificación de Resultados")
        deporte_filtro = st.selectbox("Selecciona el deporte a consultar:", ["🏈 NFL", "🏀 NBA"], key="dep_hist")
        
        df_historial = cargar_historial_por_deporte(deporte_filtro)
        
        if not df_historial.empty:
            st.info(f"Mostrando el historial para: **{deporte_filtro}**.")
            st.dataframe(df_historial, use_container_width=True)
            
            st.markdown("---")
            st.subheader("📝 Calificar Resultado de un Partido")
            
            col_id, col_estado, col_btn = st.columns([1, 2, 1])
            with col_id:
                id_apuesta = st.selectbox("ID de Apuesta:", df_historial["id"].tolist())
            with col_estado:
                nuevo_resultado = st.selectbox("Resultado Real:", ["Pendiente", "Ganada", "Perdida", "Empate / Anulada"])
            with col_btn:
                st.write("") 
                if st.button("Actualizar Estado", use_container_width=True):
                    actualizar_estado_apuesta(id_apuesta, nuevo_resultado)
                    st.success(f"¡Apuesta #{id_apuesta} actualizada a '{nuevo_resultado}'!")
                    st.rerun()
        else:
            st.warning(f"No hay apuestas registradas todavía para {deporte_filtro}.")

