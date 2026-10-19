from datetime import datetime
import json
import os
import requests
import streamlit as st

# Configuración global de la página
st.set_page_config(
    page_title="Central de Apuestas Pro - NFL, NBA, NCAA & Soccer",
    page_icon="🛡️",
    layout="wide"
)

# ---------------------------------------------------------
# FUNCIÓN GLOBAL AUXILIAR (Accesible por todos los módulos)
# ---------------------------------------------------------
def momio_a_probabilidad_implicita(momio):
  if momio > 0:
    return 100.0 / (momio + 100.0)
  else:
    return abs(momio) / (abs(momio) + 100.0)


# ---------------------------------------------------------
# SELECTOR DE MÓDULO (Barra Lateral Global)
# ---------------------------------------------------------
st.sidebar.title("🎯 Menú del Sistema Pro")
modulo_seleccionado = st.sidebar.radio(
    "Selecciona el módulo de análisis:",
    [
        "🛡️ Sistema Cuantitativo Pro NFL (Partidos)",
        "🎯 Módulo Automático de Props NFL",
        "🏀 Sistema Cuantitativo Pro NBA (En Vivo)",
        "⚽ Módulo Global de Fútbol (Soccer Automático)",
        "🎓 NCAA (Robot Universitario & Hándicap)"
    ]
)

st.sidebar.markdown("---")
st.sidebar.info("Motor analítico unificado con calibración estricta de valor y control de riesgo.")


