"""Módulo de Puente y Automatización Universal con Conversión Automática de
Proyecciones a Probabilidad (NFL, NBA, Fútbol, NHL).
"""
import streamlit as st
import math

def calcular_probabilidad_por_margen(proyeccion_modelo, linea_casa, deporte):
    """Convierte la diferencia entre tu modelo y la línea de la casa
    en una probabilidad estimada utilizando una distribución estadística de referencia.
    """
    diferencia = proyeccion_modelo - linea_casa  
    
    if "NFL" in deporte:
        desviacion_std = 13.5
    elif "NBA" in deporte:
        desviacion_std = 11.0
    elif "Fútbol" in deporte:
        desviacion_std = 1.15  
    else:
        desviacion_std = 1.5  
        
    z = diferencia / (desviacion_std * math.sqrt(2))
    probabilidad = 0.5 * (1.0 + math.erf(z)) * 100.0
    
    return max(15.0, min(85.0, round(probabilidad, 2)))

def mostrar_puente_kelly_universal():
    st.header("⚡ Automatización Élite: De Proyección a Criterio Kelly")
    st.caption("Introduce los dos equipos del partido, tus proyecciones y el sistema calculará todo automáticamente.")
    st.markdown("---")
    
    # 1. Selector de Deporte
    deporte_sel = st.selectbox("Selecciona el Deporte:", ["🏈 NFL", "🏀 NBA", "⚽ Fútbol (Soccer)", "🏒 NHL (Hockey)"])
    
    st.subheader("📊 1. Encuentro y Pronóstico")
    
    # ¡Aquí ingresas los dos equipos como sugeriste!
    col_eq1, col_eq2 = st.columns(2)
    with col_eq1:
        equipo_local = st.text_input("Equipo Local:", value="Kansas City Chiefs")
    with col_eq2:
        equipo_visitante = st.text_input("Equipo Visitante:", value="San Francisco 49ers")
        
    # Seleccionas a quién le vas a apostar basándote en los dos equipos
            
    modo_calculo = st.radio(
        "¿Cómo deseas ingresar los datos de tu modelo?",
        ["🧮 Automático (Comparar mi proyección vs. Línea de la casa)", "📊 Directo (Ya tengo el porcentaje de probabilidad)"],
        horizontal=True
    )
    
    col1, col2 = st.columns(2)
    
    with col1:
        mercado_sel = st.selectbox("Mercado a Apostar:", [
            f"Spread / Hándicap: {equipo_local}", 
            f"Spread / Hándicap: {equipo_visitante}", 
            "Total Puntos / Goles (Over / Under)", 
            "Moneyline (Ganador)"
        ])
        
        if "Automático" in modo_calculo:
            proyeccion_modelo = st.number_input("Lo que proyecta tu modelo (Puntos/Goles/Margen):", value=3.5, step=0.5)
            linea_casa = st.number_input("La línea de la casa de apuestas:", value=1.5, step=0.5)
            
            prob_modelo = calcular_probabilidad_por_margen(proyeccion_modelo, linea_casa, deporte_sel)
            st.info(f"🧠 Probabilidad estimada automáticamente para el pick: **{prob_modelo}%**")
        else:
            prob_modelo = st.slider("Probabilidad estimada por tu modelo (%)", min_value=20.0, max_value=95.0, value=56.0, step=0.5)
            
    with col2:
        st.subheader("💰 2. Datos de la Casa de Apuestas")
        momio_casa = st.number_input("Momio Americano (Ej. -110, +135):", value=-110, step=5)
        bankroll = st.number_input("Bankroll Disponible ($ MXN):", value=st.session_state.get("bankroll_global", 15250.0), step=100.0)
        fraccion_kelly = st.slider("Fracción de Criterio Kelly (Riesgo):", min_value=0.1, max_value=1.0, value=0.25, step=0.05)
        
    st.markdown("---")
    st.subheader("🎯 3. Diagnóstico Automático de Valor")
    
    # Cálculos matemáticos
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
    
    st.markdown("---")
    
    if edge > 0:
        st.success(f"✅ **¡Apuesta Viable para {equipo_local} vs {equipo_visitante}!** Ventaja detectada del **{edge:.2f}%** en el mercado de *{mercado_sel}*.")
        
        if st.button("💾 Registrar y Asegurar en el Bankroll (SQLite)", use_container_width=True):
            st.session_state["bankroll_global"] = bankroll
            st.success("¡Pronóstico guardado correctamente en tu control!")
    else:
        st.warning("⚠️ **Precaución:** La línea de la casa no ofrece suficiente ventaja matemática. Se recomienda omitir.")