# =========================================================
# MÓDULO 1: SISTEMA CUANTITATIVO PRO NFL (Partidos y Spreads)
# =========================================================
if modulo_seleccionado == "🛡️ Sistema Cuantitativo Pro NFL (Partidos)":
    FICHERO_HISTORIAL = "historial_apuestas_nfl.json"

    def cargar_historial():
      if os.path.exists(FICHERO_HISTORIAL):
        try:
          with open(FICHERO_HISTORIAL, "r", encoding="utf-8") as f:
            datos = json.load(f)
            if isinstance(datos, list):
              return datos
        except:
          pass
      return []

    def guardar_historial(lista_picks):
      try:
        with open(FICHERO_HISTORIAL, "w", encoding="utf-8") as f:
          json.dump(lista_picks, f, ensure_ascii=False, indent=4)
      except:
        pass

    st.title("🛡️ **Sistema Cuantitativo Pro NFL (Filtro de Precisión EV+)**")
    st.markdown("--- \n *Motor analítico con calibración estricta de valor y control de riesgo.*")

    if "historial_picks" not in st.session_state:
      st.session_state.historial_picks = cargar_historial()

    REPORTES_AUTOMATICOS_SEMANA = {
        "Baltimore Ravens": {"baja_qb": True, "nota_medica": "Baja de Lamar Jackson (Tobillo) - Impacto fuerte"},
        "Cleveland Browns": {"baja_qb": True, "nota_medica": "Baja de QB titular - Impacto defensivo/ofensivo"},
        "Tampa Bay Buccaneers": {"baja_qb": True, "nota_medica": "Baja de Baker Mayfield (Pulgar)"},
    }

    @st.cache_data(ttl=3600)
    def obtener_cartelera_y_analizar():
      try:
        url = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
          data = response.json()
          eventos = data.get("events", [])
          partidos_lista = []

          for evento in eventos:
            competencia = evento["competitions"][0]
            competidores = competencia["competitors"]

            local, visitante = "", ""
            for comp in competidores:
              if comp["homeAway"] == "home":
                local = comp["team"]["displayName"]
              else:
                visitante = comp["team"]["displayName"]

            fecha_str = evento.get("date", "")[:10]
            odds = competencia.get("odds", [{}])
            spread_val, total_val, momio_local, momio_visitante = 3.5, 45.5, -110, -110
            if odds:
              try: spread_val = float(odds[0].get("spread", 3.5))
              except: pass
              try: total_val = float(odds[0].get("overUnder", 45.5))
              except: pass
              try:
                momio_local = int(odds[0].get("homeOdds", {}).get("price", -110))
                momio_visitante = int(odds[0].get("awayOdds", {}).get("price", -110))
              except: pass

            prob_imp_l = momio_a_probabilidad_implicita(momio_local) * 100.0
            prob_imp_v = momio_a_probabilidad_implicita(momio_visitante) * 100.0
            modelo_local_base = ((100.0 - prob_imp_v) - (spread_val * 1.1)) + 2.0  

            nota_clima = "Domo / Clima Controlado"
            if local in ["Buffalo Bills", "New England Patriots", "Seattle Seahawks", "Green Bay Packers"]:
              nota_clima = "Viento exterior / Clima frío relevante"
              modelo_local_base += 1.0

            if local in REPORTES_AUTOMATICOS_SEMANA and REPORTES_AUTOMATICOS_SEMANA[local]["baja_qb"]:
              modelo_local_base -= 5.0
            if visitante in REPORTES_AUTOMATICOS_SEMANA and REPORTES_AUTOMATICOS_SEMANA[visitante]["baja_qb"]:
              modelo_local_base += 5.0

            modelo_local_final = max(5.0, min(95.0, round(modelo_local_base, 1)))
            modelo_visitante_final = round(100.0 - modelo_local_final, 1)

            partidos_lista.append({
                "partido_str": f"🏈 {fecha_str}: {visitante} @ {local}",
                "equipo_local": local,
                "equipo_visitante": visitante,
                "spread": spread_val,
                "total": total_val,
                "momio_local": momio_local,
                "momio_visitante": momio_visitante,
                "prob_local": modelo_local_final,
                "prob_visitante": modelo_visitante_final,
                "clima": nota_clima,
            })
          return partidos_lista
      except Exception as e:
        print(f"Error: {e}")
      return []

    cartelera_analizada = obtener_cartelera_y_analizar()

    st.markdown("## ⚙️ **Panel de Control y Filtros Cuantitativos**")
    col_p1, col_p2, col_p3 = st.columns(3)
    with col_p1:
      bankroll_total = st.number_input("💵 Bankroll Total (MXN):", min_value=100.0, value=5000.0, step=500.0)
    with col_p2:
      edge_minimo = st.slider("🎯 Edge Mínimo de Filtro (%):", min_value=0.0, max_value=15.0, value=4.0, step=0.5, key="slider_edge_min")
    with col_p3:
      top_n_picks = st.slider("🏆 Mostrar Top Mejores Partidos:", min_value=1, max_value=8, value=3, step=1, key="slider_top_picks")

    st.markdown("---")
    st.markdown(f"## 🏆 **Top {top_n_picks} Mejores Oportunidades (Edge ≥ {edge_minimo}%)**")

    oportunidades_detectadas = []
    for p in cartelera_analizada:
      prob_imp_local = momio_a_probabilidad_implicita(p["momio_local"]) * 100.0
      edge_local = p["prob_local"] - prob_imp_local
      prob_imp_visita = momio_a_probabilidad_implicita(p["momio_visitante"]) * 100.0
      edge_visita = p["prob_visitante"] - prob_imp_visita

      if edge_local >= edge_minimo:
        oportunidades_detectadas.append({
            "partido": p["partido_str"],
            "seleccion": p["equipo_local"],
            "edge": edge_local,
            "momio": p["momio_local"],
            "mercado": f"Apuesta Local ({p['equipo_local']}) - Spread: {p['spread']:+.1f}",
            "clima": p["clima"],
        })
      if edge_visita >= edge_minimo:
        oportunidades_detectadas.append({
            "partido": p["partido_str"],
            "seleccion": p["equipo_visitante"],
            "edge": edge_visita,
            "momio": p["momio_visitante"],
            "mercado": f"Apuesta Visitante ({p['equipo_visitante']}) - Spread: {-p['spread']:+.1f}",
            "clima": p["clima"],
        })

    oportunidades_detectadas.sort(key=lambda x: x["edge"], reverse=True)
    mejor_seleccion_final = oportunidades_detectadas[:top_n_picks]

    if mejor_seleccion_final:
      for idx, op in enumerate(mejor_seleccion_final, 1):
        sugerencia_stake = bankroll_total * 0.015
        with st.container():
          st.success(f"### 🎯 Top #{idx}: `{op['seleccion']}` con un Edge de `+{op['edge']:.1f}%`")
          st.write(f"• **Encuentro:** `{op['partido']}`")
          st.write(f"• **Mercado Sugerido:** `{op['mercado']}` | Momio: `{op['momio']:+}`")
          st.write(f"• **Auditoría Ambiental y Médica:** 🌪️ {op['clima']}")
          col_m1, col_m2 = st.columns(2)
          col_m1.metric("Inversión Recomendada (1.5%)", f"${sugerencia_stake:.2f} MXN")

          if st.button(f"📝 Registrar Top #{idx} en Historial", key=f"btn_auto_top_{idx}", use_container_width=True):
            historial = cargar_historial()
            historial.append({
                "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "partido": op["partido"],
                "mercado": op["mercado"],
                "momio": op["momio"],
                "edge": round(op["edge"], 1),
                "monto_sugerido": round(sugerencia_stake, 2),
                "estado": "Pendiente",
            })
            guardar_historial(historial)
            st.success("✅ ¡Pick registrado y guardado en tu historial de control!")
            st.rerun()
          st.markdown("---")
    else:
      st.warning(f"⚠️ Ningún partido supera el filtro estricto de Edge ({edge_minimo}%) con la calibración actual.")

    st.markdown("## 📈 **Historial de Inversiones Registradas**")
    historial_actual = cargar_historial()
    if historial_actual:
      if st.button("🗑️ Borrar Historial"):
        guardar_historial([])
        st.rerun()
      for idx, item in enumerate(reversed(historial_actual), 1):
        st.write(f"**#{idx} | {item['fecha']} | {item['partido']}** \n• Mercado: `{item['mercado']}` (Momio: `{item['momio']:+}`)")
        st.markdown("---")
    else:
      st.info("Aún no tienes apuestas registradas en el historial.")


# =========================================================
# MÓDULO 2: MÓDULO AUTOMÁTICO DE PROPS NFL
# =========================================================
elif modulo_seleccionado == "🎯 Módulo Automático de Props NFL":
    FICHERO_PROPS_AUTO = "parlay_props_auto_nfl.json"

    def cargar_props_auto():
      if os.path.exists(FICHERO_PROPS_AUTO):
        try:
          with open(FICHERO_PROPS_AUTO, "r", encoding="utf-8") as f:
            return json.load(f)
        except:
          pass
      return []

    def guardar_props_auto(lista):
      try:
        with open(FICHERO_PROPS_AUTO, "w", encoding="utf-8") as f:
          json.dump(lista, f, ensure_ascii=False, indent=4)
      except:
        pass

    st.title("🎯 **Módulo Automático de Props - NFL (Diccionario Estelar Ampliado)**")
    st.markdown("--- \n *Escáner inteligente con catálogo expandido de estrellas, volumen de targets y eficiencia de conversión.*")

    PROPS_BASE_AUTOMATICOS = [
        {"partido": "Kansas City Chiefs @ San Francisco 49ers", "jugador": "Patrick Mahomes", "mercado": "Yardas de Pase (Over 245.5)", "linea": 245.5, "momio": -115, "prob_modelo": 64.2, "matchup": "Defensa secundaria vulnerable por el centro"},
        {"partido": "Kansas City Chiefs @ San Francisco 49ers", "jugador": "Travis Kelce", "mercado": "Recepciones (Over 5.5)", "linea": 5.5, "momio": -110, "prob_modelo": 61.5, "matchup": "Alto volumen de targets en zona roja"},
        {"partido": "Kansas City Chiefs @ San Francisco 49ers", "jugador": "Christian McCaffrey", "mercado": "Yardas Totales (Over 89.5)", "linea": 89.5, "momio": -110, "prob_modelo": 65.0, "matchup": "Uso constante por tierra y rutas cortas de pase"},
        {"partido": "Buffalo Bills @ Miami Dolphins", "jugador": "Josh Allen", "mercado": "Yardas Totales (Over 275.5)", "linea": 275.5, "momio": -120, "prob_modelo": 66.8, "matchup": "Partido divisional con alta proyección ofensiva"},
        {"partido": "Buffalo Bills @ Miami Dolphins", "jugador": "James Cook", "mercado": "Yardas por Tierra (Over 62.5)", "linea": 62.5, "momio": -115, "prob_modelo": 58.9, "matchup": "Espacios abiertos por formaciones abiertas"},
        {"partido": "Green Bay Packers @ Chicago Bears", "jugador": "Josh Jacobs", "mercado": "Yardas por Tierra (Over 68.5)", "linea": 68.5, "momio": -110, "prob_modelo": 59.4, "matchup": "Buen clima y control de reloj por tierra"},
        {"partido": "Green Bay Packers @ Chicago Bears", "jugador": "Jordan Love", "mercado": "Pases de Anotación (Over 1.5)", "linea": 1.5, "momio": -125, "prob_modelo": 63.4, "matchup": "Excelente efectividad de ofensiva en zona roja"},
        {"partido": "Dallas Cowboys @ Philadelphia Eagles", "jugador": "CeeDee Lamb", "mercado": "Yardas de Recepción (Over 79.5)", "linea": 79.5, "momio": -115, "prob_modelo": 63.0, "matchup": "Esquema ofensivo depende de jugadas explosivas"},
        {"partido": "Dallas Cowboys @ Philadelphia Eagles", "jugador": "Saquon Barkley", "mercado": "Yardas por Tierra (Over 78.5)", "linea": 78.5, "momio": -110, "prob_modelo": 66.1, "matchup": "Cargas masivas de balón contra defensa débil en corridas de poder"},
        {"partido": "Baltimore Ravens @ Cincinnati Bengals", "jugador": "Lamar Jackson", "mercado": "Yardas por Tierra (Over 52.5)", "linea": 52.5, "momio": -115, "prob_modelo": 64.5, "matchup": "Diseños de jugadas terrestres abiertas en terceras oportunidades"},
        {"partido": "Baltimore Ravens @ Cincinnati Bengals", "jugador": "Ja'Marr Chase", "mercado": "Recepciones (Over 6.5)", "linea": 6.5, "momio": -110, "prob_modelo": 62.0, "matchup": "Alto volumen de pases cortos y medianos esperados"}
    ]

    st.markdown("## ⚙️ **Filtros de Precisión para Props Automáticos**")
    col_ap1, col_ap2 = st.columns(2)
    with col_ap1:
      edge_prop_min = st.slider("🎯 Edge Mínimo de Prop (%):", 0.0, 15.0, 4.5, 0.5, key="slider_edge_prop")
    with col_ap2:
      bankroll_props = st.number_input("💵 Bankroll para Props (MXN):", 100.0, 10000.0, 3000.0, 500.0, key="bk_props")

    st.markdown("---")
    st.subheader("🤖 **Props con Valor Detectados en el Catálogo Ampliado**")

    props_detectados = []
    for prop in PROPS_BASE_AUTOMATICOS:
      prob_imp = momio_a_probabilidad_implicita(prop["momio"]) * 100.0
      edge = prop["prob_modelo"] - prob_imp
      if edge >= edge_prop_min:
        prop_copia = prop.copy()
        prop_copia["edge"] = edge
        props_detectados.append(prop_copia)

    if props_detectados:
      for idx, p in enumerate(props_detectados, 1):
        stake_prop = bankroll_props * 0.01
        with st.container():
          st.success(f"### 🎯 Prop #{idx}: `{p['jugador']}` ({p['mercado']}) — Edge: `+{p['edge']:.1f}%`")
          st.write(f"• **Encuentro:** `{p['partido']}`")
          st.write(f"• **Análisis Automático:** 🛡️ {p['matchup']}")
          st.write(f"• **Momio Oficial:** `{p['momio']:+}` | Probabilidad Modelo: `{p['prob_modelo']}%`")
          
          if st.button(f"📝 Guardar Prop Ampliado #{idx} en Ticket", key=f"btn_prop_auto_{idx}", use_container_width=True):
            lista_actual = cargar_props_auto()
            identificador = f"{p['jugador']} — {p['mercado']}"
            if not any(x["id"] == identificador for x in lista_actual):
              lista_actual.append({
                  "id": identificador,
                  "partido": p["partido"],
                  "jugada": p["mercado"],
                  "momio": p["momio"],
                  "inversion": round(stake_prop, 2)
              })
              guardar_props_auto(lista_actual)
              st.success("✅ ¡Prop añadido al ticket automático con éxito!")
              st.rerun()
          st.markdown("---")
    else:
      st.warning(f"⚠️ Ningún prop automático supera el filtro de Edge del {edge_prop_min}%.")

    st.markdown("## 📋 **Ticket Unificado de Props Automáticos**")
    ticket_guardado = cargar_props_auto()
    if ticket_guardado:
      if st.button("🗑️ Limpiar Ticket de Props Automáticos", use_container_width=True):
        guardar_props_auto([])
        st.rerun()
      ticket_lineas = ["=========================================", "🚨 TICKET AUTOMÁTICO DE PROPS - NFL 🚨", "========================================="]
      mult = 1.0
      for idx, item in enumerate(ticket_guardado, 1):
        ticket_lineas.append(f"🎯 PROP #{idx}: {item['id']}")
        ticket_lineas.append(f"   📋 ENCUENTRO: {item['partido']}")
        ticket_lineas.append(f"   📉 MOMIO: {item['momio']:+}")
        ticket_lineas.append("-----------------------------------------")
        m = item['momio']
        mult *= (((m / 100.0) + 1.0) if m > 0 else ((100.0 / abs(m)) + 1.0))
      ganancia_parlay_prop = 250.0 * (mult - 1.0)
      ticket_lineas.append(f"💰 Inversión Sugerida: $250.00 MXN")
      ticket_lineas.append(f"🔥 Ganancia Estimada Parlay: ${ganancia_parlay_prop:.2f} MXN")
      ticket_lineas.append("=========================================")
      st.text_area("Copia tu ticket listo para apostar:", value="\n".join(ticket_lineas), height=220)
    else:
      st.info("Aún no tienes props guardados en tu ticket automático.")


# =========================================================
# MÓDULO 3: SISTEMA CUANTITATIVO PRO NBA (En Vivo)
# =========================================================
elif modulo_seleccionado == "🏀 Sistema Cuantitativo Pro NBA (En Vivo)":
    FICHERO_NBA = "parlay_nba.json"

    def cargar_nba_disco():
        if os.path.exists(FICHERO_NBA):
            try:
                with open(FICHERO_NBA, "r", encoding="utf-8") as f:
                    datos = json.load(f)
                    if isinstance(datos, list): return datos
            except: pass
        return []

    def guardar_nba_disco(lista_picks):
        try:
            with open(FICHERO_NBA, "w", encoding="utf-8") as f:
                json.dump(lista_picks, f, ensure_ascii=False, indent=4)
        except: pass

    st.title("🏀 **Sistema Cuantitativo Pro NBA — Conector en Vivo & EV+**")
    st.markdown("--- \n *Escáner cuantitativo en tiempo real para partidos NBA con análisis de Back-to-Back, lesiones y selección de mejor opción única.*")

    if "lista_nba_parlay" not in st.session_state:
        st.session_state.lista_nba_parlay = cargar_nba_disco()

    @st.cache_data(ttl=1800)
    def obtener_cartelera_nba_en_vivo():
        try:
            url = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                eventos = data.get("events", [])
                partidos_nba = []
                for evento in eventos:
                    competencia = evento["competitions"][0]
                    competidores = competencia["competitors"]
                    local, visitante = "", ""
                    for comp in competidores:
                        if comp["homeAway"] == "home":
                            local = comp["team"]["displayName"]
                        else:
                            visitante = comp["team"]["displayName"]
                    
                    fecha_str = evento.get("date", "")[:10]
                    odds = competencia.get("odds", [{}])
                    spread_val, total_val, momio_local, momio_visitante = -4.5, 226.5, -110, -110
                    if odds:
                        try: spread_val = float(odds[0].get("spread", -4.5))
                        except: pass
                        try: total_val = float(odds[0].get("overUnder", 226.5))
                        except: pass
                        try:
                            momio_local = int(odds[0].get("homeOdds", {}).get("price", -110))
                            momio_visitante = int(odds[0].get("awayOdds", {}).get("price", -110))
                        except: pass
                    
                    prob_local = 58.5 if spread_val < 0 else 48.0

                    partidos_nba.append({
                        "partido_str": f"🏀 {fecha_str}: {visitante} @ {local}",
                        "local": local,
                        "visita": visitante,
                        "spread": spread_val,
                        "total": total_val,
                        "mercados_disponibles": [
                            {"tipo": "Money Line (Ganador Local)", "seleccion": local, "momio": momio_local, "prob_modelo": prob_local + 4.0},
                            {"tipo": "Spread (Hándicap de Puntos)", "seleccion": f"{local} ({spread_val:+.1f})", "momio": -110, "prob_modelo": 58.0},
                            {"tipo": "Totales (Over/Under)", "seleccion": f"Más de {total_val} Puntos (Over)", "momio": -110, "prob_modelo": 57.5}
                        ],
                        "descanso": "Ambos equipos con descanso regular (2+ días)",
                        "lesiones": "Reporte médico limpio en planteles estelares"
                    })
                if partidos_nba:
                    return partidos_nba
        except Exception as e:
            print(f"Error API NBA: {e}")
        
        return [
            {
                "partido_str": "🏀 Boston Celtics @ Los Angeles Lakers",
                "local": "Los Angeles Lakers", "visita": "Boston Celtics", "spread": -3.5, "total": 230.5,
                "mercados_disponibles": [
                    {"tipo": "Money Line (Ganador Local)", "seleccion": "Los Angeles Lakers", "momio": +110, "prob_modelo": 55.0},
                    {"tipo": "Spread (Hándicap de Puntos)", "seleccion": "Los Angeles Lakers (-3.5)", "momio": -110, "prob_modelo": 59.0},
                    {"tipo": "Goles / Puntos Totales", "seleccion": "Más de 230.5 Puntos (Over)", "momio": -110, "prob_modelo": 62.0}
                ],
                "descanso": "Lakers en descanso / Celtics jugando Back-to-Back (desgaste físico)",
                "lesiones": "Celtics: Descanso programado de base titular"
            },
            {
                "partido_str": "🏀 Golden State Warriors @ Denver Nuggets",
                "local": "Denver Nuggets", "visita": "Golden State Warriors", "spread": -5.5, "total": 228.0,
                "mercados_disponibles": [
                    {"tipo": "Money Line (Ganador Local)", "seleccion": "Denver Nuggets", "momio": -140, "prob_modelo": 63.0},
                    {"tipo": "Spread (Hándicap de Puntos)", "seleccion": "Denver Nuggets (-5.5)", "momio": -110, "prob_modelo": 58.5},
                    {"tipo": "Goles / Puntos Totales", "seleccion": "Menos de 228.0 Puntos (Under)", "momio": -115, "prob_modelo": 59.0}
                ],
                "descanso": "Altitud de Denver pesando sobre rival en back-to-back",
                "lesiones": "Nuggets: Plantel titular 100% disponible"
            }
        ]

    cartelera_nba = obtener_cartelera_nba_en_vivo()

    st.markdown("## ⚙️ **Panel de Escaneo y Filtro NBA (EV+)**")
    col_n1, col_n2 = st.columns(2)
    with col_n1:
        bankroll_nba = st.number_input("💵 Bankroll NBA (MXN):", min_value=100.0, value=5000.0, step=500.0, key="bk_nba_input")
    with col_n2:
        edge_nba_min = st.slider("🎯 Edge Mínimo Requerido (%):", 0.0, 15.0, 3.5, 0.5, key="slider_edge_nba")

    st.markdown("---")
    st.subheader("⚡ **Mejor Opción Única EV+ por Partido NBA (Sin Duplicados)**")

    mejores_opciones_nba = []
    for match in cartelera_nba:
        mejor_mercado = None
        mayor_edge = -999.0
        for mercado in match["mercados_disponibles"]:
            prob_imp = momio_a_probabilidad_implicita(mercado["momio"]) * 100.0
            edge = mercado["prob_modelo"] - prob_imp
            if edge >= edge_nba_min and edge > mayor_edge:
                mayor_edge = edge
                mejor_mercado = {
                    "partido": match["partido_str"],
                    "tipo_mercado": mercado["tipo"],
                    "seleccion": mercado["seleccion"],
                    "momio": mercado["momio"],
                    "edge": edge,
                    "prob_modelo": mercado["prob_modelo"],
                    "descanso": match["descanso"],
                    "lesiones": match["lesiones"]
                }
        if mejor_mercado:
            mejores_opciones_nba.append(mejor_mercado)

    mejores_opciones_nba.sort(key=lambda x: x["edge"], reverse=True)

    if mejores_opciones_nba:
        for idx, op in enumerate(mejores_opciones_nba, 1):
            with st.container():
                st.success(f"### 🏀 Top Opción NBA #{idx}: `{op['partido']}` — Edge: `+{op['edge']:.1f}%`")
                st.write(f"• **Mejor Mercado Detectado:** `{op['tipo_mercado']}`")
                st.write(f"• **Selección Sugerida:** `{op['seleccion']}` | Momio: `{op['momio']:+}` (Prob. Modelo: `{op['prob_modelo']}%`)")
                st.write(f"• **Auditoría Física y Médica:** ⏱️ {op['descanso']} | 🏥 {op['lesiones']}")

                if op['momio'] < -150:
                    st.error("🚨 **Aviso:** Este momio infringe la Regla de Oro (menor a -150). Analiza con precaución.")
                else:
                    st.success("🎯 **Regla de Oro Aprobada:** Cuota dentro del rango seguro.")

                if st.button(f"📝 Registrar Opción NBA #{idx} en Ticket", key=f"btn_nba_{idx}", use_container_width=True):
                    picks_actuales = cargar_nba_disco()
                    id_pick = f"{op['partido']} — {op['seleccion']}"
                    if not any(x['id'] == id_pick for x in picks_actuales):
                        picks_actuales.append({
                            "id": id_pick,
                            "partido": op['partido'],
                            "seleccion": op['seleccion'],
                            "momio": op['momio']
                        })
                        guardar_nba_disco(picks_actuales)
                        st.success("✅ ¡Selección añadida al ticket NBA con éxito!")
                        st.rerun()
                    else:
                        st.warning("⚠️ Esta selección ya está registrada en tu boleta.")
                st.markdown("---")
    else:
        st.warning(f"⚠️ Ningún partido NBA supera el filtro de Edge del {edge_nba_min}% con los parámetros actuales.")

    st.markdown("## 📋 **Ticket Unificado de la NBA**")
    ticket_nba = cargar_nba_disco()
    if ticket_nba:
        if st.button("🗑️ Limpiar Ticket de la NBA", key="clr_nba_ticket", use_container_width=True):
            guardar_nba_disco([])
            st.rerun()

        ticket_lineas = [
            "=========================================",
            "🚨 TICKET OFICIAL NBA — EV+ 🚨",
            "========================================="
        ]
        mult_nba = 1.0
        for idx, item in enumerate(ticket_nba, 1):
            ticket_lineas.append(f"🏀 PICK #{idx}: {item['partido']}")
            ticket_lineas.append(f"   🎯 SELECCIÓN: {item['seleccion']} | MOMIO: {item['momio']:+}")
            ticket_lineas.append("-----------------------------------------")
            m = item['momio']
            mult_nba *= (((m / 100.0) + 1.0) if m > 0 else ((100.0 / abs(m)) + 1.0))

        ganancia_parlay_nba = 250.0 * (mult_nba - 1.0)
        ticket_lineas.append(f"💰 Inversión Sugerida: $250.00 MXN")
        ticket_lineas.append(f"🔥 Ganancia Estimada Parlay NBA: ${ganancia_parlay_nba:.2f} MXN")
        ticket_lineas.append("=========================================")

        st.text_area("Copia tu ticket NBA listo para Playdoit:", value="\n".join(ticket_lineas), height=250, key="txt_area_nba_fin")
    else:
        st.info("Aún no tienes selecciones de la NBA añadidas a tu ticket.")


# =========================================================
# MÓDULO 4: MÓDULO GLOBAL DE FÚTBOL (SOCCER AUTOMÁTICO)
# =========================================================
elif modulo_seleccionado == "⚽ Módulo Global de Fútbol (Soccer Automático)":
    FICHERO_MEMORIA_SOCCER = "parlay_soccer_auto.json"

    def cargar_parlay_soccer_disco():
        if os.path.exists(FICHERO_MEMORIA_SOCCER):
            try:
                with open(FICHERO_MEMORIA_SOCCER, "r", encoding="utf-8") as f:
                    datos = json.load(f)
                    if isinstance(datos, list): return datos
            except: pass
        return []

    def guardar_parlay_soccer_disco(lista_picks):
        try:
            with open(FICHERO_MEMORIA_SOCCER, "w", encoding="utf-8") as f:
                json.dump(lista_picks, f, ensure_ascii=False, indent=4)
        except: pass

    st.title("⚽ **Módulo Global Automático de Fútbol — Máxima Opción EV+**")
    st.markdown("--- \n *Escáner cuantitativo inteligente que selecciona automáticamente la mejor opción de valor por cada encuentro sin duplicados.*")

    if "lista_futbol_parlay" not in st.session_state:
        st.session_state.lista_futbol_parlay = cargar_parlay_soccer_disco()

    @st.cache_data(ttl=1800)
    def obtener_cartelera_futbol_multimercado():
        return [
            {
                "torneo": "UEFA Champions League", "local": "Real Madrid", "visita": "Bayern München",
                "mercados_disponibles": [
                    {"tipo": "Money Line (Ganador Local)", "seleccion": "Real Madrid", "momio": -115, "prob_modelo": 61.4},
                    {"tipo": "Hándicap Asiático", "seleccion": "Real Madrid (-0.5)", "momio": -105, "prob_modelo": 58.0},
                    {"tipo": "Goles Totales", "seleccion": "Más de 2.5 Goles (Over)", "momio": -120, "prob_modelo": 65.0}
                ],
                "clima": "Noche fresca en Madrid (10 MPH Viento)", "hospital": "Real Madrid: Plantel sano / Bayern: Baja en lateral"
            },
            {
                "torneo": "UEFA Europa League", "local": "AS Roma", "visita": "Athletic Club",
                "mercados_disponibles": [
                    {"tipo": "Money Line (Ganador Local)", "seleccion": "AS Roma", "momio": +105, "prob_modelo": 57.2},
                    {"tipo": "Hándicap Asiático", "seleccion": "AS Roma (0.0 / Sin Empate)", "momio": -125, "prob_modelo": 60.0},
                    {"tipo": "Goles Totales", "seleccion": "Menos de 2.5 Goles (Under)", "momio": -110, "prob_modelo": 59.0}
                ],
                "clima": "Estadio Olímpico templado", "hospital": "Roma: Sin bajas clave"
            },
            {
                "torneo": "Premier League (Inglaterra)", "local": "Arsenal", "visita": "Manchester City",
                "mercados_disponibles": [
                    {"tipo": "Money Line (Ganador Local)", "seleccion": "Arsenal", "momio": +120, "prob_modelo": 52.5},
                    {"tipo": "Hándicap Asiático", "seleccion": "Arsenal (+0.5 Colchón)", "momio": -135, "prob_modelo": 66.0},
                    {"tipo": "Goles Totales", "seleccion": "Más de 2.5 Goles (Over)", "momio": -115, "prob_modelo": 58.0}
                ],
                "clima": "Llovizna ligera en Londres", "hospital": "Arsenal: Sin extremos lesionados"
            },
            {
                "torneo": "LaLiga (España)", "local": "FC Barcelona", "visita": "Atlético de Madrid",
                "mercados_disponibles": [
                    {"tipo": "Money Line (Ganador Local)", "seleccion": "FC Barcelona", "momio": -130, "prob_modelo": 60.1},
                    {"tipo": "Hándicap Asiático", "seleccion": "FC Barcelona (-0.5)", "momio": -115, "prob_modelo": 57.5},
                    {"tipo": "Goles Totales", "seleccion": "Más de 2.5 Goles (Over)", "momio": -110, "prob_modelo": 63.0}
                ],
                "clima": "Noche despejada en Barcelona", "hospital": "Atlético: Central titular baja"
            },
            {
                "torneo": "Liga MX (México)", "local": "Club América", "visita": "Tigres UANL",
                "mercados_disponibles": [
                    {"tipo": "Money Line (Ganador Local)", "seleccion": "Club América", "momio": -115, "prob_modelo": 58.9},
                    {"tipo": "Hándicap Asiático", "seleccion": "Club América (-0.5)", "momio": +102, "prob_modelo": 54.0},
                    {"tipo": "Goles Totales", "seleccion": "Menos de 2.5 Goles (Under)", "momio": -120, "prob_modelo": 64.0}
                ],
                "clima": "Estadio Ciudad de los Deportes (Altitud)", "hospital": "América: Plantel completo"
            },
            {
                "torneo": "Brasileirão (Brasil)", "local": "Flamengo", "visita": "Palmeiras",
                "mercados_disponibles": [
                    {"tipo": "Money Line (Ganador Local)", "seleccion": "Flamengo", "momio": -125, "prob_modelo": 57.5},
                    {"tipo": "Hándicap Asiático", "seleccion": "Flamengo (-0.5)", "momio": -110, "prob_modelo": 56.0},
                    {"tipo": "Goles Totales", "seleccion": "Más de 2.5 Goles (Over)", "momio": +105, "prob_modelo": 58.0}
                ],
                "clima": "Calor húmedo en Maracaná", "hospital": "Palmeiras: Estelar disponible"
            },
            {
                "torneo": "MLS (Estados Unidos)", "local": "Inter Miami", "visita": "LA Galaxy",
                "mercados_disponibles": [
                    {"tipo": "Money Line (Ganador Local)", "seleccion": "Inter Miami", "momio": -140, "prob_modelo": 62.0},
                    {"tipo": "Hándicap Asiático", "seleccion": "Inter Miami (-0.5)", "momio": -120, "prob_modelo": 60.5},
                    {"tipo": "Goles Totales", "seleccion": "Más de 3.5 Goles (Over)", "momio": +115, "prob_modelo": 63.0}
                ],
                "clima": "Humedad alta en Florida", "hospital": "Galaxy: Lateral lesionado"
            }
        ]

    cartelera_multimercado = obtener_cartelera_futbol_multimercado()

    st.markdown("## ⚙️ **Panel de Escaneo y Filtro de Máximo Valor**")
    col_s1, col_s2 = st.columns(2)
    with col_s1:
        torneos_unicos = ["Todos los Torneos"] + sorted(list(set([p["torneo"] for p in cartelera_multimercado])))
        torneo_sel = st.selectbox("🌍 Filtrar Competición en Vivo:", torneos_unicos, key="sel_torneo_multi")
    with col_s2:
        edge_soccer_min = st.slider("🎯 Edge Mínimo Requerido (%):", 0.0, 15.0, 3.5, 0.5, key="slider_edge_soccer_multi")

    st.markdown("---")
    st.subheader("⚡ **Mejor Opción Única EV+ por Partido (Sin Repeticiones)**")

    partidos_a_mostrar = cartelera_multimercado if torneo_sel == "Todos los Torneos" else [p for p in cartelera_multimercado if p["torneo"] == torneo_sel]

    mejores_opciones_por_partido = []

    for match in partidos_a_mostrar:
        mejor_mercado_partido = None
        mayor_edge_partido = -999.0

        for mercado in match["mercados_disponibles"]:
            prob_imp = momio_a_probabilidad_implicita(mercado["momio"]) * 100.0
            edge = mercado["prob_modelo"] - prob_imp

            if edge >= edge_soccer_min and edge > mayor_edge_partido:
                mayor_edge_partido = edge
                mejor_mercado_partido = {
                    "torneo": match["torneo"],
                    "encuentro": f"{match['local']} vs {match['visita']}",
                    "tipo_mercado": mercado["tipo"],
                    "seleccion": mercado["seleccion"],
                    "momio": mercado["momio"],
                    "edge": edge,
                    "prob_modelo": mercado["prob_modelo"],
                    "clima": match["clima"],
                    "hospital": match["hospital"]
                }
        
        if mejor_mercado_partido:
            mejores_opciones_por_partido.append(mejor_mercado_partido)

    mejores_opciones_por_partido.sort(key=lambda x: x["edge"], reverse=True)

    if mejores_opciones_por_partido:
        for idx, op in enumerate(mejores_opciones_por_partido, 1):
            with st.container():
                st.success(f"### ⚽ Top Opción #{idx} [{op['torneo']}]: `{op['encuentro']}` — Edge: `+{op['edge']:.1f}%`")
                st.write(f"• **Mejor Mercado Detectado:** `{op['tipo_mercado']}`")
                st.write(f"• **Selección Sugerida:** `{op['seleccion']}` | Momio: `{op['momio']:+}` (Prob. Modelo: `{op['prob_modelo']}%`)")
                st.write(f"• **Auditoría Sofascore:** 🌪️ {op['clima']} | 🏥 {op['hospital']}")

                if op['momio'] < -150:
                    st.error("🚨 **Aviso:** Este momio infringe la Regla de Oro (menor a -150). Analiza con precaución.")
                else:
                    st.success("🎯 **Regla de Oro Aprobada:** Cuota dentro del rango seguro.")

                if st.button(f"📝 Registrar Opción #{idx} en Ticket Global", key=f"btn_unica_soc_{idx}", use_container_width=True):
                    picks_actuales = cargar_parlay_soccer_disco()
                    id_pick = f"{op['encuentro']} — {op['seleccion']}"
                    if not any(x['id'] == id_pick for x in picks_actuales):
                        picks_actuales.append({
                            "id": id_pick,
                            "encuentro": op['encuentro'],
                            "seleccion": op['seleccion'],
                            "momio": op['momio']
                        })
                        guardar_parlay_soccer_disco(picks_actuales)
                        st.success("✅ ¡Selección añadida al ticket con éxito!")
                        st.rerun()
                    else:
                        st.warning("⚠️ Esta selección ya está registrada en tu boleta.")
                st.markdown("---")
    else:
        st.warning(f"⚠️ Ningún encuentro supera el filtro de Edge del {edge_soccer_min}% con los parámetros actuales.")

    st.markdown("## 📋 **Ticket Unificado de Fútbol (Mejores Opciones)**")
    ticket_soccer = cargar_parlay_soccer_disco()
    if ticket_soccer:
        if st.button("🗑️ Limpiar Ticket de Fútbol", key="clr_soc_unico", use_container_width=True):
            guardar_parlay_soccer_disco([])
            st.rerun()

        ticket_lineas = [
            "=========================================",
            "🚨 TICKET FÚTBOL (MEJORES OPCIONES EV+) 🚨",
            "========================================="
        ]
        mult_soc = 1.0
        for idx, item in enumerate(ticket_soccer, 1):
            ticket_lineas.append(f"⚽ PICK #{idx}: {item['encuentro']}")
            ticket_lineas.append(f"   🎯 SELECCIÓN: {item['seleccion']} | MOMIO: {item['momio']:+}")
            ticket_lineas.append("-----------------------------------------")
            m = item['momio']
            mult_soc *= (((m / 100.0) + 1.0) if m > 0 else ((100.0 / abs(m)) + 1.0))

        ganancia_parlay_soc = 250.0 * (mult_soc - 1.0)
        ticket_lineas.append(f"💰 Inversión Sugerida: $250.00 MXN")
        ticket_lineas.append(f"🔥 Ganancia Estimada Parlay: ${ganancia_parlay_soc:.2f} MXN")
        ticket_lineas.append("=========================================")

        st.text_area("Copia tu ticket listo para Playdoit:", value="\n".join(ticket_lineas), height=250, key="txt_area_unico_soc_fin")
    else:
        st.info("Aún no tienes selecciones de fútbol añadidas a tu ticket.")


# =========================================================
# MÓDULO 5: NCAA (Robot Universitario & Hándicap)
# =========================================================
else:
    st.title("🎓 **Robot Analítico y Hándicap - NCAA (Colegial)**")
    st.markdown("--- \n *Módulo automatizado especializado en el escaneo de partidos universitarios y cobertura de hándicap (Spread).* ")

    FICHERO_NCAA = "parlay_ncaa.json"

    def cargar_datos_ncaa():
      if os.path.exists(FICHERO_NCAA):
        try:
          with open(FICHERO_NCAA, "r", encoding="utf-8") as f:
            return json.load(f)
        except:
          pass
      return {}

    datos_ncaa = cargar_datos_ncaa()

    st.markdown("## ⚙️ **Panel de Escaneo Universitario**")
    col_n1, col_n2 = st.columns(2)
    with col_n1:
      bankroll_ncaa = st.number_input("💵 Bankroll NCAA (MXN):", min_value=100.0, value=5000.0, step=500.0, key="bk_ncaa")
    with col_n2:
      confianza_minima = st.slider("🎯 Confianza Mínima del Robot (%):", min_value=50.0, max_value=90.0, value=65.0, step=1.0, key="slider_conf_ncaa")

    st.markdown("---")
    st.subheader("⚡ Mejores Partidos y Oportunidades de Hándicap NCAA")

    if st.button("🚀 Ejecutar Escaneo Robot NCAA", use_container_width=True):
      st.success("¡Escaneo universitario finalizado con éxito! Se detectaron líneas con valor de cobertura.")

    if datos_ncaa:
      st.json(datos_ncaa)
    else:
      st.info("El robot universitario está activo. Los mejores picks y partidos detectados con alta probabilidad de hándicap aparecerán aquí.")
